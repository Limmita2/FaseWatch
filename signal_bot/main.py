import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import httpx
import websockets
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("facewatch_signal_bot")

load_dotenv()

SIGNAL_NUMBER = os.getenv("SIGNAL_NUMBER", "").strip()
SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://facewatch_signal:8080").rstrip("/")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend:8000").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "").strip()
INTERNAL_API_KEY = os.getenv("TELETHON_API_KEY", "").strip()
RECONNECT_DELAY = 5
REFRESH_INTERVAL = 30

tracked_groups: dict[str, dict] = {}
history_progress: dict[str, dict] = {}
history_deadline: datetime | None = None


def build_ws_url() -> str:
    base = SIGNAL_API_URL
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return f"{base}/v1/receive/{quote(SIGNAL_NUMBER, safe='')}"


def get_nested(data: dict, *path: str):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_timestamp(raw_value) -> str:
    if raw_value is None:
        return datetime.now(timezone.utc).isoformat()

    if isinstance(raw_value, (int, float)):
        # signal-cli обычно отдает миллисекунды.
        value = float(raw_value)
        if value > 10_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()

    value = str(raw_value).strip()
    if not value:
        return datetime.now(timezone.utc).isoformat()
    return value


def parse_signal_event(payload: dict) -> dict | None:
    envelope = payload.get("envelope") if isinstance(payload, dict) else None
    if not isinstance(envelope, dict):
        return None

    data_message = first_non_empty(
        envelope.get("dataMessage"),
        get_nested(envelope, "syncMessage", "sentMessage"),
        payload.get("dataMessage"),
    )
    if not isinstance(data_message, dict):
        return None

    group_info = first_non_empty(
        data_message.get("groupInfo"),
        data_message.get("groupV2"),
    )
    if not isinstance(group_info, dict):
        return None

    sender_number = str(
        first_non_empty(
            envelope.get("sourceNumber"),
            envelope.get("source"),
            get_nested(payload, "sender", "number"),
        ) or ""
    ).strip()
    if not sender_number:
        return None

    if sender_number == SIGNAL_NUMBER:
        logger.info("Пропущено собственное исходящее сообщение Signal")
        return None

    group_id = str(
        first_non_empty(
            group_info.get("groupId"),
            group_info.get("id"),
            group_info.get("groupV2Id"),
        ) or ""
    ).strip()
    if not group_id:
        return None

    attachments = data_message.get("attachments") or []
    image_attachment = None
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        content_type = str(attachment.get("contentType") or "").lower()
        if content_type.startswith("image/"):
            image_attachment = attachment
            break

    text_value = first_non_empty(
        data_message.get("message"),
        data_message.get("body"),
        data_message.get("text"),
    )

    return {
        "group_id": group_id,
        "group_name": str(first_non_empty(group_info.get("title"), group_info.get("name")) or group_id),
        "message_id": str(
            first_non_empty(
                envelope.get("timestamp"),
                data_message.get("timestamp"),
                payload.get("timestamp"),
            ) or ""
        ),
        "sender_id": sender_number,
        "sender_name": str(first_non_empty(envelope.get("sourceName"), sender_number)),
        "text": str(text_value or ""),
        "timestamp": normalize_timestamp(
            first_non_empty(
                envelope.get("timestamp"),
                data_message.get("timestamp"),
                payload.get("timestamp"),
            )
        ),
        "attachment": image_attachment,
    }


async def send_to_backend(data: dict, photo_bytes: bytes | None = None, filename: str = "signal.jpg") -> dict | None:
    headers = {}
    if BOT_API_KEY:
        headers["X-API-Key"] = BOT_API_KEY

    for attempt in range(1, 6):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                if photo_bytes is not None:
                    response = await client.post(
                        f"{BACKEND_API_URL}/api/bot/message",
                        data=data,
                        files={"photo": (filename, photo_bytes, "image/jpeg")},
                        headers=headers,
                    )
                else:
                    response = await client.post(
                        f"{BACKEND_API_URL}/api/bot/message",
                        data=data,
                        headers=headers,
                    )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            if attempt == 5:
                logger.error("Ошибка отправки в backend после %d попыток: %s", attempt, exc)
                return None
            logger.warning("Backend недоступен, повтор %d/5: %s", attempt, exc)
            await asyncio.sleep(2)
    return None


def get_internal_headers() -> dict[str, str]:
    headers = {}
    if INTERNAL_API_KEY:
        headers["X-Api-Key"] = INTERNAL_API_KEY
    return headers


async def refresh_tracked_groups():
    global tracked_groups
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BACKEND_API_URL}/api/platforms/signal/groups/internal",
                headers=get_internal_headers(),
            )
            response.raise_for_status()
            tracked_groups = {
                item["external_id"]: item
                for item in response.json()
            }
    except Exception as exc:
        logger.error("Не удалось обновить список активных Signal-групп: %s", exc)


async def fetch_signal_groups() -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{SIGNAL_API_URL}/v1/groups/{quote(SIGNAL_NUMBER, safe='')}")
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("groups", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


async def sync_discovered_groups(status: str = "active", last_error: str | None = None):
    if not SIGNAL_NUMBER:
        return

    groups_payload: list[dict] = []
    try:
        raw_groups = await fetch_signal_groups()
        for item in raw_groups:
            if not isinstance(item, dict):
                continue
            external_id = str(first_non_empty(item.get("id"), item.get("groupId"), item.get("internal_id")) or "").strip()
            if not external_id:
                continue
            name = str(first_non_empty(item.get("name"), item.get("title"), external_id))
            groups_payload.append({
                "external_id": external_id,
                "name": name,
                "metadata": item,
            })
    except Exception as exc:
        logger.error("Не удалось получить список Signal-групп: %s", exc)
        status = "error"
        last_error = str(exc)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/platforms/signal/sync/internal",
                headers=get_internal_headers(),
                json={
                    "account_identifier": SIGNAL_NUMBER,
                    "status": status,
                    "last_error": last_error,
                    "groups": groups_payload,
                },
            )
            response.raise_for_status()
    except Exception as exc:
        logger.error("Не удалось синхронизировать Signal discovery с backend: %s", exc)
        return

    await refresh_tracked_groups()


