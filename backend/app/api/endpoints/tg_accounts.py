"""
Endpoints для управления Telegram-аккаунтами (Telethon).
"""
import uuid
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.models.models import TelegramAccount, TelegramAccountGroup, Group, Message
from app.api.deps import require_admin, get_current_user

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    region: Optional[str] = None
    phone: str
    api_id: str
    api_hash: str


class AccountOut(BaseModel):
    id: str
    name: str
    region: Optional[str] = None
    phone: str
    status: str
    is_active: bool
    created_at: Optional[str] = None


class InternalAccountOut(AccountOut):
    api_id: str
    api_hash: str
    session_string: Optional[str] = None


class VerifyCodeBody(BaseModel):
    code: str
    password: Optional[str] = None


class AddGroupBody(BaseModel):
    telegram_group_id: Optional[int] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None


class ProgressBody(BaseModel):
    history_load_progress: int
    last_message_id: Optional[int] = None
    history_loaded: Optional[bool] = False


class DiscoveredGroupOut(BaseModel):
    telegram_id: int
    title: str
    already_connected: bool
    group_id: Optional[str] = None


# ── Helper: check internal API key ───────────────────────────────────────────

def verify_internal_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.TELETHON_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


def serialize_account(account: TelegramAccount) -> AccountOut:
    return AccountOut(
        id=str(account.id),
        name=account.name,
        region=account.region,
        phone=account.phone,
        status=account.status or "pending_auth",
        is_active=account.is_active,
        created_at=account.created_at.isoformat() if account.created_at else None,
    )


def serialize_internal_account(account: TelegramAccount) -> InternalAccountOut:
    public_data = serialize_account(account).model_dump()
    return InternalAccountOut(
        **public_data,
        api_id=account.api_id,
        api_hash=account.api_hash,
        session_string=account.session_string,
    )


def serialize_account_group(link: TelegramAccountGroup, group_name: Optional[str], telegram_id: Optional[int]):
    return {
        "id": str(link.id),
        "group_id": str(link.group_id),
        "group_name": group_name,
        "telegram_id": telegram_id,
        "history_loaded": link.history_loaded,
        "history_load_progress": link.history_load_progress,
        "last_message_id": link.last_message_id,
        "is_active": link.is_active,
    }


def ensure_telegram_group_id(telegram_id: Optional[int]) -> int:
    if telegram_id is None or telegram_id >= 0:
        raise HTTPException(status_code=400, detail="Only Telegram groups/channels with negative telegram_id are supported")
    return telegram_id


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[AccountOut])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccount)
        .where(TelegramAccount.is_active.is_(True))
        .order_by(TelegramAccount.created_at.desc())
    )
    accounts = result.scalars().all()
    return [serialize_account(a) for a in accounts]


