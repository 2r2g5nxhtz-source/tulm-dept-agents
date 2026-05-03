#!/bin/bash
# Синхронизация railway_tools.py и maritime_tools.py с Hetzner → локальный репо
# Запускать: bash scripts/sync_from_hetzner.sh

set -e
SERVER="root@178.104.81.174"
REMOTE_DIR="/root/tulm-dept-agents/agent"
LOCAL_DIR="$(dirname "$0")/../agent"

echo "=== Синхронизация инструментов с Hetzner ==="

# Скачиваем railway_tools.py
echo "Скачиваю railway_tools.py..."
scp "$SERVER:$REMOTE_DIR/railway_tools.py" "$LOCAL_DIR/railway_tools.py"
echo "  ✅ railway_tools.py"

# Скачиваем maritime_tools.py
echo "Скачиваю maritime_tools.py..."
scp "$SERVER:$REMOTE_DIR/maritime_tools.py" "$LOCAL_DIR/maritime_tools.py"
echo "  ✅ maritime_tools.py"

# Скачиваем актуальный agent_factory.py с сервера (он богаче локального)
echo "Скачиваю agent_factory.py..."
scp "$SERVER:$REMOTE_DIR/agent_factory.py" "$LOCAL_DIR/agent_factory.py"
echo "  ✅ agent_factory.py"

echo ""
echo "=== Синхронизация завершена ==="
echo "Проверь изменения: git diff agent/"
echo "Затем: git add agent/ && git commit -m 'sync railway/maritime tools from hetzner'"
