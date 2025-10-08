import os
import binascii

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без 0/O/I/L

def random_base32(length: int = 8) -> str:
    # bytes -> hex -> map в A..Z/2..9 (просто и быстро)
    raw = binascii.hexlify(os.urandom(length)).decode("ascii").upper()
    # сократим и заменим недопустимые символы (хак, но ок для кодов)
    mapped = []
    for ch in raw[:length]:
        if ch.isdigit():
            idx = (ord(ch) - ord('0')) % len(ALPHABET)
        else:
            idx = (ord(ch) - ord('A')) % len(ALPHABET)
        mapped.append(ALPHABET[idx])
    return "".join(mapped)

def generate_unique_code(prefix: str = "GAP", size: int = 10) -> str:
    return f"{prefix}-{random_base32(size)}"
