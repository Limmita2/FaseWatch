import asyncio
import os
import sys
from sqlalchemy import select, func

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Group).where(Group.name == "133002"))
        group = result.scalar_one_or_none()
        
        if not group:
            print("❌ Группа '133002' не найдена в базе!")
            return
            
        print(f"✅ Найдена группа: {group.name} (ID: {group.id})")
        
        # Считаем количество сообщений в этой группе
        query = select(func.count(Message.id)).where(Message.group_id == group.id)
        msg_result = await db.execute(query)
        msg_count = msg_result.scalar()
        
        # Считаем количество фотографий (has_photo = True)
        photo_query = select(func.count(Message.id)).where(Message.group_id == group.id, Message.has_photo == True)
        photo_result = await db.execute(photo_query)
        photo_count = photo_result.scalar()
        
        print(f"📊 Всего сообщений в группе: {msg_count}")
        print(f"📸 Сообщений с фотографиями: {photo_count}")

if __name__ == "__main__":
    asyncio.run(check())
