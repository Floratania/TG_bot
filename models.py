from sqlalchemy import Column, Integer, BigInteger, String, Enum
from db import Base

class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    user_id = Column(Integer, nullable=True)
    phone = Column(String(20), nullable=True)
    role = Column(Enum("користувач", "дилер", "менеджер", "адмін", "старший адмін"), default="користувач")
    temp_code = Column(BigInteger, nullable=True)


from sqlalchemy import Column, Integer, String, Enum, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import DateTime

Base = declarative_base()

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, nullable=False)
    manager_id = Column(Integer, nullable=True)
    sender = Column(Enum("client", "manager"), nullable=False)
    type = Column(Enum("text", "photo", "video", "document", "voice"), nullable=False)
    text = Column(Text, nullable=True)
    file_id = Column(String(255), nullable=True)
    media_group_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
