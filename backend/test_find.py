import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.database import AsyncSessionLocal
from app.models.models import Message
from sqlalchemy import select

async def test_find_page():
    async with AsyncSessionLocal() as db:
        # Get a random message with a photo
        res = await db.execute(select(Message).where(Message.has_photo == True).limit(5))
        msgs = res.scalars().all()
        
        if not msgs:
            print("No messages with photos found to test.")
            return

        msg = msgs[-1] # take the last one
        print(f"Testing find_page for photo: {msg.photo_path}")
        
        filename = msg.photo_path.split('/')[-1] if msg.photo_path else 'unknown.jpg'
        print(f"Filename ID: {filename}")
        
        # Test the endpoint logic (we simply replicate the logic because FastAPI TestClient requires more setup)
        from sqlalchemy import func, and_
        filters = [Message.photo_path.like(f"%{filename}%")]
        result = await db.execute(select(Message).where(and_(*filters)))
        found_msg = result.scalar_one_or_none()
        
        if not found_msg:
            print("FAILED: Message not found by photo ID.")
            return
            
        print(f"Found message ID: {found_msg.id}")
        
        # Count newer messages
        count_stmt = select(func.count()).select_from(Message).where(Message.timestamp > found_msg.timestamp)
        count_res = await db.execute(count_stmt)
        newer = count_res.scalar() or 0
        
        limit = 50
        page = (newer // limit) + 1
        
        print(f"SUCCESS! Message is on relative page (overall): {page}")

if __name__ == "__main__":
    asyncio.run(test_find_page())
