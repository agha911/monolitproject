# monolitproject/backend/app/notifications/winners_handlers.py
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from sqlalchemy import select

from app.database import get_async_session
from app.models.db_tournament_winner import TournamentWinner
from app.models.user import User  # поправь импорт, если модель в другом месте

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
    row: list[types.InlineKeyboardButton] = []
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
            return r.status_code == 200
        except Exception:
            return False
    return await loop.run_in_executor(None, _do)

async def _ensure_state(chat_id: int, winner_id: int) -> Optional[WinnerState]:
    """Если STATE отсутствует (рассылка пришла из другого процесса), восстановим по БД."""
    if chat_id in STATE and STATE[chat_id].winner_id == winner_id:
        return STATE[chat_id]

    ret: Optional[WinnerState] = None
    async for session in get_async_session():
        # winner по id
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
            # безопасность: нажимать кнопки может только сам победитель
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
        break  # закрываем сессию, т.к. get_async_session — генератор
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

        # prize:<winner_id>:<key>
        if kind == "prize":
            try:
                winner_id_str, choice = rest.split(":", 1)
                winner_id = int(winner_id_str)
            except Exception:
                await bot.answer_callback_query(c.id, "Xəta"); return

            st = await _ensure_state(chat_id, winner_id)
            if not st:
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

        # confirm:<winner_id>
        if kind == "confirm":
            try:
                winner_id = int(rest)
            except Exception:
                await bot.answer_callback_query(c.id, "Xəta"); return

            st = await _ensure_state(chat_id, winner_id)
            if not st or st.stage != "confirm":
                await bot.answer_callback_query(c.id, "Sessiya tapılmadı"); return

            # обязательные проверки
            if not st.gift_choice:
                await bot.answer_callback_query(c.id, "Hədiyyəni seçməlisən"); return
            if st.gift_choice == "tshirt" and not st.tshirt_size:
                await bot.answer_callback_query(c.id, "Futbolka ölçüsünü seçməlisən"); return
            if (st.league, st.rank) in USDT_REWARD and not st.trc20_address:
                await bot.answer_callback_query(c.id, "TRC20 ünvanını göndərməlisən"); return

            payload = {"gift_choice": st.gift_choice, "tshirt_size": st.tshirt_size}
            if (st.league, st.rank) in USDT_REWARD:
                payload["trc20_address"] = st.trc20_address

            ok = await _patch_winner_async(st.winner_id, payload)
            if ok:
                await bot.edit_message_text("✅ Məlumat qeydə alındı. Çatdırılma/ödəniş üçün əlaqə saxlayacağıq.", chat_id, c.message.message_id)
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

