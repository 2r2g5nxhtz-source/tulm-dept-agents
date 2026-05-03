#!/bin/sh
# Запускаем оба процесса:
# - webhook_server.py для GitHub Actions auto-deploy (порт 9999)
# - bot.py для ручного управления через Telegram (если задан DEPLOY_BOT_TOKEN)

set -e

python webhook_server.py &
WEBHOOK_PID=$!

if [ -n "$DEPLOY_BOT_TOKEN" ]; then
    python bot.py &
    BOT_PID=$!
    echo "Started webhook (pid=$WEBHOOK_PID) and telegram bot (pid=$BOT_PID)"
else
    echo "DEPLOY_BOT_TOKEN not set, running webhook only (pid=$WEBHOOK_PID)"
fi

# Если любой процесс упадёт — перезапускаем контейнер (Docker restart policy сработает)
wait -n
exit $?
