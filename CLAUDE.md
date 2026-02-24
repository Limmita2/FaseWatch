# FaceWatch — Обзор проекта

Система мониторинга Telegram-каналов с распознаванием лиц. Бот собирает сообщения и фото из Telegram-групп, распознаёт лица через InsightFace, сохраняет векторные эмбеддинги в Qdrant, и предоставляет веб-интерфейс для поиска, идентификации и управления персонами.

## Стек технологий

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async), Pydantic Settings, Alembic |
| **Frontend** | React 18, Vite 5, TypeScript, TailwindCSS 4, Zustand, react-router-dom 6, axios |
| **Bot** | Python 3.11, aiogram 3.x (polling mode), httpx |
| **ML/AI** | InsightFace (buffalo_l / ArcFace), 512-dim embedding, CPU mode |
| **БД** | PostgreSQL 15 (async через asyncpg) |
| **Векторная БД** | Qdrant (коллекция `faces`, cosine similarity, 512 dim) |
| **Очередь задач** | Celery + Redis |
| **Хранилище файлов** | QNAP NAS (монтируется в `/mnt/qnap_photos`) |
| **Инфраструктура** | Docker Compose (7 контейнеров), Nginx (reverse proxy) |

## Структура проекта

```
FaseWatch/
├── .env                        # Переменные окружения (секреты, не коммитить!)
├── docker-compose.yml          # Оркестрация всех сервисов
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── entrypoint.sh           # Запуск: alembic upgrade + uvicorn
│   ├── alembic.ini             # Конфигурация миграций
│   ├── alembic/                # Миграции БД
│   └── app/
│       ├── main.py             # FastAPI app, lifespan, CORS, роуты, /api/dashboard
│       ├── core/
│       │   ├── config.py       # Settings (pydantic-settings, из .env)
│       │   ├── database.py     # AsyncEngine, AsyncSessionLocal, Base
│       │   └── security.py     # bcrypt hash/verify, JWT create/decode
│       ├── models/
│       │   └── models.py       # SQLAlchemy модели (6 таблиц)
│       ├── services/
│       │   ├── qdrant_service.py   # Qdrant CRUD (upsert, search, ensure_collection)
│       │   └── storage_service.py  # Сохранение фото/кропов на QNAP
│       ├── worker/
│       │   ├── celery_app.py   # Celery config (broker=Redis)
│       │   └── tasks.py        # Задача process_photo (InsightFace pipeline)
│       └── api/
│           ├── deps.py         # Зависимости (get_current_user, get_db)
│           └── endpoints/
│               ├── auth.py         # POST /api/auth/login
│               ├── messages.py     # GET /api/messages, GET /api/messages/{id}/context
│               ├── persons.py      # GET/PATCH /api/persons, POST /api/persons/merge
│               ├── queue.py        # GET /api/queue, POST confirm/reject
│               ├── search.py       # POST /api/search/face, GET /api/search/text
│               ├── groups.py       # GET /api/groups
│               ├── imports.py      # POST /api/import (загрузка бэкапов)
│               ├── webhook.py      # POST /webhook/telegram
│               └── bot_receiver.py # POST /api/bot/message (от бота)
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
│           ├── DashboardPage.tsx   # / — статистика, последние сообщения
│           ├── MessagesPage.tsx    # /messages — все сообщения с фильтрами
│           ├── SearchPage.tsx      # /search — поиск по фото (лицу) и тексту
│           ├── PersonsPage.tsx     # /persons — список персон, редактирование
│           ├── QueuePage.tsx       # /queue — очередь идентификации (confirm/reject)
│           ├── GroupsPage.tsx      # /groups — Telegram-группы
│           └── ImportPage.tsx      # /import — загрузка бэкапов Telegram
│
└── bot/
    ├── Dockerfile
    ├── requirements.txt        # aiogram, httpx, python-dotenv
    └── main.py                 # Бот: polling, обработка фото/текста → backend API
```

## Модели базы данных (PostgreSQL)

```
┌──────────┐     ┌──────────────┐     ┌────────┐
│  Group   │────<│   Message    │────<│  Face   │
│          │     │              │     │         │
│ id (PK)  │     │ id (PK)      │     │ id (PK) │
│ telegram_│     │ group_id (FK)│     │ person_id (FK) → Person │
│ name     │     │ text         │     │ message_id (FK)│
│ bot_activ│     │ has_photo    │     │ crop_path      │
│          │     │ photo_path   │     │ qdrant_point_id│
│          │     │ sender_name  │     │ bbox (JSON)    │
│          │     │ timestamp    │     │ confidence     │
└──────────┘     └──────────────┘     └────────┘
                                          │
                                          ▼
┌──────────┐     ┌─────────────────────────┐
│  Person  │<────│  IdentificationQueue    │
│          │     │                         │
│ id (PK)  │     │ id (PK)                 │
│ display_ │     │ face_id (FK)            │
│ confirmed│     │ suggested_person_id (FK)│
└──────────┘     │ similarity              │
                 │ status (pending/confirmed/rejected) │
┌──────────┐     │ reviewed_by (FK) → User │
│  User    │     └─────────────────────────┘
│          │
│ id (PK)  │
│ username │
│ password_│
│ role (admin/operator) │
└──────────┘
```

## Основные бизнес-процессы

