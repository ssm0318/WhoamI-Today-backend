#!/bin/bash

# Configuration
DB_NAME="adoorback"  # Adjust if your production DB name is different
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo "    ADOORBACK DATABASE RESET SCRIPT"
echo "=========================================="
echo "WARNING: This script will:"
echo "1. Backup the current database."
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
pg_dump $DB_NAME > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup successful."
else
    echo "Backup failed! Aborting."
    exit 1
fi

# 2. Recreate DB
echo "[2/6] Recreating database..."
# Note: Recreating the DB usually requires postgres user privileges.
# We assume this script is run by a user who can sudo to postgres, or has direct access.
echo "Dropping database..."
sudo -u postgres dropdb $DB_NAME
echo "Creating database..."
sudo -u postgres createdb $DB_NAME

# 3. Migrate
echo "[3/6] Running migrations..."
python3 manage.py migrate

# 4. Create Superuser
echo "[4/6] Creating Superuser..."
# We run the helper script which uses interactive input for password
python3 create_admin.py

# 5. Seed Questions
echo "[5/6] Seeding Questions..."
python3 manage.py load_questions

# 6. Seed Choices
echo "[6/6] Seeding Interests and Personas..."
python3 manage.py initialize_choices

echo "=========================================="
echo "    DATABASE RESET COMPLETE"
echo "=========================================="
