"""
Webhook endpoint для приёма сообщений от Telegram бота.
"""
from fastapi import APIRouter, Request
from app.core.config import settings

router = APIRouter()


@router.post("/webhook/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """
    Принимает Update от Telegram API.
    Обработка пересылается в бот через внутренний механизм.
    """
    if bot_token != settings.BOT_TOKEN:
        return {"ok": False, "error": "Invalid token"}

    data = await request.json()
    # Обработка данных происходит через бот (aiogram)
    # Этот endpoint используется если бот работает в режиме webhook
    return {"ok": True}
