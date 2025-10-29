import logging
from sqlalchemy.orm import Session
from models import TelegramUser, ChatMessage, SupportChat
from utils import normalize_phone
from db import SessionLocal
from typing import List
from config import SUPER_ADMIN_ID
from datetime import datetime


# --- Налаштування логування ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Користувачі ---
def get_user_by_telegram_id(db: Session, telegram_id: int):
    logger.info(f"Запущено get_user_by_telegram_id для telegram_id={telegram_id}")
    return db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()

def get_user_role(db: Session, telegram_id: int) -> str:
    logger.info(f"Запущено get_user_role для telegram_id={telegram_id}")
    user = get_user_by_telegram_id(db, telegram_id)
    role = user.role if user else "користувач"
    logger.info(f"Отримана роль: {role}")
    return role

def save_user(db: Session, telegram_id: int, phone: str, role="користувач", user_id=None):
    logger.info(f"Запущено save_user для telegram_id={telegram_id}, phone={phone}, role={role}")
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
    logger.info(f"Користувач збережено: {user}")
    return user

def is_manager(db: Session, telegram_id: int) -> bool:
    logger.info(f"Запущено is_manager для telegram_id={telegram_id}")
    if telegram_id == SUPER_ADMIN_ID:
        logger.info("Користувач є супер-адміном")
        return True
    role = get_user_role(db, telegram_id)
    result = role in ["менеджер", "адмін", "старший адмін"]
    logger.info(f"is_manager результат: {result}")
    return result

# --- Чати ---
def get_support_chat_by_client_id(db: Session, client_id: int) -> SupportChat:
    logger.info(f"Запущено get_support_chat_by_client_id для client_id={client_id}")
    return db.query(SupportChat).filter(SupportChat.client_id == client_id).first()

def assign_manager_to_chat(db: Session, client_id: int, manager_id: int) -> SupportChat:
    logger.info(f"Запущено assign_manager_to_chat для client_id={client_id}, manager_id={manager_id}")
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        chat.manager_id = manager_id
        chat.status = "open"
        chat.last_manager_message_at = datetime.utcnow()
        db.commit()
        db.refresh(chat)
    logger.info(f"Чат після призначення менеджера: {chat}")
    return chat

def close_support_chat(db: Session, client_id: int):
    logger.info(f"Запущено close_support_chat для client_id={client_id}")
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        chat.status = "closed"
        db.commit()
        db.refresh(chat)
        logger.info(f"Чат закрито: {chat}")
        

def get_active_support_chats(db: Session) -> List[SupportChat]:
    logger.info("Запущено get_active_support_chats")
    chats = db.query(SupportChat).filter(SupportChat.status != "closed").order_by(
        SupportChat.last_client_message_at.desc()
    ).all()
    logger.info(f"Знайдено активних чатів: {len(chats)}")
    return chats

# --- Повідомлення ---
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
    logger.info(f"Запущено save_message: client_id={client_id}, sender={sender}, type={type_}")
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
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
        db.refresh(msg)
        if chat:
            db.refresh(chat)

        logger.info(f"Повідомлення збережено: {msg}")
        return msg
    except Exception as e:
        logger.error(f"Помилка save_message: {e}")
    finally:
        if close_session:
            db.close()

def get_chat_history(db: Session, client_id: int, limit: int = 50) -> List[ChatMessage]:
    logger.info(f"Запущено get_chat_history для client_id={client_id}, limit={limit}")
    messages = db.query(ChatMessage).filter(
        ChatMessage.client_id == client_id
    ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
    logger.info(f"Знайдено повідомлень: {len(messages)}")
    return messages

def get_manager_roles() -> List[str]:
    logger.info("Запущено get_manager_roles")
    roles = ["менеджер", "адмін", "старший адмін"]
    logger.info(f"Ролі менеджерів: {roles}")
    return roles
