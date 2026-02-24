"""
CRUD эндпоинты для управления пользователями (только admin).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.core.database import get_db
from app.core.security import hash_password
from app.models.models import User, UserRole
from app.api.deps import require_admin

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"
    description: Optional[str] = None


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Список всех пользователей."""
    result = await db.execute(
        select(User).where(User.username != "admin").order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        UserOut(
            id=str(u.id),
            username=u.username,
            role=u.role.value,
            description=u.description,
        )
        for u in users
    ]


@router.post("/", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Создание пользователя."""
    # Проверяем уникальность
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    try:
        role = UserRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Роль должна быть 'admin' или 'operator'")

    user = User(
        id=uuid.uuid4(),
        username=body.username,
        password_hash=hash_password(body.password),
        role=role,
        description=body.description,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id),
        username=user.username,
        role=user.role.value,
        description=user.description,
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Удаление пользователя (нельзя удалить себя и суперадмина)."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    # Защита суперадмина от удаления
    target = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = target.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.username == "admin":
        raise HTTPException(status_code=403, detail="Нельзя удалить суперадминистратора")



    await db.delete(user)
    await db.commit()
    return {"deleted": True, "id": user_id}
