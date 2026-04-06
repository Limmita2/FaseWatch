# FaceWatch — Обзор проекта

Система мониторинга Telegram-каналов с распознаванием лиц. Бот собирает сообщения и фото из Telegram-групп, распознаёт лица через InsightFace, сохраняет векторные эмбеддинги в Qdrant, и предоставляет веб-интерфейс для поиска и управления.

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

## Структура проекта

```
FaseWatch/
├── .env                        # Переменные окружения (секреты, не коммитить!)
├── docker-compose.yml          # Оркестрация всех сервисов
├── facewatch.service           # Systemd unit для автозапуска
├── setup_production.sh         # Скрипт продакшн-установки
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── entrypoint.sh           # Запуск: alembic upgrade + uvicorn (4 workers)
│   ├── alembic.ini             # Конфигурация миграций
│   ├── alembic/                # Миграции БД
│   └── app/
│       ├── main.py             # FastAPI app, lifespan (InsightFace warm-up), CORS, роуты
│       ├── core/
│       │   ├── config.py       # Settings (pydantic-settings, из .env)
│       │   ├── database.py     # AsyncEngine (pool_size=30, max_overflow=50), AsyncSessionLocal
│       │   └── security.py     # bcrypt hash/verify, JWT create/decode
│       ├── models/
│       │   └── models.py       # SQLAlchemy модели: Group, Message, Face, MessagePhone, User
│       ├── services/
│       │   ├── qdrant_service.py   # Qdrant CRUD (upsert, search, ensure_collection)
│       │   ├── phone_utils.py      # Извлечение и нормализация украинских телефонов
│       │   └── storage_service.py  # Сохранение фото/кропов на QNAP
│       ├── worker/
│       │   ├── celery_app.py   # Celery config (broker=Redis)
│       │   └── tasks.py        # Задача process_photo (InsightFace pipeline)
│       └── api/
│           ├── deps.py         # Зависимости (get_current_user, get_db)
│           └── endpoints/
│               ├── auth.py         # POST /api/auth/login
│               ├── messages.py     # GET /api/messages, GET /api/messages/{id}/context
│               ├── search.py       # POST /api/search/face, GET /api/search/text, GET /api/search/phone
│               ├── groups.py       # GET /api/groups
│               ├── imports.py      # POST /api/import (загрузка бэкапов)
│               ├── users.py        # GET/POST/DELETE /api/users
│               ├── input.py        # POST /api/input (ручной ввод фото)
│               ├── webhook.py      # POST /webhook/telegram
│               └── bot_receiver.py # POST /api/bot/message (от бота)
│   ├── backfill_phones.py      # Полная пересборка message_phones по актуальному паттерну
│   ├── import_local.py         # Локальный импорт сообщений/фото в систему
│   ├── delete_duplicate_photos.py # Глобальная очистка дубликатов (SQL, Qdrant, QNAP)
│   └── delete_spam.py          # Удаление спама по заданным критериям
│
├── frontend/
│   ├── Dockerfile              # Multi-stage: npm build → Nginx
│   ├── nginx.conf              # Reverse proxy: /api/ → backend:8000, SPA fallback
│   ├── package.json
│   └── src/
│       ├── main.tsx            # Точка входа React
│       ├── App.tsx             # Роутинг (BrowserRouter), ProtectedRoute
│       ├── index.css           # Глобальные стили (TailwindCSS)
│       ├── store/
│       │   └── authStore.ts    # Zustand store (token, role, login/logout)
│       ├── services/
│       │   └── api.ts          # axios instance, JWT interceptor, API-методы
│       ├── components/
│       │   └── layout/         # AppLayout (sidebar + content)
│       └── pages/
│           ├── LoginPage.tsx       # /login — форма авторизации
│           ├── DashboardPage.tsx   # / — статистика, последние сообщения, счётчики телефонов
│           ├── MessagesPage.tsx    # /messages — все сообщения с фильтрами
│           ├── SearchPage.tsx      # /search — поиск по фото (лицу), тексту и номеру
│           ├── GroupsPage.tsx      # /groups — Telegram-группы
│           ├── ImportPage.tsx      # /import — загрузка бэкапов Telegram
│           ├── InputPage.tsx       # /input — ручной ввод фото для обработки
│           └── UsersPage.tsx       # /users — управление пользователями
│
└── bot/
    ├── Dockerfile
    ├── requirements.txt        # aiogram, httpx, python-dotenv
    └── main.py                 # Бот: polling, обработка фото/текста → backend API
```

## Модели базы данных (MariaDB)

5 основных таблиц (Person и IdentificationQueue удалены):

