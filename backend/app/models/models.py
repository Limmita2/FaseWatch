import uuid
import enum
from sqlalchemy import (
    Column, String, Boolean, Float, BigInteger, Integer, Text,
    ForeignKey, Enum, TIMESTAMP, JSON, Uuid, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"


class IdentificationStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    region = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=False)
    api_id = Column(String(20), nullable=False)
    api_hash = Column(String(50), nullable=False)
    session_string = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="pending_auth")  # pending_auth | active | error | disabled
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    account_groups = relationship("TelegramAccountGroup", back_populates="account")


class TelegramAccountGroup(Base):
    __tablename__ = "telegram_account_groups"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id = Column(Uuid, ForeignKey("telegram_accounts.id"), nullable=False)
    group_id = Column(Uuid, ForeignKey("groups.id"), nullable=False)
    history_loaded = Column(Boolean, default=False)
    history_load_progress = Column(Integer, default=0)
    last_message_id = Column(BigInteger, nullable=True)
    joined_at = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)

    account = relationship("TelegramAccount", back_populates="account_groups")
    group = relationship("Group")

    __table_args__ = (
        Index("ix_tg_account_groups_account", "account_id"),
        Index("ix_tg_account_groups_group", "group_id"),
    )


class Group(Base):
    __tablename__ = "groups"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=True)
    name = Column(Text, nullable=False)
    bot_active = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=False, server_default='0', nullable=False)
    is_public = Column(Boolean, default=True, server_default='1', nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    messages = relationship("Message", back_populates="group")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id = Column(Uuid, ForeignKey("groups.id"), nullable=False)
    telegram_message_id = Column(BigInteger, nullable=True)
    sender_telegram_id = Column(BigInteger, nullable=True)
    sender_name = Column(Text, nullable=True)
    text = Column(Text, nullable=True)
    has_photo = Column(Boolean, default=False)
    photo_path = Column(Text, nullable=True)   # путь на QNAP
    timestamp = Column(TIMESTAMP, nullable=True)
    imported_from_backup = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    photo_hash = Column(String(64), index=True, nullable=True)
    # Telethon account support
    source_account_id = Column(Uuid, ForeignKey("telegram_accounts.id"), nullable=True)
    source_type = Column(String(10), default="bot")  # bot | account | import
    document_text = Column(Text, nullable=True)  # витягнутий текст з PDF/DOCX
    document_name = Column(String(255), nullable=True)

    group = relationship("Group", back_populates="messages")
    faces = relationship("Face", back_populates="message")
    source_account = relationship("TelegramAccount")

    __table_args__ = (
        Index("ix_messages_group_timestamp", "group_id", "timestamp"),
        Index("ix_messages_group_created", "group_id", "created_at"),
        Index("ix_messages_timestamp", "timestamp"),
        Index("ix_messages_has_photo", "has_photo"),
        Index("ix_messages_photo_hash", "photo_hash"),
        Index("ix_messages_source_account", "source_account_id"),
        UniqueConstraint("group_id", "telegram_message_id", name="uq_group_telegram_msg"),
    )

class Face(Base):
    __tablename__ = "faces"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id = Column(Uuid, ForeignKey("messages.id"), nullable=True)
    crop_path = Column(Text, nullable=True)
    qdrant_point_id = Column(Uuid, nullable=True)
    bbox = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    message = relationship("Message", back_populates="faces")

    __table_args__ = (
        Index("ix_faces_message_id", "message_id"),
        Index("ix_faces_qdrant_point_id", "qdrant_point_id"),
    )


class MessagePhone(Base):
    __tablename__ = "message_phones"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id = Column(Uuid, ForeignKey("messages.id"), nullable=False)
    phone = Column(String(15), nullable=False)

    message = relationship("Message")

    __table_args__ = (
        Index("ix_message_phones_phone", "phone"),
        Index("ix_message_phones_message_id", "message_id"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.operator)
    description = Column(Text, nullable=True)
    last_ip = Column(String(50), nullable=True)
    allowed_ip = Column(String(50), default="*", server_default="*", nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
