from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def current_user(db: Session = Depends(get_db), init_data: str = Depends(...)) -> User:
    # твоя логика — заменить ... на обработку initData
    telegram_id = parse_telegram_user_id(init_data)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@router.get("/api/user/invites")
def get_user_invites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    invited = user.invited_users[:4]
    return {"invited": [i < len(invited) for i in range(4)]}

