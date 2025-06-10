from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_async_session
from app.models.user import User
import urllib.parse
import json

router = APIRouter()

@router.get("/api/user/invites")
async def get_user_invites(
    init_data: str,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        decoded = urllib.parse.unquote(init_data)
        parsed = json.loads(decoded) if decoded.startswith('{') else dict(urllib.parse.parse_qsl(decoded))

        user_data = parsed.get("user")
        if isinstance(user_data, str):
            user_data = json.loads(user_data)

        user_id = (
            user_data.get("id")
            if isinstance(user_data, dict)
            else parsed.get("id")
        )

        if not user_id:
            raise ValueError("Missing user_id")

        telegram_id = int(user_id)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid init_data: {str(e)}")

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        return {"invited": [False, False, False, False]}

    invited_users = user.invited_users[:4]

    invited_flags = [
        bool(invited and invited.telegram_id)
        for invited in invited_users
    ]

    # Дополняем до 4 флагов
    invited_flags += [False] * (4 - len(invited_flags))

    return {"invited": invited_flags}




