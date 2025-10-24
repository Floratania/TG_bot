from sqlalchemy.orm import Session
from models import TelegramUser, ChatMessage, SupportChat
from utils import normalize_phone
from db import SessionLocal
from typing import List
from sqlalchemy.sql import func
from config import SUPER_ADMIN_ID
from datetime import datetime

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

def is_attached_to_site(telegram_id: int) -> bool:
    db = SessionLocal()
    try:
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == telegram_id).first()
        return bool(user and user.user_id)
    finally:
        db.close()

def save_message(client_id: int, sender: str, type_: str, text: str = None, file_id: str = None, manager_id: int = None, media_group_id: str = None):
    db = SessionLocal()
    try:
        print(f"\n📝 save_message викликано:")
        print(f"   client_id={client_id}, sender={sender}, type={type_}")
        print(f"   text={text[:50] if text else None}...")
        print(f"   manager_id={manager_id}")
        
        # 1. Зберігаємо повідомлення
        msg = ChatMessage(
            client_id=client_id,
            manager_id=manager_id,
            sender=sender,
            type=type_,
            text=text,
            file_id=file_id,
            media_group_id=media_group_id,
            created_at=datetime.utcnow()  # Явно встановлюємо час
        )
        db.add(msg)
        db.flush()  # Отримуємо ID перед commit
        
        print(f"✅ Повідомлення додано в БД, ID={msg.id}, created_at={msg.created_at}")

        # 2. Оновлюємо або створюємо SupportChat
        chat = db.query(SupportChat).filter(SupportChat.client_id == client_id).first()
        
        if sender == "client":
            if not chat:
                print(f"🆕 Створюємо новий чат для клієнта {client_id}")
                chat = SupportChat(
                    client_id=client_id,
                    status="awaiting_manager",
                    last_client_message_at=datetime.utcnow()
                )
                db.add(chat)
            elif chat.status == "closed":
                print(f"🔄 Відновлюємо закритий чат для клієнта {client_id}")
                chat.status = "awaiting_manager"
                chat.manager_id = None
                chat.last_client_message_at = datetime.utcnow()
            else:
                print(f"📊 Оновлюємо існуючий чат для клієнта {client_id}")
                chat.last_client_message_at = datetime.utcnow()
                
        elif sender == "manager":
            if chat:
                print(f"💬 Менеджер {manager_id} відповідає в чат {client_id}")
                chat.last_manager_message_at = datetime.utcnow()
            else:
                print(f"⚠️ УВАГА: Чат для клієнта {client_id} не знайдено!")

        db.commit()
        db.refresh(msg)
        if chat:
            db.refresh(chat)
            
        print(f"✅ Транзакція завершена успішно\n")
        return msg
        
    except Exception as e:
        print(f"❌ ПОМИЛКА в save_message: {e}")
        db.rollback()
        raise
    finally:
        db.close()

# ФУНКЦІЇ для керування чатами
def get_manager_roles() -> List[str]:
    """Повертає список ролей, які можуть бути менеджерами підтримки."""
    return ["менеджер", "адмін", "старший адмін"]

def is_manager(db: Session, telegram_id: int) -> bool:
    """Перевіряє, чи є користувач менеджером, включаючи SUPER_ADMIN_ID."""
    
    if telegram_id == SUPER_ADMIN_ID:
        return True
        
    user_role = get_user_role(db, telegram_id)
    return user_role in get_manager_roles()

def get_active_support_chats(db: Session) -> List[SupportChat]:
    """Повертає список активних чатів (не закритих)."""
    return db.query(SupportChat).filter(
        SupportChat.status != "closed"
    ).order_by(
        SupportChat.last_client_message_at.desc()
    ).all()

def get_support_chat_by_client_id(db: Session, client_id: int) -> SupportChat:
    """Знаходить SupportChat за ID клієнта."""
    return db.query(SupportChat).filter(SupportChat.client_id == client_id).first()

def assign_manager_to_chat(db: Session, client_id: int, manager_id: int) -> SupportChat:
    """Призначає менеджера до чату і встановлює статус 'open'."""
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        print(f"👤 Призначаємо менеджера {manager_id} до чату {client_id}")
        chat.manager_id = manager_id
        chat.status = "open"
        db.commit()
        db.refresh(chat)
        return chat
    return None

def close_support_chat(db: Session, client_id: int):
    """Закриває чат підтримки."""
    chat = get_support_chat_by_client_id(db, client_id)
    if chat:
        print(f"🚪 Закриваємо чат {client_id}")
        chat.status = "closed"
        db.commit()
        db.refresh(chat)

def get_chat_history(db: Session, client_id: int, limit: int = 50) -> List[ChatMessage]:
    """Повертає історію повідомлень для клієнта."""
    messages = db.query(ChatMessage).filter(
        ChatMessage.client_id == client_id
    ).order_by(
        ChatMessage.created_at.desc()
    ).limit(limit).all()
    
    print(f"📚 Завантажено {len(messages)} повідомлень для клієнта {client_id}")
    return messages