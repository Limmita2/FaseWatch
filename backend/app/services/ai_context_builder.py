from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Iterable

import redis.asyncio as aioredis
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import Message, Group, Face


GENERAL_CONTEXT_LIMIT = 20000
GROUP_CONTEXT_LIMIT = 20000
DAILY_CONTEXT_LIMIT = 9000
CASE_CONTEXT_LIMIT = 30000
DAILY_CONTEXT_MESSAGES = 40
DAILY_BRIEF_EVENT_LIMIT = 12
DAILY_MESSAGE_TEXT_LIMIT = 240
DAILY_PERSON_MATCH_LIMIT = 15
MVS_PERSON_MATCH_GROUPS = ("Безвісти зниклі МВС", "Розшук МВС")


def _truncate_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return value[:limit]


def _message_line(group_name: str | None, msg: Message, text_limit: int = 500) -> str:
    parts = [
        f"[{msg.timestamp.isoformat(sep=' ', timespec='seconds') if msg.timestamp else 'без часу'}]",
        f"Група: {group_name or '—'}",
        f"Відправник: {msg.sender_name or '—'}",
    ]
    body = f"Текст: {_truncate_text(msg.text, text_limit) or '—'}"
    if msg.document_text:
        body += f'\nДокумент "{msg.document_name or "без назви"}": {_truncate_text(msg.document_text, text_limit)}'
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


def _compact_text(value: str | None, limit: int = DAILY_MESSAGE_TEXT_LIMIT) -> str:
    if not value:
        return ""
    normalized = " ".join(value.split())
    return normalized[:limit]


def _brief_event_line(group_name: str | None, msg: Message) -> str:
    timestamp = msg.timestamp.isoformat(sep=" ", timespec="minutes") if msg.timestamp else "без часу"
    text = _compact_text(msg.text)
    if msg.document_text:
        document = _compact_text(msg.document_text)
        document_name = msg.document_name or "без назви"
        text = f'{text} Документ "{document_name}": {document}'.strip()
    elif not text and msg.document_name:
        text = f"Документ: {msg.document_name}"
    if not text:
        text = "повідомлення без тексту"
    return f"- [{timestamp}] {group_name or '—'}: {text}"


def _format_seen_at(value: datetime | None) -> str:
    if not value:
        return "без часу"
    return value.isoformat(sep=" ", timespec="minutes")


def _format_group_hits(rows: list[dict], limit: int = 4) -> str:
    chunks = []
    for row in sorted(rows, key=lambda item: item["last_seen"] or datetime.min, reverse=True)[:limit]:
        chunks.append(
            f'{row["group_name"]} ({row["face_count"]} облич, остання поява: {_format_seen_at(row["last_seen"])})'
        )
    remaining = len(rows) - limit
    if remaining > 0:
        chunks.append(f"+{remaining} груп")
    return "; ".join(chunks)


def _select_diverse_events(rows: list[tuple[Message, str | None]], limit: int) -> list[str]:
    selected: list[tuple[Message, str | None]] = []
    seen_groups: set[str] = set()

    for msg, group_name in rows:
        key = group_name or str(msg.group_id)
        if key in seen_groups:
            continue
        selected.append((msg, group_name))
        seen_groups.add(key)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        selected_ids = {msg.id for msg, _ in selected}
        for msg, group_name in rows:
            if msg.id in selected_ids:
                continue
            selected.append((msg, group_name))
            selected_ids.add(msg.id)
            if len(selected) >= limit:
                break

    return [_brief_event_line(group_name, msg) for msg, group_name in selected]


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
            "PERSON_ID: доступні для облич, які вже пройшли кластеризацію.",
        ]
        body = _fit_lines((_message_line(group.name, msg) for msg in messages), GROUP_CONTEXT_LIMIT)
        return "\n".join(header) + "\n\n" + body


async def build_context_for_daily() -> str:
    cache_key = f"ai_context:daily:v2:{datetime.utcnow().date().isoformat()}"
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
            .limit(DAILY_CONTEXT_MESSAGES)
        )
        mvs_person_match_lines = await build_mvs_person_match_lines(db, since, limit=8)

        header = [
            "ЩОДЕННИЙ ОПЕРАТИВНИЙ КОНТЕКСТ",
            f"ПЕРІОД: {since.isoformat(sep=' ', timespec='seconds')} — {datetime.utcnow().isoformat(sep=' ', timespec='seconds')}",
            f"НОВІ ПОВІДОМЛЕННЯ: {message_count}",
            f"НОВІ ФОТО: {photo_count}",
            f"НОВІ ОБЛИЧЧЯ: {face_count}",
            "ЗБІГИ PERSON_ID З ГРУПАМИ МВС:",
        ]
        header.extend(mvs_person_match_lines or ["- За останні 24 години збігів з групами МВС не виявлено."])
        header.append("АКТИВНІ ГРУПИ:")
        group_lines = [f"- {name}: {msg_count} повідомлень" for name, msg_count in active_groups.all()]
        body = _fit_lines(
            (_message_line(group_name, msg, DAILY_MESSAGE_TEXT_LIMIT) for msg, group_name in recent_rows.all()),
            DAILY_CONTEXT_LIMIT,
        )
        context = "\n".join(header + group_lines) + "\n\nОСТАННІ ПОДІЇ:\n\n" + body

    redis = await _get_redis()
    try:
        await redis.setex(cache_key, 3600, context)
    finally:
        await redis.aclose()
    return context