@router.get("/internal", response_model=List[InternalAccountOut])
async def list_accounts_internal(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    result = await db.execute(
        select(TelegramAccount).order_by(TelegramAccount.created_at.desc())
    )
    accounts = result.scalars().all()
    return [serialize_internal_account(a) for a in accounts]


@router.post("/")
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    existing = await db.execute(
        select(TelegramAccount).where(TelegramAccount.phone == body.phone)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Account with this phone already exists")

    account = TelegramAccount(
        id=uuid.uuid4(),
        name=body.name,
        region=body.region,
        phone=body.phone,
        api_id=body.api_id,
        api_hash=body.api_hash,
        status="pending_auth",
        is_active=True,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {"id": str(account.id), "status": account.status}


@router.post("/{account_id}/auth/send-code")
async def send_code(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        import redis.asyncio as aioredis

        client = TelegramClient(
            StringSession(account.session_string or ""),
            int(account.api_id),
            account.api_hash,
        )
        await client.connect()
        sent = await client.send_code_request(account.phone)
        phone_code_hash = sent.phone_code_hash
        temp_session_string = client.session.save()
        await client.disconnect()

        # Зберігаємо phone_code_hash разом з тимчасовою session, щоб verify-code
        # продовжив той самий auth flow, а не стартував з порожнього клієнта.
        r = aioredis.from_url(settings.REDIS_URL)
        await r.setex(
            f"tg_auth:{account_id}",
            600,
            json.dumps(
                {
                    "phone_code_hash": phone_code_hash,
                    "session_string": temp_session_string,
                }
            ),
        )
        await r.aclose()

        account.status = "pending_auth"
        account.last_error = None
        await db.commit()

        return {"status": "code_sent"}
    except Exception as e:
        account.last_error = str(e)
        account.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to send code: {e}")


@router.post("/{account_id}/auth/verify-code")
async def verify_code(
    account_id: str,
    body: VerifyCodeBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    r = None
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import (
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            SessionPasswordNeededError,
        )
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        auth_payload = await r.get(f"tg_auth:{account_id}")

        if not auth_payload:
            raise HTTPException(status_code=400, detail="Code expired or not found. Send code again.")

        if isinstance(auth_payload, bytes):
            auth_payload = auth_payload.decode()

        try:
            auth_data = json.loads(auth_payload)
            phone_code_hash = auth_data["phone_code_hash"]
            temp_session_string = auth_data["session_string"]
        except (TypeError, KeyError, json.JSONDecodeError):
            await r.delete(f"tg_auth:{account_id}")
            raise HTTPException(status_code=400, detail="Invalid auth state. Send code again.")

        client = TelegramClient(
            StringSession(temp_session_string or ""),
            int(account.api_id),
            account.api_hash,
        )
        await client.connect()

        try:
            await client.sign_in(
                phone=account.phone,
                code=body.code,
                phone_code_hash=phone_code_hash,
            )
        except (PhoneCodeExpiredError, PhoneCodeInvalidError):
            await client.disconnect()
            account.status = "pending_auth"
            account.last_error = None
            await db.commit()
            await r.delete(f"tg_auth:{account_id}")
            message = "Code expired. Send a new code and try again."
            raise HTTPException(status_code=400, detail=message)
        except SessionPasswordNeededError:
            if not body.password:
                await client.disconnect()
                raise HTTPException(status_code=400, detail="2FA password required")
            await client.sign_in(password=body.password)

        session_string = client.session.save()
        await client.disconnect()

        account.session_string = session_string
        account.status = "active"
        account.last_error = None
        await db.commit()
        await r.delete(f"tg_auth:{account_id}")

        return {"status": "authenticated"}
    except HTTPException:
        raise
    except Exception as e:
        account.last_error = str(e)
        account.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Auth failed: {e}")
    finally:
        if r is not None:
            await r.aclose()


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    await db.execute(
        update(Message)
        .where(Message.source_account_id == account.id)
        .values(source_account_id=None)
    )
    await db.execute(
        delete(TelegramAccountGroup).where(TelegramAccountGroup.account_id == account.id)
    )
    await db.delete(account)
    await db.commit()
    return {"ok": True}


@router.get("/{account_id}/groups")
async def list_account_groups(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(
            TelegramAccountGroup,
            Group.name.label("group_name"),
            Group.telegram_id.label("telegram_id"),
        )
        .join(Group, TelegramAccountGroup.group_id == Group.id)
        .where(
            TelegramAccountGroup.account_id == uuid.UUID(account_id),
            TelegramAccountGroup.is_active.is_(True),
        )
        .order_by(TelegramAccountGroup.joined_at.desc())
    )
    rows = result.all()
    return [
        serialize_account_group(r.TelegramAccountGroup, r.group_name, r.telegram_id)
        for r in rows
    ]


@router.get("/{account_id}/discover-groups", response_model=List[DiscoveredGroupOut])
async def discover_account_groups(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not account.session_string:
        raise HTTPException(status_code=400, detail="Account is not authenticated yet")

    attached_rows = await db.execute(
        select(Group.telegram_id, Group.id)
        .join(TelegramAccountGroup, TelegramAccountGroup.group_id == Group.id)
        .where(
            TelegramAccountGroup.account_id == uuid.UUID(account_id),
            TelegramAccountGroup.is_active.is_(True),
        )
    )
    attached_by_telegram_id = {
        int(telegram_id): str(group_id)
        for telegram_id, group_id in attached_rows.all()
        if telegram_id is not None
    }

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(account.session_string),
            int(account.api_id),
            account.api_hash,
        )
        await client.connect()

        discovered_groups: list[DiscoveredGroupOut] = []
        async for dialog in client.iter_dialogs():
            telegram_id = int(dialog.id)
            if telegram_id >= 0:
                continue

            title = (dialog.name or "").strip() or str(telegram_id)
            discovered_groups.append(
                DiscoveredGroupOut(
                    telegram_id=telegram_id,
                    title=title,
                    already_connected=telegram_id in attached_by_telegram_id,
                    group_id=attached_by_telegram_id.get(telegram_id),
                )
            )

        await client.disconnect()
        return discovered_groups
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover groups: {e}")


@router.get("/{account_id}/groups/internal")
async def list_account_groups_internal(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    result = await db.execute(
        select(
            TelegramAccountGroup,
            Group.name.label("group_name"),
            Group.telegram_id.label("telegram_id"),
        )
        .join(Group, TelegramAccountGroup.group_id == Group.id)
        .where(
            TelegramAccountGroup.account_id == uuid.UUID(account_id),
            TelegramAccountGroup.is_active.is_(True),
        )
        .order_by(TelegramAccountGroup.joined_at.desc())
    )
    rows = result.all()
    return [
        serialize_account_group(r.TelegramAccountGroup, r.group_name, r.telegram_id)
        for r in rows
    ]


@router.post("/{account_id}/groups")
async def add_account_group(
    account_id: str,
    body: AddGroupBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    acc_uuid = uuid.UUID(account_id)

    # Знайти або створити групу
    group = None
    if body.group_id:
        res = await db.execute(select(Group).where(Group.id == uuid.UUID(body.group_id)))
        group = res.scalar_one_or_none()
        if group:
            ensure_telegram_group_id(group.telegram_id)
    elif body.telegram_group_id:
        telegram_group_id = ensure_telegram_group_id(body.telegram_group_id)
        res = await db.execute(select(Group).where(Group.telegram_id == telegram_group_id))
        group = res.scalar_one_or_none()
        if not group:
            group = Group(
                id=uuid.uuid4(),
                telegram_id=telegram_group_id,
                source_platform="telegram",
                external_id=str(telegram_group_id),
                name=(body.group_name or f"Group {telegram_group_id}"),
                is_approved=True,
            )
            db.add(group)
            await db.commit()
            await db.refresh(group)
        elif body.group_name and group.name != body.group_name:
            group.name = body.group_name
            await db.commit()
        elif group.external_id != str(telegram_group_id) or group.source_platform != "telegram":
            group.external_id = str(telegram_group_id)
            group.source_platform = "telegram"
            await db.commit()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Перевірити чи вже є зв'язок
    existing = await db.execute(
        select(TelegramAccountGroup).where(
            TelegramAccountGroup.account_id == acc_uuid,
            TelegramAccountGroup.group_id == group.id,
        )
    )
    link = existing.scalar_one_or_none()
    if link:
        link.is_active = True
        await db.commit()
        return {"id": str(link.id), "group_id": str(group.id)}

    link = TelegramAccountGroup(
        id=uuid.uuid4(),
        account_id=acc_uuid,
        group_id=group.id,
        history_loaded=False,
        history_load_progress=0,
    )
    db.add(link)
    await db.commit()
    return {"id": str(link.id), "group_id": str(group.id)}


@router.delete("/{account_id}/groups/{group_id}")
async def remove_account_group(
    account_id: str,
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(TelegramAccountGroup).where(
            TelegramAccountGroup.account_id == uuid.UUID(account_id),
            TelegramAccountGroup.group_id == uuid.UUID(group_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Not found")
    link.is_active = False
    await db.commit()
    return {"ok": True}


@router.patch("/{account_id}/groups/{group_id}/progress")
async def update_progress(
    account_id: str,
    group_id: str,
    body: ProgressBody,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_key),
):
    result = await db.execute(
        select(TelegramAccountGroup).where(
            TelegramAccountGroup.account_id == uuid.UUID(account_id),
            TelegramAccountGroup.group_id == uuid.UUID(group_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Not found")

    link.history_load_progress = body.history_load_progress
    if body.last_message_id is not None:
        link.last_message_id = body.last_message_id
    if body.history_loaded:
        link.history_loaded = True
    await db.commit()
    return {"ok": True}
