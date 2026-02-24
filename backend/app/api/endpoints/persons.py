"""
Endpoints для управления персонами: список, карточка, объединение, разъединение.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.models.models import Person, Face
from app.api.deps import get_current_user, require_admin

router = APIRouter()


class PersonOut(BaseModel):
    id: str
    display_name: Optional[str] = None
    confirmed: bool
    face_count: int = 0

    class Config:
        from_attributes = True


class PersonUpdate(BaseModel):
    display_name: Optional[str] = None
    confirmed: Optional[bool] = None


class MergeRequest(BaseModel):
    source_person_id: str
    target_person_id: str


@router.get("/", response_model=List[PersonOut])
async def list_persons(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Person).order_by(Person.created_at.desc()))
    persons = result.scalars().all()
    out = []
    for p in persons:
        face_result = await db.execute(select(Face).where(Face.person_id == p.id))
        face_count = len(face_result.scalars().all())
        out.append(PersonOut(
            id=str(p.id),
            display_name=p.display_name,
            confirmed=p.confirmed,
            face_count=face_count,
        ))
    return out


@router.get("/{person_id}")
async def get_person(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Person).where(Person.id == uuid.UUID(person_id)))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Персона не найдена")

    faces_result = await db.execute(select(Face).where(Face.person_id == person.id))
    faces = faces_result.scalars().all()

    return {
        "id": str(person.id),
        "display_name": person.display_name,
        "confirmed": person.confirmed,
        "faces": [
            {
                "id": str(f.id),
                "crop_path": f.crop_path,
                "message_id": str(f.message_id) if f.message_id else None,
                "confidence": f.confidence,
            }
            for f in faces
        ],
    }


@router.patch("/{person_id}")
async def update_person(
    person_id: str,
    body: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Person).where(Person.id == uuid.UUID(person_id)))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Персона не найдена")

    if body.display_name is not None:
        person.display_name = body.display_name
    if body.confirmed is not None:
        person.confirmed = body.confirmed

    await db.commit()
    return {"id": str(person.id), "display_name": person.display_name}


@router.post("/merge")
async def merge_persons(
    body: MergeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Объединяет все лица source -> target, удаляет source."""
    source_id = uuid.UUID(body.source_person_id)
    target_id = uuid.UUID(body.target_person_id)

    faces_result = await db.execute(select(Face).where(Face.person_id == source_id))
    for face in faces_result.scalars().all():
        face.person_id = target_id

    source_result = await db.execute(select(Person).where(Person.id == source_id))
    source = source_result.scalar_one_or_none()
    if source:
        await db.delete(source)

    await db.commit()
    return {"merged": True, "target_person_id": str(target_id)}


@router.delete("/{person_id}")
async def delete_person(
    person_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Удаление персоны и всех связанных лиц (admin only)."""
    from app.models.models import IdentificationQueue
    pid = uuid.UUID(person_id)

    # Удаляем записи в очереди
    queue_result = await db.execute(
        select(IdentificationQueue).join(Face).where(Face.person_id == pid)
    )
    for q in queue_result.scalars().all():
        await db.delete(q)

    # Удаляем лица
    faces_result = await db.execute(select(Face).where(Face.person_id == pid))
    for face in faces_result.scalars().all():
        await db.delete(face)

    # Удаляем персону
    result = await db.execute(select(Person).where(Person.id == pid))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Персона не найдена")
    await db.delete(person)

    await db.commit()
    return {"deleted": True, "id": person_id}
