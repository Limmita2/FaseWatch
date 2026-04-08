# FaseWatch
Как импортировать огромный архив шаг за шагом:

Положите ваш огромный .zip файл в новую папку (например: /mnt/qnap_photos/backup/my_huge_chat.zip).
Зайдите в терминале Ubuntu в папку с проектом: cd "/home/ukafase/Рабочий стол/FaseWatch"
Запустите скрипт через Docker одной командой (указав путь к файлу изнутри контейнера и название группы, в которую идет импорт):
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/my_huge_chat.zip --group "Моя Огромная Группа"

Важно на будущее: при изменениях кода backend всегда нужно делать 'docker compose build backend && docker compose up -d backend', а не просто restart.

docker compose exec backend python import_local.py /mnt/qnap_photos/backup/1.zip --group "КОПІНФО ЛРУ"

## WhatsApp подключение

1. Соберите и поднимите сервис: `docker compose build facewatch_whatsapp && docker compose up -d facewatch_whatsapp`
2. Посмотрите QR-код в логах: `docker logs -f facewatch_whatsapp`
3. Отсканируйте QR в WhatsApp: `Настройки -> Связанные устройства -> Привязка устройства`
4. После успешной авторизации сессия сохранится в `./whatsapp-session`, повторное сканирование после обычного рестарта не потребуется

Важно:
- backend должен быть доступен по `WHATSAPP_BACKEND_URL`
- при потере сессии контейнер завершится и после рестарта покажет новый QR
- сервис читает только групповые входящие сообщения и не отправляет read/delivery confirmations
