"""
Telegram Bot для FaceWatch (aiogram 3.x).
Сбор сообщений (текст + фото) из групп и отправка на обработку в backend.
"""
import asyncio
import os
import httpx
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ContentType
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend:8000")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def send_to_backend(endpoint: str, data: dict, files: dict = None):
    """Отправляет данные на backend API."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            if files:
                resp = await client.post(f"{BACKEND_API_URL}{endpoint}", data=data, files=files)
            else:
                resp = await client.post(f"{BACKEND_API_URL}{endpoint}", json=data)
            return resp.json()
        except Exception as e:
            print(f"Ошибка при отправке на backend: {e}")
            return None


@dp.message(F.content_type.in_([ContentType.PHOTO]))
async def handle_photo(message: types.Message):
    """Обработка фото из групповых чатов."""
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
    await send_to_backend("/api/bot/message", data, files)


@dp.message(F.content_type == ContentType.TEXT)
async def handle_text(message: types.Message):
    """Обработка текстовых сообщений из групповых чатов."""
    # Пропускаем приватные сообщения и команды
    if message.chat.type == "private":
        await message.answer("FaceWatch Bot активен. Добавьте меня в группу для мониторинга.")
        return
    if message.text and message.text.startswith("/"):
        return

    data = {
        "group_telegram_id": str(message.chat.id),
        "group_name": message.chat.title or "Unknown",
        "message_id": str(message.message_id),
        "sender_telegram_id": str(message.from_user.id) if message.from_user else "",
        "sender_name": message.from_user.full_name if message.from_user else "",
        "text": message.text or "",
        "timestamp": message.date.isoformat(),
    }

    await send_to_backend("/api/bot/message", data)


@dp.message(F.content_type == ContentType.NEW_CHAT_MEMBERS)
async def handle_new_member(message: types.Message):
    """Бот добавлен в группу."""
    for member in message.new_chat_members:
        if member.id == bot.id:
            print(f"Бот добавлен в группу: {message.chat.title} ({message.chat.id})")


async def main():
    print(f"FaceWatch Bot запущен (polling mode)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
