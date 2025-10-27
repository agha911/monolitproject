# helpers/partner_auth.py
from sqlalchemy import select, insert, update
from app.models.partner import Partner
from app.models.drop import Drop
from app.models.drop_purchase import DropPurchase
from app.database import SessionLocal  # ваш способ получить сессию

def partner_by_api_key(db, api_key: str):
    return db.execute(select(Partner).where(Partner.api_key == api_key)).scalar_one_or_none()

def upsert_partner_user(db, partner_id: int, telegram_id: int):
    # простая вставка с защитой от дубля
    try:
        db.execute(insert(PartnerUser).values(partner_id=partner_id, telegram_id=telegram_id))
        db.commit()
    except Exception:
        db.rollback()  # запись, вероятно, уже есть

def get_partner_for_telegram(db, telegram_id: int):
    row = db.execute(
        select(Partner, PartnerUser).join(PartnerUser, PartnerUser.partner_id == Partner.id)\
            .where(PartnerUser.telegram_id == telegram_id)
    ).first()
    return row[0] if row else None

def list_partner_drops(db, partner_id: int, limit=5, offset=0):
    return db.execute(
        select(Drop).where(Drop.partner_id == partner_id).order_by(Drop.id.desc()).limit(limit).offset(offset)
    ).scalars().all()

def toggle_drop_active(db, drop_id: int, partner_id: int):
    d = db.execute(select(Drop).where(Drop.id == drop_id, Drop.partner_id == partner_id)).scalar_one_or_none()
    if not d:
        return None
    d.active = not bool(d.active)
    db.commit()
    db.refresh(d)
    return d

def get_purchase_by_code(db, code: str, partner_id: int):
    return db.execute(
        select(DropPurchase).where(DropPurchase.unique_code == code)
    ).scalar_one_or_none()

def set_purchase_status(db, code: str, new_status: str, partner_id: int):
    p = db.execute(
        select(DropPurchase).where(DropPurchase.unique_code == code)
    ).scalar_one_or_none()
    if not p:
        return None, "not_found"
    # при желании проверьте, что код относится к дропу этого партнёра:
    d = db.execute(select(Drop).where(Drop.id == p.drop_id, Drop.partner_id == partner_id)).scalar_one_or_none()
    if not d:
        return None, "forbidden"

    if new_status == "redeemed":
        if p.status != "active":
            return None, "wrong_status"
        p.status = "redeemed"
        p.redeemed_at = datetime.utcnow()
    elif new_status == "revoked":
        if p.status == "redeemed":
            return None, "already_redeemed"
        p.status = "revoked"
    else:
        return None, "bad_status"

    db.commit()
    db.refresh(p)
    return p, "ok"