async def update_group_progress(group_db_id: str, progress: int, last_cursor: str | None, done: bool = False):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(
                f"{BACKEND_API_URL}/api/platforms/signal/groups/{group_db_id}/progress/internal",
                headers=get_internal_headers(),
                json={
                    "history_load_progress": progress,
                    "last_cursor": last_cursor,
                    "history_loaded": done,
                },
            )
            response.raise_for_status()
    except Exception as exc:
        logger.error("Не удалось обновить прогресс Signal: %s", exc)


async def finalize_signal_history():
    for external_id, group in tracked_groups.items():
        current = history_progress.get(
            external_id,
            {"count": group.get("history_load_progress", 0), "last_cursor": group.get("last_cursor")},
        )
        await update_group_progress(group["group_id"], current["count"], current["last_cursor"], True)
    await refresh_tracked_groups()


async def download_attachment(attachment: dict) -> tuple[bytes, str] | None:
    attachment_id = first_non_empty(attachment.get("id"), attachment.get("attachmentId"))
    if attachment_id is None:
        return None

    filename = str(first_non_empty(attachment.get("filename"), attachment.get("id")) or "signal")
    content_type = str(attachment.get("contentType") or "image/jpeg")
    extension = "jpg"
    if "/" in content_type:
        extension = content_type.split("/", 1)[1].split(";", 1)[0] or "jpg"
    final_name = f"{filename}.{extension}" if "." not in filename else filename

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(f"{SIGNAL_API_URL}/v1/attachments/{attachment_id}")
        response.raise_for_status()
        return response.content, final_name


async def process_event(payload: dict):
    parsed = parse_signal_event(payload)
    if not parsed:
        return

    tracked_group = tracked_groups.get(parsed["group_id"])
    if not tracked_group or not tracked_group.get("is_active"):
        return

    source_type = "bot"
    if history_deadline and datetime.now(timezone.utc) <= history_deadline:
        source_type = "history"

    backend_payload = {
        "group_external_id": parsed["group_id"],
        "group_name": tracked_group.get("name") or parsed["group_name"],
        "message_id": parsed["message_id"],
        "sender_external_id": parsed["sender_id"],
        "sender_name": parsed["sender_name"],
        "text": parsed["text"],
        "timestamp": parsed["timestamp"],
        "source_platform": "signal",
        "source_type": source_type,
    }

    if parsed["attachment"]:
        logger.info(
            "Signal фото: group=%s sender=%s text=%s",
            parsed["group_name"],
            parsed["sender_name"],
            parsed["text"][:80],
        )
        try:
            attachment_data = await download_attachment(parsed["attachment"])
            if not attachment_data:
                logger.warning("Не удалось определить attachment id для сообщения %s", parsed["message_id"])
                return
            photo_bytes, filename = attachment_data
            result = await send_to_backend(backend_payload, photo_bytes=photo_bytes, filename=filename)
            logger.info("Signal фото отправлено в backend: %s", result)
        except Exception as exc:
            logger.exception("Ошибка обработки Signal attachment: %s", exc)
        return

    logger.info(
        "Signal текст: group=%s sender=%s text=%s",
        parsed["group_name"],
        parsed["sender_name"],
        parsed["text"][:120],
    )
    result = await send_to_backend(backend_payload)
    logger.info("Signal текст отправлен в backend: %s", result)

    if source_type == "history":
        current = history_progress.get(parsed["group_id"], {"count": 0, "last_cursor": None})
        current["count"] += 1
        current["last_cursor"] = parsed["message_id"]
        history_progress[parsed["group_id"]] = current
        if current["count"] % 25 == 0:
            await update_group_progress(tracked_group["group_id"], current["count"], current["last_cursor"], False)


async def periodic_group_sync():
    while True:
        try:
            await sync_discovered_groups(status="active", last_error=None)
        except Exception as exc:
            logger.error("Signal periodic sync error: %s", exc)
        await asyncio.sleep(REFRESH_INTERVAL)


async def listen_forever():
    global history_deadline
    while True:
        if not SIGNAL_NUMBER:
            logger.error("SIGNAL_NUMBER не задан. Signal listener ожидает конфигурацию и повторит попытку через %d секунд.", RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)
            continue

        ws_url = build_ws_url()
        history_deadline = datetime.now(timezone.utc) + timedelta(seconds=15)
        logger.info("Запуск Signal listener")
        logger.info("Signal API URL: %s", SIGNAL_API_URL)
        logger.info("Backend URL: %s", BACKEND_API_URL)
        logger.info("WebSocket URL: %s", ws_url)

        try:
            await sync_discovered_groups(status="connecting", last_error=None)
            sync_task = asyncio.create_task(periodic_group_sync())
            logger.info("Подключение к Signal WebSocket...")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
                logger.info("Signal WebSocket подключен")
                await sync_discovered_groups(status="active", last_error=None)
                await asyncio.sleep(15)
                await finalize_signal_history()
                async for raw_message in websocket:
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        logger.warning("Получено невалидное сообщение Signal: %s", raw_message)
                        continue
                    await process_event(payload)
            sync_task.cancel()
        except Exception as exc:
            await sync_discovered_groups(status="error", last_error=str(exc))
            logger.exception("Signal WebSocket отключен: %s", exc)
            logger.info("Повторное подключение через %d секунд", RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    asyncio.run(listen_forever())
