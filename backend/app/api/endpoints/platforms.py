"""
Endpoints для Signal/WhatsApp источников.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.models import Group, Message, PlatformGroupLink, PlatformState

router = APIRouter()

SUPPORTED_PLATFORMS = {"signal", "whatsapp"}


class PlatformGroupSyncIn(BaseModel):
    external_id: str
    name: str
    metadata: Optional[dict[str, Any]] = None


class PlatformSyncBody(BaseModel):
    account_identifier: Optional[str] = None
    status: str = "active"
    last_error: Optional[str] = None
    meta: Optional[dict[str, Any]] = None
    groups: list[PlatformGroupSyncIn] = []


class PlatformProgressBody(BaseModel):
    history_load_progress: int
    last_cursor: Optional[str] = None
    history_loaded: Optional[bool] = False


def verify_internal_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.TELETHON_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


def ensure_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=404, detail="Unsupported platform")
    return normalized


async def upsert_platform_group(
    db: AsyncSession,
    platform: str,
    item: PlatformGroupSyncIn,
) -> PlatformGroupLink:
    result = await db.execute(
        select(Group).where(
            Group.source_platform == platform,
            Group.external_id == item.external_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        group = Group(
            id=uuid.uuid4(),
            source_platform=platform,
            external_id=item.external_id,
            name=item.name,
            is_approved=True,
            bot_active=True,
        )
        db.add(group)
        await db.flush()
    else:
        if item.name and group.name != item.name:
            group.name = item.name
        group.bot_active = True

    link_result = await db.execute(
        select(PlatformGroupLink).where(
            PlatformGroupLink.platform == platform,
            PlatformGroupLink.group_id == group.id,
        )
    )
    link = link_result.scalar_one_or_none()
    if not link:
        link = PlatformGroupLink(
            id=uuid.uuid4(),
            platform=platform,
            group_id=group.id,
            is_active=True,
            history_loaded=False,
            history_load_progress=0,
            meta=item.metadata or None,
        )
        db.add(link)
    else:
        if item.metadata is not None:
            link.meta = item.metadata
    return link


async def serialize_group_link(
    db: AsyncSession,
    link: PlatformGroupLink,
    group: Group,
) -> dict[str, Any]:
    message_count = await db.scalar(
        select(func.count(Message.id)).where(
            Message.group_id == group.id,
            Message.source_platform == group.source_platform,
        )
    ) or 0

    oldest_message_result = await db.execute(
        select(Message)
        .where(
            Message.group_id == group.id,
            Message.source_platform == group.source_platform,
            Message.external_message_id.is_not(None),
            Message.timestamp.is_not(None),
        )
        .order_by(Message.timestamp.asc(), Message.created_at.asc())
        .limit(1)
    )
    oldest_message = oldest_message_result.scalar_one_or_none()

    return {
        "id": str(link.id),
        "group_id": str(group.id),
        "name": group.name,
        "external_id": group.external_id,
        "source_platform": group.source_platform,
        "history_loaded": link.history_loaded,
        "history_load_progress": link.history_load_progress,
        "last_cursor": link.last_cursor,
        "is_active": link.is_active,
        "metadata": link.meta,
        "oldest_message_id": oldest_message.external_message_id if oldest_message else None,
        "oldest_message_timestamp": oldest_message.timestamp.isoformat() if oldest_message and oldest_message.timestamp else None,
        "message_count": message_count,
    }


@router.get("/{platform}/status")
async def get_platform_status(
    platform: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    platform = ensure_platform(platform)
    state = await db.get(PlatformState, platform)
    groups_count = await db.execute(
        select(PlatformGroupLink).where(PlatformGroupLink.platform == platform)
    )
    rows = groups_count.scalars().all()
    return {
        "platform": platform,
        "status": state.status if state else "inactive",
        "account_identifier": state.account_identifier if state else None,
        "last_error": state.last_error if state else None,
        "meta": state.meta if state else None,
        "groups_total": len(rows),
        "groups_live": len([row for row in rows if row.is_active]),
        "groups_history_loaded": len([row for row in rows if row.history_loaded]),
    }


@router.get("/{platform}/groups")
async def list_platform_groups(
    platform: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    platform = ensure_platform(platform)
    result = await db.execute(
        select(PlatformGroupLink, Group)
        .join(Group, PlatformGroupLink.group_id == Group.id)
        .where(PlatformGroupLink.platform == platform)
        .order_by(Group.name.asc())
    )
    rows = []
    for link, group in result.all():
        rows.append(await serialize_group_link(db, link, group))
    return rows


@router.patch("/{platform}/groups/{group_id}/toggle")
async def toggle_platform_group(
    platform: str,
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    platform = ensure_platform(platform)
    result = await db.execute(
        select(PlatformGroupLink).where(
            PlatformGroupLink.platform == platform,
            PlatformGroupLink.group_id == uuid.UUID(group_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Not found")
    link.is_active = not link.is_active
    await db.commit()
    return {"ok": True, "is_active": link.is_active}


@router.get("/{platform}/groups/internal")
async def list_platform_groups_internal(
    platform: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    platform = ensure_platform(platform)
    result = await db.execute(
        select(PlatformGroupLink, Group)
        .join(Group, PlatformGroupLink.group_id == Group.id)
        .where(
            PlatformGroupLink.platform == platform,
            PlatformGroupLink.is_active.is_(True),
        )
    )
    rows = []
    for link, group in result.all():
        rows.append(await serialize_group_link(db, link, group))
    return rows


@router.post("/{platform}/sync/internal")
async def sync_platform_groups_internal(
    platform: str,
    body: PlatformSyncBody,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    platform = ensure_platform(platform)
    state = await db.get(PlatformState, platform)
    if not state:
        state = PlatformState(platform=platform)
        db.add(state)

    state.account_identifier = body.account_identifier
    state.status = body.status
    state.last_error = body.last_error
    state.meta = body.meta

    links: list[PlatformGroupLink] = []
    for item in body.groups:
        link = await upsert_platform_group(db, platform, item)
        links.append(link)

    await db.commit()
    return {"ok": True, "groups_synced": len(links)}


@router.patch("/{platform}/groups/{group_id}/progress/internal")
async def update_platform_progress_internal(
    platform: str,
    group_id: str,
    body: PlatformProgressBody,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    platform = ensure_platform(platform)
    result = await db.execute(
        select(PlatformGroupLink).where(
            PlatformGroupLink.platform == platform,
            PlatformGroupLink.group_id == uuid.UUID(group_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Not found")

    link.history_load_progress = body.history_load_progress
    if body.last_cursor is not None:
        link.last_cursor = body.last_cursor
    if body.history_loaded:
        link.history_loaded = True
    await db.commit()
    return {"ok": True}
