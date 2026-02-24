#!/bin/bash
# Entrypoint для backend: запускает миграции, затем uvicorn
set -e

echo "Ожидание MariaDB..."
# Проверяем TCP-подключение к MariaDB
until python -c "
import os, socket
# Парсим хост и порт из DATABASE_URL
url = os.environ.get('DATABASE_URL', '')
# mysql+aiomysql://user:pass@host:port/db
parts = url.split('@')[-1].split('/')
host_port = parts[0].split(':')
host = host_port[0]
port = int(host_port[1]) if len(host_port) > 1 else 3306
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect((host, port))
s.close()
" 2>/dev/null; do
    echo "  MariaDB ещё не доступна, ждём..."
    sleep 2
done
echo "MariaDB доступна!"

echo "Применяю миграции Alembic..."
cd /app
alembic upgrade head 2>/dev/null || echo "Миграции не найдены — таблицы будут созданы автоматически при старте"

echo "Запуск FaceWatch API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
