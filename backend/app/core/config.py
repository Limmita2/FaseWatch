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

    # InsightFace
    FACE_SIMILARITY_THRESHOLD: float = 0.75

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
