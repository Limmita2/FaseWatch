"""
Endpoints для поиска: по фото (лицу) и по тексту.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import Optional
import asyncio
import os
import uuid
import cv2
import numpy as np
import threading
import logging
import onnxruntime as ort

from app.core.database import get_db
from app.models.models import Message, Face, Group
from app.services.qdrant_service import ensure_collection_exists, search_similar_faces
from app.api.deps import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# ── ONNX threading config для backend (поиск) ──
SEARCH_ORT_THREADS = int(os.getenv("SEARCH_ORT_THREADS", "8"))

os.environ.setdefault("OMP_NUM_THREADS", str(SEARCH_ORT_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(SEARCH_ORT_THREADS))
os.environ.setdefault("OPENBLAS_NUM_THREADS", str(SEARCH_ORT_THREADS))

# ── Lazy singleton для InsightFace (поиск — меньший det_size) ──
_face_app = None
_face_app_lock = threading.Lock()


def _get_face_app():
    global _face_app
    if _face_app is None:
        with _face_app_lock:
            if _face_app is None:
                from insightface.app import FaceAnalysis

                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = SEARCH_ORT_THREADS
                sess_options.inter_op_num_threads = 2
                sess_options.execution_mode = ort.ExecutionMode.ORT_PARALLEL

                logger.info(
                    "Инициализация InsightFace для search (det_size=320, threads=%d)...",
                    SEARCH_ORT_THREADS,
                )
                app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CPUExecutionProvider"],
                )
                # Меньший det_size для поиска — лицо обычно крупное, 320 достаточно
                app.prepare(ctx_id=-1, det_size=(320, 320))

                # Применяем session options для многопоточности
                for model in app.models:
                    if hasattr(model, 'session') and model.session is not None:
                        model_path = getattr(model.session, '_model_path', None)
                        if model_path:
                            model.session = ort.InferenceSession(
                                model_path,
                                sess_options=sess_options,
                                providers=["CPUExecutionProvider"],
                            )

                _face_app = app
                logger.info("InsightFace загружен для search (ORT %s).", ort.__version__)
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
    4. Возвращает карточки с контекстом (±5 сообщений)
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
                "matches": []
            })
        return {
            "faces_detected": len(detected_faces),
            "requires_selection": True,
            "results": all_results
        }

    # ── Поиск для выбранного лица ──
    qdrant_client = ensure_collection_exists()

    selected_index = face_index if face_index is not None and face_index < len(detected_faces) else 0
    face_to_process = detected_faces[selected_index]

    vector = face_to_process.embedding.tolist()

    score_threshold = threshold / 100.0
    similar = search_similar_faces(qdrant_client, vector, top_k=top_k, score_threshold=score_threshold)

    if not similar:
        # Нет совпадений — быстрый выход
        final_results = []
        for i in range(len(detected_faces)):
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

    # ── BATCH загрузка данных (вместо N отдельных запросов) ──

    # Собираем все уникальные ID из Qdrant результатов
    msg_ids = set()
    face_ids = set()
    for match in similar:
        p = match.payload
        if p.get("message_id"):
            msg_ids.add(uuid.UUID(p["message_id"]))
        if p.get("face_id"):
            face_ids.add(uuid.UUID(p["face_id"]))

    # 1) Batch: все сообщения
    messages_map = {}
    if msg_ids:
        result = await db.execute(select(Message).where(Message.id.in_(msg_ids)))
        for m in result.scalars().all():
            messages_map[str(m.id)] = m


    # 3) Batch: все лица (crop_path)
    faces_map = {}
    if face_ids:
        result = await db.execute(select(Face).where(Face.id.in_(face_ids)))
        for f in result.scalars().all():
            faces_map[str(f.id)] = f

    # 4) Batch: все группы для контекста
    group_ids = {m.group_id for m in messages_map.values() if m.group_id}
    groups_map = {}
    if group_ids:
        result = await db.execute(select(Group).where(Group.id.in_(group_ids)))
        for g in result.scalars().all():
            groups_map[str(g.id)] = g

    # 5) Batch: контекстные сообщения (before/after) для всех матчей
    context_map = {}  # msg_id -> {"before": [...], "after": [...]}
    if messages_map:
        # Загружаем контекст для каждого матча
        for msg_id_str, msg in messages_map.items():
            if not msg.timestamp or not msg.group_id:
                context_map[msg_id_str] = {"before": [], "after": []}
                continue

            before_q, after_q = await asyncio.gather(
                db.execute(
                    select(Message)
                    .where(
                        Message.group_id == msg.group_id,
                        or_(
                            Message.timestamp < msg.timestamp,
                            and_(Message.timestamp == msg.timestamp, Message.created_at < msg.created_at)
                        )
                    )
                    .order_by(Message.timestamp.desc(), Message.created_at.desc())
                    .limit(5)
                ),
                db.execute(
                    select(Message)
                    .where(
                        Message.group_id == msg.group_id,
                        or_(
                            Message.timestamp > msg.timestamp,
                            and_(Message.timestamp == msg.timestamp, Message.created_at > msg.created_at)
                        )
                    )
                    .order_by(Message.timestamp.asc(), Message.created_at.asc())
                    .limit(5)
                ),
            )
            context_map[msg_id_str] = {
                "before": list(reversed(before_q.scalars().all())),
                "after": list(after_q.scalars().all()),
            }

    # ── Сборка результатов (без лишних SQL запросов) ──

    def ser(m):
        return {
            "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    face_results = []
    for match in similar:
        payload = match.payload
        msg_id = payload.get("message_id")
        face_id_str = payload.get("face_id")

        # Контекст из предзагруженных данных
        context = None
        matched_photo_path = None
        if msg_id and msg_id in messages_map:
            msg = messages_map[msg_id]
            matched_photo_path = msg.photo_path
            group = groups_map.get(str(msg.group_id)) if msg.group_id else None
            ctx = context_map.get(msg_id, {"before": [], "after": []})
            context = {
                "group_name": group.name if group else None,
                "before": [ser(m) for m in ctx["before"]],
                "message": ser(msg),
                "after": [ser(m) for m in ctx["after"]],
            }


        # Crop path из предзагруженных данных
        face_crop_path = None
        if face_id_str and face_id_str in faces_map:
            face_crop_path = faces_map[face_id_str].crop_path

        face_results.append({
            "similarity": round(match.score * 100, 1),
            "person": None,
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

    def ser(m):
        return {
            "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    results_data = []
    for msg, gname in rows:
        # Fetch context: 5 before, 5 after with tie-breaker
        before_q, after_q = await asyncio.gather(
            db.execute(
                select(Message)
                .where(
                    Message.group_id == msg.group_id,
                    or_(
                        Message.timestamp < msg.timestamp,
                        and_(Message.timestamp == msg.timestamp, Message.created_at < msg.created_at)
                    )
                )
                .order_by(Message.timestamp.desc(), Message.created_at.desc())
                .limit(5)
            ),
            db.execute(
                select(Message)
                .where(
                    Message.group_id == msg.group_id,
                    or_(
                        Message.timestamp > msg.timestamp,
                        and_(Message.timestamp == msg.timestamp, Message.created_at > msg.created_at)
                    )
                )
                .order_by(Message.timestamp.asc(), Message.created_at.asc())
                .limit(5)
            )
        )
        before = before_q.scalars().all()
        after = after_q.scalars().all()
        
        context = {
            "group_name": gname,
            "before": [ser(m) for m in reversed(before)],
            "message": ser(msg),
            "after": [ser(m) for m in after],
        }
        
        results_data.append({
            "id": str(msg.id),
            "group_id": str(msg.group_id),
            "group_name": gname,
            "text": msg.text,
            "has_photo": msg.has_photo,
            "photo_path": msg.photo_path,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "sender_name": msg.sender_name,
            "context": context
        })

    return {
        "query": q,
        "total": len(rows),
        "results": results_data,
    }
