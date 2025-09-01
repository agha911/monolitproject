# monolitproject/backend/app/notifications/winners_handlers.py
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple, List

import requests
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from sqlalchemy import select, update

from app.database import get_async_session
from app.models.db_tournament_winner import TournamentWinner
from app.models.user import User  # поправь импорт, если модель в другом месте

# --- финальный период турнира (UTC naive в БД) ---
PERIOD_START = datetime(2025, 8, 17, 20, 0, 0)  # 18.08 00:00 AZ
PERIOD_END   = datetime(2025, 9,  1, 19, 59, 0)  # 01.09 23:59 AZ

USDT_REWARD: Dict[Tuple[str, int], int] = {
    ("gold",   1): 30, ("gold",   2): 20, ("gold",   3): 10,
    ("silver", 1): 20, ("silver", 2): 15, ("silver", 3): 5,
}

PRIZES = {"thermos": "Termos", "powerbank": "Powerbank", "tshirt": "Futbolka"}
SIZES  = {"XS", "S", "M", "L", "XL", "XXL"}
LEAGUE_AZ = {"gold": "Qızıl", "silver": "Gümüş", "bronze": "Bürünc"}

_TRON_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{25,49}$")
def looks_like_trc20(addr: str) -> bool:
    return bool(_TRON_RE.fullmatch((addr or "").strip()))

API_BASE_URL  = os.getenv("API_BASE_URL", "https://monolitproject.onrender.com")
PATCH_URL_TPL = f"{API_BASE_URL}/api/tournament/winners/{{winner_id}}"

@dataclass
class WinnerState:
    winner_id: int
    league: str
    rank: int
    clicks: int
    gift_choice: Optional[str] = None
    tshirt_size: Optional[str] = None
    trc20_address: Optional[str] = None
    stage: str = "choose_prize"  # choose_prize | choose_size | wait_trc20 | confirm

STATE: Dict[int, WinnerState] = {}  # chat_id -> state

def kb_prizes(winner_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎁 Termos",    callback_data=f"prize:{winner_id}:thermos"),
        types.InlineKeyboardButton("🔋 Powerbank", callback_data=f"prize:{winner_id}:powerbank"),
    )
    kb.add(types.InlineKeyboardButton("👕 Futbolka", callback_data=f"prize:{winner_id}:tshirt"))
    return kb

