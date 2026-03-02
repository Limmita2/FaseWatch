import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message
from sqlalchemy import select

async def clean_qdrant():
    qdrant = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    
    try:
        await qdrant.get_collection('faces')
    except Exception:
        print("Collection doesn't exist.")
        return

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Group).where(Group.name == 'Kilce_Krop'))
        group = res.scalar_one_or_none()
        if not group:
            print("Group not found")
            return
            
        print(f"Cleaning Qdrant vectors for group {group.name} ({group.id})...")
        
        # We delete ALL points in Qdrant where message_id is from our deleted batch.
        # However, we deleted the messages from DB, so we can't look them up.
        # But wait! We DO know which messages ARE valid. Any vector for this group_id 
        # whose message_id is NOT in the valid list should be deleted.
        
        print("Fetching valid message IDs for this group from DB...")
        res = await db.execute(select(Message.id).where(Message.group_id == group.id))
        valid_msg_ids = set([str(x) for x in res.scalars().all()])
        print(f"Group currently has {len(valid_msg_ids)} valid messages in DB.")
        
        # Use Qdrant's Scroll API to find all vectors for this group
        offset = None
        deleted_count = 0
        total_scanned = 0
        
        print("Scanning Qdrant for orphaned vectors...")
        while True:
            records, next_page = await qdrant.scroll(
                collection_name='faces',
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="group_id",
                            match=models.MatchValue(value=str(group.id))
                        )
                    ]
                ),
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )
            
            total_scanned += len(records)
            
            ids_to_delete = []
            for record in records:
                msg_id = record.payload.get("message_id")
                if str(msg_id) not in valid_msg_ids:
                    ids_to_delete.append(record.id)
                    
            if ids_to_delete:
                await qdrant.delete(
                    collection_name='faces',
                    points_selector=models.PointIdsList(
                        points=ids_to_delete,
                    ),
                )
                deleted_count += len(ids_to_delete)
                print(f"Scanned {total_scanned}, deleted {deleted_count} orphaned vectors so far...")
                
            if next_page is None:
                break
            offset = next_page

        print(f"Done! Total orphaned vectors deleted from Qdrant: {deleted_count}")

if __name__ == "__main__":
    asyncio.run(clean_qdrant())