### 1. Сбор сообщений из Telegram
```
Telegram группа → Bot (aiogram, polling) → POST /api/bot/message → Backend
    → Сохраняет Message в PostgreSQL
    → Если фото: сохраняет файл на QNAP, запускает Celery task process_photo
```

### 2. Распознавание лиц (Celery worker)
```
process_photo task:
    1. Открывает фото с QNAP (cv2.imread)
    2. InsightFace.get() → обнаружение лиц, генерация 512-dim вектора
    3. search_similar_faces() в Qdrant (cosine, threshold ≥ 0.75)
    4. Если похожее лицо найдено → IdentificationQueue (pending, оператор подтверждает)
    5. Если не найдено → создаёт новую Person
    6. Сохраняет кроп лица на QNAP (/faces/{person_id}/{face_id}.jpg)
    7. upsert вектор в Qdrant (payload: face_id, person_id, message_id, group_id)
```

### 3. Идентификация (веб-интерфейс)
```
Оператор в /queue видит pending записи → confirm (привязка к Person) или reject
```

### 4. Поиск
```
По фото: загрузка фото → InsightFace → вектор → Qdrant search → результаты
По тексту: ILIKE поиск по Message.text в PostgreSQL
```

### 5. Импорт
```
Загрузка HTML/ZIP экспорта Telegram → парсинг → создание Message/Group → фото → Celery
```

## API маршруты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/login` | Логин (username + password → JWT) |
| GET | `/api/dashboard` | Статистика (кол-во групп, сообщений, лиц, персон, pending) |
| GET | `/api/messages` | Список сообщений (фильтры: группа, дата, has_photo) |
| GET | `/api/messages/{id}/context` | Контекст сообщения |
| GET | `/api/persons` | Список персон |
| GET | `/api/persons/{id}` | Детали персоны с лицами |
| PATCH | `/api/persons/{id}` | Обновить display_name / confirmed |
| POST | `/api/persons/merge` | Объединить две персоны |
| GET | `/api/queue` | Очередь идентификации (pending) |
| POST | `/api/queue/{id}/confirm` | Подтвердить идентификацию |
| POST | `/api/queue/{id}/reject` | Отклонить идентификацию |
| POST | `/api/search/face` | Поиск по фото лица (multipart/form-data) |
| GET | `/api/search/text` | Поиск по тексту сообщений |
| GET | `/api/groups` | Список Telegram-групп |
| POST | `/api/import` | Импорт бэкапа (multipart/form-data) |
| POST | `/api/bot/message` | Приём сообщений от Telegram бота |
| POST | `/webhook/telegram` | Webhook для Telegram (не используется, бот в polling) |

## Docker Compose — сервисы

| Контейнер | Порт | Образ | Зависимости |
|-----------|------|-------|-------------|
| `facewatch_db` | 5432 (internal) | postgres:15-alpine | — |
| `facewatch_qdrant` | 6333 (localhost) | qdrant/qdrant:latest | — |
| `facewatch_redis` | 6379 (internal) | redis:alpine | — |
| `facewatch_backend` | 8000 (internal) | ./backend | postgres, qdrant, redis |
| `facewatch_celery` | — | ./backend | backend, redis |
| `facewatch_bot` | — | ./bot | backend |
| `facewatch_frontend` | **3000 → 80** | ./frontend (nginx) | backend |

**Доступ к приложению:** `http://localhost:3000`
**Дефолтный логин:** `admin` / `admin` (создаётся автоматически при первом запуске)

## Переменные окружения (.env)

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен Telegram бота |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Реквизиты PostgreSQL |
| `DATABASE_URL` | Строка подключения (postgresql+asyncpg://...) |
| `QDRANT_HOST` / `QDRANT_PORT` | Адрес Qdrant |
| `REDIS_URL` | Адрес Redis |
| `QNAP_MOUNT_PATH` | Путь монтирования QNAP NAS |
| `JWT_SECRET` | Секрет для JWT токенов |
| `JWT_ALGORITHM` | Алгоритм JWT (HS256) |
| `JWT_EXPIRE_HOURS` | Время жизни токена (8 часов) |
| `FACE_SIMILARITY_THRESHOLD` | Порог похожести лиц (0.75) |

## Авторизация

- **Механизм:** JWT Bearer token (в header `Authorization: Bearer <token>`)
- **Хеширование:** bcrypt
- **Хранение на фронте:** `localStorage` (token, role)
- **Стейт:** Zustand (`useAuthStore`)
- **Роли:** `admin`, `operator`
- **Истечение:** настраивается через `JWT_EXPIRE_HOURS`

## Хранилище файлов (QNAP)

```
/mnt/qnap_photos/
├── photos/{group_id}/{YYYY-MM}/{message_id}_{timestamp}.jpg   # оригиналы
├── faces/{person_id}/{face_id}.jpg                            # кропы лиц
```

Файлы доступны через backend: `GET /files/...` (FastAPI StaticFiles mount).
Nginx проксирует `/files/` на backend.

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

# Миграции БД (внутри контейнера backend)
docker exec -it facewatch_backend alembic revision --autogenerate -m "description"
docker exec -it facewatch_backend alembic upgrade head

# Локальная разработка фронтенда
cd frontend && npm install && npm run dev  # → http://localhost:5173
```
