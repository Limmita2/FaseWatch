#!/usr/bin/env python3
"""
Бенчмарк поиска по фото — замеряет каждый этап отдельно.
Запуск: docker compose exec backend python /app/benchmark_search.py
"""
import asyncio
import time
import os
import sys

# ─────────────────────────────────────────────
# 1. Qdrant поиск
# ─────────────────────────────────────────────
def bench_qdrant():
    from qdrant_client import QdrantClient
    client = QdrantClient(host="qdrant", port=6333)

    # Берём первую точку из коллекции как тестовый вектор
    points = client.scroll("faces", limit=1, with_vectors=True)
    if not points[0]:
        print("Qdrant: нет точек в коллекции!")
        return
    vector = points[0][0].vector

    t1 = time.time()
    results = client.query_points(
        collection_name="faces",
        query=vector,
        limit=20,
    )
    t2 = time.time()
    print(f"  Qdrant поиск (top_k=20):    {(t2-t1)*1000:.1f} мс  ({len(results.points)} результатов)")

# ─────────────────────────────────────────────
# 2. Чтение фото с QNAP
# ─────────────────────────────────────────────
def bench_qnap_photo():
    import cv2
    qnap_path = os.getenv("QNAP_MOUNT_PATH", "/mnt/qnap_photos")

    # Ищем любое jpg/jpeg на QNAP
    photo_path = None
    for root, dirs, files in os.walk(qnap_path):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg")):
                photo_path = os.path.join(root, f)
                break
        if photo_path:
            break

    if not photo_path:
        print(f"  QNAP фото: файлы не найдены в {qnap_path}")
        return

    # Несколько замеров (первый может быть кешированным ОС)
    times = []
    for _ in range(3):
        t1 = time.time()
        img = cv2.imread(photo_path)
        t2 = time.time()
        if img is not None:
            times.append((t2 - t1) * 1000)

    if times:
        avg = sum(times) / len(times)
        print(f"  QNAP фото чтение (avg 3x): {avg:.1f} мс  (файл: .../{os.path.basename(photo_path)}, {os.path.getsize(photo_path)//1024} KB)")
    else:
        print(f"  QNAP фото: не удалось прочитать {photo_path}")

# ─────────────────────────────────────────────
# 3. MySQL/MariaDB запрос
# ─────────────────────────────────────────────
async def bench_mysql():
    import aiomysql
    db_url = os.getenv("DATABASE_URL", "")
    # mysql+aiomysql://user:pass@host:port/db
    import re
    m = re.match(r"mysql\+aiomysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", db_url)
    if not m:
        print("  MySQL: не удалось разобрать DATABASE_URL")
        return
    user, password, host, port, db = m.groups()

    conn = await aiomysql.connect(host=host, port=int(port), user=user, password=password, db=db)
    cur = await conn.cursor()

    # Warm-up
    await cur.execute("SELECT 1")
    await cur.fetchall()

    # Тест 1: простой SELECT COUNT
    t1 = time.time()
    await cur.execute("SELECT COUNT(*) FROM messages")
    count = (await cur.fetchone())[0]
    t2 = time.time()
    print(f"  MySQL COUNT(messages):      {(t2-t1)*1000:.1f} мс  ({count} строк)")

    # Тест 2: SELECT 5 строк по timestamp (с индексом)
    t1 = time.time()
    await cur.execute("SELECT id, timestamp FROM messages ORDER BY timestamp DESC LIMIT 5")
    await cur.fetchall()
    t2 = time.time()
    print(f"  MySQL SELECT 5 (по индексу):{(t2-t1)*1000:.1f} мс")

    # Тест 3: SELECT IN (5 ID)
    await cur.execute("SELECT id FROM messages LIMIT 5")
    ids = [row[0] for row in await cur.fetchall()]
    if ids:
        placeholders = ",".join(["%s"] * len(ids))
        t1 = time.time()
        await cur.execute(f"SELECT id, text, timestamp FROM messages WHERE id IN ({placeholders})", ids)
        await cur.fetchall()
        t2 = time.time()
        print(f"  MySQL SELECT IN (5 ids):    {(t2-t1)*1000:.1f} мс")

    await cur.close()
    conn.close()

# ─────────────────────────────────────────────
# 4. InsightFace (детекция лица на тестовом изображении)
# ─────────────────────────────────────────────
def bench_insightface():
    import cv2
    import numpy as np
    qnap_path = os.getenv("QNAP_MOUNT_PATH", "/mnt/qnap_photos")

    photo_path = None
    for root, dirs, files in os.walk(qnap_path):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg")):
                photo_path = os.path.join(root, f)
                break
        if photo_path:
            break

    if not photo_path:
        print("  InsightFace: нет фото для теста")
        return

    img = cv2.imread(photo_path)
    if img is None:
        return

    # Импортируем уже инициализированный синглтон
    sys.path.insert(0, "/app")
    from app.api.endpoints.search import _get_face_app

    print("  InsightFace: загрузка модели (первый раз — дольше)...")
    t1 = time.time()
    face_app = _get_face_app()
    t2 = time.time()
    print(f"  InsightFace init:           {(t2-t1)*1000:.1f} мс")

    t1 = time.time()
    faces = face_app.get(img)
    t2 = time.time()
    print(f"  InsightFace детекция:       {(t2-t1)*1000:.1f} мс  ({len(faces)} лиц найдено)")

# ─────────────────────────────────────────────
async def main():
    print("\n========== FaceWatch Benchmark ==========\n")

    print("[1] Qdrant поиск:")
    bench_qdrant()

    print("\n[2] Чтение фото с QNAP:")
    bench_qnap_photo()

    print("\n[3] MySQL/MariaDB запросы:")
    await bench_mysql()

    print("\n[4] InsightFace детекция:")
    bench_insightface()

    print("\n==========================================")
    print("Итог: сумма = время одного поиска по фото")

if __name__ == "__main__":
    asyncio.run(main())
