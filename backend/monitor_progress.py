#!/usr/bin/env python3
"""
Монитор прогресса обработки фото.
Показывает прогресс-бар в реальном времени.
"""
import sys
import time
from sqlalchemy import create_engine, text
from tqdm import tqdm

DB_URL = "mysql+pymysql://facewatch:ke050442@192.168.24.178:3306/facewatch_db"


def get_stats():
    """Получить статистику из БД."""
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        total = conn.execute(text('SELECT COUNT(*) FROM messages WHERE has_photo=1')).scalar()
        faces = conn.execute(text('SELECT COUNT(*) FROM faces')).scalar()
    engine.dispose()
    return total, faces


def main():
    print("Мониторинг прогресса обработки фото...\n")
    
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False
        print("tqdm не установлен. Установите: pip install tqdm\n")
    
    total_photos, total_faces = get_stats()
    
    # Считаем обработанные сообщения по наличию faces
    engine = create_engine(DB_URL)
    
    if has_tqdm:
        with tqdm(total=total_photos, desc="Обработка", unit="фото", ncols=100) as pbar:
            pbar.set_postfix({'лиц': total_faces})
            last_faces = total_faces
            last_photos = 0
            
            try:
                while True:
                    time.sleep(5)
                    _, new_faces = get_stats()
                    
                    # Оцениваем прогресс по количеству лиц
                    # (каждое фото ≈ 0.8 лица в среднем)
                    estimated_processed = min(total_photos, int(new_faces / 0.8))
                    
                    pbar.n = estimated_processed
                    pbar.set_postfix({'лиц': new_faces, '+': new_faces - last_faces})
                    pbar.refresh()
                    
                    if new_faces == last_faces:
                        # Проверяем, не закончилась ли обработка
                        time.sleep(5)
                        _, final_faces = get_stats()
                        if final_faces == last_faces:
                            print("\n✅ Обработка завершена!")
                            break
                    
                    last_faces = new_faces
                    
            except KeyboardInterrupt:
                print("\n\nМониторинг остановлен пользователем.")
    else:
        # Простой режим без tqdm
        last_faces = total_faces
        try:
            while True:
                time.sleep(5)
                _, new_faces = get_stats()
                
                # Простая текстовая прогрессия
                estimated_processed = min(total_photos, int(new_faces / 0.8))
                percent = (estimated_processed / total_photos) * 100 if total_photos > 0 else 0
                
                bar_len = 50
                filled = int(bar_len * estimated_processed / total_photos) if total_photos > 0 else 0
                bar = '█' * filled + '░' * (bar_len - filled)
                
                sys.stdout.write(f'\r[{bar}] {estimated_processed}/{total_photos} ({percent:.1f}%) | Лиц: {new_faces} (+{new_faces - last_faces})')
                sys.stdout.flush()
                
                if new_faces == last_faces:
                    time.sleep(5)
                    _, final_faces = get_stats()
                    if final_faces == last_faces:
                        print("\n✅ Обработка завершена!")
                        break
                
                last_faces = new_faces
                
        except KeyboardInterrupt:
            print("\n\nМониторинг остановлен пользователем.")
    
    # Финальная статистика
    final_photos, final_faces = get_stats()
    print(f"\n📊 Финальная статистика:")
    print(f"   Всего фото: {final_photos}")
    print(f"   Найдено лиц: {final_faces}")
    print(f"   Лиц на фото: {final_faces/final_photos:.2f}" if final_photos > 0 else "")


if __name__ == "__main__":
    main()
