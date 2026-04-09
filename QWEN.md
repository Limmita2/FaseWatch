# FaceWatch (FaceWatch) — Проектный контекст

## Обзор проекта

**FaseWatch** — система мониторинга мессенджеров (Telegram, Signal, WhatsApp) с распознаванием лиц. Боты и Telethon-аккаунты собирают сообщения и фото из групп, распознают лица через InsightFace, сохраняют векторные эмбеддинги в Qdrant, и предоставляют веб-интерфейс для поиска и управления. Встроенный AI-модуль (Ollama) генерирует аналитические отчёты и брифинги.

### Ключевые возможности
- Сбор сообщений и фото из Telegram, Signal, WhatsApp
- Распознавание лиц: InsightFace (buffalo_l / ArcFace), 512-dim эмбеддинги
- Поиск по лицу (загрузка фото → вектор → Qdrant), тексту (FULLTEXT), телефону
- AI-модуль: чат с контекстом, ежедневные брифинги, отчёты по делам/персонам (Ollama, gemma4)
- Импорт бэкапов Telegram (HTML/ZIP) и локальный импорт больших архивов
- Веб-интерфейс (React + TailwindCSS) для просмотра, поиска и администрирования
- JWT-авторизация с ролями `admin` / `operator`
- Мультиплатформенность: Telegram (бот + Telethon), Signal (signal-cli-rest-api), WhatsApp (whatsapp-web.js)

---

## Стек технологий

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async, aiomysql), Pydantic Settings, Alembic |
| **Frontend** | React 18, Vite 5, TypeScript, TailwindCSS 4, Zustand, react-router-dom 6, axios, react-markdown |
| **Telegram Bot** | Python 3.11, aiogram 3.x (polling mode), httpx |
| **Telethon** | Telethon — MTProto API для сбора из личных чатов и закрытых групп |
| **Signal Bot** | Python, signal-cli-rest-api (WebSocket), websockets, httpx |
| **WhatsApp Bot** | Node.js, whatsapp-web.js |
| **ML/AI** | InsightFace (buffalo_l / ArcFace), 512-dim embedding, CPU mode (ONNX Runtime); Ollama (gemma4:e4b) |
| **БД** | MariaDB (внешний сервер на QNAP 192.168.24.178:3306, async через aiomysql) |
| **Векторная БД** | Qdrant (коллекция `faces`, cosine similarity, 512 dim) |
| **Очередь задач** | Celery + Redis (concurrency=8, prefork) |
| **Хранилище файлов** | QNAP NAS (монтируется в `/mnt/qnap_photos`) |
| **Инфраструктура** | Docker Compose (9+ контейнеров), Nginx (reverse proxy внутри frontend) |

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
│   │   ├── models/models.py    # SQLAlchemy модели (см. ниже)
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
│   │           ├── users.py, input.py, webhook.py, bot_receiver.py,
│   │           ├── tg_accounts.py, ai.py, platforms.py
│   ├── backfill_phones.py      # Полная пересборка message_phones
│   ├── import_local.py         # Локальный импорт больших Telegram Desktop ZIP
│   ├── delete_duplicate_photos.py  # Глобальная очистка дубликатов (SQL, Qdrant, QNAP)
│   ├── delete_spam.py          # Удаление спама по заданным критериям
│   ├── apply_qdrant_indexes.py # Обновление индексов Qdrant
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
│           ├── GroupsPage, ImportPage, InputPage, UsersPage,
│           ├── TgAccountsPage, AiPage, ReportsPage, WaAccountsPage, SignalPage
│
├── bot/
│   ├── Dockerfile
│   ├── requirements.txt        # aiogram, httpx, python-dotenv
│   └── main.py                 # Бот: polling, обработка фото/текста → backend API
│
├── signal_bot/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py                 # Signal: WebSocket listener, обработка фото/текста → backend
│
├── whatsapp_bot/
│   ├── Dockerfile
│   ├── package.json
│   └── index.js                # WhatsApp: QR-авторизация, пересылка сообщений → backend
│
└── telethon_manager/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                 # Telethon-сборщик: авторизация по аккаунтам, мониторинг групп
    ├── account_worker.py       # Worker для работы с аккаунтами
    ├── history_loader.py       # Загрузка истории сообщений
    └── document_parser.py      # Парсинг PDF/DOCX документов
