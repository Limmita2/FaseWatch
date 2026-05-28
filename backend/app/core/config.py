from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # База данных
    DATABASE_URL: str = "mysql+aiomysql://facewatch:ke050442@192.168.24.178:3306/facewatch_db"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Хранилище файлов (QNAP mount)
    QNAP_MOUNT_PATH: str = "/mnt/qnap_photos"

    # JWT
    JWT_SECRET: str = "change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    # Telegram
    BOT_TOKEN: Optional[str] = None
    TG_API_ID: Optional[str] = None
    TG_API_HASH: Optional[str] = None
    TELETHON_API_KEY: str = "change_me"

    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODELS: str = "gemini-2.0-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite"
    GEMINI_TIMEOUT: int = 120
    GEMINI_TEMPERATURE: float = 0.2

    # InsightFace
    FACE_SIMILARITY_THRESHOLD: float = 0.45
    FACE_CROP_PADDING: float = 0.3

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
