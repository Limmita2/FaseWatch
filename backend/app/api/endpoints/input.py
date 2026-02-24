"""
Endpoint для ручного ввода фото с описанием.
Загружает фото + текст → создаёт Message → сохраняет на QNAP → Celery для распознавания лиц.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pathlib import Path
import uuid
import os

from app.core.database import get_db
from app.core.config import settings
from app.models.models import Group, Message
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/")
async def input_photo(
    photo: UploadFile = File(...),
    text: str = Form(""),
    group_name: str = Form("Ручной ввод"),
    group_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Ручной ввод: загрузка фото с текстом.
    Фото сохраняется на QNAP, запускается Celery task для распознавания лиц.
    """
    # Находим или создаём группу
    group = None
    if group_id:
        result = await db.execute(select(Group).where(Group.id == uuid.UUID(group_id)))
        group = result.scalar_one_or_none()

    if not group:
        # Ищем группу "Ручной ввод" или создаём
        result = await db.execute(select(Group).where(Group.name == group_name))
        group = result.scalar_one_or_none()
        if not group:
            group = Group(id=uuid.uuid4(), name=group_name, bot_active=False)
            db.add(group)
            await db.flush()

    # Читаем фото
    contents = await photo.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Пустой файл")

    # Сохраняем на QNAP
    now = datetime.utcnow()
    ts_str = now.strftime("%Y-%m")
    msg_id = uuid.uuid4()
    dest_dir = Path(settings.QNAP_MOUNT_PATH) / "photos" / str(group.id) / ts_str
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{msg_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
    file_path = dest_dir / filename
    with open(file_path, "wb") as f:
        f.write(contents)

    # Создаём Message
    msg = Message(
        id=msg_id,
        group_id=group.id,
        sender_name="Ручной ввод",
        text=text if text else None,
        has_photo=True,
        photo_path=str(file_path),
        timestamp=now,
        imported_from_backup=False,
    )
    db.add(msg)
    await db.commit()

    # Запускаем Celery task
    from app.worker.tasks import process_photo
    process_photo.delay(
        str(msg.id),
        str(file_path),
        str(group.id),
        now.isoformat(),
    )

    return {
        "message_id": str(msg.id),
        "group_id": str(group.id),
        "group_name": group.name,
        "photo_path": str(file_path),
        "text": text,
        "faces_queued": True,
    }
