#!/usr/bin/env python3
"""
Проверка прогресса обработки фото.
Запускайте вручную для получения текущей статистики.
"""
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://facewatch:ke050442@192.168.24.178:3306/facewatch_db"

engine = create_engine(DB_URL)
with engine.connect() as conn:
    total = conn.execute(text('SELECT COUNT(*) FROM messages WHERE has_photo=1')).scalar()
    faces = conn.execute(text('SELECT COUNT(*) FROM faces')).scalar()

engine.dispose()

print(f"📊 Статистика обработки:")
print(f"   Всего фото: {total:,}")
print(f"   Найдено лиц: {faces:,}")
if total > 0:
    print(f"   Лиц на фото: {faces/total:.2f}")
