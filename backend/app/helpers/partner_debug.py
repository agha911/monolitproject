# app/helpers/partner_debug.py
from app.bot_instance import bot
from telebot import types
import logging

log = logging.getLogger("bot")

@bot.message_handler(commands=['ping'])
def _ping(m):
    bot.reply_to(m, "pong")

@bot.message_handler(commands=['partner_login'])
def _partner_login(m):
    # просто покажем, что команда поймана и что передано
    parts = m.text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else "(нет аргумента)"
    log.info(f"[DBG] partner_login fired. from={m.from_user.id} arg={arg!r}")
    bot.reply_to(m, f"[DBG] /partner_login пойман. arg={arg}")

@bot.message_handler(commands=['partner'])
def _partner(m):
    log.info(f"[DBG] partner fired. from={m.from_user.id}")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("ok", callback_data="dbg:ok"))
    bot.send_message(m.chat.id, "[DBG] меню партнёра отрисовано", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "dbg:ok")
def _ok(cb):
    bot.answer_callback_query(cb.id, "ok")
