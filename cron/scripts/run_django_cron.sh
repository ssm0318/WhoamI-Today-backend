#!/bin/bash

# === 환경 변수 로드 ===
ENV_FILE="/app/.env"
DEV_ENV_FILE="/app/.env.development"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    echo "Loaded environment variables from $ENV_FILE"
elif [ -f "$DEV_ENV_FILE" ]; then
    set -a
    source "$DEV_ENV_FILE"
    set +a
    echo "Loaded environment variables from $DEV_ENV_FILE"
else
    echo "No environment file found. Exiting..."
    exit 1
fi

# === 로그 설정 ===
LOG_DIR="/app/cron/log"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date +\%Y-\%m-\%d).log"

# === runcrons 실행 ===
echo "[INFO] Running: python manage.py runcrons $*" >> "$LOG_FILE"
/usr/local/bin/python /app/adoorback/manage.py runcrons "$@" >> "$LOG_FILE" 2>&1
