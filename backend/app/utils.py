import json
from urllib.parse import parse_qs

def parse_telegram_user_id(init_data: str) -> int:
    try:
        parsed = parse_qs(init_data)
        user_json = parsed.get("user", [None])[0]
        if user_json:
            user = json.loads(user_json)
            return int(user["id"])
    except Exception as e:
        print("[parse_telegram_user_id ERROR]", e)

    raise ValueError("Invalid init_data or user ID not found")
