import os
import glob
import time
import requests
import io
import fitz  # PyMuPDF
import gc

# ================= НАСТРОЙКИ =================
FOLDER_PATH = "/mnt/qnap_photos/backup" 
API_URL = "http://127.0.0.1:8000/api/bot/message"
PROCESSED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_pdfs.txt")
REQUEST_TIMEOUT = 60

GROUP_TELEGRAM_ID = "9022585"
GROUP_NAME = "Коменданська година"
# =============================================

def process_and_send_pdfs(folder_path):
    # 1. Поиск всех PDF файлов в указанной папке без рекурсии (иначе виснет на сетевом диске)
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    
    if not pdf_files:
        print(f"В папке {folder_path} не найдено ни одного PDF файла!")
        return
    
    print(f"Всего найдено PDF-файлов: {len(pdf_files)}")

    # 2. Считываем уже обработанные файлы (защита от падений)
    processed_files = set()
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                processed_files.add(line.strip())
    
    pending_pdfs = [f for f in pdf_files if f not in processed_files]
    print(f"✅ Вже оброблено: {len(processed_files)} файлів. Залишилось: {len(pending_pdfs)}")

    if len(pending_pdfs) == 0:
        print("Всі PDF-файли вже успішно завантажені! Роботу завершено.")
        return

    # Задаем начальный уникальный числовой ID (timestamp)
    current_message_id = int(time.time())

    session = requests.Session()

    print("Шаг 1. Пофайлова обробка та завантаження...")
    
    for file_index, file_path in enumerate(pending_pdfs, 1):
        print(f"\n[{file_index}/{len(pending_pdfs)}] Відкриття файлу {os.path.basename(file_path)}...")
        
        try:
            # Открываем PDF-документ
            pdf_document = fitz.open(file_path)
            pages_count = len(pdf_document)
            
            pages_uploaded_for_doc = 0
            
            file_completed_successfully = True

            for page_number in range(pages_count):
                page = pdf_document.load_page(page_number)

                # 1. Извлекаем текст именно с этой страницы
                page_text = page.get_text("text").strip()
                if not page_text:
                    page_text = "Текст відсутній на даній сторінці"

                # 2. Конвертируем страницу в картинку (300 dpi)
                zoom = 300.0 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Сохраняем пиктограмму в память (JPEG)
                image_bytes = pix.tobytes("jpeg")

                # Увеличиваем счетчик message_id
                current_message_id += 1

                # 3. Отправляем в API
                data = {
                    "group_telegram_id": GROUP_TELEGRAM_ID,
                    "group_name": GROUP_NAME,
                    "message_id": str(current_message_id),
                    "text": page_text[:4000],  # Ограничение по длине текста, если требуется (tg лимит 4096)
                }

                files_dict = {
                    "photo": (f"page_{page_number + 1}.jpg", io.BytesIO(image_bytes), "image/jpeg")
                }

                try:
                    response = session.post(
                        API_URL,
                        data=data,
                        files=files_dict,
                        timeout=REQUEST_TIMEOUT,
                    )
                except requests.RequestException as e:
                    print(f"Помилка завантаження сторінки {page_number + 1}: {e}")
                    file_completed_successfully = False
                    break

                if response.status_code != 200:
                    print(f"Помилка завантаження сторінки {page_number + 1}: {response.status_code} - {response.text}")
                    file_completed_successfully = False
                    break

                try:
                    response_payload = response.json()
                except ValueError:
                    print(f"Помилка завантаження сторінки {page_number + 1}: backend повернув не-JSON: {response.text}")
                    file_completed_successfully = False
                    break

                if response_payload.get("ok") is not True:
                    print(f"Помилка завантаження сторінки {page_number + 1}: backend повернув {response_payload}")
                    file_completed_successfully = False
                    break

                pages_uploaded_for_doc += 1

            pdf_document.close()

            if file_completed_successfully and pages_uploaded_for_doc == pages_count:
                with open(PROCESSED_FILE, "a", encoding="utf-8") as pf:
                    pf.write(f"{file_path}\n")
                print(f"👉 Документ успішно оброблено. Завантажено {pages_uploaded_for_doc} сторінок.")
            else:
                print(
                    f"⚠️ Документ НЕ позначено як оброблений. "
                    f"Завантажено {pages_uploaded_for_doc} з {pages_count} сторінок."
                )

        except Exception as e:
            print(f"Помилка при обробці файлу {file_path}: {e}")

        # Очистка памяти после каждого файла
        gc.collect()

if __name__ == "__main__":
    process_and_send_pdfs(FOLDER_PATH)
