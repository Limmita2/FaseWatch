"""
Endpoint для приёма данных от бота (внутренний API).
"""
import asyncio
import hashlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import pymysql
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
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
MESSAGE_UNIQUE_CONSTRAINTS = {"uq_group_telegram_msg", "uq_group_external_msg"}
SUPPORTED_SOURCE_PLATFORMS = {"telegram", "signal", "whatsapp"}


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
            return any(name in str(original) for name in MESSAGE_UNIQUE_CONSTRAINTS)
    return False


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _normalize_platform(value: Any) -> str:
    platform = _as_text(value).strip().lower() or "telegram"
    if platform not in SUPPORTED_SOURCE_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported source_platform: {platform}")
    return platform


async def _parse_request_payload(request: Request) -> tuple[dict[str, str], UploadFile | None]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        return {key: _as_text(value) for key, value in payload.items()}, None

    form = await request.form()
    payload: dict[str, str] = {}
    photo: UploadFile | None = None
    for key, value in form.multi_items():
        is_upload = isinstance(value, UploadFile) or (
            hasattr(value, "filename") and callable(getattr(value, "read", None))
        )
        if is_upload:
            if key == "photo":
                photo = value
            continue
        payload[key] = _as_text(value)
    return payload, photo


async def _resolve_group(
    db: AsyncSession,
    source_platform: str,
    group_external_id: str,
    group_name: str,
) -> Group:
    group = None
    telegram_id = None
    if source_platform == "telegram":
        try:
            telegram_id = int(group_external_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Telegram group ID")

        result = await db.execute(select(Group).where(Group.telegram_id == telegram_id))
        group = result.scalar_one_or_none()

    if group is None:
        result = await db.execute(
            select(Group).where(
                Group.source_platform == source_platform,
                Group.external_id == group_external_id,
            )
        )
        group = result.scalar_one_or_none()

    if group is None:
        group = Group(
            id=uuid.uuid4(),
            telegram_id=telegram_id,
            source_platform=source_platform,
            external_id=group_external_id,
            name=group_name or group_external_id,
            is_approved=source_platform != "telegram",
        )
        db.add(group)
        await db.commit()
        await db.refresh(group)
        return group

    changed = False
    if group.source_platform != source_platform:
        group.source_platform = source_platform
        changed = True
    if group.external_id != group_external_id:
        group.external_id = group_external_id
        changed = True
    if source_platform == "telegram" and telegram_id is not None and group.telegram_id != telegram_id:
        group.telegram_id = telegram_id
        changed = True
    if group_name and group.name != group_name:
        group.name = group_name
        changed = True

    if changed:
        await db.commit()
        await db.refresh(group)

    return group


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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Принимает сообщение от бота/telethon и сохраняет в БД."""
    payload, photo = await _parse_request_payload(request)

    source_platform = _normalize_platform(payload.get("source_platform"))
    group_external_id = _as_text(payload.get("group_external_id") or payload.get("group_telegram_id")).strip()
    if not group_external_id:
        raise HTTPException(status_code=400, detail="group_external_id is required")

    group_name = _as_text(payload.get("group_name")).strip()
    message_id = _as_text(payload.get("message_id")).strip()
    if not message_id:
        raise HTTPException(status_code=400, detail="message_id is required")

    sender_telegram_id = _as_text(payload.get("sender_telegram_id")).strip()
    sender_external_id = _as_text(payload.get("sender_external_id") or sender_telegram_id).strip()
    sender_name = _as_text(payload.get("sender_name")).strip()
    text = _as_text(payload.get("text"))
    timestamp = _as_text(payload.get("timestamp")).strip()
    source_account_id = _as_text(payload.get("source_account_id")).strip()
    source_type = _as_text(payload.get("source_type")).strip() or "bot"
    document_text = _as_text(payload.get("document_text"))
    document_name = _as_text(payload.get("document_name")).strip()

    group = await _resolve_group(db, source_platform, group_external_id, group_name)

    if not group.is_approved:
        return {"ok": False, "status": "pending_approval"}

    tg_msg_id = int(message_id) if source_platform == "telegram" and message_id.isdigit() else None
    external_message_id = message_id
    if tg_msg_id is not None:
        dup = await db.execute(
            select(Message).where(
                Message.group_id == group.id,
                Message.telegram_message_id == tg_msg_id
            )
        )
        if dup.scalar_one_or_none():
            return {"ok": True, "duplicate": True}
    if external_message_id:
        dup = await db.execute(
            select(Message).where(
                Message.group_id == group.id,
                Message.external_message_id == external_message_id,
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
        external_message_id=external_message_id or None,
        sender_telegram_id=int(sender_telegram_id) if sender_telegram_id.isdigit() else None,
        sender_external_id=sender_external_id or None,
        sender_name=sender_name or None,
        text=text or None,
        has_photo=has_photo,
        photo_path=photo_path,
        photo_hash=photo_hash,
        timestamp=ts,
        imported_from_backup=False,
        photo_processed_at=None,
        source_platform=source_platform,
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
