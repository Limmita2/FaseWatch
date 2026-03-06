#!/usr/bin/env python3
"""
Скрипт для создания payload-индексов в существующей Qdrant-коллекции 'faces'.
Запускать один раз после деплоя: python3 apply_qdrant_indexes.py
"""
import sys
import os

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qdrant_client import QdrantClient

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "faces"


def main():
    print(f"Подключение к Qdrant: {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Проверяем что коллекция существует
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        print(f"Коллекция '{COLLECTION_NAME}' не найдена! Запустите приложение сначала.")
        sys.exit(1)

    # Информация о коллекции
    info = client.get_collection(COLLECTION_NAME)
    print(f"Коллекция '{COLLECTION_NAME}': {info.points_count} точек")

    # Создаём payload-индекс по message_id
    print("Создаю payload-индекс: message_id...")
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="message_id",
        field_schema="keyword",
    )
    print("  ✓ message_id индекс создан")

    # Создаём payload-индекс по face_id
    print("Создаю payload-индекс: face_id...")
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="face_id",
        field_schema="keyword",
    )
    print("  ✓ face_id индекс создан")

    # Проверяем результат
    info_after = client.get_collection(COLLECTION_NAME)
    schema = getattr(info_after, 'payload_schema', {})
    print(f"\nГотово! Текущие индексы: {list(schema.keys()) if schema else 'смотрите в dashboard'}")
    print(f"Qdrant dashboard: http://localhost:{QDRANT_PORT}/dashboard")


if __name__ == "__main__":
    main()
