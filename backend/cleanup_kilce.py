import asyncio
import os
import shutil
from pathlib import Path
from sqlalchemy import select, delete
from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message, Face
from app.core.config import settings

async def clean():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Group).where(Group.name == 'Kilce_Krop'))
        group = res.scalar_one_or_none()
        if not group:
            print('Group Kilce_Krop not found.')
            return
            
        print(f"Began cleanup for group {group.name} ({group.id})")
        
        # 1. DELETE FACES associated with imported messages
        print("Finding imported messages...")
        msg_query = select(Message.id).where(
            Message.group_id == group.id, 
            Message.imported_from_backup == True
        )
        res = await db.execute(msg_query)
        msg_ids = res.scalars().all()
        
        if not msg_ids:
            print("No imported messages found. Nothing to clean.")
            return
            
        print(f"Found {len(msg_ids)} imported messages.")
        
        batch_size = 5000
        faces_deleted = 0
        for i in range(0, len(msg_ids), batch_size):
            batch = msg_ids[i:i+batch_size]
            delete_faces_stmt = delete(Face).where(Face.message_id.in_(batch))
            result = await db.execute(delete_faces_stmt)
            faces_deleted += result.rowcount
            print(f"Deleted {faces_deleted} faces so far...")
            await db.commit()
            
        print(f"Total faces deleted from DB: {faces_deleted}")
        
        # 2. DELETE MESSAGES
        msgs_deleted = 0
        for i in range(0, len(msg_ids), batch_size):
            batch = msg_ids[i:i+batch_size]
            delete_msgs_stmt = delete(Message).where(Message.id.in_(batch))
            result = await db.execute(delete_msgs_stmt)
            msgs_deleted += result.rowcount
            print(f"Deleted {msgs_deleted} messages so far...")
            await db.commit()

        print(f"Total messages deleted from DB: {msgs_deleted}")
        
        # 3. DELETE PHOTOS from disk
        qnap_path = Path(settings.QNAP_MOUNT_PATH) / "photos" / str(group.id)
        if qnap_path.exists():
            import time
            current_time = time.time()
            deleted_files = 0
            for file_path in qnap_path.rglob("*.jpg"):
                if current_time - file_path.stat().st_mtime < 86400: # 24 hours
                    try:
                        os.remove(file_path)
                        deleted_files += 1
                    except Exception as e:
                        pass
            print(f"Deleted {deleted_files} physical photo files from QNAP.")
            
        print("Done!")

if __name__ == "__main__":
    asyncio.run(clean())
