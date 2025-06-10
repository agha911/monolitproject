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

        user_id = (
            parsed.get("user", {}).get("id")
            if isinstance(parsed.get("user"), dict)
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
    return {"invited": [i < len(invited_users) for i in range(4)]}



