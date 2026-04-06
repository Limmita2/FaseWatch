import asyncio
import os
import shutil
import httpx
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message, Face
from app.core.config import settings

# Qdrant collection is usually passed through env, defaulting to 'faces'
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "faces")
QDRANT_URL = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"

SPAM_IDS = [-5111347706, -100123, -5006756607, 343751998, 346340843]

async def delete_group(tg_id: int):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Group).where(Group.telegram_id == tg_id))
        group = result.scalar_one_or_none()
        
        if not group:
            print(f"➖ Группа с ID {tg_id} не найдена в базе (уже удалена?).")
            return
            
        group_id_str = str(group.id)
        print(f"🗑 Начинаем полное удаление группы {tg_id} (UUID: {group_id_str})...")

        # 1. Удаление из Qdrant (по payload filter)
        print("   -> Удаление векторов из Qdrant...")
        delete_payload = {
            "filter": {
                "must": [
                    {"key": "group_id", "match": {"value": group_id_str}}
                ]
            }
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/delete",
                    json=delete_payload
                )
                if resp.status_code == 200:
                    print("      ✅ Qdrant: очищено успешно.")
                else:
                    print(f"      ⚠️ Qdrant статус: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"      ❌ Ошибка удаления из Qdrant: {e}")

        # 2. Удаление файлов с диска (QNAP)
        print("   -> Удаление файлов с QNAP...")
        photos_dir = os.path.join(settings.QNAP_MOUNT_PATH, "photos", group_id_str)
        faces_dir = os.path.join(settings.QNAP_MOUNT_PATH, "faces", group_id_str)
        
        deleted_files = False
        if os.path.exists(photos_dir):
            shutil.rmtree(photos_dir, ignore_errors=True)
            print(f"      ✅ Удалена папка {photos_dir}")
            deleted_files = True
        if os.path.exists(faces_dir):
            shutil.rmtree(faces_dir, ignore_errors=True)
            print(f"      ✅ Удалена папка {faces_dir}")
            deleted_files = True
            
        if not deleted_files:
            print("      (Файлы на физическом диске не найдены, пропускаем)")

        # 3. Удаление из MySQL
        print("   -> Удаление из БД (MySQL)...")
        # Удаляем лица и сообщения
        messages = await db.execute(select(Message).where(Message.group_id == group.id))
        msg_list = messages.scalars().all()
        for msg in msg_list:
            faces = await db.execute(select(Face).where(Face.message_id == msg.id))
            for face in faces.scalars().all():
                await db.delete(face)
            await db.delete(msg)
            
        # Наконец, удаляем саму группу
        await db.delete(group)
        await db.commit()
        print(f"✅ Группа {tg_id} ПОЛНОСТЬЮ удалена (сообщений удалено: {len(msg_list)}).\n")

async def main():
    for tg_id in SPAM_IDS:
        await delete_group(tg_id)
    print("🎉 Очистка завершена!")

if __name__ == "__main__":
    asyncio.run(main())
