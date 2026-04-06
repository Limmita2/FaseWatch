# FaseWatch (FaceWatch) — Проектный контекст

## Обзор проекта

**FaseWatch** — система мониторинга Telegram-каналов с распознаванием лиц. Бот собирает сообщения и фото из Telegram-групп, распознаёт лица через InsightFace, сохраняет векторные эмбеддинги в Qdrant, и предоставляет веб-интерфейс для поиска и управления.

### Ключевые возможности
- Сбор сообщений и фото из Telegram через aiogram бота (polling mode)
- Распознавание лиц: InsightFace (ArcFace), 512-dim эмбеддинги
- Поиск по лицу (загрузка фото → вектор → Qdrant), тексту (FULLTEXT), телефону
- Импорт бэкапов Telegram (HTML/ZIP) и локальный импорт больших архивов
- Веб-интерфейс (React + TailwindCSS) для просмотра, поиска и администрирования
- JWT-авторизация с ролями `admin` / `operator`
- Резервное копирование MariaDB + Qdrant (cron, ежедневно в 2:00)

---

## Стек технологий

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async, aiomysql), Pydantic Settings, Alembic |
| **Frontend** | React 18, Vite 5, TypeScript, TailwindCSS 4, Zustand, react-router-dom 6, axios |
| **Bot** | Python 3.11, aiogram 3.x (polling mode), httpx |
| **ML/AI** | InsightFace (buffalo_l / ArcFace), 512-dim embedding, CPU mode (ONNX Runtime) |
| **БД** | MariaDB (внешний сервер на QNAP 192.168.24.178:3306, async через aiomysql) |
| **Векторная БД** | Qdrant (коллекция `faces`, cosine similarity, 512 dim) |
| **Очередь задач** | Celery + Redis (concurrency=8, prefork) |
| **Хранилище файлов** | QNAP NAS (монтируется в `/mnt/qnap_photos`) |
| **Инфраструктура** | Docker Compose (6 контейнеров), Nginx (reverse proxy внутри frontend) |

---

## Структура проекта

```
FaseWatch/
├── .env                        # Переменные окружения (секреты, не коммитить!)
├── .env.example                # Шаблон переменных окружения
├── .gitignore
├── docker-compose.yml          # Оркестрация всех сервисов
├── facewatch.service           # Systemd unit для автозапуска
├── setup_production.sh         # Скрипт продакшн-установки
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── entrypoint.sh           # Запуск: alembic upgrade + uvicorn (4 workers)
│   ├── alembic.ini
│   ├── alembic/                # Миграции БД
│   ├── app/
│   │   ├── main.py             # FastAPI app, lifespan (InsightFace warm-up), CORS, роуты
│   │   ├── core/
│   │   │   ├── config.py       # Settings (pydantic-settings, из .env)
│   │   │   ├── database.py     # AsyncEngine (pool_size=30, max_overflow=50), AsyncSessionLocal
│   │   │   └── security.py     # bcrypt hash/verify, JWT create/decode
│   │   ├── models/models.py    # SQLAlchemy модели: Group, Message, Face, MessagePhone, User
│   │   ├── services/
│   │   │   ├── qdrant_service.py   # Qdrant CRUD (upsert, search, ensure_collection)
│   │   │   ├── phone_utils.py      # Извлечение и нормализация украинских телефонов
│   │   │   └── storage_service.py  # Сохранение фото/кропов на QNAP
│   │   ├── worker/
│   │   │   ├── celery_app.py   # Celery config (broker=Redis)
│   │   │   └── tasks.py        # Задача process_photo (InsightFace pipeline)
│   │   └── api/
│   │       ├── deps.py
│   │       └── endpoints/
│   │           ├── auth.py, messages.py, search.py, groups.py, imports.py,
│   │           ├── users.py, input.py, webhook.py, bot_receiver.py
│   ├── backfill_phones.py      # Полная пересборка message_phones
│   ├── import_local.py         # Локальный импорт больших Telegram Desktop ZIP
│   ├── delete_duplicate_photos.py
│   ├── delete_spam.py
│   ├── apply_qdrant_indexes.py
│   └── различные утилиты мониторинга (check_*.py, monitor_progress.py)
│
├── frontend/
│   ├── Dockerfile              # Multi-stage: npm build → Nginx
│   ├── nginx.conf              # Reverse proxy: /api/ → backend:8000, SPA fallback
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx, App.tsx, index.css
│       ├── store/authStore.ts      # Zustand (token, role, login/logout)
│       ├── services/api.ts         # axios instance + JWT interceptor
│       ├── components/layout/
│       └── pages/
│           ├── LoginPage, DashboardPage, MessagesPage, SearchPage,
│           ├── GroupsPage, ImportPage, InputPage, UsersPage
│
└── bot/
    ├── Dockerfile
    ├── requirements.txt        # aiogram, httpx, python-dotenv
    └── main.py                 # Бот: polling, обработка фото/текста → backend API
```

---

## Модели базы данных (MariaDB)

5 основных таблиц:

```
Group ──< Message ──< Face
            │
            └──< MessagePhone

User (отдельная таблица авторизации)
```

