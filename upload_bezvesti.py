import os
import json
import base64
import requests
import io
import glob
import gc
import ijson

# ================= НАСТРОЙКИ =================
FOLDER_PATH = "/mnt/qnap_photos/backup" 
API_URL = "http://127.0.0.1:8000/api/bot/message"
PROCESSED_FILE = "./processed_bezvesti_ids.txt"

# Порог отсеивания заглушек. 
MIN_BASE64_LENGTH = 3000

# =============================================

def format_date(date_str):
    """
    Конвертирует дату из формата '1999-07-09T00:00:00' или '1999-07-09'
    в формат '09.07.1999'. Если дата пустая или некорректная, возвращает как есть.
    """
    if not date_str:
        return "Невідомо"
    try:
        # Убираем время, если оно есть (оставляем только YYYY-MM-DD)
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        
        # Разбиваем по тире
        parts = date_str.split("-")
        if len(parts) == 3:
            # Возвращаем в формате DD.MM.YYYY
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return date_str

def process_and_send(folder_path):
    main_file = os.path.join(folder_path, "mvswantedbezvesti_1.json")
    if not os.path.exists(main_file):
        print(f"Главный файл {main_file} не найден!")
        return

    # 1. Считываем уже обработанные ID из базы (чтобы не было дублей)
    processed_ids = set()
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                processed_ids.add(line.strip())
    
    print(f"✅ Вже завантажено в БД: {len(processed_ids)} анкет безвісти зниклих. Вони будуть пропущені.")

    # 2. Загружаем информацию об анкетах
    print("Крок 1. Завантаження інформації про анкети...")
    try:
        with open(main_file, "r", encoding="utf-8") as f:
            persons = json.load(f)
    except Exception as e:
        print(f"Помилка при читанні головного файлу: {e}")
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
    total_to_upload = len(pending_persons)

    if total_to_upload == 0:
        print("Всі анкети успішно завантажені! Роботу завершено.")
        return

    # Список файлов с фото для базы без вести пропавших
    photo_files = [
        os.path.join(folder_path, "mvswantedbezvesti_photo.json"),
        os.path.join(folder_path, "mvswantedbezvesti_photof.json")
    ]
    
    session = requests.Session()
    total_uploaded = 0

    print("Крок 2. Пофайлове завантаження та відправка...")
    for file_index, file_path in enumerate(photo_files, 1):
        if not os.path.exists(file_path):
            print(f"Файл {file_path} не знайдено, пропускаємо.")
            continue
            
        print(f"\n[{file_index}/{len(photo_files)}] Відкриття файлу {os.path.basename(file_path)}...")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Використовуємо ijson для потокового читання без завантаження в оперативну пам'ять
                photos = ijson.items(f, 'item')
                
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

                    # Извлекаем данные
                    last_name = person.get("LAST_NAME_U") or ""
                    first_name = person.get("FIRST_NAME_U") or ""
                    middle_name = person.get("MIDDLE_NAME_U") or ""
                    fio = f"{last_name} {first_name} {middle_name}".strip()

                    # Форматуємо дати за вашим запитом
                    birth_date = format_date(person.get("BIRTH_DATE"))
                    lost_date = format_date(person.get("LOST_DATE"))
                    
                    article = person.get("ARTICLE_CRIM") or "Не вказана"
                    category = person.get("CATEGORY") or "Не вказана"
                    lost_place = person.get("LOST_PLACE") or "Невідомо"

                    text = (
                        f"ПІБ: {fio}\n"
                        f"Дата народження: {birth_date}\n"
                        f"Стаття: {article}\n"
                        f"Категорія: {category}\n"
                        f"Дата зникнення: {lost_date}\n"
                        f"Місце зникнення: {lost_place}"
                    )

                    # ВАЖЛИВО: Я створив нову групу "Безвісти зниклі", щоб анкети розшуку і безвісти не перемішалися
                    # і щоб не було конфліктів унікальних ID
                    data = {
                        "group_telegram_id": "999999022",
                        "group_name": "Безвісти зниклі МВС",
                        "message_id": str(photo_id),
                        "text": text,
                    }

                    try:
                        image_bytes = base64.b64decode(b64_data)
                        files = {
                            "photo": (f"{photo_id}.jpg", io.BytesIO(image_bytes), "image/jpeg")
                        }
                        
                        print(f"[{total_uploaded + 1}/{total_to_upload}] Відправляємо анкети {fio}...", end=" ", flush=True)
                        response = session.post(API_URL, data=data, files=files)
                        
                        if response.status_code == 200:
                            print("✅ ОК")
                            # Записываем успешно загруженный ID в файл
                            with open(PROCESSED_FILE, "a", encoding="utf-8") as pf:
                                pf.write(f"{photo_id}\n")
                            
                            # Убираем из очереди
                            del pending_persons[photo_id]
                            uploaded_in_file += 1
                            total_uploaded += 1
                            
                            if uploaded_in_file % 100 == 0:
                                print(f"З цього файлу завантажено вже {uploaded_in_file} фото...")
                                
                            # Пауза тільки після перших 10 завантажених фотографій
                            if total_uploaded == 10:
                                print("\n✋ ТЕСТ: Завантажено рівно 10 фотографій.")
                                print("Будь ласка, перевірте як вони відображаються у вас у системі.")
                                input("\n▶️ Коли будете готові, натисніть клавішу Enter, щоб продовжити завантаження всіх інших фотографій... ")
                                print("⏳ Продовжуємо фонове завантаження...\n")
                        
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
