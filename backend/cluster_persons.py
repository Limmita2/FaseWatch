import asyncio
import uuid
import logging
import sys
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

# Add app directory to sys.path
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal
from app.models.models import Face, Person, Message
from app.services.qdrant_service import get_qdrant_client, find_person_for_vector, COLLECTION_NAME, update_point_person_id

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BATCH_SIZE = 500
PERSON_THRESHOLD = 0.70

async def cluster_existing_faces():
    """
    Retroactively cluster all faces in the database using the 0.70 similarity threshold.
    """
    client = get_qdrant_client()
    
    async with AsyncSessionLocal() as db:
        # Get count of faces without person_id
        count_q = await db.execute(select(func.count(Face.id)).where(Face.person_id == None))
        total_to_process = count_q.scalar()
        logger.info(f"Total faces to process: {total_to_process}")
        
        if total_to_process == 0:
            logger.info("No faces without person_id found. Everything is already clustered.")
            return

        processed_count = 0
        
        while True:
            # Fetch a batch of faces without person_id
            stmt = (
                select(Face, Message.timestamp)
                .join(Message, Face.message_id == Message.id, isouter=True)
                .where(Face.person_id == None)
                .limit(BATCH_SIZE)
            )
            result = await db.execute(stmt)
            batch = result.all()
            
            if not batch:
                break
            
            # 1. Batch retrieve vectors from Qdrant
            point_ids = [str(f.Face.qdrant_point_id) for f in batch if f.Face.qdrant_point_id]
            points_map = {}
            if point_ids:
                try:
                    points = client.retrieve(
                        collection_name=COLLECTION_NAME,
                        ids=point_ids,
                        with_vectors=True
                    )
                    for p in points:
                        points_map[str(p.id)] = p.vector
                except Exception as e:
                    logger.error(f"Error retrieving points from Qdrant: {e}")

            for face_row in batch:
                face = face_row.Face
                timestamp = face_row.timestamp
                
                point_id_str = str(face.qdrant_point_id)
                if point_id_str not in points_map:
                    logger.warning(f"Face {face.id} (point {point_id_str}) not found in Qdrant or has no vector. Skipping.")
                    face.person_id = "skipped"
                    continue
                
                vector = points_map[point_id_str]
                
                # 2. Find existing person (this is still 1-by-1, but better than 2 calls)
                try:
                    person_id = find_person_for_vector(client, vector, threshold=PERSON_THRESHOLD)
                    
                    if person_id:
                        # Update existing person cache or DB
                        person_obj = (await db.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
                        if person_obj:
                            person_obj.face_count += 1
                            if timestamp:
                                if not person_obj.first_seen or timestamp < person_obj.first_seen:
                                    person_obj.first_seen = timestamp
                                if not person_obj.last_seen or timestamp > person_obj.last_seen:
                                    person_obj.last_seen = timestamp
                    else:
                        # Create new person
                        person_id = str(uuid.uuid4())
                        new_person = Person(
                            id=person_id,
                            face_count=1,
                            thumbnail_face_id=str(face.id),
                            first_seen=timestamp,
                            last_seen=timestamp
                        )
                        db.add(new_person)
                    
                    # 3. Update Face in DB
                    face.person_id = person_id
                    
                    # 4. Update Qdrant payload
                    update_point_person_id(client, point_id_str, person_id)
                    
                except Exception as e:
                    logger.error(f"Error processing face {face.id}: {e}")
                    continue
            
            await db.commit()
            processed_count += len(batch)
            logger.info(f"Processed {processed_count}/{total_to_process} faces...")

if __name__ == "__main__":
    asyncio.run(cluster_existing_faces())
