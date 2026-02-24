"""
Endpoints для очереди идентификации: список pending, подтвердить/отклонить.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import uuid

from app.core.database import get_db
from app.models.models import IdentificationQueue, IdentificationStatus, Face
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/")
async def list_queue(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(IdentificationQueue)
        .where(IdentificationQueue.status == IdentificationStatus.pending)
        .order_by(IdentificationQueue.created_at.desc())
    )
    items = result.scalars().all()
    return [
        {
            "id": str(item.id),
            "face_id": str(item.face_id),
            "suggested_person_id": str(item.suggested_person_id) if item.suggested_person_id else None,
            "similarity": item.similarity,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in items
    ]


@router.post("/{queue_id}/confirm")
async def confirm_identification(
    queue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IdentificationQueue).where(IdentificationQueue.id == uuid.UUID(queue_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    item.status = IdentificationStatus.confirmed
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.utcnow()

    # Привязываем лицо к персоне
    face_result = await db.execute(select(Face).where(Face.id == item.face_id))
    face = face_result.scalar_one_or_none()
    if face:
        face.person_id = item.suggested_person_id

    await db.commit()
    return {"status": "confirmed"}


@router.post("/{queue_id}/reject")
async def reject_identification(
    queue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(IdentificationQueue).where(IdentificationQueue.id == uuid.UUID(queue_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    item.status = IdentificationStatus.rejected
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.utcnow()

    # Создаём новую персону для этого лица
    from app.models.models import Person
    new_person = Person(id=uuid.uuid4())
    db.add(new_person)
    await db.flush()

    face_result = await db.execute(select(Face).where(Face.id == item.face_id))
    face = face_result.scalar_one_or_none()
    if face:
        face.person_id = new_person.id

    await db.commit()
    return {"status": "rejected", "new_person_id": str(new_person.id)}