### Таблица Message — ключевые поля
- `id` (UUID), `group_id` (FK), `telegram_msg_id`, `sender_name`
- `text`, `has_photo`, `photo_path`, `photo_hash` (SHA-256 для дедупликации)
- `timestamp`, `imported_from`, `created_at`

### Таблица Face
- `id` (UUID), `message_id` (FK), `crop_path`, `qdrant_point_id`
- `bbox` (JSON), `confidence`, `created_at`

### Таблица MessagePhone
- `id` (UUID), `message_id` (FK), `phone` (нормализованный украинский номер)

### Таблица User
- `id` (UUID), `username`, `password` (bcrypt hash)
- `role` (admin/operator), `description`, `last_ip`, `allowed_ip` (маска с fnmatch)

### Ключевые индексы (Message)
| Индекс | Тип | Поля | Назначение |
|--------|-----|------|------------|
| `ix_messages_group_timestamp` | составной | (group_id, timestamp) | основной для контекста |
| `ix_messages_group_created` | составной | (group_id, created_at) | — |
| `ix_messages_timestamp` | одиночный | (timestamp) | — |
| `ix_messages_has_photo` | одиночный | (has_photo) | фильтр по фото |
| `ix_messages_photo_hash` | одиночный | (photo_hash) | **дедупликация фото** |
| `ft_messages_text` | FULLTEXT | (text) | текстовый поиск |

---

## Docker Compose — сервисы

6 контейнеров (БД **не в Docker** — MariaDB работает на QNAP):

| Сервис | Порт | Образ | Зависимости |
|--------|------|-------|-------------|
| `qdrant` | 6333 (localhost) | qdrant/qdrant:latest | — |
| `redis` | 6379 (internal) | redis:alpine (256mb) | — |
| `backend` | 8000 (localhost) | ./backend | qdrant, redis |
| `celery_worker` | — | ./backend | backend, redis |
| `bot` | — | ./bot | backend |
| `frontend` | **3000 → 80** | ./frontend (nginx) | backend |

**Доступ к приложению:** `http://localhost:3000`
**API документация:** `http://localhost:8000/docs`
**Дефолтный логин:** `admin` / `admin`

---

## Команды

### Основные

```bash
# Запуск всех сервисов
docker compose up --build -d

# Логи
docker compose logs -f [service_name]

# Остановка
docker compose down

# Остановка + удаление volumes
docker compose down -v

# Статус контейнеров
docker compose ps

# Пересборка backend (ВАЖНО: при изменениях кода backend всегда build, а не restart)
docker compose build backend && docker compose up -d backend

# Пересборка backend + celery после изменений в логике импорта/обработки фото
docker compose build backend celery_worker && docker compose up -d backend celery_worker

# Пересборка всех сервисов
docker compose up --build -d
```

### Локальный импорт

```bash
# Импорт большого Telegram Desktop ZIP архива
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/<archive>.zip --group "Название группы"

# Примеры:
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/1.zip --group "КОПІНФО ЛРУ"
```

### Миграции БД

```bash
# Создать миграцию
docker exec -it facewatch_backend alembic revision --autogenerate -m "description"

# Применить миграции
docker exec -it facewatch_backend alembic upgrade head
```

### Qdrant

```bash
# Обновить индексы Qdrant
docker exec -it facewatch_backend python apply_qdrant_indexes.py
```

### Frontend (локальная разработка)

```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173
npm run build # продакшн-сборка
```

### Бэкапы

```bash
# Ручной бэкап
sudo /usr/local/bin/fasewatch_backup.sh
```

---

## API маршруты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/login` | Логин (username + password → JWT) |
| GET | `/api/dashboard` | Статистика (группы, сообщения, лица, телефоны) |
| GET | `/api/messages` | Список сообщений (фильтры: группа, дата, has_photo) |
| GET | `/api/messages/{id}/context` | Контекст сообщения (±5 сообщений) |
| POST | `/api/search/face` | Поиск по фото лица (multipart, top_k, threshold) |
| GET | `/api/search/text` | Поиск по тексту (FULLTEXT) |
| GET | `/api/search/phone` | Поиск по номеру телефона |
| GET | `/api/groups` | Список Telegram-групп |
| POST | `/api/import` | Импорт бэкапа (multipart/form-data) |
| GET | `/api/users` | Список пользователей |
| POST | `/api/users` | Создание пользователя |
| DELETE | `/api/users/{id}` | Удаление пользователя |
| POST | `/api/input` | Ручной ввод фото для обработки |
| POST | `/api/bot/message` | Приём данных от Telegram бота |
| POST | `/webhook/telegram` | Webhook для Telegram (не используется) |

---

## Переменные окружения (.env)

