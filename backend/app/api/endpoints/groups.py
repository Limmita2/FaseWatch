"""
Endpoints для управления группами.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import Group, Message
from app.api.deps import get_current_user, require_admin

router = APIRouter()


class GroupOut(BaseModel):
    id: str
    telegram_id: Optional[int] = None
    name: str
    bot_active: bool
    last_message_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[GroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Group).order_by(Group.created_at.desc()))
    groups = result.scalars().all()
    out = []
    for g in groups:
        last = await db.execute(
            select(Message.timestamp)
            .where(Message.group_id == g.id)
            .order_by(Message.timestamp.desc())
            .limit(1)
        )
        last_ts = last.scalar_one_or_none()
        out.append(GroupOut(
            id=str(g.id),
            telegram_id=g.telegram_id,
            name=g.name,
            bot_active=g.bot_active,
            last_message_at=last_ts.isoformat() if last_ts else None,
        ))
    return out


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Удаление группы и всех сообщений (admin only)."""
    from app.models.models import Face
    from fastapi import HTTPException
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
