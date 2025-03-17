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

# Set backup directories
DATA_D="/app/db_backup/data"
LOG_DIR="/app/db_backup/log"
LOG_FILE="${LOG_DIR}/backup_$(date +\%Y-\%m-\%d).log"

# Ensure directories exist
mkdir -p "$DATA_D" "$LOG_DIR"

# 로그 파일 생성 및 실행 시간 기록
{
    echo "========================================="
    echo "DB Backup Script Started: $(date)"

    # Perform DB backup
    BACKUP_FILE="$DATA_D/whoamitoday_$(date +%Y-%m-%d).backup.gz"
    echo "Backing up database to: $BACKUP_FILE"

    # pipefail 활성화
    set -o pipefail

    if PGPASSWORD=$DB_PASSWORD pg_dump -h abc -U "$DB_USER" -Fc -w whoamitoday | gzip > "$BACKUP_FILE" 2>> "$LOG_FILE"; then
        echo "DB backup completed successfully: $(date)"
    else
        echo "❌ DB backup failed: $(date)"
        exit 1
    fi

    # pipefail 비활성화 (다른 명령어에 영향 안 주도록)
    set +o pipefail

    # Remove backup data older than 7 days
    echo "Removing old backups..."
    find "$DATA_D" -type f -name "whoamitoday_*.backup.gz" -mtime +7 -exec rm -v {} \;

    echo "Backup script finished: $(date)"
    echo "========================================="
} >> "$LOG_FILE" 2>&1
