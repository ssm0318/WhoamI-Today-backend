#!/bin/bash

# 기본 환경 변수 파일 설정
ENV_FILE="/app/.env"
DEV_ENV_FILE="/app/.env.development"

# .env 파일이 존재하면 로드하고, 없으면 .env.development를 로드
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

LOG_DIR="/app/cron/log"
# shellcheck disable=SC1001
LOG_FILE="${LOG_DIR}/$(date +\%Y-\%m-\%d).log"

mkdir -p "$LOG_DIR"
/usr/local/bin/python /app/adoorback/manage.py runcrons >> "$LOG_FILE" 2>&1
