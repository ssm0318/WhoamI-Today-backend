#!/bin/bash

# Set default environment variable file
ENV_FILE="/app/.env"
DEV_ENV_FILE="/app/.env.development"

# Load .env file if it exists, otherwise load .env.development
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

# Create log file and record execution time
{
    echo "========================================="
    echo "DB Backup Script Started: $(date)"

    # Perform DB backup
    BACKUP_FILE="$DATA_D/whoamitoday_$(date +%Y-%m-%d_%H).backup.gz"
    echo "Backing up database to: $BACKUP_FILE"

    # Enable pipefail
    set -o pipefail

    if PGPASSWORD=$DB_PASSWORD pg_dump -h "$DB_HOST" -U "$DB_USER" -Fc -w whoamitoday | gzip > "$BACKUP_FILE" 2>> "$LOG_FILE"; then
        echo "✅ DB backup completed successfully: $(date)"
    else
        echo "❌ DB backup failed: $(date)"
        exit 1
    fi

    # Disable pipefail (to not affect other commands)
    set +o pipefail

    # Remove backup data older than 72 hours
    echo "Removing old backups (older than 3 days)..."
    find "$DATA_D" -type f -name "whoamitoday_*.backup.gz" -mmin +4320 -exec rm -v {} \;

    echo "Backup script finished: $(date)"
    echo "========================================="
} >> "$LOG_FILE" 2>&1
