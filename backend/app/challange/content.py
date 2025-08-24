# monolitproject/backend/app/challenge/content.py
from __future__ import annotations
from typing import TypedDict, Literal, List

# Допустимые варианты ответа
Option = Literal["A", "B", "C", "D"]

class Day(TypedDict):
    day_index: int                    # 1..5
    tiktok_url: str                   # ссылка на ролик
    question: str                     # текст вопроса
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: Option            # "A" | "B" | "C" | "D"
    codeword: str                     # кодовое слово, показывается только при верном ответе
    reward_watch: int                 # монеты за часть 1 (просмотр)
    reward_answer: int                # монеты за часть 2 (ответ, независимо от верности)
    is_active: bool                   # можно временно выключать день

# Общие настройки квеста
ENABLED: bool = True
FINAL_REWARD: int = 500_000          # награда за финальный ввод всех 5 слов
VERSION: str = "2025-08-25"          # меняй при правках (удобно для кеша на фронте)

# Контент 5 дней
# ⚠️ Заполни реальные тексты/ссылки/слова. day_index должен быть уникален и от 1 до 5.
DAYS: List[Day] = [
    {
        "day_index": 1,
        "tiktok_url": "https://www.tiktok.com/@account/video/1111111111",
        "question": "Sual 1: Videonun əsas fikri nədir?",
        "option_a": "Variant A",
        "option_b": "Variant B",
        "option_c": "Variant C",
        "option_d": "Variant D",
        "correct_option": "C",
        "codeword": "ALMA",
        "reward_watch": 1_000,
        "reward_answer": 2_000,
        "is_active": True,
    },
    {
        "day_index": 2,
        "tiktok_url": "https://www.tiktok.com/@account/video/2222222222",
        "question": "Sual 2: Müəllif nəyi vurğulayır?",
        "option_a": "Variant A",
        "option_b": "Variant B",
        "option_c": "Variant C",
        "option_d": "Variant D",
        "correct_option": "A",
        "codeword": "KITAB",
        "reward_watch": 1_000,
        "reward_answer": 2_000,
        "is_active": True,
    },
    {
        "day_index": 3,
        "tiktok_url": "https://www.tiktok.com/@account/video/3333333333",
        "question": "Sual 3: Videoda hansı nüans önəmlidir?",
        "option_a": "Variant A",
        "option_b": "Variant B",
        "option_c": "Variant C",
        "option_d": "Variant D",
        "correct_option": "D",
        "codeword": "QIZIL",
        "reward_watch": 1_000,
        "reward_answer": 2_000,
        "is_active": True,
    },
    {
        "day_index": 4,
        "tiktok_url": "https://www.tiktok.com/@account/video/4444444444",
        "question": "Sual 4: Müəllifin misal gətirdiyi anlayış nədir?",
        "option_a": "Variant A",
        "option_b": "Variant B",
        "option_c": "Variant C",
        "option_d": "Variant D",
        "correct_option": "B",
        "codeword": "DƏNİZ",
        "reward_watch": 1_000,
        "reward_answer": 2_000,
        "is_active": True,
    },
    {
        "day_index": 5,
        "tiktok_url": "https://www.tiktok.com/@account/video/5555555555",
        "question": "Sual 5: Videonun nəticəsi nəyə gətirir?",
        "option_a": "Variant A",
        "option_b": "Variant B",
        "option_c": "Variant C",
        "option_d": "Variant D",
        "correct_option": "A",
        "codeword": "SAMANI",
        "reward_watch": 1_000,
        "reward_answer": 2_000,
        "is_active": True,
    },
]

# --- необязательно, но удобно для локальной проверки структуры ---
def _validate() -> None:
    """Быстрая валидация, можно дернуть при старте приложения."""
    assert ENABLED in (True, False)
    assert isinstance(FINAL_REWARD, int) and FINAL_REWARD >= 0
    seen = set()
    for d in DAYS:
        idx = d["day_index"]
        assert 1 <= idx <= 5, "day_index должен быть 1..5"
        assert idx not in seen, f"дублируется day_index={idx}"
        seen.add(idx)
        assert d["correct_option"] in ("A", "B", "C", "D")
        assert isinstance(d["reward_watch"], int) and d["reward_watch"] >= 0
        assert isinstance(d["reward_answer"], int) and d["reward_answer"] >= 0
        assert isinstance(d["is_active"], bool)

# Можно вызвать в точке инициализации (по желанию)
# _validate()
