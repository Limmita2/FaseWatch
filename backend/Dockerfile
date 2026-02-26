FROM python:3.11-slim

# Системные зависимости для InsightFace (OpenCV) и psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Предварительно скачиваем веса InsightFace, чтобы избежать конфликтов (INVALID_PROTOBUF) 
# при одновременном запуске нескольких воркеров Celery
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l')"

# Копируем код приложения
COPY . .
# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Копируем entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Запуск через entrypoint (миграции + uvicorn)
CMD ["/entrypoint.sh"]
