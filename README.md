# FaseWatch
Как импортировать огромный архив шаг за шагом:

Положите ваш огромный .zip файл в новую папку (например: /mnt/qnap_photos/backup/my_huge_chat.zip).
Зайдите в терминале Ubuntu в папку с проектом: cd "/home/ukafase/Рабочий стол/FaseWatch"
Запустите скрипт через Docker одной командой (указав путь к файлу изнутри контейнера и название группы, в которую идет импорт):
docker compose exec backend python import_local.py /mnt/qnap_photos/backup/my_huge_chat.zip --group "Моя Огромная Группа"
