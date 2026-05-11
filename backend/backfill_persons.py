"""
Retroactive person clustering for existing faces without person_id.

Usage (inside Docker):
    docker compose exec backend python backfill_persons.py

Options:
    --batch      DB batch size (default: 500)
    --threshold  Cosine similarity threshold (default: 0.70)
"""
import argparse
import logging
import sys
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backfill_persons")


def find_existing_person(qdrant, collection: str, vector: list, threshold: float, exclude_point_id: str) -> str | None:
    """
    Шукає серед вже оброблених лиць (тих, що мають person_id у payload).
    Виключає саму точку exclude_point_id щоб уникнути self-match.
    Повертає person_id або None.
    """
    # Беремо top-10 за косинусною подібністю — щоб знайти хоча б одне з person_id
    result = qdrant.query_points(
        collection_name=collection,
        query=vector,
        limit=10,
        score_threshold=threshold,
        with_payload=True,
    )
    for pt in result.points:
        if str(pt.id) == exclude_point_id:
            continue  # self-match
        pid = pt.payload.get("person_id") if pt.payload else None
        if pid:
            return pid
    return None


def main(batch_size: int = 500, threshold: float = 0.70):
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.models.models import Face, Message, Person
    from app.services.qdrant_service import get_qdrant_client, COLLECTION_NAME

    sync_url = settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql")
    engine = create_engine(sync_url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    Session = sessionmaker(bind=engine)

    qdrant = get_qdrant_client()

    with Session() as s:
        total = s.scalar(
            select(func.count()).select_from(Face).where(Face.person_id.is_(None))
        )
    logger.info("Faces without person_id: %d", total)
    if total == 0:
        logger.info("Nothing to do.")
        return

    processed = 0
    matched = 0
    created = 0
    skipped = 0
    # Кеш щоб не зчитувати Person із БД зайвий раз
    person_seen: set[str] = set()

    logger.info("Starting (threshold=%.2f, batch=%d)...", threshold, batch_size)

    while True:
        with Session() as session:
            rows = (
                session.query(Face, Message.timestamp)
                .join(Message, Face.message_id == Message.id)
                .filter(Face.person_id.is_(None), Face.qdrant_point_id.isnot(None))
                .order_by(Face.id)
                .limit(batch_size)
                .all()
            )
            if not rows:
                break

            # Завантажуємо вектори з Qdrant одним пакетним запитом
            point_ids = [str(face.qdrant_point_id) for face, _ in rows]
            qdrant_points = qdrant.retrieve(
                collection_name=COLLECTION_NAME,
                ids=point_ids,
                with_vectors=True,
                with_payload=False,
            )
            vector_map = {str(p.id): p.vector for p in qdrant_points}

            for face, msg_ts in rows:
                pid_str = str(face.qdrant_point_id)
                raw_vec = vector_map.get(pid_str)

                if raw_vec is None:
                    skipped += 1
                    processed += 1
                    # Призначаємо person_id щоб не зависати на одних і тих же
                    person_id = str(uuid.uuid4())
                    new_p = Person(id=person_id, face_count=1,
                                   thumbnail_face_id=str(face.id),
                                   first_seen=msg_ts, last_seen=msg_ts)
                    session.add(new_p)
                    session.merge(face).person_id = person_id
                    continue

                vector = raw_vec if isinstance(raw_vec, list) else list(raw_vec)

                existing_pid = find_existing_person(qdrant, COLLECTION_NAME, vector, threshold, pid_str)

                if existing_pid:
                    person_id = existing_pid
                    if existing_pid not in person_seen:
                        p = session.get(Person, existing_pid)
                        if p:
                            p.face_count = (p.face_count or 0) + 1
                            if msg_ts and (not p.last_seen or msg_ts > p.last_seen):
                                p.last_seen = msg_ts
                        person_seen.add(existing_pid)
                    else:
                        # швидкий шлях без SELECT
                        from sqlalchemy import update
                        session.execute(
                            update(Person)
                            .where(Person.id == existing_pid)
                            .values(face_count=Person.face_count + 1)
                        )
                    matched += 1
                else:
                    person_id = str(uuid.uuid4())
                    new_p = Person(id=person_id, face_count=1,
                                   thumbnail_face_id=str(face.id),
                                   first_seen=msg_ts, last_seen=msg_ts)
                    session.add(new_p)
                    person_seen.add(person_id)
                    created += 1

                session.merge(face).person_id = person_id

                # Одразу оновлюємо Qdrant — щоб наступні лиця у цьому ж батчі
                # вже бачили person_id цього лиця і правильно групувались
                qdrant.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload={"person_id": person_id},
                    points=[pid_str],
                )

                processed += 1

            session.commit()

        pct = processed / total * 100 if total else 100
        logger.info(
            "Progress: %d/%d (%.1f%%) | matched=%d  new_persons=%d  no_vector=%d",
            processed, total, pct, matched, created, skipped,
        )

        if len(person_seen) > 50_000:
            person_seen.clear()

    logger.info("Done! processed=%d matched=%d new_persons=%d no_vector=%d",
                processed, matched, created, skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--threshold", type=float, default=0.70)
    args = parser.parse_args()
    main(batch_size=args.batch, threshold=args.threshold)
