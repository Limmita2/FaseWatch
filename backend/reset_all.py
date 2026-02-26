import asyncio
import logging
from app.core.database import engine
from app.models.models import Base
from app.services.qdrant_service import get_qdrant_client, COLLECTION_NAME
import redis.asyncio as aioredis
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def drop_mariadb():
    logger.info("Dropping all MariaDB tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("MariaDB tables recreated.")

def drop_qdrant():
    logger.info("Clearing Qdrant collection...")
    try:
        q_client = get_qdrant_client()
        q_client.delete_collection(COLLECTION_NAME)
        logger.info("Qdrant collection deleted.")
    except Exception as e:
        logger.error(f"Error clearing Qdrant: {e}")

async def flush_redis():
    logger.info("Clearing Redis...")
    try:
        r = aioredis.from_url(settings.REDIS_URL.replace("redis://redis", "redis://localhost"))
        await r.flushall()
        logger.info("Redis flushed.")
    except Exception as e:
        logger.error(f"Error clearing Redis: {e}")

async def main():
    await drop_mariadb()
    drop_qdrant()
    # Redis won't have localhost listening inside backend container properly, 
    # since REDIS_URL has redis://redis. Wait, settings.REDIS_URL has the correct url!
    # I should just use settings.REDIS_URL.
    
    logger.info("Clearing Redis with right URL...")
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.flushall()
        logger.info("Redis flushed.")
    except Exception as e:
        logger.error(f"Error clearing Redis: {e}")

if __name__ == "__main__":
    asyncio.run(main())
