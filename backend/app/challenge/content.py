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
FINAL_REWARD: int = 300000          # награда за финальный ввод всех 5 слов
VERSION: str = "2025-08-25"          # меняй при правках (удобно для кеша на фронте)

# Контент 5 дней
# ⚠️ Заполни реальные тексты/ссылки/слова. day_index должен быть уникален и от 1 до 5.
DAYS: List[Day] = [
    {
        "day_index": 1,
        "tiktok_url": "https://vt.tiktok.com/ZSAyE2R1N/",
        "question": "İnsanı digər heyvanlardan əsasən nə ayırır?",
        "option_a": "Lal dilində danışmaq bacarığı",
        "option_b": "Səs çıxarmaq qabiliyyəti",
        "option_c": "Öz haqqında düşünmək, refleksiya",
        "option_d": "Gözəl danışıq tərzi",
        "correct_option": "C",
        "codeword": "ALMA",
        "reward_watch": 50000,
        "reward_answer": 150000,
        "is_active": True,
    },
    {
        "day_index": 2,
        "tiktok_url": "https://vt.tiktok.com/ZSAyKc96Q/",
        "question": "Videoya görə “emergentlik” nə deməkdir?",
        "option_a": "Ayrı-ayrı hissələrin xüsusiyyətlərindən fərqli olaraq bütöv sistemin yeni xüsusiyyətlər yaratması",
        "option_b": "Atomların boşluqdan ibarət olması",
        "option_c": "Molekulların cansız olması",
        "option_d": "Hüceyrələrin canlı olması",
        "correct_option": "A",
        "codeword": "KITAB",
        "reward_watch": 50000,
        "reward_answer": 150000,
        "is_active": True,
    },
    {
        "day_index": 3,
        "tiktok_url": "https://vt.tiktok.com/ZSAyEeXj6/",
        "question": "Videoya görə qiymət və dəyər arasındakı əsas fərq nədir??",
        "option_a": "Qiymət dəyişir, dəyər isə sabitdir",
        "option_b": "Hər ikisi daim dəyişir",
        "option_c": "Hər ikisi yalnız mağazada müəyyən olunur",
        "option_d": "Qiymət sabitdir, dəyər isə vəziyyətdən asılı olaraq dəyişir",
        "correct_option": "D",
        "codeword": "QIZIL",
        "reward_watch": 50000,
        "reward_answer": 150000,
        "is_active": True,
    },
    {
        "day_index": 4,
        "tiktok_url": "https://vt.tiktok.com/ZSAyKcjjr/",
        "question": "Videoya görə icmanın formalaşmasında ən vacib amil nədir?",
        "option_a": "İdarəetməni üzərinə götürən liderlərin olması",
        "option_b": "İnsanların aidiyyət hissi – öz səsinin dəyərli olduğunu hiss etməsi",
        "option_c": "Fəal iştirakçıların ünsiyyət mədəniyyəti yaratması",
        "option_d": "Qaydaların və ənənələrin yaradılması",
        "correct_option": "B",
        "codeword": "DƏNİZ",
        "reward_watch": 50000,
        "reward_answer": 150000,
        "is_active": True,
    },
    {
        "day_index": 5,
        "tiktok_url": "https://vt.tiktok.com/ZSAyEYU5a/",
        "question": "Videoya görə pulun gücü nədən asılıdır?",
        "option_a": "İnsanların ona olan inamından",
        "option_b": "Pulun yalnız rəqəmsal formada mövcud olmasından",
        "option_c": "Dövlətin qanunla pul vahidini elan etməsindən",
        "option_d": "Onun qızıldan və ya dəniz qabığından hazırlanmasından",
        "correct_option": "A",
        "codeword": "SAMANI",
        "reward_watch": 50000,
        "reward_answer": 150000,
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
