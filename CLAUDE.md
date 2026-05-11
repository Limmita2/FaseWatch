# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## FaceWatch — Огляд

Система моніторингу месенджерів (Telegram, WhatsApp, Signal) з розпізнаванням облич. Бот збирає повідомлення та фото, InsightFace генерує 512-dim ембеддінги, Qdrant зберігає вектори та кластеризує їх у персони.

## Стек

| Шар | Технології |
|-----|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy async (aiomysql), Alembic |
| **Frontend** | React 18, Vite 5, TypeScript, TailwindCSS 4, Zustand, axios |
| **ML** | InsightFace (buffalo_l / ArcFace), 512-dim COSINE, ONNX Runtime |
| **БД** | MariaDB на QNAP 192.168.24.178:3306 (поза Docker) |
| **Векторна БД** | Qdrant (колекція `faces`, cosine similarity, 512 dim) |
| **Черга** | Celery + Redis (concurrency=8, prefork) |
| **Файли** | QNAP NAS, монтується в `/mnt/qnap_photos` |
| **Інфра** | Docker Compose (6 контейнерів), Nginx reverse proxy у frontend |

## Команди

```bash
# Запуск
docker compose up --build -d

# Логи
docker compose logs -f [backend|celery_worker|bot|frontend]

# Пересборка після змін у backend/worker
docker compose build backend celery_worker && docker compose up -d backend celery_worker

# Тільки frontend
docker compose build frontend && docker compose up -d frontend

# Міграції (з середини контейнера)
docker exec -it facewatch_backend alembic revision --autogenerate -m "description"
docker exec -it facewatch_backend alembic upgrade head

# Локальна розробка frontend
cd frontend && npm install && npm run dev  # → http://localhost:5173

# Локальний імпорт Telegram Desktop ZIP
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/export.zip --group "Назва"

# Ретроспективна кластеризація персон (для старих облич без person_id)
docker compose cp backend/backfill_persons.py backend:/app/backfill_persons.py
docker compose exec backend python backfill_persons.py [--batch 500] [--threshold 0.70]

# Глобальне очищення дублікатів
docker compose exec backend python delete_duplicate_photos.py
```

Доступ: `http://localhost:3000` | Логін: `admin` / `admin`

## Архітектура та ключові потоки

### Обробка фото (Celery pipeline)

```
Bot → POST /api/bot/message → backend
    → save photo to QNAP
    → db.commit()
    → celery.send_task("process_photo", ...)   ← після commit щоб уникнути race
         → cv2.imread → InsightFace.get() → 512-dim vector
         → find_person_for_vector(qdrant, vector, threshold=0.70)
              ↳ знайдено → використовуємо існуючий person_id, ++face_count
              ↳ не знайдено → новий Person UUID
         → upsert_face_vector(qdrant, payload={face_id, message_id, group_id, person_id})
         → Face.person_id = person_id → DB commit
```

### Кластеризація персон

- `PERSON_THRESHOLD = 0.70` у `backend/app/services/qdrant_service.py`
- `find_person_for_vector()` шукає серед точок з непустим `person_id` у payload (top-1, cosine ≥ 0.70)
- Нові фото: вектор іще не у Qdrant → правильний пошук без self-match
- Старі фото (без person_id): `backfill_persons.py` — шукає top-10, пропускає self-match

### Пошук

- **По фото**: InsightFace → вектор → `Qdrant.query_points` → контекст ±5 повідомлень
- **По тексту**: FULLTEXT `MATCH AGAINST IN BOOLEAN MODE`, fallback `LIKE %q%`
- **По телефону**: нормалізація UA-номера → `message_phones` → пов'язані повідомлення

Усі 3 типи пошуку повертають `group_notes` (нотатки оператора до групи) у відповіді.

### Дедуплікація фото

SHA-256 хеш фото → `photo_hash` у Message. Якщо хеш вже є — ціле повідомлення ігнорується (не зберігається ні в БД, ні у Qdrant, ні на QNAP).

### Авторизація

JWT Bearer token. Ролі: `admin` (повний доступ), `operator` (не бачить груп з `is_public=False`). IP-фільтрація через `fnmatch` по полю `User.allowed_ip`.

## Моделі БД (6 таблиць)

```
Person            Group              Message            Face
──────────        ──────────         ──────────         ──────────
id (UUID PK)      id (UUID PK)       id (UUID PK)       id (UUID PK)
face_count        telegram_id        group_id → Group   message_id → Message
thumbnail_face_id name               sender_name        person_id → Person
first_seen        notes (Text)       text               crop_path
last_seen         is_public          photo_path         qdrant_point_id
                  last_message_at    photo_hash         bbox (JSON)
                  source_platform    has_photo          confidence

MessagePhone      User
──────────        ──────────
id (UUID PK)      id (UUID PK)
message_id        username
phone             password_hash
                  role
                  allowed_ip
```

Ключові індекси: `ix_messages_group_timestamp` (основний для контексту), `ft_messages_text` (FULLTEXT), `ix_message_phones_phone`, `ix_faces_person_id`.

## API ендпоінти

| Метод | Шлях | Опис |
|-------|------|------|
| POST | `/api/auth/login` | JWT логін |
| GET | `/api/dashboard` | Статистика |
| GET | `/api/messages/` | Список повідомлень |
| GET | `/api/messages/{id}/context` | Контекст ±5 |
| POST | `/api/search/face` | Пошук по фото (multipart) |
| GET | `/api/search/text` | Текстовий пошук |
| GET | `/api/search/phone` | Пошук по телефону |
| GET/PATCH/DELETE | `/api/groups/` | Групи (notes, toggle-public) |
| GET | `/api/tg-accounts/` | Telegram акаунти |
| GET/PATCH | `/api/platforms/{signal\|whatsapp}/...` | WhatsApp/Signal джерела |
| GET/POST/... | `/api/ai/chats`, `/api/ai/reports` | AI чат і звіти |
| POST | `/api/import/` | Імпорт Telegram ZIP |
| POST | `/api/input/` | Ручний ввод фото |
| POST | `/api/bot/message` | Приймає дані від бота |

## Frontend структура

- `src/store/authStore.ts` — Zustand: token, role, login/logout
- `src/services/api.ts` — всі axios-виклики. Інтерцептор: JWT header + redirect на `/login` при 401
- `src/pages/SearchPage.tsx` — найскладніша сторінка: 3 таби (фото/текст/телефон), модал контексту, face-картки
- `src/pages/GroupsPage.tsx` — таблиця груп з inline-редагуванням `notes` (save on blur)

## Важливі деталі

- **Async SQLAlchemy**: lazy relationship access (`msg.group.notes`) **не працює**. Завжди використовуй явний JOIN з `.label()` і tuple unpacking у select.
- **Celery tasks**: синхронний SQLAlchemy (`mysql+pymysql`), ініціалізується через `_get_session()` із глобальним `_engine`.
- **Міграції**: `entrypoint.sh` при старті синхронізує `alembic_version` до поточного head навіть якщо схема вже актуальна (для безпечного старту на бойовій БД).
- **Qdrant payload**: нові точки мають `{face_id, message_id, group_id, timestamp, person_id}`. Старі (до кластеризації) — без `person_id`.
- **Файлове сховище**: оригінали → `/mnt/qnap_photos/photos/{group_id}/{YYYY-MM}/`, кропи → `/mnt/qnap_photos/faces/{2-char-shard}/{face_id}.jpg`
