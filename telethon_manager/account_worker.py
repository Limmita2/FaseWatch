"""
AccountWorker — слухає нові повідомлення через Telethon.
"""
import asyncio
import logging
import os
from zoneinfo import ZoneInfo

import httpx
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, Channel
from telethon.utils import get_peer_id

from document_parser import extract_document_text

logger = logging.getLogger("account_worker")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
LOCAL_TZ = ZoneInfo("Europe/Kyiv")
POLL_INTERVAL_SECONDS = 15  # polling interval for channels/supergroups


class AccountWorker:
    def __init__(self, account: dict, groups: list):
        self.account = account
        self.account_id = account["id"]
        self.client = TelegramClient(
            StringSession(account.get("session_string") or ""),
            int(account["api_id"]),
            account["api_hash"],
        )
        self._running = False
        self._task = None
        self._handler_registered = False
        self.allowed_chat_ids: set[int] = set()
        # Храним last_message_id для каждой группы (для polling)
        self.group_last_msg_id: dict[int, int] = {}
        # Telegram entity cache: chat_id -> entity
        self._group_entities: dict[int, object] = {}
        self.update_groups(groups)

    def update_groups(self, groups: list):
        self.groups = groups
        self.allowed_chat_ids = {
            int(group["telegram_id"])
            for group in groups
            if (
                group.get("is_active")
                and group.get("history_loaded")
                and group.get("telegram_id") is not None
                and int(group["telegram_id"]) < 0
            )
        }
        # Обновляем last_message_id из БД для polling
        for group in groups:
            tid = int(group["telegram_id"])
            if tid in self.allowed_chat_ids:
                last_id = group.get("last_message_id")
                if last_id:
                    self.group_last_msg_id[tid] = int(last_id)

    async def connect(self):
        if self.client.is_connected():
            return
        logger.info(f"[{self.account['phone']}] Connecting for history sync...")
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(f"Account {self.account['phone']} is not authorized")

    async def start_live(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self.client.is_connected():
            await self.client.disconnect()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run_loop(self):
        """Основной цикл: только polling для каналов/супергрупп.

        Telethon events.NewMessage не работает для каналов, поэтому
        polling — основной механизм доставки новых сообщений.
        """
        while self._running:
            try:
                await self.connect()
                logger.info(f"[{self.account['phone']}] Live polling enabled.")
                await self._poll_groups()  # начальный проход
                await self._poll_loop()
            except Exception as e:
                if self._running:
                    logger.error(f"[{self.account['phone']}] Error: {e}. Reconnecting in 10s...")
                    await asyncio.sleep(10)

    async def _poll_loop(self):
        """Периодический polling новых сообщений для каналов/супергрупп.

        Telethon events.NewMessage не работает для каналов, поэтому
        polling через iter_messages с min_id.
        """
        while self._running:
            try:
                await self._poll_groups()
            except Exception as e:
                logger.error(f"[{self.account['phone']}] Poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _poll_groups(self):
        """Проверяет новые сообщения во всех группах."""
        for group in self.groups:
            if not self._running:
                break

            tid = int(group.get("telegram_id") or 0)
            if tid not in self.allowed_chat_ids:
                continue

            last_id = self.group_last_msg_id.get(tid, 0)

            try:
                if tid not in self._group_entities:
                    self._group_entities[tid] = await self.client.get_entity(tid)

                entity = self._group_entities[tid]

                async for msg in self.client.iter_messages(
                    entity, limit=50, min_id=last_id, reverse=False
                ):
                    if not msg or msg.id <= last_id:
                        continue

                    try:
                        await self._handle_message_obj(msg, tid, entity)
                        self.group_last_msg_id[tid] = msg.id
                    except Exception as e:
                        logger.error(f"Handler error for msg {msg.id}: {e}")

            except Exception as e:
                logger.debug(f"Poll group {tid} error: {e}")

    async def _handle_message_obj(self, msg, chat_id, chat):
        """Обрабатывает одно сообщение."""
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

        chat_title = getattr(chat, "title", str(chat_id))

        base_data = {
            "group_telegram_id": str(chat_id),
            "group_name": chat_title,
            "message_id": str(msg.id),
            "sender_telegram_id": str(msg.sender_id or ""),
            "sender_name": sender_name,
            "timestamp": ts or "",
            "source_account_id": self.account_id,
            "source_type": "account",
        }

        # Фото
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            try:
                file_bytes = await self.client.download_media(msg.media, bytes)
                if file_bytes:
                    base_data["text"] = msg.message or ""
                    await self._post_with_photo(base_data, file_bytes)
                    return
            except Exception as e:
                logger.error(f"Photo download error: {e}")

        # Документ (PDF / DOCX)
        if msg.media and isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            filename = ""
            for attr in doc.attributes:
                if hasattr(attr, "file_name"):
                    filename = attr.file_name
                    break

            if filename.lower().endswith((".pdf", ".docx")):
                try:
                    file_bytes = await self.client.download_media(msg.media, bytes)
                    if file_bytes:
                        doc_text = extract_document_text(file_bytes, filename)
                        if doc_text:
                            base_data["text"] = msg.message or ""
                            base_data["document_text"] = doc_text
                            base_data["document_name"] = filename
                            await self._post_json(base_data)
                            return
                except Exception as e:
                    logger.error(f"Doc download error: {e}")

        # Текст
        if msg.message:
            base_data["text"] = msg.message
            await self._post_json(base_data)

    def _register_handlers(self):
        if self._handler_registered:
            return

        client = self.client

        @client.on(events.NewMessage)
        async def handler(event):
            try:
                await self._handle_message(event)
            except Exception as e:
                logger.error(f"Handler error: {e}")

        self._handler_registered = True

    async def _handle_message(self, event):
        msg = event.message
        chat = await event.get_chat()
        chat_id = get_peer_id(chat) if chat is not None else event.chat_id

        if chat_id is None or int(chat_id) not in self.allowed_chat_ids:
            return

        ts = None
        if msg.date:
            ts = msg.date.astimezone(LOCAL_TZ).replace(tzinfo=None).isoformat()

        base_data = {
            "group_telegram_id": str(chat_id),
            "group_name": getattr(chat, "title", str(chat_id)),
            "message_id": str(msg.id),
            "sender_telegram_id": str(msg.sender_id or ""),
            "sender_name": "",
            "timestamp": ts or "",
            "source_account_id": self.account_id,
            "source_type": "account",
        }

        # Спробуємо отримати ім'я відправника
        try:
            sender = await event.get_sender()
            if sender:
                full_name = " ".join(filter(None, [
                    getattr(sender, "first_name", ""),
                    getattr(sender, "last_name", ""),
                ]))
                base_data["sender_name"] = full_name
        except Exception:
            pass

        # Фото
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            try:
                file_bytes = await self.client.download_media(msg.media, bytes)
                if file_bytes:
                    base_data["text"] = msg.message or ""
                    await self._post_with_photo(base_data, file_bytes)
                    return
            except Exception as e:
                logger.error(f"Photo download error: {e}")

        # Документ (PDF / DOCX)
        if msg.media and isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            filename = ""
            for attr in doc.attributes:
                if hasattr(attr, "file_name"):
                    filename = attr.file_name
                    break

            if filename.lower().endswith((".pdf", ".docx")):
                try:
                    file_bytes = await self.client.download_media(msg.media, bytes)
                    if file_bytes:
                        doc_text = extract_document_text(file_bytes, filename)
                        if doc_text:
                            base_data["text"] = msg.message or ""
                            base_data["document_text"] = doc_text
                            base_data["document_name"] = filename
                            await self._post_json(base_data)
                            return
                except Exception as e:
                    logger.error(f"Doc download error: {e}")

        # Текст
        if msg.message:
            base_data["text"] = msg.message
            await self._post_json(base_data)

    async def _post_json(self, data: dict):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{BACKEND_URL}/api/bot/message", data=data)
                logger.debug(f"Posted text: {resp.status_code}")
        except Exception as e:
            logger.error(f"Post error: {e}")

    async def _post_with_photo(self, data: dict, photo_bytes: bytes):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                files = {"photo": ("photo.jpg", photo_bytes, "image/jpeg")}
                resp = await client.post(f"{BACKEND_URL}/api/bot/message", data=data, files=files)
                logger.debug(f"Posted photo: {resp.status_code}")
        except Exception as e:
            logger.error(f"Post photo error: {e}")
