"""
Endpoint для приёма данных от бота (внутренний API).
"""
import asyncio
import hashlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Group, Message, MessagePhone
from app.core.database import get_db
from app.services.storage_service import save_photo_to_qnap
from app.services.phone_utils import extract_phones as extract_phones_util

router = APIRouter()

LOCAL_TZ = ZoneInfo("Europe/Kyiv")
MYSQL_DEADLOCK_CODES = {1205, 1213}
MESSAGE_UNIQUE_CONSTRAINT = "uq_group_telegram_msg"


def _is_mysql_deadlock(error: Exception) -> bool:
    if not isinstance(error, OperationalError):
        return False
    original = getattr(error, "orig", None)
    if isinstance(original, pymysql.MySQLError) and original.args:
        return original.args[0] in MYSQL_DEADLOCK_CODES
    return False


def _is_duplicate_message_error(error: Exception) -> bool:
    if not isinstance(error, IntegrityError):
        return False
    original = getattr(error, "orig", None)
    if isinstance(original, pymysql.IntegrityError):
        if original.args and original.args[0] == 1062:
            return MESSAGE_UNIQUE_CONSTRAINT in str(original)
    return False


async def _commit_message_with_retry(db: AsyncSession, msg: Message) -> bool:
    for attempt in range(3):
        db.add(msg)
        try:
            await db.commit()
            return True
        except IntegrityError as exc:
            await db.rollback()
            if _is_duplicate_message_error(exc):
                return False
            raise
        except OperationalError as exc:
            await db.rollback()
            if not _is_mysql_deadlock(exc) or attempt == 2:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))
    return False


@router.post("/message")
async def receive_bot_message(
    group_telegram_id: str = Form(...),
    group_name: str = Form(""),
    message_id: str = Form(...),
    sender_telegram_id: str = Form(""),
    sender_name: str = Form(""),
    text: str = Form(""),
    timestamp: str = Form(""),
    photo: UploadFile = File(None),
    source_account_id: str = Form(""),
    source_type: str = Form("bot"),
    document_text: str = Form(""),
    document_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Принимает сообщение от бота/telethon и сохраняет в БД."""
    tg_id = int(group_telegram_id) if group_telegram_id else None
    result = await db.execute(select(Group).where(Group.telegram_id == tg_id))
    group = result.scalar_one_or_none()

    if not group:
        group = Group(id=uuid.uuid4(), telegram_id=tg_id, name=group_name, is_approved=False)
        db.add(group)
        await db.commit()
        await db.refresh(group)
    elif group_name and group.name != group_name:
        group.name = group_name
        await db.commit()

    if not group.is_approved:
        return {"ok": False, "status": "pending_approval"}

    tg_msg_id = int(message_id) if message_id.isdigit() else None
    if tg_msg_id is not None:
        dup = await db.execute(
            select(Message).where(
                Message.group_id == group.id,
                Message.telegram_message_id == tg_msg_id
            )
        )
        if dup.scalar_one_or_none():
            return {"ok": True, "duplicate": True}

    ts = None
    try:
        ts = datetime.fromisoformat(timestamp)
        if ts.tzinfo is not None:
            ts = ts.astimezone(LOCAL_TZ).replace(tzinfo=None)
    except (ValueError, TypeError):
        ts = datetime.now(LOCAL_TZ).replace(tzinfo=None)

    photo_path = None
    has_photo = False
    photo_hash = None
    if photo:
        photo_data = await photo.read()
        if photo_data:
            photo_hash = hashlib.sha256(photo_data).hexdigest()
            dup_photo = await db.execute(select(Message).where(Message.photo_hash == photo_hash))
            if dup_photo.scalars().first():
                return {"ok": True, "duplicate": True, "reason": "photo_duplicated"}

            has_photo = True
            ts_str = ts.strftime("%Y-%m-%dT%H-%M-%S") if ts else "unknown"
            photo_path = save_photo_to_qnap(photo_data, str(group.id), message_id, ts_str)

    # Resolve source_account_id
    src_account_uuid = None
    if source_account_id:
        try:
            src_account_uuid = uuid.UUID(source_account_id)
        except ValueError:
            pass

    msg = Message(
        id=uuid.uuid4(),
        group_id=group.id,
        telegram_message_id=tg_msg_id,
        sender_telegram_id=int(sender_telegram_id) if sender_telegram_id.isdigit() else None,
        sender_name=sender_name or None,
        text=text or None,
        has_photo=has_photo,
        photo_path=photo_path,
        photo_hash=photo_hash,
        timestamp=ts,
        imported_from_backup=False,
        source_account_id=src_account_uuid,
        source_type=source_type or "bot",
        document_text=document_text[:50000] if document_text else None,
        document_name=document_name or None,
    )
    inserted = await _commit_message_with_retry(db, msg)
    if not inserted:
        return {"ok": True, "duplicate": True}

    if text or document_text:
        search_text = text or document_text
        phones = extract_phones_util(search_text)
        if phones:
            for phone in phones:
                db.add(MessagePhone(id=uuid.uuid4(), message_id=msg.id, phone=phone))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
            except OperationalError as exc:
                await db.rollback()
                if not _is_mysql_deadlock(exc):
                    raise

    if photo_path:
        from app.worker.tasks import process_photo
        process_photo.delay(str(msg.id), photo_path, str(group.id), ts.isoformat() if ts else "")

    return {"ok": True, "message_id": str(msg.id)}

@router.post("/approve")
async def approve_group(group_telegram_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    """Одобрение новой группы."""
    try:
        tg_id = int(group_telegram_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid telegram ID")

    result = await db.execute(select(Group).where(Group.telegram_id == tg_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    group.is_approved = True
    group.bot_active = True
    await db.commit()
    return {"ok": True, "status": "approved"}

@router.post("/reject")
async def reject_group(group_telegram_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    """Отклонение группы."""
    try:
        tg_id = int(group_telegram_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid telegram ID")

    result = await db.execute(select(Group).where(Group.telegram_id == tg_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    group.is_approved = False
    group.bot_active = False
    await db.commit()
    return {"ok": True, "status": "rejected"}
