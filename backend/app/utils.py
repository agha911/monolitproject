from urllib.parse import parse_qs

def parse_telegram_user_id(init_data: str) -> int:
    try:
        parsed = parse_qs(init_data)
        user_id_str = parsed.get("user", [None])[0]
        if user_id_str:
            # Извлекаем ID из строки вроде 'user={"id":123456,...}'
            import json
            user_obj = json.loads(user_id_str)
            return int(user_obj["id"])
    except Exception as e:
        print("[parse_telegram_user_id ERROR]", e)

    raise ValueError("Invalid init_data or missing user id")
