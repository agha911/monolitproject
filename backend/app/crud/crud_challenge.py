from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

# наши таблицы
from app.models.db_challenge import challenge_user_progress, challenge_user_final
# модель пользователя (для начислений)
from app.models.user import User  # при необходимости поправь путь
# контент (дни, ответы, награды) хранится в коде
from app.challenge import content  # app/challenge/content.py


# === централизованная выдача монет (+зачёт в турнире) =========================
async def award_coins(session: AsyncSession, user_id: int, amount: int, reason: str) -> None:
    """
    Простейшая реализация:
    - users.total_xp += amount
    - users.tournament_clicks += amount
    Если у тебя есть отдельный лог транзакций — добавь здесь.
    """
    if amount <= 0:
        return
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            total_xp=User.total_xp + amount,
            tournament_clicks=User.tournament_clicks + amount
        )
    )


# === вспомогательные функции ==================================================
def _get_day_public(day: dict) -> dict:
    """Отдаём на фронт без correct_option и codeword."""
    return {
        "day_index": day["day_index"],
        "tiktok_url": day["tiktok_url"],
        "question": day["question"],
        "option_a": day["option_a"],
        "option_b": day["option_b"],
        "option_c": day["option_c"],
        "option_d": day["option_d"],
        "reward_watch": day["reward_watch"],
        "reward_answer": day["reward_answer"],
        "is_active": day["is_active"],
    }


def _get_day_internal(day_index: int) -> dict | None:
    for d in content.DAYS:
        if d["day_index"] == day_index:
            return d
    return None


# === публичная конфигурация квеста ===========================================
async def get_config() -> Dict[str, Any]:
    """
    Отдаём включённость, финальную награду, версию и публичную инфу по дням.
    Чтение только из кода (content.py), БД не нужна.
    """
    if not content.ENABLED:
        return {"enabled": False, "final_reward": 0, "version": content.VERSION, "days": []}

    days_public = [_get_day_public(d) for d in sorted(content.DAYS, key=lambda x: x["day_index"])]
    return {
        "enabled": True,
        "final_reward": content.FINAL_REWARD,
        "version": content.VERSION,
        "days": days_public,
    }


