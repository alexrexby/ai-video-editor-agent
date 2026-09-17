#!/usr/bin/env bash
set -e

# Configuration: pass arguments or set environment variables
# Usage: ./deploy.sh user@server_ip ~/.ssh/key_path /opt/app_dir service_name
SERVER="${1:-${DEPLOY_SERVER:-root@your-server-ip}}"
KEY="${2:-${DEPLOY_SSH_KEY:-$HOME/.ssh/id_rsa}}"
REMOTE_DIR="${3:-${DEPLOY_REMOTE_DIR:-/opt/ai_video_editor}}"
SERVICE_NAME="${4:-${DEPLOY_SERVICE_NAME:-ai-video-agent.service}}"

if [[ "$SERVER" == "root@your-server-ip" ]]; then
    echo "❌ Ошибка: Укажите адрес сервера для деплоя!"
    echo "Пример: ./deploy.sh root@123.45.67.89 ~/.ssh/id_rsa"
    exit 1
fi

echo "🚀 [1/3] Синхронизация файлов проекта на $SERVER:$REMOTE_DIR/..."
rsync -avz -e "ssh -i $KEY -o StrictHostKeyChecking=no" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'venv' \
    --exclude '.venv' \
    --exclude 'node_modules' \
    --exclude '.env' \
    --exclude 'temp_render' \
    --exclude '*.mp4' \
    --exclude '*.mov' \
    --exclude '*.log' \
    --exclude '.DS_Store' \
    ./ "$SERVER:$REMOTE_DIR/"

echo "⚙️ [2/3] Перезапуск службы $SERVICE_NAME на сервере..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "systemctl restart $SERVICE_NAME"

echo "✅ [3/3] Деплой успешно завершён!"
