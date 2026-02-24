"""
Endpoint для приёма данных от бота (внутренний API).
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.models.models import Group, Message
from app.services.storage_service import save_photo_to_qnap

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
        group = Group(id=uuid.uuid4(), telegram_id=tg_id, name=group_name)
        db.add(group)
        await db.flush()

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
    if photo:
        photo_data = await photo.read()
        if photo_data:
            has_photo = True
            ts_str = ts.strftime("%Y-%m-%dT%H-%M-%S") if ts else "unknown"
            photo_path = save_photo_to_qnap(photo_data, str(group.id), message_id, ts_str)

    # Сохраняем сообщение
    msg = Message(
        id=uuid.uuid4(),
        group_id=group.id,
        telegram_message_id=int(message_id) if message_id.isdigit() else None,
        sender_telegram_id=int(sender_telegram_id) if sender_telegram_id.isdigit() else None,
        sender_name=sender_name or None,
        text=text or None,
        has_photo=has_photo,
        photo_path=photo_path,
        timestamp=ts,
        imported_from_backup=False,
    )
    db.add(msg)
    await db.commit()

    # Если есть фото — отправляем в Celery для распознавания лиц
    if photo_path:
        from app.worker.tasks import process_photo
        process_photo.delay(str(msg.id), photo_path, str(group.id), ts.isoformat() if ts else "")

    return {"ok": True, "message_id": str(msg.id)}
