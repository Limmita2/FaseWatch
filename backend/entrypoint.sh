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

CURRENT_REVISION=$(python - <<'PY'
import os
from pathlib import Path

from sqlalchemy import create_engine, text


db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("")
    raise SystemExit(0)

sync_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
try:
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        print(row[0] if row else "")
except Exception:
    print("")
PY
)

HEAD_REVISION=$(alembic heads | awk 'NR==1 {print $1}')

SCHEMA_AT_HEAD=$(python - <<'PY'
import os

from sqlalchemy import create_engine, text


db_url = os.environ["DATABASE_URL"]
sync_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
engine = create_engine(sync_url)
with engine.begin() as conn:
    checks = [
        conn.execute(text("SHOW COLUMNS FROM groups LIKE 'is_public'")).first() is not None,
        conn.execute(text("SHOW COLUMNS FROM users LIKE 'last_ip'")).first() is not None,
        conn.execute(text("SHOW COLUMNS FROM users LIKE 'allowed_ip'")).first() is not None,
    ]
    print("1" if all(checks) else "0")
PY
)

if [ -n "$CURRENT_REVISION" ] && [ "$CURRENT_REVISION" != "$HEAD_REVISION" ] && [ "$SCHEMA_AT_HEAD" = "1" ]; then
    echo "Схема уже соответствует head, синхронизирую alembic_version: $CURRENT_REVISION -> $HEAD_REVISION"
    CURRENT_REVISION="$CURRENT_REVISION" HEAD_REVISION="$HEAD_REVISION" python - <<'PY'
import os

from sqlalchemy import create_engine, text


db_url = os.environ["DATABASE_URL"]
sync_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
current_revision = os.environ["CURRENT_REVISION"]
head_revision = os.environ["HEAD_REVISION"]

engine = create_engine(sync_url)
with engine.begin() as conn:
    count = conn.execute(
        text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'alembic_version'")
    ).scalar() or 0
    if count:
        updated = conn.execute(
            text("UPDATE alembic_version SET version_num = :head WHERE version_num = :current"),
            {"head": head_revision, "current": current_revision},
        ).rowcount
        if not updated:
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
                {"head": head_revision},
            )
    else:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": head_revision},
        )
PY
fi

alembic upgrade head || echo "Миграции не найдены — таблицы будут созданы автоматически при старте"

echo "Запуск FaceWatch API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
