import asyncio
import os
import sys
import uuid
import re
import shutil
import zipfile
import traceback
from pathlib import Path
from datetime import datetime
import argparse

# Добавляем путь, чтобы импорты приложения работали
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal
from app.models.models import Group, Message
from app.core.config import settings
from app.api.endpoints.imports import parse_telegram_messages_html
from app.worker.tasks import process_photo
from sqlalchemy import select

async def import_backup_local(zip_path: str, group_name: str, extract_dir: str = "/mnt/qnap_photos/backup/temp_extract"):
    if not os.path.exists(zip_path):
        print(f"❌ Файл {zip_path} не найден.")
        return

    print(f"🚀 Начинаем импорт из {zip_path} в группу '{group_name}'")
    
    # 1. Создаем или находим группу
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Group).where(Group.name == group_name))
        group = result.scalar_one_or_none()
        
        if not group:
            group = Group(id=uuid.uuid4(), name=group_name)
            db.add(group)
            await db.commit()
            await db.refresh(group)
            print(f"📁 Создана новая группа: {group_name} (ID: {group.id})")
        else:
            print(f"📁 Используем существующую группу: {group_name} (ID: {group.id})")

    # 2. Распаковка архива
    zip_dir = os.path.join(extract_dir, f"extract_{uuid.uuid4().hex[:8]}")
    os.makedirs(zip_dir, exist_ok=True)
    
    try:
        print(f"⏳ Распаковка архива в {zip_dir}...")
        print("   (Для файлов размером ~40GB этот процесс может занять от 10 минут до часа в зависимости от диска)")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(zip_dir)
        print("✅ Распаковка завершена.")

        # 3. Поиск файлов сообщений
        export_dir = None
        html_files = []
        for root, dirs, files in os.walk(zip_dir):
            for file_name in files:
                if re.match(r"^messages.*\.html$", file_name):
                    export_dir = root
                    html_files.append(file_name)

        if not export_dir or not html_files:
            print("❌ Файлы сообщений (messages*.html) не найдены в архиве.")
            return

        def sort_key(filename):
            match = re.search(r"messages(\d*)\.html", filename)
            if not match: return 0
            num_str = match.group(1)
            return int(num_str) if num_str else 0

        html_files.sort(key=sort_key)
        photos_dir = os.path.join(export_dir, "photos")
        
        print(f"📋 Найдено {len(html_files)} файлов с сообщениями (HTML).")

        # 4. Обработка файлов по очереди, чтобы избежать OOM (вылета по оперативной памяти)
        stats = {"messages": 0, "photos": 0, "faces_queued": 0}
        
        for html_file in html_files:
            print(f"👉 Парсинг {html_file}...")
            html_path = os.path.join(export_dir, html_file)
            
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
                
            messages_data = parse_telegram_messages_html(html_content, photos_dir if os.path.exists(photos_dir) else "")
            print(f"   Найдено {len(messages_data)} сообщений. Идет сохранение в Базу Данных и копирование фото...")
            
            # Открываем новую сессию БД для каждого файла, чтобы не держать огромные транзакции
            async with AsyncSessionLocal() as db:
                for msg_data in messages_data:
                    has_photo = bool(msg_data["photo_rel_path"])
                    photo_qnap_path = None

                    if has_photo and os.path.exists(photos_dir):
                        src_photo = os.path.join(export_dir, msg_data["photo_rel_path"])
                        if os.path.isfile(src_photo):
                            ts_str = msg_data["timestamp"].strftime("%Y-%m") if msg_data["timestamp"] else "unknown"
                            dest_dir = Path(settings.QNAP_MOUNT_PATH) / "photos" / str(group.id) / ts_str
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest_file = dest_dir / f"{msg_data['message_id']}_{uuid.uuid4().hex[:8]}.jpg"
                            
                            shutil.copy2(src_photo, str(dest_file))
                            photo_qnap_path = str(dest_file)
                            stats["photos"] += 1

                    msg = Message(
                        id=uuid.uuid4(),
                        group_id=group.id,
                        telegram_message_id=int(msg_data["message_id"]) if msg_data["message_id"] else None,
                        sender_name=msg_data["sender_name"],
                        text=msg_data["text"],
                        has_photo=has_photo,
                        photo_path=photo_qnap_path,
                        timestamp=msg_data["timestamp"],
                        imported_from_backup=True,
                    )
                    db.add(msg)
                    stats["messages"] += 1

                    # Прямая отправка в Celery очередь
                    if photo_qnap_path:
                        process_photo.delay(
                            str(msg.id),
                            photo_qnap_path,
                            str(group.id),
                            msg_data["timestamp"].isoformat() if msg_data["timestamp"] else "",
                        )
                        stats["faces_queued"] += 1
                        
                await db.commit()
                print(f"   Файл {html_file} успешно обработан!")

        print("\n==================================")
        print("🎉 ИМПОРТ УСПЕШНО ЗАВЕРШЕН!")
        print(f"✉️  Сообщений добавлено: {stats['messages']}")
        print(f"📸 Фотографий скопировано на QNAP: {stats['photos']}")
        print(f"🤖 Отправлено задач в Celery на распознавание: {stats['faces_queued']}")
        print("==================================\n")
        
    except Exception as e:
        print(f"\n❌ ПРОИЗОШЛА КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
    finally:
        print(f"🧹 Очистка временных файлов ({zip_dir}). Пожалуйста, подождите...")
        shutil.rmtree(zip_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Локальный скрипт для импорта ОГРОМНЫХ ZIP-архивов Telegram Desktop (создан специально для больших файлов, например >40GB).")
    parser.add_argument("zip_path", help="Абсолютный путь к ZIP архиву, например, /mnt/qnap_photos/backup/my_export.zip")
    parser.add_argument("--group", required=True, help="Название группы в которую нужно импортировать данные (или к которой нужно добавить данные)")
    
    args = parser.parse_args()
    
    asyncio.run(import_backup_local(args.zip_path, args.group))
