"""
Endpoint для приёма данных от бота (внутренний API).
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.models.models import Group, Message, MessagePhone
from app.services.storage_service import save_photo_to_qnap
from app.services.phone_utils import extract_phones as extract_phones_util

router = APIRouter()

LOCAL_TZ = ZoneInfo("Europe/Kyiv")


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
    db: AsyncSession = Depends(get_db),
):
    """Принимает сообщение от бота и сохраняет в БД."""
    # Находим или создаём группу
    tg_id = int(group_telegram_id) if group_telegram_id else None
    result = await db.execute(select(Group).where(Group.telegram_id == tg_id))
    group = result.scalar_one_or_none()

    if not group:
        # Новая группа по умолчанию НЕ одобрена администратором
        group = Group(id=uuid.uuid4(), telegram_id=tg_id, name=group_name, is_approved=False)
        db.add(group)
        await db.commit() # Сразу коммитим, чтобы она появилась в базе
        await db.refresh(group)

    # Если группа не одобрена, возвращаем специальный статус (чтобы бот запросил одобрение)
    if not group.is_approved:
        return {"ok": False, "status": "pending_approval"}

    # Дедупликация: проверка, есть ли уже это сообщение от бота
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

    # Обработка timestamp — конвертируем UTC из Telegram в Europe/Kyiv
    ts = None
    try:
        ts = datetime.fromisoformat(timestamp)
        # Если есть timezone info (UTC от Telegram) — конвертируем в локальное
        if ts.tzinfo is not None:
            ts = ts.astimezone(LOCAL_TZ).replace(tzinfo=None)
    except (ValueError, TypeError):
        ts = datetime.now(LOCAL_TZ).replace(tzinfo=None)

    # Сохраняем фото на QNAP
    photo_path = None
    has_photo = False
    photo_hash = None
    if photo:
        photo_data = await photo.read()
        if photo_data:
            import hashlib
            photo_hash = hashlib.sha256(photo_data).hexdigest()
            # Проверка на наличие дубликата картинки
            dup_photo = await db.execute(select(Message).where(Message.photo_hash == photo_hash))
            if dup_photo.scalars().first():
                # Полностью игнорируем дубликат
                return {"ok": True, "duplicate": True, "reason": "photo_duplicated"}

            has_photo = True
            ts_str = ts.strftime("%Y-%m-%dT%H-%M-%S") if ts else "unknown"
            photo_path = save_photo_to_qnap(photo_data, str(group.id), message_id, ts_str)

    # Сохраняем сообщение
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
    )
    db.add(msg)
    await db.commit()

    # Извлекаем телефоны из текста и сохраняем в message_phones
    if text:
        phones = extract_phones_util(text)
        if phones:
            for phone in phones:
                db.add(MessagePhone(id=uuid.uuid4(), message_id=msg.id, phone=phone))
            await db.commit()

    # Если есть фото — отправляем в Celery для распознавания лиц
    if photo_path:
        from app.worker.tasks import process_photo
        process_photo.delay(str(msg.id), photo_path, str(group.id), ts.isoformat() if ts else "")

    return {"ok": True, "message_id": str(msg.id)}

@router.post("/approve")
async def approve_group(group_telegram_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    """Одобрение новой группы (разрешить парсинг сообщений)."""
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
    """Отклонение группы (остановить попытки парсинга)."""
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
