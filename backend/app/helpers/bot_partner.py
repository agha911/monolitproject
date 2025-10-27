# bot_partner.py
from telebot import types
from app.database import SessionLocal
from helpers.partner_auth import (
    partner_by_api_key, upsert_partner_user, get_partner_for_telegram,
    list_partner_drops, toggle_drop_active, get_purchase_by_code, set_purchase_status
)
from app.bot_instance import bot  # ваш инстанс TeleBot

@bot.message_handler(commands=['partner_login'])
def partner_login(msg):
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(msg, "Отправьте: /partner_login <api_key>")
        return
    api_key = args[1].strip()
    with SessionLocal() as db:
        partner = partner_by_api_key(db, api_key)
        if not partner:
            bot.reply_to(msg, "Неверный ключ.")
            return
        upsert_partner_user(db, partner.id, msg.from_user.id)
        bot.reply_to(msg, f"Готово! Доступ выдан: {partner.name}\nВведите /partner")

@bot.message_handler(commands=['partner'])
def partner_menu(msg):
    with SessionLocal() as db:
        partner = get_partner_for_telegram(db, msg.from_user.id)
        if not partner:
            bot.reply_to(msg, "Нет доступа. Введите /partner_login <api_key>")
            return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 Мои дропы", callback_data="p:drops:0"))
    kb.add(types.InlineKeyboardButton("🔎 По коду", switch_inline_query_current_chat="code "))
    kb.add(types.InlineKeyboardButton("📊 Статистика", callback_data="p:stats"))
    bot.send_message(msg.chat.id, f"Партнёр: {partner.name}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("p:drops:"))
def partner_drops(cb):
    page = int(cb.data.split(":")[2])
    with SessionLocal() as db:
        partner = get_partner_for_telegram(db, cb.from_user.id)
        if not partner:
            bot.answer_callback_query(cb.id, "Нет доступа")
            return
        drops = list_partner_drops(db, partner.id, limit=5, offset=page*5)
    if not drops:
        bot.answer_callback_query(cb.id, "Больше нет")
        return
    for d in drops:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            ("🔴 Включить" if not d.active else "🟢 Выключить"),
            callback_data=f"p:toggle:{d.id}"
        ))
        bot.send_message(cb.message.chat.id,
            f"#{d.id} {d.title}\nСтатус: {'🟢 активен' if d.active else '🔴 неактивен'}",
            reply_markup=kb
        )
    # пагинация
    nav = types.InlineKeyboardMarkup()
    nav.add(types.InlineKeyboardButton("Дальше ➡️", callback_data=f"p:drops:{page+1}"))
    bot.send_message(cb.message.chat.id, "Навигация", reply_markup=nav)
    bot.answer_callback_query(cb.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("p:toggle:"))
def partner_toggle(cb):
    drop_id = int(cb.data.split(":")[2])
    with SessionLocal() as db:
        partner = get_partner_for_telegram(db, cb.from_user.id)
        if not partner:
            bot.answer_callback_query(cb.id, "Нет доступа")
            return
        d = toggle_drop_active(db, drop_id, partner.id)
    if not d:
        bot.answer_callback_query(cb.id, "Не найдено/нет доступа")
    else:
        bot.answer_callback_query(cb.id, "Готово")
        bot.edit_message_text(
            chat_id=cb.message.chat.id, message_id=cb.message.message_id,
            text=f"#{d.id} {d.title}\nСтатус: {'🟢 активен' if d.active else '🔴 неактивен'}"
        )

# Поиск кода: пользователь пишет "code GAPXXXXXXXX"
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("code "))
def code_lookup(msg):
    code = msg.text.split(maxsplit=1)[1].strip()
    with SessionLocal() as db:
        partner = get_partner_for_telegram(db, msg.from_user.id)
        if not partner:
            bot.reply_to(msg, "Нет доступа. /partner_login <api_key>")
            return
        p = get_purchase_by_code(db, code, partner.id)
        if not p:
            bot.reply_to(msg, "Код не найден.")
            return
        # кнопки действий
        kb = types.InlineKeyboardMarkup()
        if p.status == "active":
          kb.add(types.InlineKeyboardButton("✅ Redeem", callback_data=f"p:redeem:{code}"))
          kb.add(types.InlineKeyboardButton("🚫 Revoke", callback_data=f"p:revoke:{code}"))
        elif p.status == "redeemed":
          kb.add(types.InlineKeyboardButton("ℹ️ Уже погашен", callback_data="noop"))
        else:
          kb.add(types.InlineKeyboardButton("ℹ️ Отменён", callback_data="noop"))

        bot.reply_to(msg, f"Код: {p.unique_code}\nСтатус: {p.status}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("p:redeem:") or c.data.startswith("p:revoke:"))
def purchase_action(cb):
    action, code = cb.data.split(":")[1], cb.data.split(":")[2]
    with SessionLocal() as db:
        partner = get_partner_for_telegram(db, cb.from_user.id)
        if not partner:
            bot.answer_callback_query(cb.id, "Нет доступа")
            return
        new_status = "redeemed" if action == "redeem" else "revoked"
        p, status = set_purchase_status(db, code, new_status, partner.id)
    if status != "ok":
        bot.answer_callback_query(cb.id, f"Ошибка: {status}")
        return
    bot.answer_callback_query(cb.id, "Готово")
    bot.edit_message_text(
        chat_id=cb.message.chat.id, message_id=cb.message.message_id,
        text=f"Код: {p.unique_code}\nСтатус: {p.status}"
    )
