"""
Telegram Bot для FaceWatch (aiogram 3.x).
Сбор сообщений (текст + фото) из групп и отправка на обработку в backend.
"""
import asyncio
import os
import sys
import logging
import httpx
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ContentType
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("facewatch_bot")

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend:8000")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def send_to_backend(endpoint: str, data: dict, files: dict = None):
    """Отправляет данные на backend API с retry при ошибках сети."""
    max_retries = 5
    delay = 2

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if files:
                    resp = await client.post(f"{BACKEND_API_URL}{endpoint}", data=data, files=files)
                else:
                    resp = await client.post(f"{BACKEND_API_URL}{endpoint}", data=data)
                result = resp.json()
                logger.info("Backend ответ (%s): %s", endpoint, result)
                return result
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "⚠️ Backend недоступен (попытка %d/%d): %s. Повтор через %d сек...",
                    attempt, max_retries, e, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                logger.error("❌ Backend недоступен после %d попыток: %s", max_retries, e)
                return None


@dp.message(F.content_type.in_([ContentType.PHOTO]))
async def handle_photo(message: types.Message):
    """Обработка фото из групповых чатов."""
    logger.info(
        f"📸 Фото от {message.from_user.full_name if message.from_user else 'Unknown'} "
        f"в '{message.chat.title or message.chat.full_name}' (chat_id={message.chat.id})"
    )

    # Берём фото максимального разрешения
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    data = {
        "group_telegram_id": str(message.chat.id),
        "group_name": message.chat.title or message.chat.full_name or "Unknown",
        "message_id": str(message.message_id),
        "sender_telegram_id": str(message.from_user.id) if message.from_user else "",
        "sender_name": message.from_user.full_name if message.from_user else "",
        "text": message.caption or "",
        "timestamp": message.date.isoformat(),
    }

    files = {"photo": ("photo.jpg", file_bytes.read(), "image/jpeg")}
    result = await send_to_backend("/api/bot/message", data, files)
    logger.info(f"📸 Фото обработано: {result}")


@dp.message(F.content_type == ContentType.TEXT)
async def handle_text(message: types.Message):
    """Обработка текстовых сообщений из групповых чатов."""
    # Пропускаем приватные сообщения и команды
    if message.chat.type == "private":
        logger.info(f"ЛС от {message.from_user.full_name if message.from_user else 'Unknown'}")
        await message.answer("FaceWatch Bot активен. Добавьте меня в группу для мониторинга.")
        return
    if message.text and message.text.startswith("/"):
        logger.info(f"Команда пропущена: {message.text}")
        return

    logger.info(
        f"💬 Текст от {message.from_user.full_name if message.from_user else 'Unknown'} "
        f"в '{message.chat.title or 'Unknown'}': {message.text[:80] if message.text else ''}"
    )

    data = {
        "group_telegram_id": str(message.chat.id),
        "group_name": message.chat.title or "Unknown",
        "message_id": str(message.message_id),
        "sender_telegram_id": str(message.from_user.id) if message.from_user else "",
        "sender_name": message.from_user.full_name if message.from_user else "",
        "text": message.text or "",
        "timestamp": message.date.isoformat(),
    }

    result = await send_to_backend("/api/bot/message", data)
    logger.info(f"💬 Текст обработан: {result}")


@dp.message(F.content_type == ContentType.NEW_CHAT_MEMBERS)
async def handle_new_member(message: types.Message):
    """Бот добавлен в группу."""
    for member in message.new_chat_members:
        if member.id == bot.id:
            logger.info(f"🆕 Бот добавлен в группу: {message.chat.title} ({message.chat.id})")


async def main():
    """Запуск бота с автоматическим переподключением при потере сети."""
    logger.info("🚀 FaceWatch Bot запущен (polling mode)")
    logger.info("   Backend URL: %s", BACKEND_API_URL)
    logger.info("   Token: %s...%s", BOT_TOKEN[:10], BOT_TOKEN[-5:])

    retry_delay = 5  # начальная задержка (сек)
    max_delay = 60   # максимальная задержка

    while True:
        try:
            logger.info("📡 Подключение к Telegram API...")
            await dp.start_polling(bot, handle_signals=False)
            break  # если polling завершился нормально (не должно в норме)
        except Exception as e:
            logger.warning(
                "⚠️ Ошибка polling: %s. Повтор через %d сек...",
                e, retry_delay,
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
        else:
            retry_delay = 5  # сброс задержки при успехе


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен (KeyboardInterrupt)")
            break
        except Exception as e:
            logger.error("💥 Критическая ошибка: %s. Перезапуск через 10 сек...", e)
            import time
            time.sleep(10)
