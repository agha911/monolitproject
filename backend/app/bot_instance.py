# app/bot_instance.py

from telebot.async_telebot import AsyncTeleBot
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
