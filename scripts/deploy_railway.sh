#!/bin/bash
# =============================================================
# Деплой railway-bot + загрузка ACWAG данных на Hetzner
# Запускать на Hetzner VPS в папке ~/tulm-dept-agents/
# =============================================================

set -e

echo "=== 1. Git pull последних изменений ==="
git pull origin main

echo ""
echo "=== 2. Копируем ACWAG.xlsx на сервер (запусти с локальной машины) ==="
echo "    scp ACWAG.xlsx root@HETZNER_IP:~/tulm-dept-agents/"
echo "    (если уже скопирован — пропусти)"
echo ""

echo "=== 3. Поднимаем postgres-railway если не запущен ==="
docker compose -f docker-compose.prod.yml up -d postgres-railway
sleep 5

echo ""
echo "=== 4. Загружаем ACWAG данные в railbot_db ==="
docker compose -f docker-compose.prod.yml run --rm \
  -e PG_CONNECTION_STRING=postgresql://railbot:railbot2026@postgres-railway:5432/railbot_db \
  -v "$(pwd)/ACWAG.xlsx:/app/ACWAG.xlsx" \
  railway-bot \
  python3 scripts/load_acwag.py /app/ACWAG.xlsx

echo ""
echo "=== 5. Перезапускаем railway-bot с новым кодом ==="
docker compose -f docker-compose.prod.yml up -d --build railway-bot

echo ""
echo "=== 6. Проверяем логи ==="
sleep 3
docker compose -f docker-compose.prod.yml logs --tail=30 railway-bot

echo ""
echo "✅ Готово! Проверь бота: @TULM_Railway_bot"
echo "   Тест: 'статистика ACWAG' / 'сколько вагонов Raykam' / 'вагоны за 2024'"