```
┌──────────┐     ┌──────────────┐     ┌─────────┐
│  Group   │────<│   Message    │────<│  Face   │
│          │     │              │     │         │
│ id (UUID)│     │ id (UUID)    │     │ id (UUID)│
│ telegram_│     │ group_id (FK)│     │ message_id (FK)│
│ name     │     │ telegram_msg │     │ crop_path      │
│ bot_activ│     │ sender_name  │     │ qdrant_point_id│
│ is_public│     │ text         │     │ bbox (JSON)    │
│ created  │     │ has_photo    │     │ confidence     │
│          │     │ photo_path   │     │ created_at     │
│          │     │ photo_hash   │     └─────────┘
│          │     │ timestamp    │
│          │     │ imported_from│     ┌──────────────┐
│          │     │ created_at   │     │ MessagePhone │
│          │     └──────────────┘     │              │
└──────────┘                          │ id (UUID)    │
                                      │ message_id   │
                                      │ phone        │
                                      └──────────────┘

                                      ┌─────────┐
                                      │  User   │
                                      │         │
                                      │ id (UUID)│
                                      │ username │
                                      │ password │
                                      │ role     │
                                      │ descript │
                                      │ last_ip  │
                                      │ allowed_ip
```

### Ключевые индексы (Message)
- `ix_messages_group_timestamp` — составной (group_id, timestamp) — основной для контекста
- `ix_messages_group_created` — составной (group_id, created_at)
- `ix_messages_timestamp` — одиночный (timestamp)
- `ix_messages_has_photo` — одиночный (has_photo)
- `ix_messages_photo_hash` — одиночный (photo_hash) — используется для быстрого поиска дубликатов загружаемых картинок
- `ft_messages_text` — FULLTEXT (text) — для текстового поиска

### Ключевые индексы (MessagePhone)
- `ix_message_phones_phone` — поиск по нормализованному телефону
- `ix_message_phones_message_id` — связь телефон → сообщение

## Основные бизнес-процессы

### 1. Сбор сообщений из Telegram
```
Telegram группа → Bot (aiogram, polling) → POST /api/bot/message → Backend
    → Сохраняет Message в MariaDB
    → Извлекает телефоны из текста и сохраняет в message_phones
    → Если фото: сохраняет файл на QNAP, запускает Celery task process_photo
```

### 2. Распознавание лиц (Celery worker)
```
process_photo task:
    1. Открывает фото с QNAP (cv2.imread)
    2. InsightFace.get() → обнаружение лиц, генерация 512-dim вектора
    3. Сохраняет кроп лица на QNAP (/faces/{shard}/{face_id}.jpg)
    4. upsert вектор в Qdrant (payload: face_id, message_id, group_id)
```

### 3. Поиск
```
По фото: загрузка фото → InsightFace → вектор → Qdrant search → контекст ±5 сообщений
По тексту: FULLTEXT MATCH AGAINST в MariaDB (fallback: LIKE %q%)
По телефону: нормализация украинского номера → поиск в `message_phones` → выдача связанных сообщений
```

### 4. Дедупликация (Строгая)
```
Загрузка фото → SHA-256 хэш → Поиск по photo_hash в БД
    → Если найден: Игнорировать всё сообщение (сохраняет диск и CPU)
    → Если не найден: Обычный процесс сохранения
```

### 5. Импорт
```
Загрузка HTML/ZIP экспорта Telegram → парсинг → создание Message/Group → фото → Celery
```

### 6. Локальный импорт больших архивов
```bash
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/<archive>.zip --group "<group_name>"
```

- `import_local.py` можно использовать как и раньше для локальной дозагрузки групп из Telegram Desktop ZIP
- задачи `process_photo` теперь отправляются в Celery только после `db.commit()`, поэтому старая гонка `Message not found` при локальном импорте закрыта
- повторный запуск одного и того же архива безопасен по `telegram_message_id`: уже импортированные сообщения пропускаются
- если в проект вносились изменения в `backend/import_local.py` или `backend/app/worker/tasks.py`, перед следующим импортом нужно пересобрать и перезапустить `backend` и `celery_worker`

## API маршруты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/login` | Логин (username + password → JWT) |
| GET | `/api/dashboard` | Статистика (группы, сообщения, лица, телефоны, уникальные телефоны) |
| GET | `/api/messages` | Список сообщений (фильтры: группа, дата, has_photo) |
| GET | `/api/messages/{id}/context` | Контекст сообщения |
| POST | `/api/search/face` | Поиск по фото лица (multipart, top_k, threshold) |
| GET | `/api/search/text` | Поиск по тексту сообщений (FULLTEXT) |
| GET | `/api/search/phone` | Поиск по номеру телефона |
| GET | `/api/groups` | Список Telegram-групп |
| POST | `/api/import` | Импорт бэкапа (multipart/form-data) |
| GET | `/api/users` | Список пользователей |
| POST | `/api/users` | Создание пользователя |
| DELETE | `/api/users/{id}` | Удаление пользователя |
| POST | `/api/input` | Ручной ввод фото для обработки |
| POST | `/api/bot/message` | Приём данных от Telegram бота (и сторонних серверов, авто-создание групп) |
| POST | `/webhook/telegram` | Webhook для Telegram (не используется, бот в polling) |

## Docker Compose — сервисы

6 контейнеров (БД **не в Docker** — MariaDB работает на QNAP):

