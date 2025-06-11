from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_async_session
from app.models.user import User
import urllib.parse
import json
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.get("/api/user/invites")
async def get_user_invites(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        decoded = urllib.parse.unquote(init_data)
        parsed = json.loads(decoded) if decoded.startswith('{') else dict(urllib.parse.parse_qsl(decoded))

        user_raw = parsed.get("user")
        if isinstance(user_raw, str):
            user_raw = json.loads(user_raw)

        user_id = (
            user_raw.get("id")
            if isinstance(user_raw, dict)
            else parsed.get("id")
        )

        if not user_id:
            raise ValueError("Missing user_id")

        telegram_id = int(user_id)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid init_data: {str(e)}")

    result = await session.execute(
        select(User)
        .options(selectinload(User.invited_users))
        .where(User.telegram_id == telegram_id)
    )

    if not user:
        return {"count": 0}

    return {"count": len(user.invited_users or [])}





