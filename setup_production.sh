#!/bin/bash
# FaseWatch — финальная настройка продакшна
# Запустить: bash /home/ukafase/Рабочий\ стол/FaseWatch/setup_production.sh

set -e
PROJECT_DIR="/home/ukafase/Рабочий стол/FaseWatch"

echo "=== FaseWatch Production Setup ==="

# 1. systemd автозапуск
echo ""
echo "[1/3] Настройка systemd..."
sudo cp "$PROJECT_DIR/facewatch.service" /etc/systemd/system/facewatch.service
sudo systemctl daemon-reload
sudo systemctl enable facewatch
echo "    systemd: включён (автозапуск при перезагрузке)"

# 2. Скрипт бэкапа
echo ""
echo "[2/3] Установка скрипта бэкапа..."
sudo cp /tmp/fasewatch_backup.sh /usr/local/bin/fasewatch_backup.sh
sudo chmod +x /usr/local/bin/fasewatch_backup.sh
echo "    Скрипт установлен: /usr/local/bin/fasewatch_backup.sh"

# 3. Cron — каждую ночь в 2:00
echo ""
echo "[3/3] Настройка cron (ежедневно в 2:00)..."
CRON_LINE="0 2 * * * /usr/local/bin/fasewatch_backup.sh >> /var/log/fasewatch_backup.log 2>&1"
(sudo crontab -l 2>/dev/null | grep -v fasewatch_backup; echo "$CRON_LINE") | sudo crontab -
echo "    Cron задача добавлена."

echo ""
echo "=== Готово! Проверка ==="
echo ""
echo "systemd:"
sudo systemctl is-enabled fasewatch && echo "  fasewatch.service: enabled" || echo "  ОШИБКА"

echo ""
echo "cron:"
sudo crontab -l | grep fasewatch || echo "  ОШИБКА: cron не настроен"

echo ""
echo "Доступ к приложению: http://localhost:3000"
echo "API документация:    http://localhost:8000/docs"
