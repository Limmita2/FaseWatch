"""
history_loader.py — завантаження історії груп через Telethon.
"""
import logging
import os

import httpx
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.utils import get_peer_id
from zoneinfo import ZoneInfo

from document_parser import extract_document_text

logger = logging.getLogger("history_loader")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
TELETHON_API_KEY = os.getenv("TELETHON_API_KEY", "")
LOCAL_TZ = ZoneInfo("Europe/Kyiv")


async def load_group_history(
    client: TelegramClient,
    account_id: str,
    group_id: str,
    tg_entity,
    last_message_id: int = None,
):
    """Завантажує та надсилає в backend повідомлення з групи."""
    logger.info(f"Starting history load: account={account_id} group={group_id}")
    chat_title = getattr(tg_entity, "title", str(tg_entity.id))
    chat_id = get_peer_id(tg_entity)

    count = 0
    last_seen_msg_id = last_message_id

    async for msg in client.iter_messages(tg_entity, limit=None, reverse=True,
                                          min_id=last_message_id or 0):
        if not msg:
            continue

        ts = None
        if msg.date:
            ts = msg.date.astimezone(LOCAL_TZ).replace(tzinfo=None).isoformat()

        sender_name = ""
        try:
            sender = await msg.get_sender()
            if sender:
                sender_name = " ".join(filter(None, [
                    getattr(sender, "first_name", ""),
                    getattr(sender, "last_name", ""),
                ]))
        except Exception:
            pass

        base_data = {
            "group_telegram_id": str(chat_id),
            "group_name": chat_title,
            "message_id": str(msg.id),
            "sender_telegram_id": str(msg.sender_id or ""),
            "sender_name": sender_name,
            "timestamp": ts or "",
            "source_account_id": account_id,
            "source_type": "account",
        }

        posted = False
        # Фото
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            try:
                file_bytes = await client.download_media(msg.media, bytes)
                if file_bytes:
                    base_data["text"] = msg.message or ""
                    async with httpx.AsyncClient(timeout=60) as hclient:
                        files = {"photo": ("photo.jpg", file_bytes, "image/jpeg")}
                        response = await hclient.post(
                            f"{BACKEND_URL}/api/bot/message",
                            data=base_data,
                            files=files,
                        )
                        if response.status_code >= 400:
                            logger.error(f"Photo post failed: {response.status_code} {response.text}")
                    posted = True
            except Exception as e:
                logger.error(f"Photo download error in history: {e}")

        # Документ
        if not posted and msg.media and isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            filename = ""
            for attr in doc.attributes:
                if hasattr(attr, "file_name"):
                    filename = attr.file_name
                    break
            if filename.lower().endswith((".pdf", ".docx")):
                try:
                    file_bytes = await client.download_media(msg.media, bytes)
                    if file_bytes:
                        doc_text = extract_document_text(file_bytes, filename)
                        if doc_text:
                            base_data["text"] = msg.message or ""
                            base_data["document_text"] = doc_text
                            base_data["document_name"] = filename
                            async with httpx.AsyncClient(timeout=30) as hclient:
                                response = await hclient.post(
                                    f"{BACKEND_URL}/api/bot/message",
                                    data=base_data,
                                )
                                if response.status_code >= 400:
                                    logger.error(f"Document post failed: {response.status_code} {response.text}")
                            posted = True
                except Exception as e:
                    logger.error(f"Doc download error in history: {e}")

        # Текст
        if not posted and msg.message:
            base_data["text"] = msg.message
            try:
                async with httpx.AsyncClient(timeout=30) as hclient:
                    response = await hclient.post(f"{BACKEND_URL}/api/bot/message", data=base_data)
                    if response.status_code >= 400:
                        logger.error(f"Text post failed: {response.status_code} {response.text}")
            except Exception as e:
                logger.error(f"Post text error: {e}")

        count += 1
        last_seen_msg_id = msg.id

        if count % 100 == 0:
            logger.info(f"History progress: {count} messages for group {group_id}")
            await _update_progress(account_id, group_id, count, last_seen_msg_id)

    # Завершення
    logger.info(f"History load complete: {count} messages for group {group_id}")
    await _update_progress(account_id, group_id, count, last_seen_msg_id, done=True)


async def _update_progress(
    account_id: str,
    group_id: str,
    progress: int,
    last_msg_id: int = None,
    done: bool = False,
):
    try:
        payload = {
            "history_load_progress": progress,
            "last_message_id": last_msg_id,
            "history_loaded": done,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(
                f"{BACKEND_URL}/api/tg-accounts/{account_id}/groups/{group_id}/progress",
                json=payload,
                headers={"X-Api-Key": TELETHON_API_KEY},
            )
            if response.status_code >= 400:
                logger.error(f"Progress update failed: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Progress update error: {e}")