| Контейнер | Порт | Образ | Зависимости |
|-----------|------|-------|-------------|
| `facewatch_qdrant` | 6333 (localhost) | qdrant/qdrant:latest | — |
| `facewatch_redis` | 6379 (internal) | redis:alpine (256mb) | — |
| `facewatch_backend` | 8000 (localhost) | ./backend | qdrant, redis |
| `facewatch_celery` | — | ./backend | backend, redis |
| `facewatch_bot` | — | ./bot | backend |
| `facewatch_frontend` | **3000 → 80** | ./frontend (nginx) | backend |

**Доступ к приложению:** `http://localhost:3000`
**Дефолтный логин:** `admin` / `admin` (создаётся автоматически при первом запуске)

## Переменные окружения (.env)

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен Telegram бота |
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

## Авторизация

- **Механизм:** JWT Bearer token (в header `Authorization: Bearer <token>`)
- **Хеширование:** bcrypt
- **Хранение на фронте:** `localStorage` (token, role)
- **Стейт:** Zustand (`useAuthStore`)
- **Роли:** `admin` (полный доступ), `operator` (скрыты группы с `is_public=False`)
- **Истечение:** настраивается через `JWT_EXPIRE_HOURS`
- **Ограничение по IP:** В БД хранится `allowed_ip` (маска) и `last_ip`. Логин через API валидирует IP-адрес клиента с использованием `fnmatch` (звездочки).

## Хранилище файлов (QNAP)

```
/mnt/qnap_photos/
├── photos/{group_id}/{YYYY-MM}/{message_id}_{timestamp}.jpg   # оригиналы
├── faces/{shard}/{face_id}.jpg                                # кропы лиц (шардированы по 2 символам UUID)
├── backups/
│   ├── mariadb/fasewatch_db_YYYY-MM-DD_HH-MM-SS.sql.gz       # бэкапы MariaDB
│   └── qdrant/qdrant_faces_YYYY-MM-DD_HH-MM-SS.snapshot       # бэкапы Qdrant
```

Файлы доступны через backend: `GET /files/...` (FastAPI StaticFiles mount).
Nginx проксирует `/files/` на backend.

## Резервное копирование

Cron-задача (ежедневно в 2:00): `/usr/local/bin/fasewatch_backup.sh`
- **MariaDB:** `mysqldump` → `.sql.gz` на QNAP
- **Qdrant:** API snapshot → скачивание `.snapshot` на QNAP
- **Ротация:** бэкапы старше 30 дней удаляются автоматически

## Производительность (оптимизации)

- **Строгая дедупликация фото:** при загрузке фото вычисляется его `SHA-256` хеш. Если картинка (даже с другим текстом) уже есть в БД (`photo_hash`), весь входящий спам-дубликат (и новый текст, и фото) моментально отбрасывается, предотвращая засорение диска QNAP и базы Qdrant, а также спасая ресурсы Celery от холостых прогонов InsightFace.
- **InsightFace warm-up** при старте сервера (не при первом запросе)
- **ONNX Runtime** с настраиваемыми потоками (SEARCH_ORT_THREADS=8, Celery: ORT=6)
- **Контекст поиска** использует индексированные последовательные запросы по `ix_messages_group_timestamp` (без filesort)
- **Телефонный поиск** использует нормализованные номера и отдельные индексы в `message_phones`
- **Connection pool:** pool_size=30, max_overflow=50
- **Uvicorn:** 4 worker-процесса

## Особенности миграций

- `backend/entrypoint.sh` при старте пытается выполнить `alembic upgrade head`
- если схема БД уже соответствует текущему `head`, но `alembic_version` отстаёт или содержит старую ревизию, entrypoint синхронизирует `alembic_version` до актуального `head`
- это сделано для безопасного старта на существующей боевой БД, где часть изменений была внесена раньше вручную или через старые миграции

## Команды

```bash
# Запуск всех сервисов
docker compose up --build -d

# Логи
docker compose logs -f [service_name]

# Остановка
docker compose down

# Остановка + удаление данных
docker compose down -v

# Статус контейнеров
docker compose ps

# Пересборка одного сервиса
docker compose build backend && docker compose up -d backend

# Пересборка backend и celery после изменений в логике импорта/обработки фото
docker compose build backend celery_worker && docker compose up -d backend celery_worker

# Локальный импорт большого Telegram Desktop ZIP
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/my_export.zip --group "Название группы"

# Глобальная очистка дубликатов (SQL, Qdrant, QNAP)
docker compose exec backend python delete_duplicate_photos.py

# Миграции БД (внутри контейнера backend)
docker exec -it facewatch_backend alembic revision --autogenerate -m "description"
docker exec -it facewatch_backend alembic upgrade head

# Обновление индексов Qdrant
docker exec -it facewatch_backend python apply_qdrant_indexes.py

# Локальная разработка фронтенда
cd frontend && npm install && npm run dev  # → http://localhost:5173

# Ручной бэкап
sudo /usr/local/bin/fasewatch_backup.sh
```
