import asyncio
import os
import hashlib
from collections import defaultdict
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal
from app.models.models import Message, Face, MessagePhone
from app.core.config import settings

COLLECTION_NAME = "faces"

async def send_tg_notification(message: str):
    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": 67838716,
            "text": message,
            "parse_mode": "HTML"
        }
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=10.0)
    except Exception as e:
        print(f"❌ Не удалось отправить уведомление в Telegram: {e}")

async def main():
    print("🚀 Начинается процесс глобальной очистки дубликатов (ОПТИМИЗИРОВАННЫЙ)...")
    
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    qdrant_client = AsyncQdrantClient(url=qdrant_url)

    async with AsyncSessionLocal() as db:
        # Получаем все сообщения с фотографиями
        print("📥 Загрузка всех фотографий из базы данных...")
        result = await db.execute(
            select(Message).where(Message.has_photo == True).order_by(Message.timestamp.asc())
        )
        messages = result.scalars().all()
        total_msgs = len(messages)
        print(f"📸 Найдено сообщений с фотографиями: {total_msgs}")

        # Группируем по хэшу
        hash_to_msgs = defaultdict(list)
        missing_files = 0
        hashed_count = 0
        pre_hashed_count = 0

        for i, msg in enumerate(messages):
            if i % 10000 == 0 and i > 0:
                print(f"📡 Обработано записей: {i}/{total_msgs}...")

            # ОПТИМИЗАЦИЯ: Если хэш уже в базе, используем его
            if msg.photo_hash:
                hash_to_msgs[msg.photo_hash].append(msg)
                pre_hashed_count += 1
                continue

            path = msg.photo_path
            if not path or not os.path.exists(path):
                missing_files += 1
                continue
                
            try:
                with open(path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                hash_to_msgs[file_hash].append(msg)
                hashed_count += 1
                
                if hashed_count % 1000 == 0:
                    print(f"⏳ Вычислен хэш для {hashed_count} НОВЫХ файлов...")
            except Exception as e:
                print(f"Ошибка чтения файла {path}: {e}")

        print(f"✅ Индексация завершена!")
        print(f"ℹ️  Использовано готовых хэшей: {pre_hashed_count}")
        print(f"ℹ️  Вычислено новых хэшей: {hashed_count}")
        print(f"⚠️  Файлов не найдено: {missing_files}")

        duplicates_found = 0
        deleted_faces_count = 0
        deleted_qdrant_points = 0
        deleted_files_size = 0
        batch_counter = 0

        print("🧹 Начинаем удаление дубликатов...")

        for file_hash, msg_group in hash_to_msgs.items():
            # Самое старое сообщение оставляем как оригинал
            original_msg = msg_group[0]
            if original_msg.photo_hash != file_hash:
                original_msg.photo_hash = file_hash
                db.add(original_msg)

            if len(msg_group) == 1:
                batch_counter += 1
                if batch_counter >= 100:
                    await db.commit()
                    batch_counter = 0
                continue

            duplicates = msg_group[1:]
            duplicates_found += len(duplicates)

            for dup in duplicates:
                dup_id = dup.id
                
                # 1. Находим и удаляем связанные лица
                faces_res = await db.execute(select(Face).where(Face.message_id == dup_id))
                faces = faces_res.scalars().all()
                for face in faces:
                    # Удаляем кроп с физического диска QNAP
                    if face.crop_path and os.path.exists(face.crop_path):
                        try:
                            file_size = os.path.getsize(face.crop_path)
                            os.remove(face.crop_path)
                            deleted_files_size += file_size
                        except Exception:
                            pass
                    
                    # Удаляем вектор из Qdrant (ИСПРАВЛЕНО: COLLECTION_NAME)
                    if face.qdrant_point_id:
                        try:
                            await qdrant_client.delete(
                                collection_name=COLLECTION_NAME,
                                points_selector=[str(face.qdrant_point_id)]
                            )
                            deleted_qdrant_points += 1
                        except Exception as e:
                            print(f"Ошибка удаления точки Qdrant {face.qdrant_point_id}: {e}")
                            
                    deleted_faces_count += 1
                
                # Удаляем записи о лицах в SQL
                await db.execute(delete(Face).where(Face.message_id == dup_id))

                # 2. Находим и удаляем связанные телефоны
                await db.execute(delete(MessagePhone).where(MessagePhone.message_id == dup_id))

                # 3. Физически удаляем дубликат фото (если путь отличается от оригинала)
                if dup.photo_path and os.path.exists(dup.photo_path):
                    if dup.photo_path != original_msg.photo_path:
                        try:
                            file_size = os.path.getsize(dup.photo_path)
                            os.remove(dup.photo_path)
                            deleted_files_size += file_size
                        except Exception:
                            pass

                # 4. Удаляем само сообщение-дубликат
                await db.execute(delete(Message).where(Message.id == dup_id))

            batch_counter += 1
            if batch_counter >= 100:
                await db.commit()
                batch_counter = 0
                print(f"📦 Прогресс: обработано {duplicates_found} дубликатов...")

        await db.commit()

        print("\n================================================")
        print("🎉 ГЛОБАЛЬНАЯ ОЧИСТКА ЗАВЕРШЕНА!")
        print(f"🗑 Удалено дублирующихся сообщений: {duplicates_found}")
        print(f"👤 Удалено кропов лиц: {deleted_faces_count}")
        print(f"🔢 Удалено векторов из Qdrant: {deleted_qdrant_points}")
        print(f"💾 Освобождено места: {deleted_files_size / (1024*1024):.2f} MB")
        print("================================================\n")

        # Отправка уведомления в Telegram
        tg_text = (
            "✅ <b>Глобальная очистка завершена!</b>\n\n"
            f"🗑 Удалено дубликатов: <code>{duplicates_found}</code>\n"
            f"👤 Удалено кропов лиц: <code>{deleted_faces_count}</code>\n"
            f"🔢 Удалено векторов Qdrant: <code>{deleted_qdrant_points}</code>\n"
            f"💾 Освобождено места: <b>{deleted_files_size / (1024*1024):.2f} MB</b>"
        )
        await send_tg_notification(tg_text)

if __name__ == "__main__":
    asyncio.run(main())
