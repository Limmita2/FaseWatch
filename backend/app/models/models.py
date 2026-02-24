import uuid
import enum
from sqlalchemy import (
    Column, String, Boolean, Float, BigInteger, Text,
    ForeignKey, Enum, TIMESTAMP, JSON, Uuid
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


class Group(Base):
    __tablename__ = "groups"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=True)
    name = Column(Text, nullable=False)
    bot_active = Column(Boolean, default=True)
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

    group = relationship("Group", back_populates="messages")
    faces = relationship("Face", back_populates="message")


class Person(Base):
    __tablename__ = "persons"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    display_name = Column(Text, nullable=True)
    confirmed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    faces = relationship("Face", back_populates="person")


class Face(Base):
    __tablename__ = "faces"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    person_id = Column(Uuid, ForeignKey("persons.id"), nullable=True)
    message_id = Column(Uuid, ForeignKey("messages.id"), nullable=True)
    crop_path = Column(Text, nullable=True)        # мини-превью на QNAP
    qdrant_point_id = Column(Uuid, nullable=True)
    bbox = Column(JSON, nullable=True)             # bounding box coordinates
    confidence = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    person = relationship("Person", back_populates="faces")
    message = relationship("Message", back_populates="faces")
    queue_entries = relationship("IdentificationQueue", back_populates="face")


class IdentificationQueue(Base):
    __tablename__ = "identification_queue"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    face_id = Column(Uuid, ForeignKey("faces.id"), nullable=False)
    suggested_person_id = Column(Uuid, ForeignKey("persons.id"), nullable=True)
    similarity = Column(Float, nullable=True)
    status = Column(Enum(IdentificationStatus), default=IdentificationStatus.pending)
    reviewed_by = Column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    face = relationship("Face", back_populates="queue_entries")
    suggested_person = relationship("Person", foreign_keys=[suggested_person_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.operator)
    description = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
