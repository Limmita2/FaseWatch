"""
Endpoints для управления группами.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import Group, Message
from app.api.deps import get_current_user, require_admin

router = APIRouter()


class GroupOut(BaseModel):
    id: str
    telegram_id: Optional[int] = None
    source_platform: str = "telegram"
    external_id: Optional[str] = None
    name: str
    bot_active: bool
    is_public: bool = True
    notes: Optional[str] = None
    last_message_at: Optional[str] = None

    class Config:
        from_attributes = True


class GroupNotesUpdate(BaseModel):
    notes: Optional[str] = None


@router.get("/", response_model=List[GroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    last_message_subq = (
        select(
            Message.group_id.label("group_id"),
            func.max(Message.timestamp).label("last_message_at"),
        )
        .group_by(Message.group_id)
        .subquery()
    )

    stmt = (
        select(Group, last_message_subq.c.last_message_at)
        .outerjoin(last_message_subq, last_message_subq.c.group_id == Group.id)
    )
    if user.role != "admin":
        stmt = stmt.where(Group.is_public == True)
    stmt = stmt.order_by(Group.created_at.desc())

    result = await db.execute(stmt)
    out = []
    for g, last_ts in result.all():
        out.append(GroupOut(
            id=str(g.id),
            telegram_id=g.telegram_id,
            source_platform=g.source_platform or "telegram",
            external_id=g.external_id,
            name=g.name,
            bot_active=g.bot_active,
            is_public=g.is_public,
            notes=g.notes,
            last_message_at=last_ts.isoformat() if last_ts else None,
        ))
    return out


@router.patch("/{group_id}/notes")
async def update_group_notes(
    group_id: str,
    body: GroupNotesUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Оновлення нотаток групи. Доступно всім авторизованим користувачам."""
    import uuid
    gid = uuid.UUID(group_id)
    result = await db.execute(select(Group).where(Group.id == gid))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Групу не знайдено")

    group.notes = body.notes
    await db.commit()
    return {"id": group_id, "notes": group.notes}


@router.patch("/{group_id}/toggle-public")
async def toggle_group_public(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    """Изменение видимости группы. Только для юзера с логином admin."""
    import uuid

    if user.username != "admin":
        raise HTTPException(status_code=403, detail="Только пользователь admin может менять видимость")

    gid = uuid.UUID(group_id)
    result = await db.execute(select(Group).where(Group.id == gid))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    group.is_public = not group.is_public
    await db.commit()
    return {"id": group_id, "is_public": group.is_public}


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Удаление группы и всех сообщений (admin only)."""
    from app.models.models import Face
    import uuid

    gid = uuid.UUID(group_id)
    result = await db.execute(select(Group).where(Group.id == gid))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    # Удаляем сообщения и связанные данные
    messages = await db.execute(select(Message).where(Message.group_id == gid))
    for msg in messages.scalars().all():
        faces = await db.execute(select(Face).where(Face.message_id == msg.id))
        for face in faces.scalars().all():
            await db.delete(face)
        await db.delete(msg)

    await db.delete(group)
    await db.commit()
    return {"deleted": True, "id": group_id}
