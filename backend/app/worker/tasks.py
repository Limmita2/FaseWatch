import uuid
import os
import logging
import threading
import onnxruntime as ort

from app.worker.celery_app import celery_app
from app.core.config import settings
from celery.exceptions import Retry

logger = logging.getLogger(__name__)

# ── Конфигурация потоков ONNX Runtime ──
# 48 ядер / 8 Celery workers = 6 потоков на воркер
ORT_THREADS = int(os.getenv("ORT_INTRA_THREADS", "6"))
ORT_INTER_THREADS = int(os.getenv("ORT_INTER_THREADS", "2"))

# Ограничиваем потоки на уровне numpy/OpenBLAS/MKL
os.environ.setdefault("OMP_NUM_THREADS", str(ORT_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(ORT_THREADS))
os.environ.setdefault("OPENBLAS_NUM_THREADS", str(ORT_THREADS))
os.environ.setdefault("NUMEXPR_NUM_THREADS", str(ORT_THREADS))

# ── Lazy singleton для InsightFace (по одному инстансу на det_size) ──
_face_apps = {}
_face_app_lock = threading.Lock()


def _expand_face_bbox(bbox: list[float], image_width: int, image_height: int, padding_ratio: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    face_width = max(1.0, x2 - x1)
    face_height = max(1.0, y2 - y1)
    pad_x = face_width * padding_ratio
    pad_y = face_height * padding_ratio

    expanded_x1 = max(0, int(x1 - pad_x))
    expanded_y1 = max(0, int(y1 - pad_y))
    expanded_x2 = min(image_width, int(x2 + pad_x))
    expanded_y2 = min(image_height, int(y2 + pad_y))

    return expanded_x1, expanded_y1, expanded_x2, expanded_y2


def _get_face_app(det_size: tuple[int, int]):
    """Возвращает кэшированный FaceAnalysis для конкретного det_size."""
    global _face_apps
    if det_size not in _face_apps:
        with _face_app_lock:
            if det_size not in _face_apps:
                from insightface.app import FaceAnalysis

                # Настраиваем ONNX session options для многопоточности
                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = ORT_THREADS
                sess_options.inter_op_num_threads = ORT_INTER_THREADS
                sess_options.execution_mode = ort.ExecutionMode.ORT_PARALLEL

                logger.info(
                    "Инициализация InsightFace (det_size=%s, ORT threads: intra=%d, inter=%d)...",
                    det_size, ORT_THREADS, ORT_INTER_THREADS,
                )
                app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CPUExecutionProvider"],
                    provider_options=[{}],
                )
                # Применяем session options ко всем моделям InsightFace
                app.prepare(ctx_id=-1, det_size=det_size)
                for model in app.models:
                    if hasattr(model, 'session') and model.session is not None:
                        # Пересоздаём сессию с нашими настройками потоков
                        model_path = model.session._model_path if hasattr(model.session, '_model_path') else None
                        if model_path:
                            model.session = ort.InferenceSession(
                                model_path,
                                sess_options=sess_options,
                                providers=["CPUExecutionProvider"],
                            )

                _face_apps[det_size] = app
                logger.info("InsightFace модель загружена для det_size=%s (ORT %s).", det_size, ort.__version__)
    return _face_apps[det_size]


def _detect_faces_adaptive(img):
    for det_size in ((320, 320), (160, 160), (640, 640)):
        faces = _get_face_app(det_size).get(img)
        if faces:
            return faces, det_size
    return [], None


# ── Lazy DB engine (один раз на воркер-процесс) ──
_engine = None
_SessionLocal = None


def _get_session():
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        sync_db_url = settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql")
        _engine = create_engine(sync_db_url, pool_pre_ping=True, pool_size=20, max_overflow=30)
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

        from app.models.models import Face, Message
        from app.services.qdrant_service import ensure_collection_exists, upsert_face_vector
        from app.services.storage_service import save_face_crop_to_qnap

        # Celery передаёт все параметры как строки (JSON) — конвертируем в UUID
        message_id_uuid = uuid.UUID(message_id) if isinstance(message_id, str) else message_id

        session = _get_session()

        # Читаем изображение
        img = cv2.imread(photo_path)
        if img is None:
            logger.error("Не удалось открыть изображение: %s", photo_path)
            return {"error": "Cannot open image", "photo_path": photo_path}
        image_height, image_width = img.shape[:2]

        # Детекция лиц (кэшированная модель)
        detected_faces, used_det_size = _detect_faces_adaptive(img)
        if detected_faces:
            logger.info(
                "Найдено %d лиц для изображения %sx%s с det_size=%s",
                len(detected_faces), image_width, image_height, used_det_size,
            )
        else:
            logger.warning(
                "Лица не найдены для изображения %sx%s, photo_path=%s",
                image_width, image_height, photo_path,
            )

        # Qdrant клиент
        qdrant_client = ensure_collection_exists()

        message = session.query(Message).filter_by(id=message_id_uuid).first()
        if not message:
            raise self.retry(
                exc=ValueError(f"Message not found yet: {message_id}"),
                countdown=5,
            )

        results = []
        for face_data in detected_faces:
            vector = face_data.embedding.tolist()
            bbox = face_data.bbox.tolist()
            confidence = float(face_data.det_score)

            # Создаём Face запись
            face = Face(
                id=uuid.uuid4(),
                message_id=message.id,
                bbox=bbox,
                confidence=confidence,
            )
            session.add(face)
            session.flush()

            # Сохраняем кроп лица на QNAP
            try:
                x1, y1, x2, y2 = _expand_face_bbox(
                    bbox,
                    image_width=image_width,
                    image_height=image_height,
                    padding_ratio=settings.FACE_CROP_PADDING,
                )
                crop = img[y1:y2, x1:x2]
                if crop.size > 0:
                    crop_path = save_face_crop_to_qnap(crop, str(face.id))
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
                    "message_id": message_id,
                    "group_id": group_id,
                    "timestamp": timestamp_str,
                },
            )
            face.qdrant_point_id = uuid.UUID(point_id)
            results.append({"face_id": str(face.id), "score": confidence})

        session.commit()
        logger.info("Обработано %d лиц для message_id=%s", len(results), message_id)

        return {"message_id": message_id, "faces_processed": len(results), "faces": results}

    except Retry:
        raise
    except Exception as e:
        logger.error("Ошибка обработки фото %s: %s", photo_path, e, exc_info=True)
        raise self.retry(exc=e, countdown=15)
    finally:
        if session:
            session.close()
