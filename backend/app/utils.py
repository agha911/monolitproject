from typing import Union

def parse_telegram_user_id(init_data: Union[str, dict]) -> int:
    try:
        print("[init_data RAW]", init_data)

        if isinstance(init_data, dict):
            user = init_data.get("user")
            if isinstance(user, str):
                user = json.loads(user)
            if not user or "id" not in user:
                raise ValueError("User ID not found in dict init_data")
            return int(user["id"])

        elif isinstance(init_data, str):
            parsed = parse_qs(init_data)
            user_raw = parsed.get("user", [None])[0]
            if user_raw:
                user_str = unquote(user_raw)
                print("[user_str DECODED]", user_str)
                user = json.loads(user_str)
                return int(user["id"])
            else:
                print("[ERROR] 'user' key not found in parsed init_data")

    except Exception as e:
        print("[parse_telegram_user_id ERROR]", e)

    raise ValueError("Invalid init_data or user ID not found")
