"""
FaceWatch — Главное приложение FastAPI.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base
from app.core.security import hash_password
from app.models.models import User, UserRole
from app.services.qdrant_service import ensure_collection_exists

from app.api.endpoints import auth, messages, persons, queue, search, groups, imports, webhook, bot_receiver, users, input


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы в БД при запуске
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Создаём дефолтного admin пользователя если нет
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                role=UserRole.admin,
                description="Администратор системы",
            )
            session.add(admin)
            await session.commit()

    # Создаём коллекцию в Qdrant
    try:
        ensure_collection_exists()
    except Exception:
        pass  # Qdrant может быть недоступен при запуске

    yield


app = FastAPI(
    title="FaceWatch API",
    description="Система мониторинга Telegram-каналов с распознаванием лиц",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — разрешаем frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтирование файлового хранилища (для отдачи фото)
try:
    app.mount("/files", StaticFiles(directory=settings.QNAP_MOUNT_PATH), name="files")
except Exception:
    pass  # Директория может не существовать

# Роуты
app.include_router(auth.router, prefix="/api/auth", tags=["Авторизация"])
app.include_router(messages.router, prefix="/api/messages", tags=["Сообщения"])
app.include_router(persons.router, prefix="/api/persons", tags=["Персоны"])
app.include_router(queue.router, prefix="/api/queue", tags=["Очередь идентификации"])
app.include_router(search.router, prefix="/api/search", tags=["Поиск"])
app.include_router(groups.router, prefix="/api/groups", tags=["Группы"])
app.include_router(imports.router, prefix="/api/import", tags=["Импорт"])
app.include_router(webhook.router, tags=["Webhook"])
app.include_router(bot_receiver.router, prefix="/api/bot", tags=["Bot Receiver"])
app.include_router(users.router, prefix="/api/users", tags=["Пользователи"])
app.include_router(input.router, prefix="/api/input", tags=["Ввод"])


@app.get("/api/dashboard")
async def dashboard():
    """Статистика для дашборда."""
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal
    from app.models.models import Group, Message, Face, Person, IdentificationQueue, IdentificationStatus

    async with AsyncSessionLocal() as session:
        groups_count = (await session.execute(select(func.count(Group.id)))).scalar()
        messages_count = (await session.execute(select(func.count(Message.id)))).scalar()
        faces_count = (await session.execute(select(func.count(Face.id)))).scalar()
        persons_count = (await session.execute(select(func.count(Person.id)))).scalar()
        pending_count = (await session.execute(
            select(func.count(IdentificationQueue.id))
            .where(IdentificationQueue.status == IdentificationStatus.pending)
        )).scalar()

        # Последние 10 сообщений
        recent = await session.execute(
            select(Message, Group.name.label("group_name"))
            .join(Group, Message.group_id == Group.id, isouter=True)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        recent_messages = [
            {
                "id": str(msg.id),
                "group_name": gname,
                "text": msg.text[:100] if msg.text else None,
                "has_photo": msg.has_photo,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            }
            for msg, gname in recent.all()
        ]

    return {
        "groups": groups_count or 0,
        "messages": messages_count or 0,
        "faces": faces_count or 0,
        "persons": persons_count or 0,
        "pending_identifications": pending_count or 0,
        "recent_messages": recent_messages,
    }


@app.get("/")
async def root():
    return {"service": "FaceWatch API", "version": "1.0.0"}
