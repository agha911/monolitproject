import json
from urllib.parse import parse_qs, unquote

def parse_telegram_user_id(init_data: str) -> int:
    try:
        print("[init_data RAW]", init_data)  # 💡 Логируем вход
        parsed = parse_qs(init_data)
        user_raw = parsed.get("user", [None])[0]
        if user_raw:
            user_str = unquote(user_raw)
            print("[user_str DECODED]", user_str)  # 💡 Логируем декодированный JSON
            user = json.loads(user_str)
            return int(user["id"])
        else:
            print("[ERROR] 'user' key not found in parsed init_data")
    except Exception as e:
        print("[parse_telegram_user_id ERROR]", e)

    raise ValueError("Invalid init_data or user ID not found")
