from sqlalchemy.orm import Session
from models import TelegramUser, ChatMessage, SupportChat
from utils import normalize_phone
from db import SessionLocal
from typing import List
from config import SUPER_ADMIN_ID
from datetime import datetime

# --- Користувачі ---

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

def is_manager(db: Session, telegram_id: int) -> bool:
    if telegram_id == SUPER_ADMIN_ID:
        return True
    role = get_user_role(db, telegram_id)
    return role in ["менеджер", "адмін", "старший адмін"]

# --- Чати ---

def get_support_chat_by_client_id(db: Session, client_id: int) -> SupportChat:
    return db.query(SupportChat).filter(SupportChat.client_id == client_id).first()

def assign_manager_to_chat(db: Session, client_id: int, manager_id: int) -> SupportChat:
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        chat.manager_id = manager_id
        chat.status = "open"
        chat.last_manager_message_at = datetime.utcnow()
        db.commit()
        db.refresh(chat)
    return chat

def close_support_chat(db: Session, client_id: int):
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        chat.status = "closed"
        db.commit()
        db.refresh(chat)

def get_active_support_chats(db: Session) -> List[SupportChat]:
    return db.query(SupportChat).filter(SupportChat.status != "closed").order_by(
        SupportChat.last_client_message_at.desc()
    ).all()

# --- Повідомлення ---

from datetime import datetime
from sqlalchemy.orm import Session
from db import SessionLocal
from models import ChatMessage, SupportChat

def save_message(
    client_id: int,
    sender: str,
    type_: str,
    text: str = None,
    file_id: str = None,
    manager_id: int = None,
    media_group_id: str = None,
    db: Session = None
):
    """Зберігає повідомлення та оновлює стан чату."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        # --- Створюємо повідомлення ---
        msg = ChatMessage(
            client_id=client_id,
            manager_id=manager_id,
            sender=sender,
            type=type_,
            text=text,
            file_id=file_id,
            media_group_id=media_group_id,
            created_at=datetime.utcnow()
        )
        db.add(msg)

        # --- Отримуємо або створюємо чат ---
        chat = db.query(SupportChat).filter(SupportChat.client_id == client_id).first()
        now = datetime.utcnow()

        if sender == "client":
            if not chat:
                chat = SupportChat(
                    client_id=client_id,
                    status="awaiting_manager",
                    last_client_message_at=now
                )
                db.add(chat)
            else:
                if chat.status == "closed":
                    chat.status = "awaiting_manager"
                    chat.manager_id = None
                chat.last_client_message_at = now

        elif sender == "manager" and chat:
            chat.last_manager_message_at = now

        db.commit()

        # Оновлюємо об’єкти після commit
        db.refresh(msg)
        if chat:
            db.refresh(chat)

        return msg

    except Exception:
        db.rollback()
        raise
    finally:
        if close_session:
            db.close()



def get_chat_history(db: Session, client_id: int, limit: int = 50) -> List[ChatMessage]:
    return db.query(ChatMessage).filter(
        ChatMessage.client_id == client_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()


def get_manager_roles() -> List[str]:
    """Повертає список ролей, які можуть бути менеджерами підтримки."""
    return ["менеджер", "адмін", "старший адмін"]
