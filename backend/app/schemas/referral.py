# schemas/referral.py
from datetime import date, datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

class ReferralBalanceOut(BaseModel):
    day_date: date
    amount: int = Field(ge=0)
    status: Literal["open", "claimed", "expired", "none"]
    expires_at_iso: str       # ISO-строка конца дня по Баку
    seconds_left: int         # сколько секунд до конца дня (если status == "open"), иначе 0

class ReferralClaimOut(BaseModel):
    status: Literal["ok", "nothing_to_claim", "already_claimed", "expired"]
    claimed_amount: int
    total_xp: int
