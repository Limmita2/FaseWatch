"""
Celery worker: обработка фото через InsightFace.
Задача:
1. Открывает фото с QNAP
2. Обнаруживает лица (InsightFace/ArcFace)
3. Для каждого лица: генерирует вектор 512-dim
4. Сохраняет кроп лица на QNAP
5. Ищет похожих в Qdrant (threshold > 0.75)
6. Создаёт или обновляет запись Person
7. Добавляет в очередь идентификации если нужно
"""
import uuid
import logging
import threading
from app.worker.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Lazy singleton для InsightFace (один раз на воркер-процесс) ──
_face_app = None
_face_app_lock = threading.Lock()


def _get_face_app():
    """Возвращает кэшированный FaceAnalysis (потокобезопасно)."""
    global _face_app
    if _face_app is None:
        with _face_app_lock:
            if _face_app is None:
                from insightface.app import FaceAnalysis
                logger.info("Инициализация InsightFace модели buffalo_l...")
                app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=-1, det_size=(640, 640))
                _face_app = app
                logger.info("InsightFace модель загружена.")
    return _face_app


# ── Lazy DB engine (один раз на воркер-процесс) ──
_engine = None
_SessionLocal = None


def _get_session():
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        sync_db_url = settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql")
        _engine = create_engine(sync_db_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


@celery_app.task(name="process_photo", bind=True, max_retries=5)
def process_photo(self, message_id: str, photo_path: str, group_id: str, timestamp_str: str):
    """
    Основная задача Celery: распознавание лиц на фото.
    """
    session = None
    try:
        import cv2

        from app.models.models import Face, Person, IdentificationQueue, IdentificationStatus, Message
        from app.services.qdrant_service import ensure_collection_exists, upsert_face_vector, search_similar_faces
        from app.services.storage_service import save_face_crop_to_qnap

        # Celery передаёт все параметры как строки (JSON) — конвертируем в UUID
        message_id_uuid = uuid.UUID(message_id) if isinstance(message_id, str) else message_id

        session = _get_session()

        # Читаем изображение
        img = cv2.imread(photo_path)
        if img is None:
            logger.error("Не удалось открыть изображение: %s", photo_path)
            return {"error": "Cannot open image", "photo_path": photo_path}

        # Детекция лиц (кэшированная модель)
        face_app = _get_face_app()
        detected_faces = face_app.get(img)

        # Qdrant клиент
        qdrant_client = ensure_collection_exists()

        message = session.query(Message).filter_by(id=message_id_uuid).first()
        if not message:
            session.close()
            return {"error": "Message not found", "message_id": message_id}

        results = []
        for face_data in detected_faces:
            vector = face_data.embedding.tolist()
            bbox = face_data.bbox.tolist()
            confidence = float(face_data.det_score)

            # Поиск похожих лиц в Qdrant
            similar = search_similar_faces(qdrant_client, vector, top_k=1, score_threshold=0.0)

            person_id_uuid = None  # UUID объект для БД
            person_id_str = None   # строка для payload Qdrant

            if similar and similar[0].score >= settings.FACE_SIMILARITY_THRESHOLD:
                # Автоматически привязываем к совпавшему лицу
                matched_person_id_str = similar[0].payload.get("person_id")
                matched_person_id_uuid = uuid.UUID(matched_person_id_str) if matched_person_id_str else None

                # Создаём Face запись сразу с person_id
                face = Face(
                    id=uuid.uuid4(),
                    person_id=matched_person_id_uuid,
                    message_id=message.id,
                    bbox=bbox,
                    confidence=confidence,
                )
                session.add(face)
                session.flush()

                person_id_str = matched_person_id_str
                person_id_uuid = matched_person_id_uuid
            else:
                # Новая персона
                new_person_id = uuid.uuid4()
                person = Person(id=new_person_id)
                session.add(person)
                session.flush()
                person_id_uuid = new_person_id
                person_id_str = str(new_person_id)

                face = Face(
                    id=uuid.uuid4(),
                    person_id=person_id_uuid,  # UUID объект
                    message_id=message.id,
                    bbox=bbox,
                    confidence=confidence,
                )
                session.add(face)
                session.flush()

            # Сохраняем кроп лица на QNAP
            try:
                x1, y1, x2, y2 = [int(c) for c in bbox]
                crop = img[y1:y2, x1:x2]
                if crop.size > 0:
                    crop_path = save_face_crop_to_qnap(crop, person_id_str, str(face.id))
                    face.crop_path = crop_path
            except Exception as crop_err:
                logger.warning("Не удалось сохранить кроп: %s", crop_err)

            # Сохраняем вектор в Qdrant
            point_id = upsert_face_vector(
                qdrant_client,
                face_id=str(face.id),
                vector=vector,
                payload={
                    "face_id": str(face.id),
                    "person_id": person_id_str,
                    "message_id": message_id,
                    "group_id": group_id,
                    "timestamp": timestamp_str,
                },
            )
            face.qdrant_point_id = uuid.UUID(point_id)
            results.append({"face_id": str(face.id), "person_id": person_id_str, "score": confidence})

        session.commit()
        logger.info("Обработано %d лиц для message_id=%s", len(results), message_id)

        return {"message_id": message_id, "faces_processed": len(results), "faces": results}

    except Exception as e:
        logger.error("Ошибка обработки фото %s: %s", photo_path, e, exc_info=True)
        raise self.retry(exc=e, countdown=15)
    finally:
        if session:
            session.close()
