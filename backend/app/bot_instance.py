# app/bot_instance.py
from telebot import TeleBot
from app.config import TELEGRAM_BOT_TOKEN

bot = TeleBot(TELEGRAM_BOT_TOKEN)
