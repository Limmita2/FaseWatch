from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Iterable

import redis.asyncio as aioredis
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import Message, Group, Face


GENERAL_CONTEXT_LIMIT = 20000
GROUP_CONTEXT_LIMIT = 20000
DAILY_CONTEXT_LIMIT = 40000
CASE_CONTEXT_LIMIT = 30000


def _truncate_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return value[:limit]


def _message_line(group_name: str | None, msg: Message) -> str:
    parts = [
        f"[{msg.timestamp.isoformat(sep=' ', timespec='seconds') if msg.timestamp else 'без часу'}]",
        f"Група: {group_name or '—'}",
        f"Відправник: {msg.sender_name or '—'}",
    ]
    body = f"Текст: {_truncate_text(msg.text, 500) or '—'}"
    if msg.document_text:
        body += f'\nДокумент "{msg.document_name or "без назви"}": {_truncate_text(msg.document_text, 500)}'
    return " | ".join(parts) + f"\n{body}"


def _fit_lines(lines: Iterable[str], limit: int) -> str:
    chunks: list[str] = []
    current = 0
    for line in lines:
        delta = len(line) + 2
        if current + delta > limit:
            break
        chunks.append(line)
        current += delta
    return "\n\n".join(chunks)


async def _get_redis():
    return aioredis.from_url(settings.REDIS_URL)


async def build_context_for_general(days: int = 3) -> str:
    async with AsyncSessionLocal() as db:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(Message, Group.name.label("group_name"))
            .join(Group, Message.group_id == Group.id)
            .where(Message.timestamp >= since)
            .order_by(Message.timestamp.desc())
            .limit(80)
        )
        rows = result.all()
        header = [
            "ЗАГАЛЬНИЙ КОНТЕКСТ FACEWATCH",
            f"ПЕРІОД: {since.isoformat(sep=' ', timespec='seconds')} — {datetime.utcnow().isoformat(sep=' ', timespec='seconds')}",
            f"ПОВІДОМЛЕННЯ: {len(rows)}",
        ]
        body = _fit_lines((_message_line(group_name, msg) for msg, group_name in rows), GENERAL_CONTEXT_LIMIT)
        return "\n".join(header) + "\n\n" + body


async def build_context_for_group(group_id: str, days: int = 3) -> str:
    async with AsyncSessionLocal() as db:
        group = await db.get(Group, uuid.UUID(group_id))
        if not group:
            raise ValueError("Group not found")

        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(Message)
            .where(Message.group_id == group.id, Message.timestamp >= since)
            .order_by(Message.timestamp.desc())
            .limit(120)
        )
        messages = result.scalars().all()

        face_count = (
            await db.execute(
                select(func.count(Face.id))
                .join(Message, Face.message_id == Message.id)
                .where(Message.group_id == group.id, Message.timestamp >= since)
            )
        ).scalar() or 0

        header = [
            f"ГРУПА: {group.name}",
            f"TG_ID: {group.telegram_id}",
            f"ПЕРІОД: {since.isoformat(sep=' ', timespec='seconds')} — {datetime.utcnow().isoformat(sep=' ', timespec='seconds')}",
            f"ПОВІДОМЛЕННЯ: {len(messages)}",
            f"ВИЯВЛЕНІ ОБЛИЧЧЯ: {face_count}",
            "PERSON_ID НЕДОСТУПНІ: у поточній схемі FaceWatch немає person_id.",
        ]
        body = _fit_lines((_message_line(group.name, msg) for msg in messages), GROUP_CONTEXT_LIMIT)
        return "\n".join(header) + "\n\n" + body