```

---

## Модели базы данных (MariaDB)

Основные таблицы:

```
TelegramAccount ──< TelegramAccountGroup >── Group ──< Message ──< Face
                                                         │
                                                         ├──< MessagePhone
                                                         │
PlatformState ───────────────────────────────────────────┤
PlatformGroupLink ───────────────────────────────────────┤
                                                         │
User ──< AiChat ──< AiMessage                            │
  │                                                      │
  └──< AiReport ─────────────────────────────────────────┘
```

### TelegramAccount
- `id` (UUID), `name`, `region`, `phone`, `api_id`, `api_hash`, `session_string`
- `is_active`, `status` (pending_auth/active/error/disabled), `last_error`

### TelegramAccountGroup (связка аккаунт ↔ группа)
- `id` (UUID), `account_id` (FK), `group_id` (FK)
- `history_loaded`, `history_load_progress`, `last_message_id`, `is_active`

### PlatformState / PlatformGroupLink
- Состояние и связи для мультиплатформенного сбора (Signal, WhatsApp, и др.)
- `platform`, `account_identifier`, `status`, `last_error`, `meta` (JSON)
- `external_id`, `history_load_progress`, `last_cursor`

### Group
- `id` (UUID), `telegram_id`, `source_platform`, `external_id`, `name`, `bot_active`
- `is_approved`, `is_public` (операторы видят только публичные), `created_at`

### Message — ключевые поля
- `id` (UUID), `group_id` (FK), `telegram_message_id`, `sender_telegram_id`
- `external_message_id`, `sender_external_id`, `sender_name`
- `text`, `has_photo`, `photo_path`, `photo_hash` (SHA-256 для дедупликации)
- `timestamp`, `imported_from_backup`, `created_at`
- `source_platform` (telegram/signal/whatsapp), `source_type` (bot/account/import/history)
- `document_text`, `document_name` (текст и имя из PDF/DOCX)

### Face
- `id` (UUID), `message_id` (FK), `crop_path`, `qdrant_point_id`
- `bbox` (JSON), `confidence`, `created_at`

### MessagePhone
- `id` (UUID), `message_id` (FK), `phone` (нормализованный украинский номер)

### User
- `id` (UUID), `username`, `password` (bcrypt hash)
- `role` (admin/operator), `description`, `last_ip`, `allowed_ip` (маска с fnmatch)

### AiChat / AiMessage / AiReport
- AI-чаты с контекстом (general/group/daily/case/person), streaming-ответы через SSE
- Сохранённые отчёты с экспортом в PDF

### Ключевые индексы (Message)
| Индекс | Тип | Поля | Назначение |
|--------|-----|------|------------|
| `ix_messages_group_timestamp` | составной | (group_id, timestamp) | основной для контекста |
| `ix_messages_group_created` | составной | (group_id, created_at) | — |
| `ix_messages_timestamp` | одиночный | (timestamp) | — |
| `ix_messages_has_photo` | одиночный | (has_photo) | фильтр по фото |
| `ix_messages_photo_hash` | одиночный | (photo_hash) | **дедупликация фото** |
| `ix_messages_source_platform` | одиночный | (source_platform) | фильтр по платформе |
| `ix_messages_source_account` | одиночный | (source_account_id) | фильтр по источнику |

---

## Docker Compose — сервисы

Контейнеры (БД **не в Docker** — MariaDB работает на QNAP):

| Сервис | Порт | Образ | Зависимости |
|--------|------|-------|-------------|
| `qdrant` | 6333 (localhost) | qdrant/qdrant:latest | — |
| `redis` | 6379 (internal) | redis:alpine (256mb) | — |
| ~~`ollama`~~ | ~~11434~~ | ~~ollama/ollama:latest~~ | **отключён** (закомментирован) |
| `backend` | 8000 (localhost) | ./backend | qdrant, redis |
| `celery_worker` | — | ./backend | backend, redis |
| `bot` | — | ./bot | backend |
| `facewatch_signal` | — | bbernhard/signal-cli-rest-api | — |
| `signal_bot` | — | ./signal_bot | backend, facewatch_signal |
| `facewatch_whatsapp` | — | ./whatsapp_bot | backend |
| `frontend` | **3000 → 80** | ./frontend (nginx) | backend |
| `telethon` | — | ./telethon_manager | backend |

**Доступ к приложению:** `http://localhost:3000`
**API документация:** `http://localhost:8000/docs`
**Дефолтный логин:** `admin` / `admin`

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
| `TG_API_ID` / `TG_API_HASH` | Telegram API credentials |
| `TELETHON_API_KEY` | Ключ для Telethon |
| `SIGNAL_NUMBER` | Номер Signal аккаунта (+380XXXXXXXXX) |
| `SIGNAL_API_URL` | URL Signal REST API (http://facewatch_signal:8080) |
| `BOT_API_KEY` | API ключ для Signal бота |
| `WHATSAPP_BACKEND_URL` | URL backend для WhatsApp бота |
| `OLLAMA_URL` | URL Ollama (http://facewatch_ollama:11434) |
| `OLLAMA_MODEL` | Модель (gemma4:e4b) |
| `OLLAMA_TIMEOUT` | Таймаут Ollama в секундах (120) |

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

### Утилиты

```bash
# Глобальная очистка дубликатов (SQL, Qdrant, QNAP)
docker compose exec backend python delete_duplicate_photos.py

# Удаление спама по заданным критериям
docker compose exec backend python delete_spam.py
```

### WhatsApp

```bash
# Подключение WhatsApp (QR-авторизация)
docker compose build facewatch_whatsapp && docker compose up -d facewatch_whatsapp
docker logs -f facewatch_whatsapp  # посмотреть QR-код
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
| POST | `/api/bot/message` | Приём данных от Telegram/Signal/WhatsApp бота |
| GET | `/api/platforms/*/groups/*` | Управление мультиплатформенными группами |
| GET/POST | `/api/tg-accounts/*` | Управление Telethon-аккаунтами |
| GET/POST | `/api/ai/*` | AI-чат, статус, отчёты, quick-запросы |

---

## Бизнес-процессы

### 1. Сбор сообщений из мессенджеров

#### Telegram (Bot)
```
Telegram группа → Bot (aiogram, polling) → POST /api/bot/message → Backend
    → Сохраняет Message в MariaDB
    → Извлекает телефоны из текста → message_phones
    → Если фото: сохраняет на QNAP → Celery task process_photo
```

#### Telegram (Telethon)
```
Telegram группа → Telethon аккаунт → POST /api/bot/message → Backend
    → Аналогичная логика, с source_type = "account"
```

#### Signal
```
Signal группа → Signal REST API (WebSocket) → signal_bot → POST /api/bot/message → Backend
    → source_platform = "signal", source_type = "bot/history"
    → Поддержка загрузки вложений через signal-cli REST API
```

#### WhatsApp
```
WhatsApp группа → whatsapp-web.js → POST /api/bot/message → Backend
    → source_platform = "whatsapp"
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

### 4. AI-модуль (Ollama)
```
Статус: проверка доступности модели
Чат: создание чата → streaming SSE-ответы → сохранение истории
Quick-запросы: daily briefing, case summary, person summary
Отчёты: сохранение + просмотр + удаление + экспорт в PDF
```

### 5. Дедупликация фото
При загрузке фото вычисляется SHA-256 хеш. Если картинка уже есть в БД (`photo_hash`), дубликат отбрасывается — экономия диска QNAP, базы Qdrant и ресурсов Celery.

### 6. Мультиплатформенное управление группами
- `platform_states` — состояние платформ (Signal, WhatsApp)
- `platform_group_links` — связь платформ с группами
- Периодическая синхронизация групп (каждые 30 сек для Signal)
- Прогресс загрузки истории с сохранением курсора

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
- **Роли:** `admin` (полный доступ), `operator` (скрыты группы с `is_public=False`, AI-вкладки, админ-страницы)
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
- Qdrant: memmap threshold=20000 (оптимизация памяти)

---

## Особенности миграций

`backend/entrypoint.sh` при старте:
1. Ожидает доступность MariaDB (TCP check)
2. Сравнивает текущую `alembic_version` с `head`
3. Проверяет фактическую схему БД (наличие колонок)
4. Если схема уже соответствует head, но версия отстаёт — синхронизирует `alembic_version`
5. Запускает `alembic upgrade head` (или пропускает, если таблицы создаются автоматически)

---

## Продакшн-настройки

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
6. **Ollama** — отключён (закомментирован в docker-compose.yml). Для восстановления — раскомментировать блок `ollama` и вернуть зависимость `backend.depends_on`
7. **Мультиплатформенность** — при добавлении новой платформы создать endpoint в `platforms.py`, обновить `PlatformState` и `PlatformGroupLink` модели, реализовать бот/коннектор
