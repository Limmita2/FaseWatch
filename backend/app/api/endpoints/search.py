"""
Endpoints для поиска: по фото (лицу) и по тексту.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import asyncio
import tempfile
import uuid
import cv2
import numpy as np
import threading
import logging

from app.core.database import get_db
from app.models.models import Message, Face, Person, Group
from app.services.qdrant_service import ensure_collection_exists, search_similar_faces
from app.api.deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Lazy singleton для InsightFace ──
_face_app = None
_face_app_lock = threading.Lock()


def _get_face_app():
    global _face_app
    if _face_app is None:
        with _face_app_lock:
            if _face_app is None:
                from insightface.app import FaceAnalysis
                logger.info("Инициализация InsightFace для search...")
                app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=-1, det_size=(640, 640))
                _face_app = app
                logger.info("InsightFace загружен для search.")
    return _face_app


def _detect_faces_sync(img):
    """Синхронная детекция лиц (для запуска в потоке)."""
    face_app = _get_face_app()
    return face_app.get(img)

@router.post("/face")
async def search_by_face(
    photo: UploadFile = File(...),
    top_k: int = Query(5, ge=1, le=20),
    threshold: int = Query(50, ge=0, le=100),
    face_index: Optional[int] = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Поиск по фото:
    1. Принимает фото, обнаруживает лица
    2. Если несколько и face_index None — возвращает bounding boxes для выбора
    3. Ищет top-K похожих в Qdrant
    4. Возвращает карточки с контекстом (±2 сообщения)
    """
    contents = await photo.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"error": "Не удалось прочитать изображение"}

    # Детекция лиц в отдельном потоке (не блокируем event loop)
    try:
        detected_faces = await asyncio.to_thread(_detect_faces_sync, img)
    except Exception as e:
        logger.error("Ошибка детекции лиц: %s", e, exc_info=True)
        return {"error": f"Ошибка детекции лиц: {str(e)}"}

    if not detected_faces:
        return {"faces_detected": 0, "results": []}

    if len(detected_faces) > 1 and face_index is None:
        all_results = []
        for face_data in detected_faces:
            all_results.append({
                "bbox": face_data.bbox.tolist(),
                "matches": []  # пусто, БД не дергаем
            })
        return {
            "faces_detected": len(detected_faces),
            "requires_selection": True,
            "results": all_results
        }

    # Иначе проводим поиск для нужного лица
    qdrant_client = ensure_collection_exists()

    selected_index = face_index if face_index is not None and face_index < len(detected_faces) else 0
    face_to_process = detected_faces[selected_index]

    vector = face_to_process.embedding.tolist()
    bbox = face_to_process.bbox.tolist()

    score_threshold = threshold / 100.0
    similar = search_similar_faces(qdrant_client, vector, top_k=top_k, score_threshold=score_threshold)

    face_results = []
    for match in similar:
        payload = match.payload
        # Получаем контекст сообщения
        msg_id = payload.get("message_id")
        context = None
        if msg_id:
            msg_result = await db.execute(select(Message).where(Message.id == uuid.UUID(msg_id)))
            msg = msg_result.scalar_one_or_none()
            if msg:
                # 5 сообщений до и 5 после
                before = await db.execute(
                    select(Message)
                    .where(Message.group_id == msg.group_id, Message.timestamp < msg.timestamp)
                    .order_by(Message.timestamp.desc()).limit(5)
                )
                after = await db.execute(
                    select(Message)
                    .where(Message.group_id == msg.group_id, Message.timestamp > msg.timestamp)
                    .order_by(Message.timestamp.asc()).limit(5)
                )
                # Получаем имя группы
                grp = await db.execute(select(Group).where(Group.id == msg.group_id))
                group = grp.scalar_one_or_none()

                def ser(m):
                    return {
                        "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
                        "photo_path": m.photo_path,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                        "sender_name": m.sender_name,
                    }

                context = {
                    "group_name": group.name if group else None,
                    "before": [ser(m) for m in reversed(before.scalars().all())],
                    "message": ser(msg),
                    "after": [ser(m) for m in after.scalars().all()],
                }

        # Получаем данные персоны и фото
        person_data = None
        person_id = payload.get("person_id")
        if person_id:
            p_result = await db.execute(select(Person).where(Person.id == uuid.UUID(person_id)))
            person = p_result.scalar_one_or_none()
            if person:
                person_data = {"id": str(person.id), "display_name": person.display_name}

        # Получаем crop_path из Face
        face_crop_path = None
        face_id_str = payload.get("face_id")
        if face_id_str:
            face_result = await db.execute(select(Face).where(Face.id == uuid.UUID(face_id_str)))
            face_obj = face_result.scalar_one_or_none()
            if face_obj:
                face_crop_path = face_obj.crop_path

        # photo_path из совпавшего сообщения
        matched_photo_path = None
        if msg_id:
            mp_result = await db.execute(select(Message).where(Message.id == uuid.UUID(msg_id)))
            mp_msg = mp_result.scalar_one_or_none()
            if mp_msg:
                matched_photo_path = mp_msg.photo_path

        face_results.append({
            "similarity": round(match.score * 100, 1),
            "person": person_data,
            "face_id": face_id_str,
            "crop_path": face_crop_path,
            "photo_path": matched_photo_path,
            "context": context,
        })

    # Собираем финальный массив results
    final_results = []
    for i in range(len(detected_faces)):
        if i == selected_index:
            final_results.append({
                "face_index": i,
                "bbox": detected_faces[i].bbox.tolist(),
                "matches": face_results
            })
        else:
            final_results.append({
                "face_index": i,
                "bbox": detected_faces[i].bbox.tolist(),
                "matches": []
            })

    return {
        "faces_detected": len(detected_faces),
        "requires_selection": False,
        "results": final_results
    }



@router.get("/text")
async def search_by_text(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Полнотекстовый поиск по полю text сообщений."""
    # Используем ILIKE для простого FTS, в будущем — tsvector
    stmt = (
        select(Message, Group.name.label("group_name"))
        .join(Group, Message.group_id == Group.id, isouter=True)
        .where(Message.text.like(f"%{q}%"))
        .order_by(Message.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "query": q,
        "total": len(rows),
        "results": [
            {
                "id": str(msg.id),
                "group_id": str(msg.group_id),
                "group_name": gname,
                "text": msg.text,
                "has_photo": msg.has_photo,
                "photo_path": msg.photo_path,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "sender_name": msg.sender_name,
            }
            for msg, gname in rows
        ],
    }