# === прогресс пользователя ====================================================
async def get_user_progress(session: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
    res = await session.execute(
        select(
            challenge_user_progress.c.day_index,
            challenge_user_progress.c.watched,
            challenge_user_progress.c.watched_rewarded,
            challenge_user_progress.c.answered,
            challenge_user_progress.c.selected_option,
            challenge_user_progress.c.is_correct,
            challenge_user_progress.c.answer_rewarded,
            challenge_user_progress.c.codeword_revealed,
        )
        .where(challenge_user_progress.c.user_id == user_id)
        .order_by(challenge_user_progress.c.day_index)
    )
    return [dict(r._mapping) for r in res.fetchall()]


async def get_progress_with_final_state(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """
    Сводка прогресса + готов ли пользователь к финалу (все 5 ответов верно).
    """
    days = await get_user_progress(session, user_id)
    final_ready = sum(1 for p in days if p["is_correct"]) == 5

    res = await session.execute(
        select(challenge_user_final).where(challenge_user_final.c.user_id == user_id)
    )
    row = res.first()
    final_state = dict(row._mapping) if row else None

    return {
        "enabled": content.ENABLED,
        "version": content.VERSION,
        "final_reward": content.FINAL_REWARD,
        "days": days,
        "final_ready": final_ready,
        "final_state": final_state,
    }


# === часть 1: отметка просмотра ==============================================
async def mark_watched(session: AsyncSession, user_id: int, day_index: int) -> Dict[str, Any]:
    if not content.ENABLED:
        raise ValueError("Challenge is disabled")

    d = _get_day_internal(day_index)
    if not d or not d["is_active"]:
        raise ValueError("Day not found or inactive")

    now = datetime.utcnow()
    # upsert прогресса
    res = await session.execute(
        select(challenge_user_progress).where(
            challenge_user_progress.c.user_id == user_id,
            challenge_user_progress.c.day_index == day_index
        )
    )
    row = res.first()

    watched_rewarded = False
    if row is None:
        await session.execute(insert(challenge_user_progress).values(
            user_id=user_id,
            day_index=day_index,
            watched=True,
            watched_rewarded=False,
            answered=False,
            answer_rewarded=False,
            codeword_revealed=False,
            created_at=now,
            updated_at=now,
        ))
    else:
        cur = dict(row._mapping)
        watched_rewarded = cur["watched_rewarded"]
        if not cur["watched"]:
            await session.execute(
                update(challenge_user_progress)
                .where(challenge_user_progress.c.user_id == user_id,
                       challenge_user_progress.c.day_index == day_index)
                .values(watched=True, updated_at=now)
            )

    # однократная награда за просмотр
    reward_given = 0
    if not watched_rewarded and d["reward_watch"] > 0:
        await award_coins(session, user_id, d["reward_watch"], f"challenge_watch_d{day_index}")
        await session.execute(
            update(challenge_user_progress)
            .where(challenge_user_progress.c.user_id == user_id,
                   challenge_user_progress.c.day_index == day_index)
            .values(watched_rewarded=True, updated_at=now)
        )
        reward_given = d["reward_watch"]

    return {"reward_watch": reward_given}


# === часть 2: отправка ответа =================================================
async def submit_answer(session: AsyncSession, user_id: int, day_index: int, selected_option: str) -> Dict[str, Any]:
    if not content.ENABLED:
        raise ValueError("Challenge is disabled")

    d = _get_day_internal(day_index)
    if not d or not d["is_active"]:
        raise ValueError("Day not found or inactive")

    opt = (selected_option or "").upper()
    if opt not in ("A", "B", "C", "D"):
        raise ValueError("Invalid option")

    is_correct = (opt == d["correct_option"])
    now = datetime.utcnow()

    res = await session.execute(
        select(challenge_user_progress).where(
            challenge_user_progress.c.user_id == user_id,
            challenge_user_progress.c.day_index == day_index
        )
    )
    row = res.first()

    if row is None:
        await session.execute(insert(challenge_user_progress).values(
            user_id=user_id,
            day_index=day_index,
            watched=False,
            watched_rewarded=False,
            answered=True,
            selected_option=opt,
            is_correct=is_correct,
            answer_rewarded=False,
            codeword_revealed=False,
            created_at=now,
            updated_at=now,
        ))
        prev_answered = False
        prev_correct = None
        prev_revealed = False
    else:
        cur = dict(row._mapping)
        prev_answered = cur["answered"]
        prev_correct = cur["is_correct"]
        prev_revealed = cur["codeword_revealed"]
        if not prev_answered:
            await session.execute(
                update(challenge_user_progress)
                .where(challenge_user_progress.c.user_id == user_id,
                       challenge_user_progress.c.day_index == day_index)
                .values(answered=True, selected_option=opt, is_correct=is_correct, updated_at=now)
            )
        else:
            # фиксируем исход первого ответа
            is_correct = prev_correct if prev_correct is not None else is_correct

    # однократная награда за факт ответа (как в ТЗ — независимо от правильности)
    res2 = await session.execute(
        select(challenge_user_progress.c.answer_rewarded)
        .where(challenge_user_progress.c.user_id == user_id,
               challenge_user_progress.c.day_index == day_index)
    )
    answer_rewarded = res2.scalar_one()
    reward_given = 0
    if not answer_rewarded and d["reward_answer"] > 0:
        await award_coins(session, user_id, d["reward_answer"], f"challenge_answer_d{day_index}")
        await session.execute(
            update(challenge_user_progress)
            .where(challenge_user_progress.c.user_id == user_id,
                   challenge_user_progress.c.day_index == day_index)
            .values(answer_rewarded=True, updated_at=now)
        )
        reward_given = d["reward_answer"]

    # показать кодовое слово — только если верно и ещё не показывали
    res3 = await session.execute(
        select(challenge_user_progress.c.codeword_revealed)
        .where(challenge_user_progress.c.user_id == user_id,
               challenge_user_progress.c.day_index == day_index)
    )
    revealed = res3.scalar_one()

    codeword_value = None
    if is_correct and not revealed:
        codeword_value = d["codeword"]
        await session.execute(
            update(challenge_user_progress)
            .where(challenge_user_progress.c.user_id == user_id,
                   challenge_user_progress.c.day_index == day_index)
            .values(codeword_revealed=True, updated_at=datetime.utcnow())
        )

    return {"reward_answer": reward_given, "is_correct": bool(is_correct), "codeword": codeword_value}


# === финал: ввод 5 кодовых слов ==============================================
async def submit_final(session: AsyncSession, user_id: int, keywords: List[str]) -> Dict[str, Any]:
    if not content.ENABLED:
        raise ValueError("Challenge is disabled")
    if len(keywords) != 5:
        raise ValueError("Need 5 keywords")

    expected = [d["codeword"] for d in sorted(content.DAYS, key=lambda x: x["day_index"])]
    norm = lambda s: (s or "").strip().lower()
    ok = all(norm(a) == norm(b) for a, b in zip(keywords, expected))

    now = datetime.utcnow()
    res = await session.execute(
        select(challenge_user_final).where(challenge_user_final.c.user_id == user_id)
    )
    row = res.first()

    if row is None:
        await session.execute(insert(challenge_user_final).values(
            user_id=user_id,
            submitted=True,
            success=ok,
            reward_granted=False,
            submitted_at=now,
            updated_at=now,
        ))
        already_granted = False
    else:
        st = dict(row._mapping)
        if st["success"] and st["reward_granted"]:
            return {"success": True, "reward": 0, "already": True}
        await session.execute(
            update(challenge_user_final)
            .where(challenge_user_final.c.user_id == user_id)
            .values(submitted=True, success=ok, updated_at=now)
        )
        already_granted = st["reward_granted"]

    reward = 0
    if ok and not already_granted and content.FINAL_REWARD > 0:
        await award_coins(session, user_id, content.FINAL_REWARD, "challenge_final")
        await session.execute(
            update(challenge_user_final)
            .where(challenge_user_final.c.user_id == user_id)
            .values(reward_granted=True, updated_at=datetime.utcnow())
        )
        reward = content.FINAL_REWARD

    return {"success": ok, "reward": reward, "already": already_granted}
