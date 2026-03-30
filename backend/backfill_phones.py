"""
Пересобирает таблицу message_phones по актуальному паттерну из phone_utils.

Примеры:
    python backfill_phones.py --reset
    python backfill_phones.py --reset --dry-run
"""
import argparse
import asyncio
import uuid

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.models import Message, MessagePhone
from app.services.phone_utils import extract_phones


BATCH = 5000


async def count_phone_stats(db) -> tuple[int, int]:
    total_rows = (
        await db.execute(select(func.count(MessagePhone.id)))
    ).scalar() or 0
    unique_phones = (
        await db.execute(select(func.count(func.distinct(MessagePhone.phone))))
    ).scalar() or 0
    return total_rows, unique_phones


async def main(reset: bool, dry_run: bool):
    async with AsyncSessionLocal() as db:
        total_messages = (
            await db.execute(
                select(func.count())
                .select_from(Message)
                .where(Message.text.isnot(None), Message.text != "")
            )
        ).scalar() or 0
        print(f"📊 Всего сообщений с текстом: {total_messages}")

        if reset:
            existing_rows, existing_unique = await count_phone_stats(db)
            print(
                "🧹 Подготовка к полной пересборке: "
                f"{existing_rows} записей, {existing_unique} уникальных номеров будет удалено"
            )
            if not dry_run:
                await db.execute(delete(MessagePhone))
                await db.commit()

        offset = 0
        inserted_rows = 0
        unique_phones_seen: set[str] = set()
        while offset < total_messages:
            result = await db.execute(
                select(Message.id, Message.text)
                .where(Message.text.isnot(None), Message.text != "")
                .order_by(Message.id)
                .offset(offset)
                .limit(BATCH)
            )
            rows = result.all()
            if not rows:
                break

            batch_rows = 0
            for message_id, text in rows:
                phones = extract_phones(text)
                if not phones:
                    continue

                unique_phones_seen.update(phones)
                if dry_run:
                    batch_rows += len(phones)
                    continue

                for phone in phones:
                    db.add(MessagePhone(id=uuid.uuid4(), message_id=message_id, phone=phone))
                    batch_rows += 1

            if not dry_run:
                await db.commit()

            inserted_rows += batch_rows
            offset += BATCH
            print(
                f"   Обработано {min(offset, total_messages)}/{total_messages} "
                f"— найдено номеров в этом батче: {batch_rows}"
            )

        if dry_run:
            print(
                "\n🔎 Dry-run завершен: "
                f"{inserted_rows} записей, {len(unique_phones_seen)} уникальных номеров"
            )
            return

        total_rows, unique_phones = await count_phone_stats(db)
        print(
            "\n🎉 Пересборка завершена: "
            f"{total_rows} записей в message_phones, "
            f"{unique_phones} уникальных номеров"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Полностью очистить message_phones перед пересборкой",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только посчитать, сколько записей и уникальных номеров будет найдено",
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset, dry_run=args.dry_run))