| Переменная | Описание |
|-----------|----------|
| `MARIADB_HOST` / `MARIADB_PORT` | Адрес MariaDB (192.168.24.178:3306) |
| `MARIADB_USER` / `MARIADB_PASSWORD` / `MARIADB_DB` | Реквизиты MariaDB |
| `DATABASE_URL` | Строка подключения (mysql+aiomysql://...) |
| `QDRANT_HOST` / `QDRANT_PORT` | Адрес Qdrant (внутри docker: qdrant:6333) |
| `REDIS_URL` | Адрес Redis (redis://redis:6379/0) |
| `QNAP_MOUNT_PATH` | Путь монтирования QNAP NAS (/mnt/qnap_photos) |
| `JWT_SECRET` | Секрет для JWT токенов |
| `JWT_ALGORITHM` | Алгоритм JWT (HS256) |
| `JWT_EXPIRE_HOURS` | Время жизни токена (8 часов) |
| `FACE_SIMILARITY_THRESHOLD` | Порог похожести лиц (0.75) |
| `SEARCH_ORT_THREADS` | Потоки ONNX Runtime для поиска (8) |
| `BOT_TOKEN` | Токен Telegram бота |

---

## Бизнес-процессы

### 1. Сбор сообщений из Telegram
```
Telegram группа → Bot (aiogram, polling) → POST /api/bot/message → Backend
    → Сохраняет Message в MariaDB
    → Извлекает телефоны из текста → message_phones
    → Если фото: сохраняет на QNAP → Celery task process_photo
```

### 2. Распознавание лиц (Celery worker)
```
process_photo task:
    1. Открывает фото (cv2.imread)
    2. InsightFace.get() → обнаружение лиц, 512-dim вектор
    3. Сохраняет кроп лица (/faces/{shard}/{face_id}.jpg)
    4. upsert вектор в Qdrant (payload: face_id, message_id, group_id)
```

### 3. Поиск
```
По фото:    загрузка фото → InsightFace → вектор → Qdrant search → контекст ±5
По тексту:  FULLTEXT MATCH AGAINST (fallback: LIKE %q%)
По телефону: нормализация украинского номера → поиск в message_phones
```

### 4. Дедупликация фото
При загрузке фото вычисляется SHA-256 хеш. Если картинка уже есть в БД (`photo_hash`), дубликат отбрасывается — экономия диска QNAP, базы Qdrant и ресурсов Celery.

---

## Хранилище файлов (QNAP)

```
/mnt/qnap_photos/
├── photos/{group_id}/{YYYY-MM}/{message_id}_{timestamp}.jpg   # оригиналы
├── faces/{shard}/{face_id}.jpg                                # кропы лиц (шардированы по 2 символам UUID)
└── backups/
    ├── mariadb/fasewatch_db_YYYY-MM-DD_HH-MM-SS.sql.gz
    └── qdrant/qdrant_faces_YYYY-MM-DD_HH-MM-SS.snapshot
```

Файлы доступны через backend: `GET /files/...` (FastAPI StaticFiles).
Nginx проксирует `/files/` на backend.

---

## Авторизация

- **Механизм:** JWT Bearer token (`Authorization: Bearer <token>`)
- **Хеширование:** bcrypt
- **Хранение на фронте:** `localStorage` (token, role)
- **Стейт:** Zustand (`useAuthStore`)
- **Роли:** `admin` (полный доступ), `operator` (скрыты группы с `is_public=False`)
- **Ограничение по IP:** поле `allowed_ip` в БД (маска с `fnmatch`), `last_ip`

---

## Резервное копирование

Cron-задача (ежедневно в 2:00): `/usr/local/bin/fasewatch_backup.sh`
- **MariaDB:** `mysqldump` → `.sql.gz` на QNAP
- **Qdrant:** API snapshot → `.snapshot` на QNAP
- **Ротация:** бэкапы старше 30 дней удаляются автоматически

---

## Производительность

- InsightFace warm-up при старте сервера
- ONNX Runtime: SEARCH_ORT_THREADS=8 (поиск), ORT_INTRA_THREADS=6 (Celery)
- Connection pool: pool_size=30, max_overflow=50
- Uvicorn: 4 worker-процесса
- Контекст поиска использует индексированные запросы по `ix_messages_group_timestamp`
- Celery: concurrency=8, prefork pool

---

## Особенности миграций

`backend/entrypoint.sh` при старте пытается выполнить `alembic upgrade head`.
Если схема БД уже соответствует текущему `head`, но `alembic_version` отстаёт — entrypoint синхронизирует версию до актуального `head` для безопасного старта на существующей БД.

---

## Продакшн-настройка

### Systemd (автозапуск)
```bash
sudo systemctl enable facewatch
sudo systemctl start facewatch
```

### Cron (бэкапы)
Устанавливается через `setup_production.sh` — ежедневно в 2:00.

---

## Важные правила разработки

1. **При изменениях кода backend** — всегда `docker compose build backend && docker compose up -d backend` (не просто `restart`)
2. **При изменениях в импорте/Celery** — `docker compose build backend celery_worker && docker compose up -d backend celery_worker`
3. **`.env` файл** — содержит секреты, не коммитить! Использовать `.env.example` как шаблон
4. **Файлы `.env` и `processed_ids.txt`** — в `.gitignore`
5. **Локальная разработка фронтенда** — `cd frontend && npm run dev` (Vite dev server на 5173)
