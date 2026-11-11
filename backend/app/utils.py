"""Compatibility entry point; accepts signed Telegram data only."""
from app.auth import validate_init_data

def parse_telegram_user_id(init_data: str) -> int:
    return validate_init_data(init_data)