def kb_sizes(winner_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    row: List[types.InlineKeyboardButton] = []
    for s in ["XS", "S", "M", "L", "XL", "XXL"]:
        row.append(types.InlineKeyboardButton(s, callback_data=f"size:{winner_id}:{s}"))
        if len(row) == 3:
            kb.row(*row); row = []
    if row: kb.row(*row)
    return kb

def kb_confirm(winner_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Təsdiq et", callback_data=f"confirm:{winner_id}"))
    kb.add(types.InlineKeyboardButton("↩️ Dəyiş",     callback_data=f"edit:{winner_id}"))
    return kb

def summarize_az(st: WinnerState) -> str:
    lines = [
        "🎉 Yekun:",
        f"• Liqa: {LEAGUE_AZ.get(st.league, st.league)}",
        f"• Yer: {st.rank}",
        f"• Kliklər: {st.clicks}",
        f"• Tərəfdaş hədiyyəsi: {PRIZES.get(st.gift_choice,'—')}",
    ]
    if st.gift_choice == "tshirt":
        lines.append(f"• Futbolka ölçüsü: {st.tshirt_size or '—'}")
    reward = USDT_REWARD.get((st.league, st.rank))
    if reward:
        lines.append(f"• Pul mükafatı: {reward} USDT (TRC20)")
        lines.append(f"• TRC20 ünvanı: {st.trc20_address or '—'}")
    return "\n".join(lines)

async def _patch_winner_async(winner_id: int, payload: dict) -> bool:
    loop = asyncio.get_running_loop()
    def _do():
        try:
            r = requests.patch(PATCH_URL_TPL.format(winner_id=winner_id), json=payload, timeout=20)
            # принимаем 2xx
            return 200 <= r.status_code < 300
        except Exception:
            return False
    return await loop.run_in_executor(None, _do)

async def _ensure_state(chat_id: int, winner_id: int) -> Optional[WinnerState]:
    """Если STATE отсутствует (рассылка пришла из другого процесса), восстановим по БД."""
    if chat_id in STATE and STATE[chat_id].winner_id == winner_id:
        return STATE[chat_id]

    ret: Optional[WinnerState] = None
    async for session in get_async_session():
        try:
            q = await session.execute(
                select(TournamentWinner, User)
                .join(User, User.id == TournamentWinner.user_id)
                .where(TournamentWinner.id == winner_id)
            )
            row = q.first()
            if not row:
                ret = None
            else:
                w, u = row
                if not getattr(u, "telegram_id", None) or int(u.telegram_id) != int(chat_id):
                    ret = None
                else:
                    st = WinnerState(
                        winner_id=int(w.id),
                        league=w.league,
                        rank=int(w.rank_in_league),
                        clicks=int(w.clicks_snapshot),
                    )
                    STATE[chat_id] = st
                    ret = st
        finally:
            break
    return ret

async def _ensure_state_by_chat(chat_id: int) -> Optional[WinnerState]:
    """Fallback для старых кнопок без winner_id: найдём победителя по chat_id за финальный период."""
    if chat_id in STATE:
        return STATE[chat_id]

    ret: Optional[WinnerState] = None
    async for session in get_async_session():
        try:
            q = await session.execute(
                select(TournamentWinner, User)
                .join(User, User.id == TournamentWinner.user_id)
                .where(
                    User.telegram_id == chat_id,
                    TournamentWinner.period_start == PERIOD_START,
                    TournamentWinner.period_end == PERIOD_END,
                    TournamentWinner.rank_in_league <= 3,
                )
                .order_by(TournamentWinner.created_at.desc())
            )
            row = q.first()
            if not row:
                ret = None
            else:
                w, _u = row
                st = WinnerState(
                    winner_id=int(w.id),
                    league=w.league,
                    rank=int(w.rank_in_league),
                    clicks=int(w.clicks_snapshot),
                )
                STATE[chat_id] = st
                ret = st
        finally:
            break
    return ret

def register_winners_handlers(bot: AsyncTeleBot):
    @bot.callback_query_handler(func=lambda c: True)
    async def _on_cb(c: types.CallbackQuery):
        chat_id = c.message.chat.id
        data = c.data or ""
        try:
            kind, rest = data.split(":", 1)
        except ValueError:
            await bot.answer_callback_query(c.id); return

        # prize:<winner_id>:<choice>  ИЛИ  prize:<choice> (fallback)
        if kind == "prize":
            parts = rest.split(":")
            winner_id: Optional[int] = None
            choice: Optional[str] = None

            if len(parts) == 2:
                # новый формат
                winner_id = int(parts[0])
                choice = parts[1]
                st = await _ensure_state(chat_id, winner_id)
            elif len(parts) == 1:
                # старый формат (без winner_id)
                choice = parts[0]
                st = await _ensure_state_by_chat(chat_id)
                winner_id = st.winner_id if st else None
            else:
                await bot.answer_callback_query(c.id, "Xəta"); return

            if not st or not winner_id:
                await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return
            if choice not in PRIZES:
                await bot.answer_callback_query(c.id, "Seçim düzgün deyil"); return

            st.gift_choice = choice
            if choice == "tshirt":
                st.stage = "choose_size"
                await bot.edit_message_text("👕 Futbolka ölçüsünü seç:", chat_id, c.message.message_id, reply_markup=kb_sizes(winner_id))
            else:
                if (st.league, st.rank) in USDT_REWARD:
                    st.stage = "wait_trc20"
                    await bot.edit_message_text("💳 Zəhmət olmasa *TRC20* ünvanını göndər (\"T\" ilə başlayır):", chat_id, c.message.message_id, parse_mode="Markdown")
                else:
                    st.stage = "confirm"
                    await bot.edit_message_text(summarize_az(st), chat_id, c.message.message_id, reply_markup=kb_confirm(winner_id))
            await bot.answer_callback_query(c.id)
            return

        # size:<winner_id>:<size>
        if kind == "size":
            try:
                winner_id_str, size = rest.split(":", 1)
                winner_id = int(winner_id_str)
            except Exception:
                await bot.answer_callback_query(c.id, "Xəta"); return

            st = await _ensure_state(chat_id, winner_id)
            if not st or st.stage not in {"choose_size", "choose_prize"}:
                await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return
            if size not in SIZES:
                await bot.answer_callback_query(c.id, "Ölçü düzgün deyil"); return

            st.tshirt_size = size
            if (st.league, st.rank) in USDT_REWARD:
                st.stage = "wait_trc20"
                await bot.edit_message_text(
                    f"👕 Ölçü: *{size}*\n\n💳 İndi *TRC20* ünvanını göndər (\"T\" ilə başlayır):",
                    chat_id, c.message.message_id, parse_mode="Markdown"
                )
            else:
                st.stage = "confirm"
                await bot.edit_message_text(summarize_az(st), chat_id, c.message.message_id, reply_markup=kb_confirm(winner_id))
            await bot.answer_callback_query(c.id)
            return

        # confirm:<winner_id>  ИЛИ просто confirm (старый формат)
        if kind == "confirm":
            # --- поддержка старого формата ---
            if rest.strip():
                try:
                    winner_id = int(rest)
                except Exception:
                    await bot.answer_callback_query(c.id, "Xəta"); return
                st = await _ensure_state(chat_id, winner_id)
            else:
                st = STATE.get(chat_id) or await _ensure_state_by_chat(chat_id)
                if not st:
                    await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return
                winner_id = st.winner_id

            if not st:
                await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return

            # --- не завязываемся на stage: просто проверим необходимые поля ---
            if not st.gift_choice:
                # нет приза — вернём пользователю выбор
                st.stage = "choose_prize"
                await bot.edit_message_text("🎁 Hədiyyəni seç:", chat_id, c.message.message_id, reply_markup=kb_prizes(winner_id))
                await bot.answer_callback_query(c.id)
                return
            if st.gift_choice == "tshirt" and not st.tshirt_size:
                st.stage = "choose_size"
                await bot.edit_message_text("👕 Futbolka ölçüsünü seç:", chat_id, c.message.message_id, reply_markup=kb_sizes(winner_id))
                await bot.answer_callback_query(c.id)
                return
            if (st.league, st.rank) in USDT_REWARD and not st.trc20_address:
                st.stage = "wait_trc20"
                await bot.edit_message_text("💳 Zəhmət olmasa *TRC20* ünvanını göndər (\"T\" ilə başlayır):", chat_id, c.message.message_id, parse_mode="Markdown")
                await bot.answer_callback_query(c.id)
                return

            # --- сохраняем: сначала пробуем PATCH, затем fallback = прямое обновление БД ---
            payload = {"gift_choice": st.gift_choice, "tshirt_size": st.tshirt_size}
            if (st.league, st.rank) in USDT_REWARD:
                payload["trc20_address"] = st.trc20_address

            saved = await _patch_winner_async(st.winner_id, payload)
            if not saved:
                # Fallback: прямой апдейт
                async for session in get_async_session():
                    try:
                        stmt = (
                            update(TournamentWinner)
                            .where(TournamentWinner.id == st.winner_id)
                            .values(
                                gift_choice=st.gift_choice,
                                tshirt_size=st.tshirt_size,
                                trc20_address=st.trc20_address,
                                updated_at=datetime.utcnow(),
                            )
                        )
                        await session.execute(stmt)
                        await session.commit()
                        saved = True
                    except Exception:
                        saved = False
                    finally:
                        break

            if saved:
                await bot.edit_message_text(
                    "✅ Məlumat qeydə alındı. Çatdırılma/ödəniş üçün əlaqə saxlayacağıq.",
                    chat_id, c.message.message_id
                )
                STATE.pop(chat_id, None)
            else:
                await bot.answer_callback_query(c.id, "Server xətası, yenidən cəhd et.")
            return

        # edit:<winner_id>
        if kind == "edit":
            try:
                winner_id = int(rest)
            except Exception:
                await bot.answer_callback_query(c.id, "Xəta"); return

            st = await _ensure_state(chat_id, winner_id)
            if not st:
                await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return

            st.stage = "choose_prize"
            st.gift_choice = None
            st.tshirt_size = None
            st.trc20_address = None
            await bot.edit_message_text("🔁 Hədiyyəni yenidən seç:", chat_id, c.message.message_id, reply_markup=kb_prizes(winner_id))
            await bot.answer_callback_query(c.id)
            return

    @bot.message_handler(content_types=["text"])
    async def _on_text(m: types.Message):
        chat_id = m.chat.id
        st = STATE.get(chat_id)
        if not st or st.stage != "wait_trc20":
            return
        addr = (m.text or "").strip()
        if not looks_like_trc20(addr):
            await bot.reply_to(m, "Bu TRC20 ünvanına oxşamır. Ünvan *\"T\" ilə başlamalıdır*. Yenidən göndər.", parse_mode="Markdown")
            return
        st.trc20_address = addr
        st.stage = "confirm"
        await bot.send_message(chat_id, summarize_az(st), reply_markup=kb_confirm(st.winner_id))




