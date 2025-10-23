from sqlalchemy.orm import Session
from models import TelegramUser
from utils import normalize_phone

def get_user_by_telegram_id(db: Session, telegram_id: int):
    return db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()

def get_user_role(db: Session, telegram_id: int) -> str:
    user = get_user_by_telegram_id(db, telegram_id)
    return user.role if user else "користувач"

def save_user(db: Session, telegram_id: int, phone: str, role="користувач", user_id=None):
    user = get_user_by_telegram_id(db, telegram_id)
    if user:
        user.phone = normalize_phone(phone)
        user.role = role
        user.user_id = user_id
    else:
        user = TelegramUser(
            telegram_id=telegram_id,
            phone=normalize_phone(phone),
            role=role,
            user_id=user_id
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


from db import SessionLocal
from models import TelegramUser

def is_attached_to_site(telegram_id: int) -> bool:
    db = SessionLocal()
    try:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()
        return bool(user and user.user_id)
    finally:
        db.close()




from db import SessionLocal
from models import ChatMessage

def save_message(client_id, sender, type_, text=None, file_id=None, manager_id=None, media_group_id=None):
    db = SessionLocal()
    try:
        msg = ChatMessage(
            client_id=client_id,
            manager_id=manager_id,
            sender=sender,
            type=type_,
            text=text,
            file_id=file_id,
            media_group_id=media_group_id
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg
    finally:
        db.close()