async def build_context_for_daily() -> str:
    cache_key = f"ai_context:daily:{datetime.utcnow().date().isoformat()}"
    redis = await _get_redis()
    try:
        cached = await redis.get(cache_key)
        if cached:
            if isinstance(cached, bytes):
                cached = cached.decode()
            return cached
    finally:
        await redis.aclose()

    async with AsyncSessionLocal() as db:
        since = datetime.utcnow() - timedelta(hours=24)
        message_count = (
            await db.execute(select(func.count(Message.id)).where(Message.timestamp >= since))
        ).scalar() or 0
        photo_count = (
            await db.execute(select(func.count(Message.id)).where(Message.timestamp >= since, Message.has_photo.is_(True)))
        ).scalar() or 0
        face_count = (
            await db.execute(
                select(func.count(Face.id))
                .join(Message, Face.message_id == Message.id)
                .where(Message.timestamp >= since)
            )
        ).scalar() or 0

        active_groups = await db.execute(
            select(Group.name, func.count(Message.id).label("msg_count"))
            .join(Message, Message.group_id == Group.id)
            .where(Message.timestamp >= since)
            .group_by(Group.id, Group.name)
            .order_by(func.count(Message.id).desc())
            .limit(10)
        )
        recent_rows = await db.execute(
            select(Message, Group.name.label("group_name"))
            .join(Group, Message.group_id == Group.id)
            .where(Message.timestamp >= since)
            .order_by(Message.timestamp.desc())
            .limit(100)
        )

        header = [
            "ЩОДЕННИЙ ОПЕРАТИВНИЙ КОНТЕКСТ",
            f"ПЕРІОД: {since.isoformat(sep=' ', timespec='seconds')} — {datetime.utcnow().isoformat(sep=' ', timespec='seconds')}",
            f"НОВІ ПОВІДОМЛЕННЯ: {message_count}",
            f"НОВІ ФОТО: {photo_count}",
            f"НОВІ ОБЛИЧЧЯ: {face_count}",
            "ЗБІГИ PERSON_ID У 3+ ГРУПАХ НЕДОСТУПНІ: у поточній схемі FaceWatch немає person_id.",
            "АКТИВНІ ГРУПИ:",
        ]
        group_lines = [f"- {name}: {msg_count} повідомлень" for name, msg_count in active_groups.all()]
        body = _fit_lines((_message_line(group_name, msg) for msg, group_name in recent_rows.all()), DAILY_CONTEXT_LIMIT)
        context = "\n".join(header + group_lines) + "\n\nОСТАННІ ПОДІЇ:\n\n" + body

    redis = await _get_redis()
    try:
        await redis.setex(cache_key, 3600, context)
    finally:
        await redis.aclose()
    return context


async def build_context_for_case(case_id: str, days: int = 7) -> str:
    raise NotImplementedError("Case analysis is unavailable: current schema has no case_id.")


async def build_context_for_person(person_id: str) -> str:
    raise NotImplementedError("Person analysis is unavailable: current schema has no person_id.")


async def get_context_summary(context_type: str, context_id: str | None = None) -> dict:
    async with AsyncSessionLocal() as db:
        if context_type == "daily":
            since = datetime.utcnow() - timedelta(hours=24)
            stats = {
                "messages": (await db.execute(select(func.count(Message.id)).where(Message.timestamp >= since))).scalar() or 0,
                "photos": (await db.execute(select(func.count(Message.id)).where(Message.timestamp >= since, Message.has_photo.is_(True)))).scalar() or 0,
                "faces": (
                    await db.execute(
                        select(func.count(Face.id))
                        .join(Message, Face.message_id == Message.id)
                        .where(Message.timestamp >= since)
                    )
                ).scalar() or 0,
            }
            return {"context_type": "daily", "stats": stats}

        if context_type == "group" and context_id:
            group = await db.get(Group, uuid.UUID(context_id))
            if not group:
                return {"context_type": "group", "missing": True}
            recent = await db.execute(
                select(Message)
                .where(Message.group_id == group.id)
                .order_by(Message.timestamp.desc())
                .limit(3)
            )
            count = (
                await db.execute(select(func.count(Message.id)).where(Message.group_id == group.id))
            ).scalar() or 0
            return {
                "context_type": "group",
                "group_id": str(group.id),
                "group_name": group.name,
                "telegram_id": group.telegram_id,
                "messages_count": count,
                "recent_events": [
                    {
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "text": _truncate_text(msg.text or msg.document_name or "", 140),
                    }
                    for msg in recent.scalars().all()
                ],
            }

    return {"context_type": context_type, "note": "No additional context summary available."}
