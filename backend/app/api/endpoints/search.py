"""
Endpoints для поиска: по фото (лицу) и по тексту.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from typing import Optional
import asyncio
import os
import uuid
import cv2
import numpy as np
import threading
import logging
import onnxruntime as ort

from app.core.database import get_db, AsyncSessionLocal
from app.models.models import Message, Face, Group, MessagePhone
from app.services.qdrant_service import ensure_collection_exists, search_similar_faces
from app.services.phone_utils import extract_phones as extract_phones_util
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
    user=Depends(get_current_user),
):
    """
    Поиск по фото:
    1. Принимает фото, обнаруживает лица
    2. Если несколько и face_index None — возвращает bounding boxes для выбора
    3. Ищет top-K похожих в Qdrant
    4. Возвращает карточки с контекстом (±5 сообщений)
    """
    import time
    t_start = time.time()

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

    t_detect = time.time()
    logger.info("TIMING detect=%.2fs faces=%d", t_detect - t_start, len(detected_faces))

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
    
    allowed_group_ids = None
    if user.role != "admin":
        g_res = await db.execute(select(Group.id).where(Group.is_public == True))
        allowed_group_ids = [str(gid) for gid in g_res.scalars().all()]
        if not allowed_group_ids:
            return {"faces_detected": len(detected_faces), "requires_selection": False, "results": []}

    similar = search_similar_faces(qdrant_client, vector, top_k=top_k, score_threshold=score_threshold, group_ids=allowed_group_ids)

    t_qdrant = time.time()
    logger.info("TIMING qdrant=%.2fs results=%d", t_qdrant - t_detect, len(similar))

    if not similar:
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

    t_db = time.time()
    logger.info("TIMING db_batch=%.2fs msgs=%d total=%.2fs", t_db - t_qdrant, len(messages_map), t_db - t_start)

    # ── Сборка лёгких результатов (без контекста — он загружается по клику) ──

    face_results = []
    for match in similar:
        payload = match.payload
        msg_id = payload.get("message_id")
        face_id_str = payload.get("face_id")

        matched_photo_path = None
        group_name = None
        if msg_id and msg_id in messages_map:
            msg = messages_map[msg_id]
            matched_photo_path = msg.photo_path
            group = groups_map.get(str(msg.group_id)) if msg.group_id else None
            group_name = group.name if group else None

        face_crop_path = None
        if face_id_str and face_id_str in faces_map:
            face_crop_path = faces_map[face_id_str].crop_path

        face_results.append({
            "similarity": round(match.score * 100, 1),
            "face_id": face_id_str,
            "crop_path": face_crop_path,
            "photo_path": matched_photo_path,
            "group_name": group_name,
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



@router.get("/face/{face_id}/context")
async def get_face_context(
    face_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Lazy-load контекста для конкретного совпавшего лица.
    Возвращает ±5 сообщений вокруг сообщения, к которому привязано лицо.
    """
    # 1) Найти Face → message_id
    face_uuid = uuid.UUID(face_id)
    face_result = await db.execute(select(Face).where(Face.id == face_uuid))
    face = face_result.scalar_one_or_none()
    if not face or not face.message_id:
        return {"context": None}

    # 2) Загрузить Message
    msg_result = await db.execute(select(Message).where(Message.id == face.message_id))
    msg = msg_result.scalar_one_or_none()
    if not msg:
        return {"context": None}

    # 3) Загрузить Group
    group = None
    if msg.group_id:
        g_result = await db.execute(select(Group).where(Group.id == msg.group_id))
        group = g_result.scalar_one_or_none()

    # 4) Загрузить контекст ±5 сообщений (индексированные запросы)
    def ser(m):
        return {
            "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    before = []
    after = []
    if msg.timestamp and msg.group_id:
        before_q = await db.execute(
            select(Message)
            .where(Message.group_id == msg.group_id, Message.timestamp <= msg.timestamp)
            .order_by(Message.timestamp.desc())
            .limit(6)
        )
        b_list = before_q.scalars().all()
        before = [m for m in b_list if str(m.id) != str(msg.id)][:5]
        before = list(reversed(before))

        after_q = await db.execute(
            select(Message)
            .where(Message.group_id == msg.group_id, Message.timestamp >= msg.timestamp)
            .order_by(Message.timestamp.asc())
            .limit(6)
        )
        a_list = after_q.scalars().all()
        after = [m for m in a_list if str(m.id) != str(msg.id)][:5]

    return {
        "context": {
            "group_name": group.name if group else None,
            "before": [ser(m) for m in before],
            "message": ser(msg),
            "after": [ser(m) for m in after],
        }
    }


@router.get("/text")
async def search_by_text(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Полнотекстовый поиск по полю text сообщений (FULLTEXT MATCH AGAINST)."""
    offset = (page - 1) * limit

    # FULLTEXT поиск — используем сырой SQL MATCH AGAINST для MariaDB
    # Экранируем запрос, убираем спецсимволы boolean mode
    safe_q = q.replace("'", "''").replace("+", "").replace("-", "").replace("*", "").replace("(", "").replace(")", "")
    
    stmt = (
        select(Message, Group.name.label("group_name"))
        .join(Group, Message.group_id == Group.id, isouter=False)
    )
    if user.role != "admin":
        stmt = stmt.where(Group.is_public == True)

    stmt_ft = stmt.where(text("MATCH(messages.text) AGAINST(:q IN BOOLEAN MODE)")).order_by(Message.timestamp.desc()).offset(offset).limit(limit)
    
    try:
        result = await db.execute(stmt_ft, {"q": safe_q})
        rows = result.all()
    except Exception:
        # Fallback на LIKE если FULLTEXT-индекс ещё не создан
        stmt_fallback = stmt.where(Message.text.like(f"%{q}%")).order_by(Message.timestamp.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt_fallback)
        rows = result.all()

    if not rows:
        return {"query": q, "total": 0, "results": []}

    def ser(m):
        return {
            "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    # ── Индекс-оптимизированная последовательная загрузка контекста ──
    async def _fetch_ctx(msg_id_str: str, msg) -> tuple:
        if not msg.timestamp or not msg.group_id:
            return msg_id_str, {"before": [], "after": []}
            
        before_q = await db.execute(
            select(Message)
            .where(
                Message.group_id == msg.group_id,
                Message.timestamp <= msg.timestamp
            )
            .order_by(Message.timestamp.desc())
            .limit(6)
        )
        b_list = before_q.scalars().all()
        
        after_q = await db.execute(
            select(Message)
            .where(
                Message.group_id == msg.group_id,
                Message.timestamp >= msg.timestamp
            )
            .order_by(Message.timestamp.asc())
            .limit(6)
        )
        a_list = after_q.scalars().all()
        
        before = [m for m in b_list if str(m.id) != str(msg.id)][:5]
        after = [m for m in a_list if str(m.id) != str(msg.id)][:5]
        
        return msg_id_str, {
            "before": list(reversed(before)),
            "after": list(after),
        }

    context_map = {}
    if rows:
        for msg, _ in rows:
            _, ctx = await _fetch_ctx(str(msg.id), msg)
            context_map[str(msg.id)] = ctx

    results_data = []
    for msg, gname in rows:
        ctx = context_map.get(str(msg.id), {"before": [], "after": []})
        context = {
            "group_name": gname,
            "before": [ser(m) for m in ctx["before"]],
            "message": ser(msg),
            "after": [ser(m) for m in ctx["after"]],
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


@router.get("/phone")
async def search_by_phone(
    q: str = Query(..., min_length=3),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Поиск по номеру телефона (нормализует ввод пользователя)."""
    import re
    # Нормализуем входной номер: оставляем только цифры
    digits = re.sub(r'\D', '', q)
    
    if not digits or len(digits) < 3:
        return {"query": q, "total": 0, "results": []}

    # Пробуем нормализовать как полный номер
    phones = extract_phones_util(q)
    if phones:
        search_phone = phones[0]
    else:
        # Используем как частичный поиск
        search_phone = digits

    offset = (page - 1) * limit

    stmt = (
        select(Message, Group.name.label("group_name"))
        .join(MessagePhone, MessagePhone.message_id == Message.id)
        .join(Group, Message.group_id == Group.id)
    )
    if user.role != "admin":
        stmt = stmt.where(Group.is_public == True)

    stmt = stmt.where(MessagePhone.phone.like(f"%{search_phone}%"))
    stmt = stmt.distinct().order_by(Message.timestamp.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return {"query": q, "normalized": search_phone, "total": 0, "results": []}

    def ser(m):
        return {
            "id": str(m.id), "text": m.text, "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    results_data = []
    for msg, gname in rows:
        # Получаем номера для этого сообщения
        phones_res = await db.execute(select(MessagePhone.phone).where(MessagePhone.message_id == msg.id))
        msg_phones = [p[0] for p in phones_res.all()]

        # Контекст: 3 до и 3 после
        context = None
        if msg.timestamp and msg.group_id:
            before_q = await db.execute(
                select(Message)
                .where(Message.group_id == msg.group_id, Message.timestamp <= msg.timestamp)
                .order_by(Message.timestamp.desc())
                .limit(4)
            )
            b_list = before_q.scalars().all()
            before = [m for m in b_list if str(m.id) != str(msg.id)][:3]
            before = list(reversed(before))

            after_q = await db.execute(
                select(Message)
                .where(Message.group_id == msg.group_id, Message.timestamp >= msg.timestamp)
                .order_by(Message.timestamp.asc())
                .limit(4)
            )
            a_list = after_q.scalars().all()
            after = [m for m in a_list if str(m.id) != str(msg.id)][:3]

            context = {
                "group_name": gname,
                "before": [ser(m) for m in before],
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
            "phones": msg_phones,
            "context": context,
        })

    return {
        "query": q,
        "normalized": search_phone,
        "total": len(rows),
        "results": results_data,
    }
