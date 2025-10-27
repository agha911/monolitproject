# app/helpers/bot_partner.py
import logging
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot_instance import bot
from app.database import async_session_maker

# Модели (проверь имена в своих файлах)
from app.models.partner import Partner, PartnerUser
from app.models.drop import Drop
from app.models.drop_purchase import DropPurchase

log = logging.getLogger("bot.partner")

# ───────────────── helpers ─────────────────

async def _get_partner_by_api_key(session: AsyncSession, api_key: str) -> Partner | None:
    res = await session.execute(select(Partner).where(Partner.api_key == api_key))
    return res.scalar_one_or_none()

async def _upsert_partner_user(session: AsyncSession, partner_id: int, tg_user_id: int) -> None:
    # есть ли запись?
    res = await session.execute(
        select(PartnerUser).where(
            PartnerUser.partner_id == partner_id,
            PartnerUser.telegram_user_id == tg_user_id,
        )
    )
    link = res.scalar_one_or_none()
    if link is None:
        session.add(PartnerUser(partner_id=partner_id, telegram_user_id=tg_user_id))
        await session.flush()

async def _get_partner_for_telegram(session: AsyncSession, tg_user_id: int) -> Partner | None:
    q = (
        select(Partner)
        .join(PartnerUser, PartnerUser.partner_id == Partner.id)
        .where(PartnerUser.telegram_user_id == tg_user_id)
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()

async def _list_partner_drops(session: AsyncSession, partner_id: int, limit: int, offset: int):
    q = (
        select(Drop)
        .where(Drop.partner_id == partner_id)
        .order_by(Drop.id.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(q)
    return res.scalars().all()

async def _toggle_drop_active(session: AsyncSession, drop_id: int, partner_id: int) -> Drop | None:
    res = await session.execute(select(Drop).where(and_(Drop.id == drop_id, Drop.partner_id == partner_id)))
    d = res.scalar_one_or_none()
    if not d:
        return None
    d.active = not bool(d.active)
    await session.flush()
    return d

async def _get_purchase_by_code_for_partner(session: AsyncSession, code: str, partner_id: int) -> DropPurchase | None:
    q = (
        select(DropPurchase)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .where(and_(DropPurchase.unique_code == code, Drop.partner_id == partner_id))
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()

async def _set_purchase_status(session: AsyncSession, code: str, new_status: str, partner_id: int):
    p = await _get_purchase_by_code_for_partner(session, code, partner_id)
    if not p:
        return None, "not_found"
    if new_status == "redeemed" and p.status != "active":
        return None, "wrong_status"
    if new_status == "revoked" and p.status == "redeemed":
        return None, "already_redeemed"
    p.status = new_status
    if new_status == "redeemed":
        from datetime import datetime
        p.redeemed_at = datetime.utcnow()
    await session.flush()
    return p, "ok"

def _clean_arg(s: str) -> str:
    return (s or "").replace("\r", " ").replace("\n", " ").strip()

# ───────────────── commands ─────────────────

@bot.message_handler(commands=['partner_login'])
async def partner_login(msg):
    try:
        parts = (msg.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await bot.reply_to(msg, "Отправьте: /partner_login <api_key>")
            return
        api_key = _clean_arg(parts[1])

        async with async_session_maker() as session:
            partner = await _get_partner_by_api_key(session, api_key)
            if not partner:
                await bot.reply_to(msg, "Неверный ключ.")
                return
            await _upsert_partner_user(session, partner.id, msg.from_user.id)
            await session.commit()

        await bot.reply_to(msg, f"Готово! Доступ выдан: {partner.name}\nВведите /partner")
    except Exception as e:
        log.exception("partner_login failed")
        await bot.reply_to(msg, f"Ошибка: {e}")

@bot.message_handler(commands=['partner'])
async def partner_menu(msg):
    try:
        async with async_session_maker() as session:
            partner = await _get_partner_for_telegram(session, msg.from_user.id)
        if not partner:
            await bot.reply_to(msg, "Нет доступа. Введите /partner_login <api_key>")
            return

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📦 Мои дропы", callback_data="p:drops:0"))
        kb.add(InlineKeyboardButton("🔎 По коду", switch_inline_query_current_chat="code "))
        kb.add(InlineKeyboardButton("📊 Статистика", callback_data="p:stats"))
        await bot.send_message(msg.chat.id, f"Партнёр: {partner.name}", reply_markup=kb)
    except Exception as e:
        log.exception("partner failed")
        await bot.reply_to(msg, f"Ошибка: {e}")

# ───────────────── callbacks ─────────────────

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("p:drops:"))
async def partner_drops(cb):
    try:
        page = int(cb.data.split(":")[2])
        async with async_session_maker() as session:
            partner = await _get_partner_for_telegram(session, cb.from_user.id)
            if not partner:
                await bot.answer_callback_query(cb.id, "Нет доступа", show_alert=True)
                return
            drops = await _list_partner_drops(session, partner.id, limit=5, offset=page * 5)

        if not drops:
            await bot.answer_callback_query(cb.id, "Больше нет", show_alert=True)
            return

        for d in drops:
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton(
                    ("🔴 Включить" if not d.active else "🟢 Выключить"),
                    callback_data=f"p:toggle:{d.id}"
                )
            )
            await bot.send_message(
                cb.message.chat.id,
                f"#{d.id} {d.title}\nСтатус: {'🟢 активен' if d.active else '🔴 неактивен'}",
                reply_markup=kb
            )

        nav = InlineKeyboardMarkup()
        nav.add(InlineKeyboardButton("Дальше ➡️", callback_data=f"p:drops:{page+1}"))
        await bot.send_message(cb.message.chat.id, "Навигация", reply_markup=nav)
        await bot.answer_callback_query(cb.id)
    except Exception as e:
        log.exception("p:drops failed")
        await bot.answer_callback_query(cb.id, f"Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("p:toggle:"))
async def partner_toggle(cb):
    try:
        drop_id = int(cb.data.split(":")[2])
        async with async_session_maker() as session:
            partner = await _get_partner_for_telegram(session, cb.from_user.id)
            if not partner:
                await bot.answer_callback_query(cb.id, "Нет доступа", show_alert=True)
                return
            d = await _toggle_drop_active(session, drop_id, partner.id)
            if d:
                await session.commit()

        if not d:
            await bot.answer_callback_query(cb.id, "Не найдено/нет доступа", show_alert=True)
            return

        await bot.answer_callback_query(cb.id, "Готово")
        await bot.edit_message_text(
            chat_id=cb.message.chat.id,
            message_id=cb.message.message_id,
            text=f"#{d.id} {d.title}\nСтатус: {'🟢 активен' if d.active else '🔴 неактивен'}"
        )
    except Exception as e:
        log.exception("p:toggle failed")
        await bot.answer_callback_query(cb.id, f"Ошибка: {e}", show_alert=True)

# ───────────────── text lookups ─────────────────

@bot.message_handler(func=lambda m: bool(m.text) and m.text.lower().startswith("code "))
async def code_lookup_prefixed(msg):
    await _handle_code_lookup(msg, _clean_arg(msg.text.split(maxsplit=1)[1]))

@bot.message_handler(func=lambda m: bool(m.text) and m.text.upper().startswith("GAP"))
async def code_lookup_plain(msg):
    await _handle_code_lookup(msg, _clean_arg(msg.text))

async def _handle_code_lookup(msg, raw_code: str):
    try:
        code = raw_code.upper()
        async with async_session_maker() as session:
            partner = await _get_partner_for_telegram(session, msg.from_user.id)
            if not partner:
                await bot.reply_to(msg, "Нет доступа. /partner_login <api_key>")
                return
            p = await _get_purchase_by_code_for_partner(session, code, partner.id)
        if not p:
            await bot.reply_to(msg, "Код не найден.")
            return

        kb = InlineKeyboardMarkup()
        if p.status == "active":
            kb.add(InlineKeyboardButton("✅ Redeem", callback_data=f"p:redeem:{code}"))
            kb.add(InlineKeyboardButton("🚫 Revoke", callback_data=f"p:revoke:{code}"))
        elif p.status == "redeemed":
            kb.add(InlineKeyboardButton("ℹ️ Уже погашен", callback_data="noop"))
        else:
            kb.add(InlineKeyboardButton("ℹ️ Отменён", callback_data="noop"))

        await bot.reply_to(msg, f"Код: {p.unique_code}\nСтатус: {p.status}", reply_markup=kb)
    except Exception as e:
        log.exception("code_lookup failed")
        await bot.reply_to(msg, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("p:redeem:") or c.data.startswith("p:revoke:")))
async def purchase_action(cb):
    try:
        _, action, code = cb.data.split(":")
        new_status = "redeemed" if action == "redeem" else "revoked"
        async with async_session_maker() as session:
            partner = await _get_partner_for_telegram(session, cb.from_user.id)
            if not partner:
                await bot.answer_callback_query(cb.id, "Нет доступа", show_alert=True)
                return
            p, status = await _set_purchase_status(session, code, new_status, partner.id)
            if status == "ok":
                await session.commit()

        if status != "ok":
            await bot.answer_callback_query(cb.id, f"Ошибка: {status}", show_alert=True)
            return

        await bot.answer_callback_query(cb.id, "Готово")
        await bot.edit_message_text(
            chat_id=cb.message.chat.id,
            message_id=cb.message.message_id,
            text=f"Код: {p.unique_code}\nСтатус: {p.status}"
        )
    except Exception as e:
        log.exception("p:redeem/revoke failed")
        await bot.answer_callback_query(cb.id, f"Ошибка: {e}", show_alert=True)
