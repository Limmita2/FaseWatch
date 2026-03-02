import asyncio
import os
import shutil
import argparse
from pathlib import Path
from sqlalchemy import select, delete
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message, Face
from app.core.config import settings

async def clean_group(group_name: str):
    print(f"Starting cleanup for group: {group_name}")
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Group).where(Group.name == group_name))
        group = res.scalar_one_or_none()
        if not group:
            print(f"Group '{group_name}' not found.")
            return
            
        group_id_str = str(group.id)
        print(f"Found group. ID: {group_id_str}")
        
        # 1. DELETE QDRANT VECTORS
        print("1. Cleaning Qdrant vectors...")
        try:
            qdrant = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
            await qdrant.delete(
                collection_name='faces',
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="group_id",
                                match=models.MatchValue(value=group_id_str)
                            )
                        ]
                    )
                ),
            )
            print("   Qdrant vectors deleted for this group.")
        except Exception as e:
            print(f"   Error cleaning Qdrant: {e}")

        # 2. DELETE PHYSICAL FILES
        print("2. Deleting physical photo files...")
        qnap_path = Path(settings.QNAP_MOUNT_PATH) / "photos" / group_id_str
        if qnap_path.exists() and qnap_path.is_dir():
            try:
                shutil.rmtree(qnap_path, ignore_errors=True)
                print(f"   Deleted directory {qnap_path}")
            except Exception as e:
                print(f"   Error deleting files: {e}")
        else:
            print(f"   Physical directory {qnap_path} does not exist.")
            
        # 3. DELETE FACES FROM DB
        print("3. Deleting faces from SQL database...")
        msg_query = select(Message.id).where(Message.group_id == group.id)
        res = await db.execute(msg_query)
        msg_ids = res.scalars().all()
        
        if msg_ids:
            batch_size = 5000
            faces_deleted = 0
            for i in range(0, len(msg_ids), batch_size):
                batch = msg_ids[i:i+batch_size]
                delete_faces_stmt = delete(Face).where(Face.message_id.in_(batch))
                result = await db.execute(delete_faces_stmt)
                faces_deleted += result.rowcount
                await db.commit()
            print(f"   Total faces deleted from DB: {faces_deleted}")
            
            # 4. DELETE MESSAGES FROM DB
            print("4. Deleting messages from SQL database...")
            msgs_deleted = 0
            for i in range(0, len(msg_ids), batch_size):
                batch = msg_ids[i:i+batch_size]
                delete_msgs_stmt = delete(Message).where(Message.id.in_(batch))
                result = await db.execute(delete_msgs_stmt)
                msgs_deleted += result.rowcount
                await db.commit()
            print(f"   Total messages deleted from DB: {msgs_deleted}")
        else:
            print("   No messages found for this group.")

        # 5. DELETE GROUP ITSELF
        print("5. Deleting group from SQL database...")
        await db.execute(delete(Group).where(Group.id == group.id))
        await db.commit()
        print("   Group deleted.")
        
        print(f"\n✅ Cleanup of group '{group_name}' finished completely!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("group_name", help="Name of the group to completely delete")
    args = parser.parse_args()
    
    asyncio.run(clean_group(args.group_name))