async def build_mvs_person_match_lines(
    db: AsyncSession,
    since: datetime,
    limit: int = DAILY_PERSON_MATCH_LIMIT,
) -> list[str]:
    recent_result = await db.execute(
        select(
            Face.person_id,
            Group.name.label("group_name"),
            Group.source_platform,
            func.count(Face.id).label("face_count"),
            func.max(Message.timestamp).label("last_seen"),
        )
        .join(Message, Face.message_id == Message.id)
        .join(Group, Message.group_id == Group.id)
        .where(
            Message.timestamp >= since,
            Face.person_id.is_not(None),
            Face.person_id != "skipped",
        )
        .group_by(Face.person_id, Group.id, Group.name, Group.source_platform)
        .order_by(func.max(Message.timestamp).desc())
        .limit(1000)
    )

    recent_by_person: dict[str, list[dict]] = {}
    person_last_seen: dict[str, datetime] = {}
    for person_id, group_name, source_platform, face_count, last_seen in recent_result.all():
        recent_by_person.setdefault(person_id, []).append(
            {
                "group_name": f"{group_name} ({source_platform})",
                "face_count": face_count,
                "last_seen": last_seen,
            }
        )
        if last_seen and (person_id not in person_last_seen or last_seen > person_last_seen[person_id]):
            person_last_seen[person_id] = last_seen

    recent_person_ids = list(recent_by_person)
    if not recent_person_ids:
        return []

    target_result = await db.execute(
        select(
            Face.person_id,
            Group.name.label("group_name"),
            Group.source_platform,
            func.count(Face.id).label("face_count"),
            func.max(Message.timestamp).label("last_seen"),
        )
        .join(Message, Face.message_id == Message.id)
        .join(Group, Message.group_id == Group.id)
        .where(
            Group.name.in_(MVS_PERSON_MATCH_GROUPS),
            Face.person_id.in_(recent_person_ids),
            Face.person_id.is_not(None),
            Face.person_id != "skipped",
        )
        .group_by(Face.person_id, Group.id, Group.name, Group.source_platform)
        .order_by(func.max(Message.timestamp).desc())
    )

    target_by_person: dict[str, list[dict]] = {}
    for person_id, group_name, source_platform, face_count, last_seen in target_result.all():
        target_by_person.setdefault(person_id, []).append(
            {
                "group_name": f"{group_name} ({source_platform})",
                "face_count": face_count,
                "last_seen": last_seen,
            }
        )

    matched_person_ids = sorted(
        target_by_person,
        key=lambda person_id: person_last_seen.get(person_id) or datetime.min,
        reverse=True,
    )

    lines = []
    for person_id in matched_person_ids[:limit]:
        lines.append(
            f"- person_id `{person_id}`: за 24 год — {_format_group_hits(recent_by_person[person_id])}; "
            f"збіг у МВС — {_format_group_hits(target_by_person[person_id], limit=2)}."
        )
    remaining = len(matched_person_ids) - limit
    if remaining > 0:
        lines.append(f"- Ще {remaining} збігів не показано через ліміт звіту.")
    return lines


async def build_daily_briefing_report(db: AsyncSession) -> str:
    since = datetime.utcnow() - timedelta(hours=24)
    now = datetime.utcnow()

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

    active_groups_result = await db.execute(
        select(Group.name, Group.source_platform, func.count(Message.id).label("msg_count"))
        .join(Message, Message.group_id == Group.id)
        .where(Message.timestamp >= since)
        .group_by(Group.id, Group.name, Group.source_platform)
        .order_by(func.count(Message.id).desc())
        .limit(10)
    )
    active_groups = active_groups_result.all()

    new_groups_result = await db.execute(
        select(
            Group.name,
            Group.source_platform,
            func.count(Message.id).label("msg_count"),
        )
        .outerjoin(
            Message,
            and_(
                Message.group_id == Group.id,
                Message.timestamp >= since,
            ),
        )
        .where(Group.created_at >= since)
        .group_by(Group.id, Group.name, Group.source_platform)
        .order_by(Group.created_at.desc(), Group.name.asc())
        .limit(20)
    )
    new_groups = new_groups_result.all()
    mvs_person_match_lines = await build_mvs_person_match_lines(db, since)

    active_group_lines = [
        f"- {name} ({source_platform}): {msg_count} повідомлень"
        for name, source_platform, msg_count in active_groups
    ] or ["- Активних груп за період немає."]

    new_group_lines = [
        f"- {name} ({source_platform}): {msg_count} повідомлень"
        for name, source_platform, msg_count in new_groups
    ] or ["- Нових груп за останні 24 години не зафіксовано."]

    return "\n\n".join(
        [
            "ДЕННИЙ ОПЕРАТИВНИЙ БРИФІНГ",
            "\n".join(
                [
                    f"Період: {since.isoformat(sep=' ', timespec='minutes')} — {now.isoformat(sep=' ', timespec='minutes')} UTC",
                    f"Нові повідомлення: {message_count}",
                    f"Нові фото: {photo_count}",
                    f"Нові обличчя: {face_count}",
                ]
            ),
            "ЗБІГИ PERSON_ID З ГРУПАМИ МВС:\n"
            + (
                "\n".join(mvs_person_match_lines)
                if mvs_person_match_lines
                else (
                    "- За останні 24 години появ person_id, що збігаються з групами "
                    "\"Безвісти зниклі МВС\" або \"Розшук МВС\", не виявлено."
                )
            ),
            "НОВІ ГРУПИ ЗА ДОБУ:\n" + "\n".join(new_group_lines),
            "АКТИВНІ ГРУПИ:\n" + "\n".join(active_group_lines),
        ]
    )


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
