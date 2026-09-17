#!/usr/bin/env bash
set -e

APP_DIR="${1:-/opt/ai_video_editor}"

echo "=== [1/5] Обновление пакетов и установка системных утилит ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ffmpeg git rsync curl ca-certificates gnupg

# Установка Node.js 20.x (LTS) для Remotion
if ! command -v node &> /dev/null; then
    echo "📦 Установка Node.js 20.x..."
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --yes
    NODE_MAJOR=20
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
    apt-get update -y
    apt-get install -y nodejs
fi

echo "=== [2/5] Настройка рабочей директории $APP_DIR ==="
mkdir -p "$APP_DIR"

echo "=== [3/5] Создание Python venv и установка зависимостей ==="
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi

"$APP_DIR/venv/bin/pip" install --upgrade pip
if [ -f "$APP_DIR/requirements.txt" ]; then
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

echo "=== [4/5] Установка зависимостей Remotion ==="
if [ -d "$APP_DIR/remotion" ]; then
    cd "$APP_DIR/remotion"
    npm install
    if [ -f "public/fonts/download_fonts.sh" ]; then
        bash public/fonts/download_fonts.sh
    fi
    cd "$APP_DIR"
fi

echo "=== [5/5] Настройка Systemd службы ==="
cat << EOF > /etc/systemd/system/ai-video-agent.service
[Unit]
Description=AI Video & Content Team Telegram Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-video-agent.service

echo "=== Готово! Скопируйте .env.example в .env и запустите: ==="
echo "  systemctl start ai-video-agent.service"
echo "  systemctl status ai-video-agent.service --no-pager"
