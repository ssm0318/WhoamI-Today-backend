#!/bin/bash

# Configuration
DB_CONTAINER="whoami-today-backend-db-1"
WEB_CONTAINER="whoami-backend"
DB_NAME="whoamitoday" # Default from production.py, implies check env vars if different
DB_USER="postgres"

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo "    ADOORBACK DATABASE RESET SCRIPT (DOCKER)"
echo "=========================================="
echo "WARNING: This script will:"
echo "1. Backup the current database from container: $DB_CONTAINER"
echo "2. DROP (DELETE) the current database: $DB_NAME"
echo "3. Create a fresh empty database."
echo "4. Restore seed data (Questions, Interests, Personas)."
echo "=========================================="
read -p "Are you absolutely sure you want to proceed? (y/n): " connect_confirm

if [[ "$connect_confirm" != "y" ]]; then
    echo "Aborted."
    exit 1
fi

# 1. Backup
echo "[1/6] Backing up database to $BACKUP_FILE..."
docker exec -t $DB_CONTAINER pg_dump -U $DB_USER $DB_NAME > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup successful."
else
    echo "Backup failed! Aborting."
    exit 1
fi

# 2. Recreate DB
echo "[2/6] Recreating database..."
# Stop web container to release connections
echo "Stopping web container to release DB connections..."
docker stop $WEB_CONTAINER

echo "Dropping database..."
docker exec -t $DB_CONTAINER dropdb -U $DB_USER --if-exists $DB_NAME
echo "Creating database..."
docker exec -t $DB_CONTAINER createdb -U $DB_USER $DB_NAME

echo "Starting web container..."
docker start $WEB_CONTAINER

# Wait for web container to be ready
echo "Waiting for web container to initialize (10s)..."
sleep 10

# 3. Migrate
echo "[3/6] Running migrations..."
docker exec -it $WEB_CONTAINER python3 manage.py migrate

# 4. Create Superuser
echo "[4/6] Creating Superuser..."
# This requires interactive input, so we use -it
docker exec -it $WEB_CONTAINER python3 create_admin.py

# 5. Seed Questions
echo "[5/6] Seeding Questions..."
docker exec -it $WEB_CONTAINER python3 manage.py load_questions

# 6. Seed Choices
echo "[6/6] Seeding Interests and Personas..."
docker exec -it $WEB_CONTAINER python3 manage.py initialize_choices

echo "=========================================="
echo "    DATABASE RESET COMPLETE"
echo "=========================================="
