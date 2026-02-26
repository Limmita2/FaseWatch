import os
import shutil
import uuid
from pathlib import Path
from PIL import Image
import numpy as np
from app.core.config import settings


def get_qnap_path() -> Path:
    """Возвращает базовый путь к хранилищу QNAP."""
    return Path(settings.QNAP_MOUNT_PATH)


def save_photo_to_qnap(
    photo_data: bytes,
    group_id: str,
    message_id: str,
    timestamp_str: str,
) -> str:
    """Сохраняет оригинальное фото на QNAP.
    Структура: /photos/{group_id}/{YYYY-MM}/{message_id}_{timestamp}.jpg
    """
    base = get_qnap_path() / "photos" / group_id / timestamp_str[:7]
    base.mkdir(parents=True, exist_ok=True)
    filename = f"{message_id}_{timestamp_str}.jpg"
    file_path = base / filename
    with open(file_path, "wb") as f:
        f.write(photo_data)
    return str(file_path)


def save_face_crop_to_qnap(
    face_crop: np.ndarray,
    face_id: str,
) -> str:
    """Сохраняет кроп лица на QNAP.
    Структура: /faces/{face_id}.jpg
    """
    base = get_qnap_path() / "faces"
    base.mkdir(parents=True, exist_ok=True)
    file_path = base / f"{face_id}.jpg"
    img = Image.fromarray(face_crop[:, :, ::-1])  # BGR -> RGB
    img.save(str(file_path))
    return str(file_path)
