"""
Endpoint GET/POST для сообщений с фильтрацией.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.models.models import Message, Group, Face
from app.api.deps import get_current_user, require_admin

router = APIRouter()


class MessageOut(BaseModel):
    id: str
    group_id: str
    group_name: Optional[str] = None
    sender_name: Optional[str] = None
    text: Optional[str] = None
    has_photo: bool
    photo_path: Optional[str] = None
    timestamp: Optional[datetime] = None
    imported_from_backup: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=List[MessageOut])
async def list_messages(
    group_id: Optional[str] = Query(None),
    only_with_photo: bool = Query(False),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    filters = []
    if group_id:
        filters.append(Message.group_id == uuid.UUID(group_id))
    if only_with_photo:
        filters.append(Message.has_photo == True)
    if date_from:
        filters.append(Message.timestamp >= date_from)
    if date_to:
        filters.append(Message.timestamp <= date_to)

    stmt = (
        select(Message, Group.name.label("group_name"))
        .join(Group, Message.group_id == Group.id, isouter=True)
        .where(and_(*filters) if filters else True)
        .order_by(Message.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    out = []
    for msg, gname in rows:
        out.append(MessageOut(
            id=str(msg.id),
            group_id=str(msg.group_id),
            group_name=gname,
            sender_name=msg.sender_name,
            text=msg.text,
            has_photo=msg.has_photo,
            photo_path=msg.photo_path,
            timestamp=msg.timestamp,
            imported_from_backup=msg.imported_from_backup,
        ))
    return out


@router.get("/{message_id}/context")
async def get_message_context(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Возвращает сообщение + 2 до и 2 после в той же группе."""
    result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
    msg = result.scalar_one_or_none()
    if not msg:
        return {"error": "Not found"}

    before = await db.execute(
        select(Message)
        .where(Message.group_id == msg.group_id, Message.timestamp < msg.timestamp)
        .order_by(Message.timestamp.desc())
        .limit(2)
    )
    after = await db.execute(
        select(Message)
        .where(Message.group_id == msg.group_id, Message.timestamp > msg.timestamp)
        .order_by(Message.timestamp.asc())
        .limit(2)
    )
    before_list = list(reversed(before.scalars().all()))
    after_list = list(after.scalars().all())

    def serialize(m):
        return {
            "id": str(m.id),
            "text": m.text,
            "has_photo": m.has_photo,
            "photo_path": m.photo_path,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "sender_name": m.sender_name,
        }

    return {
        "before": [serialize(m) for m in before_list],
        "message": serialize(msg),
        "after": [serialize(m) for m in after_list],
    }


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Удаление сообщения и связанных лиц (admin only)."""
    mid = uuid.UUID(message_id)
    result = await db.execute(select(Message).where(Message.id == mid))
    msg = result.scalar_one_or_none()
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Сообщение не найдено")

    # Удаляем связанные очереди и лица
    faces = await db.execute(select(Face).where(Face.message_id == mid))
    for face in faces.scalars().all():
        await db.delete(face)

    await db.delete(msg)
    await db.commit()
    return {"deleted": True, "id": message_id}
