import json
from typing import AsyncGenerator

import httpx

from app.core.config import settings


SYSTEM_PROMPT_BASE = """
Ти — аналітичний асистент системи FaceWatch відділу кримінального аналізу
Національної поліції України (Одеська область).
Відповідай офіційно-діловою українською мовою.
Оперуй тільки наданими даними. Не вигадуй факти.
Особи згадуються як їх person_id або псевдонім якщо є.
"""

SYSTEM_PROMPT_CASE = SYSTEM_PROMPT_BASE + """
Контекст: аналіз кримінального провадження.
Будуй хронологію подій, виділяй ключових осіб, знаходь протиріччя.
"""

SYSTEM_PROMPT_PERSON = SYSTEM_PROMPT_BASE + """
Контекст: аналіз конкретної особи.
Аналізуй патерни появ, зв'язки з іншими особами та провадженнями.
"""

SYSTEM_PROMPT_DAILY = SYSTEM_PROMPT_BASE + """
Контекст: щоденний оперативний брифінг.
Структуруй інформацію: термінові збіги → провадження → зв'язки → пріоритети.
"""

SYSTEM_PROMPT_GROUP = SYSTEM_PROMPT_BASE + """
Контекст: аналіз активності конкретної Telegram-групи.
Виділяй ключові теми, часові патерни, повторювані згадки та ризики.
"""

SYSTEM_PROMPT_GENERAL = SYSTEM_PROMPT_BASE + """
Контекст: загальний аналітичний діалог по доступних даних FaceWatch.
"""

AI_NUM_CTX = 4096


class OllamaService:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                return any(model.get("name") == self.model for model in models)
        except Exception:
            return False

    async def get_status(self) -> dict:
        version = "unknown"
        available = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                tags_response = await client.get(f"{self.base_url}/api/tags")
                tags_response.raise_for_status()
                models = tags_response.json().get("models", [])
                available = any(model.get("name") == self.model for model in models)

                version_response = await client.get(f"{self.base_url}/api/version")
                if version_response.status_code == 200:
                    version = version_response.json().get("version", "unknown")
        except Exception:
            pass
        return {
            "available": available,
            "model": self.model,
            "version": version,
        }

    async def chat(self, messages: list[dict], system_prompt: str) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "system": system_prompt.strip(),
            "options": {"num_ctx": AI_NUM_CTX},
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = (data.get("message") or {}).get("content") or ""
                    if chunk:
                        yield chunk

    async def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": AI_NUM_CTX},
        }
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "")


ollama_service = OllamaService()
