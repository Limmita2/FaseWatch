import os
import json
import base64
import requests
import io
import glob
import gc

# ================= НАСТРОЙКИ =================
FOLDER_PATH = "/mnt/qnap_photos/backup" 
API_URL = "http://127.0.0.1:8000/api/bot/message"
PROCESSED_FILE = "./processed_ids.txt"

# Порог отсеивания заглушек. 
MIN_BASE64_LENGTH = 3000 
# =============================================

def process_and_send(folder_path):
    main_file = os.path.join(folder_path, "mvswantedperson_1.json")
    if not os.path.exists(main_file):
        print(f"Главный файл {main_file} не найден!")
        return

    # 1. Считываем уже обработанные ID из базы (чтобы не было дублей)
    processed_ids = set()
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                processed_ids.add(line.strip())
    
    print(f"✅ Вже завантажено в БД: {len(processed_ids)} фотографій. Вони будуть пропущені.")

    # 2. Загружаем информацию об анкетах
    print("Шаг 1. Загрузка информации об анкетах...")
    try:
        with open(main_file, "r", encoding="utf-8") as f:
            persons = json.load(f)
    except Exception as e:
        print(f"Ошибка при чтении главного файла: {e}")
        return

    # Словарь "Кому еще нужно загрузить фото" (исключаем уже загруженных)
    pending_persons = {}
    for person in persons:
        photo_id = str(person.get("PHOTOID"))
        if photo_id and photo_id not in processed_ids:
            pending_persons[photo_id] = person
    
    del persons # Очищаем память
    gc.collect()

    print(f"⏳ Залишилось обробити та завантажити: {len(pending_persons)} анкет з фото.")

    if len(pending_persons) == 0:
        print("Всі анкети успішно завантажені! Роботу завершено.")
        return

    # 3. Обрабатываем файлы с фотографиями по одному (чтобы не было Out Of Memory)
    photo_files = glob.glob(os.path.join(folder_path, "mvswantedperson_photo_*.json"))
    
    session = requests.Session()

    print("Шаг 2. Пофайлове завантаження та відправка...")
    for file_index, file_path in enumerate(photo_files, 1):
        print(f"\n[{file_index}/{len(photo_files)}] Відкриття файлу {os.path.basename(file_path)}...")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                photos = json.load(f)
                
            uploaded_in_file = 0

            for photo in photos:
                photo_id = str(photo.get("ID"))
                b64_data = photo.get("PHOTOIDBASE64ENCODE")

                # Пропускаем если: нет данных, заглушка, или мы уже загрузили его ранее
                if not photo_id or not b64_data:
                    continue
                if len(b64_data) < MIN_BASE64_LENGTH:
                    continue
                if photo_id not in pending_persons:
                    continue

                person = pending_persons[photo_id]

                # Извлекаем остальные данные
                last_name = person.get("LAST_NAME_U") or ""
                first_name = person.get("FIRST_NAME_U") or ""
                middle_name = person.get("MIDDLE_NAME_U") or ""
                fio = f"{last_name} {first_name} {middle_name}".strip()

                birth_date = person.get("BIRTH_DATE") or "Невідомо"
                article = person.get("ARTICLE_CRIM") or "Не вказана"
                category = person.get("CATEGORY") or "Не вказана"
                lost_date = person.get("LOST_DATE") or "Невідомо"
                lost_place = person.get("LOST_PLACE") or "Невідомо"

                text = (
                    f"ПІБ: {fio}\n"
                    f"Дата народження: {birth_date}\n"
                    f"Стаття: {article}\n"
                    f"Категорія: {category}\n"
                    f"Дата зникнення: {lost_date}\n"
                    f"Місце зникнення: {lost_place}"
                )

                data = {
                    "group_telegram_id": "999999021",
                    "group_name": "Розшук МВС",
                    "message_id": str(photo_id),
                    "text": text,
                }

                try:
                    image_bytes = base64.b64decode(b64_data)
                    files = {
                        "photo": (f"{photo_id}.jpg", io.BytesIO(image_bytes), "image/jpeg")
                    }
                    
                    response = session.post(API_URL, data=data, files=files)
                    
                    if response.status_code == 200:
                        # Записываем успешно загруженный ID в файл, чтобы даже при новом падении мы не начали с начала
                        with open(PROCESSED_FILE, "a", encoding="utf-8") as pf:
                            pf.write(f"{photo_id}\n")
                        
                        # Убираем из очереди
                        del pending_persons[photo_id]
                        uploaded_in_file += 1
                        
                        if uploaded_in_file % 100 == 0:
                            print(f"З цього файлу завантажено вже {uploaded_in_file} фото...")
                    
                except Exception as e:
                    print(f"Помилка при обробці/відправці {fio}: {e}")

            print(f"👉 Завершено розбір {os.path.basename(file_path)}. Успішно загружено з нього: {uploaded_in_file}")
            
            # ВАЖНО: Удаляем данные из памяти перед следующим файлом!
            del photos
            gc.collect()

        except Exception as e:
            print(f"Помилка при читанні файлу {file_path}: {e}")

if __name__ == "__main__":
    process_and_send(FOLDER_PATH)
