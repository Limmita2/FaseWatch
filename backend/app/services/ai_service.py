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

class GeminiService:
    def __init__(self) -> None:
        self.base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
        self.model = settings.GEMINI_MODEL
        self.fallback_models = [
            model.strip()
            for model in settings.GEMINI_FALLBACK_MODELS.split(",")
            if model.strip()
        ]
        self.api_key = settings.GEMINI_API_KEY
        self.timeout = settings.GEMINI_TIMEOUT
        self.temperature = settings.GEMINI_TEMPERATURE

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    @staticmethod
    def _clean_model_name(model: str) -> str:
        return model.removeprefix("models/").strip()

    def _candidate_models(self) -> list[str]:
        models = [self.model, *self.fallback_models]
        result: list[str] = []
        for model in models:
            clean = self._clean_model_name(model)
            if clean and clean not in result:
                result.append(clean)
        return result

    def _url(self, method: str, model: str | None = None, stream: bool = False) -> str:
        model_name = self._clean_model_name(model or self.model)
        suffix = f"/models/{model_name}:{method}"
        if stream:
            suffix += "?alt=sse"
        return f"{self.base_url}{suffix}"

    def _build_payload(self, messages: list[dict], system_prompt: str | None = None) -> dict:
        contents = []
        for message in messages:
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": content}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "topP": 0.95,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt.strip()}]}
        return payload

    @staticmethod
    def _extract_text(data: dict) -> str:
        chunks: list[str] = []
        for candidate in data.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    chunks.append(text)
        return "".join(chunks)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
            message = ((data.get("error") or {}).get("message") or "").strip()
            if message:
                return message
        except Exception:
            pass
        return response.text.strip() or response.reason_phrase

    @staticmethod
    def _is_retryable_error(status_code: int | None, message: str) -> bool:
        lowered = message.lower()
        retryable_markers = (
            "high demand",
            "overloaded",
            "temporarily unavailable",
            "try again later",
            "rate limit",
            "quota",
            "resource exhausted",
        )
        return status_code in {429, 500, 502, 503, 504} or any(
            marker in lowered for marker in retryable_markers
        )

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models/{self.model}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                return True
        except Exception:
            return False

    async def get_status(self) -> dict:
        if not self.api_key:
            return {
                "available": False,
                "provider": "gemini",
                "model": self.model,
                "version": "api",
                "detail": "GEMINI_API_KEY is not configured",
            }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models/{self.model}",
                    headers=self._headers(),
                )
                if response.is_error:
                    raise RuntimeError(self._error_detail(response))
                data = response.json()
                return {
                    "available": True,
                    "provider": "gemini",
                    "model": self.model,
                    "fallback_models": self.fallback_models,
                    "version": data.get("version") or data.get("displayName") or "api",
                }
        except Exception as exc:
            return {
                "available": False,
                "provider": "gemini",
                "model": self.model,
                "fallback_models": self.fallback_models,
                "version": "api",
                "detail": str(exc),
            }

    async def chat(self, messages: list[dict], system_prompt: str) -> AsyncGenerator[str, None]:
        payload = self._build_payload(messages, system_prompt)
        errors: list[str] = []

        for model in self._candidate_models():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    self._url("streamGenerateContent", model=model, stream=True),
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.is_error:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        try:
                            data = json.loads(body)
                            message = ((data.get("error") or {}).get("message") or "").strip()
                        except Exception:
                            message = body.strip()
                        message = message or response.reason_phrase
                        errors.append(f"{model}: {message}")
                        if self._is_retryable_error(response.status_code, message):
                            continue
                        raise RuntimeError(message)

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            continue
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        chunk = self._extract_text(data)
                        if chunk:
                            yield chunk
                    return

        raise RuntimeError("; ".join(errors) or "Gemini models are unavailable")

    async def generate(self, prompt: str) -> str:
        payload = self._build_payload([{"role": "user", "content": prompt}])
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for model in self._candidate_models():
                response = await client.post(
                    self._url("generateContent", model=model),
                    headers=self._headers(),
                    json=payload,
                )
                if response.is_error:
                    message = self._error_detail(response)
                    errors.append(f"{model}: {message}")
                    if self._is_retryable_error(response.status_code, message):
                        continue
                    raise RuntimeError(message)
                return self._extract_text(response.json())
        raise RuntimeError("; ".join(errors) or "Gemini models are unavailable")


ai_service = GeminiService()
