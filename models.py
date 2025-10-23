from sqlalchemy import Column, Integer, BigInteger, String, Enum, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db import Base
from datetime import datetime

class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    user_id = Column(Integer, nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(Enum("користувач", "дилер", "менеджер", "адмін", "старший адмін"), default="користувач")
    temp_code = Column(BigInteger, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    client_id = Column(BigInteger, nullable=False, index=True)
    manager_id = Column(BigInteger, nullable=True, index=True)
    sender = Column(Enum("client", "manager"), nullable=False)
    type = Column(Enum("text", "photo", "video", "document", "voice"), nullable=False)
    text = Column(Text, nullable=True)
    file_id = Column(String(255), nullable=True)
    media_group_id = Column(String(255), nullable=True, index=True)
    
    # ВИПРАВЛЕНО: додано default для Python + server_default для MySQL
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now()
    )


class SupportChat(Base):
    __tablename__ = "support_chats"

    client_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), primary_key=True)
    manager_id = Column(BigInteger, nullable=True)
    status = Column(Enum("open", "closed", "awaiting_manager"), default="awaiting_manager")
    
    # Зв'язок
    client = relationship(
        "TelegramUser",
        primaryjoin="SupportChat.client_id == TelegramUser.telegram_id",
        foreign_keys=[client_id],
        backref="support_chat"
    )

    last_client_message_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now()
    )
    last_manager_message_at = Column(DateTime(timezone=True), nullable=True)