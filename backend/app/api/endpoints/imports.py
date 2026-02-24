"""
Endpoint импорта резервной копии Telegram Desktop.
Принимает ZIP-архив, парсит messages.html, сохраняет фото → QNAP → Celery.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
import tempfile
import zipfile
import shutil
import uuid
import json
import io
import os
import re

from app.core.database import get_db
from app.core.config import settings
from app.models.models import Group, Message
from app.api.deps import get_current_user

router = APIRouter()


def parse_telegram_messages_html(html_content: str, photos_dir: str):
    """
    Парсит messages.html из экспорта Telegram Desktop.
    Возвращает список словарей с ключами:
        message_id, sender_name, timestamp, text, photo_rel_path
    """
    soup = BeautifulSoup(html_content, "html.parser")
    messages_divs = soup.find_all("div", class_=re.compile(r"message\s+default"))

    parsed = []
    current_sender = None

    for div in messages_divs:
        # Извлекаем message_id
        msg_id_attr = div.get("id", "")
        msg_id_num = re.sub(r"\D", "", msg_id_attr)

        # Если это первое сообщение серии — извлекаем from_name
        from_name_div = div.find("div", class_="from_name")
        if from_name_div:
            current_sender = from_name_div.get_text(strip=True)

        # Дата/время
        date_div = div.find("div", class_="date")
        timestamp_str = None
        timestamp = None
        if date_div:
            timestamp_str = date_div.get("title", "")
            try:
                timestamp = datetime.strptime(timestamp_str[:19], "%d.%m.%Y %H:%M:%S")
            except ValueError:
                pass

        # Текст
        text_div = div.find("div", class_="text")
        text = text_div.get_text(strip=True) if text_div else None

        # Фото
        photo_wrap = div.find("a", class_="photo_wrap")
        photo_rel_path = None
        if photo_wrap:
            href = photo_wrap.get("href", "")
            if href:
                photo_rel_path = href

        parsed.append({
            "message_id": msg_id_num,
            "sender_name": current_sender,
            "timestamp": timestamp,
            "text": text if text else None,
            "photo_rel_path": photo_rel_path,
        })

    return parsed


@router.post("/")
async def import_backup(
    file: UploadFile = File(...),
    group_name: str = Form(""),
    group_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Импорт резервной копии Telegram Desktop (ZIP).
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Ожидается ZIP-файл")

    # Создаём или находим группу
    group = None
    if group_id:
        result = await db.execute(select(Group).where(Group.id == uuid.UUID(group_id)))
        group = result.scalar_one_or_none()

    if not group:
        group = Group(id=uuid.uuid4(), name=group_name or file.filename.replace(".zip", ""))
        db.add(group)
        await db.flush()

    # Распаковываем ZIP во временную директорию
    tmp_dir = tempfile.mkdtemp()
    try:
        contents = await file.read()
        zip_path = os.path.join(tmp_dir, "backup.zip")
        with open(zip_path, "wb") as f:
            f.write(contents)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_dir)

        # Ищем messages.html
        html_path = None
        for root, dirs, files in os.walk(tmp_dir):
            if "messages.html" in files:
                html_path = os.path.join(root, "messages.html")
                photos_dir = os.path.join(root, "photos")
                break

        if not html_path:
            raise HTTPException(status_code=400, detail="messages.html не найден в архиве")

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        messages_data = parse_telegram_messages_html(html_content, photos_dir if os.path.exists(photos_dir) else "")

        # Сохраняем сообщения в БД и фото на QNAP
        stats = {"messages": 0, "photos": 0, "faces_queued": 0}

        for msg_data in messages_data:
            has_photo = bool(msg_data["photo_rel_path"])
            photo_qnap_path = None

            if has_photo and os.path.exists(photos_dir):
                src_photo = os.path.join(os.path.dirname(html_path), msg_data["photo_rel_path"])
                if os.path.isfile(src_photo):
                    ts_str = msg_data["timestamp"].strftime("%Y-%m") if msg_data["timestamp"] else "unknown"
                    dest_dir = Path(settings.QNAP_MOUNT_PATH) / "photos" / str(group.id) / ts_str
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / f"{msg_data['message_id']}_{uuid.uuid4().hex[:8]}.jpg"
                    shutil.copy2(src_photo, str(dest_file))
                    photo_qnap_path = str(dest_file)
                    stats["photos"] += 1

            msg = Message(
                id=uuid.uuid4(),
                group_id=group.id,
                telegram_message_id=int(msg_data["message_id"]) if msg_data["message_id"] else None,
                sender_name=msg_data["sender_name"],
                text=msg_data["text"],
                has_photo=has_photo,
                photo_path=photo_qnap_path,
                timestamp=msg_data["timestamp"],
                imported_from_backup=True,
            )
            db.add(msg)
            stats["messages"] += 1

            # Если есть фото — ставим в очередь Celery для распознавания лиц
            if photo_qnap_path:
                from app.worker.tasks import process_photo
                process_photo.delay(
                    str(msg.id),
                    photo_qnap_path,
                    str(group.id),
                    msg_data["timestamp"].isoformat() if msg_data["timestamp"] else "",
                )
                stats["faces_queued"] += 1

        await db.commit()

        return {
            "group_id": str(group.id),
            "group_name": group.name,
            "stats": stats,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
