from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "facewatch",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # Ограничение на количество задач на воркера (предотвращает утечки)
    worker_max_tasks_per_child=100,
    worker_prefetch_multiplier=4,
    # Оптимизация Redis для высокой нагрузки
    broker_pool_limit=100,
    broker_connection_max_retries=10,
    broker_connection_retry_on_startup=True,
    # Таймауты задач
    task_soft_time_limit=120,
    task_time_limit=180,
    # Аcks — только после завершения
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)
