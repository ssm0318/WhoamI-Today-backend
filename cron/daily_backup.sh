#!/bin/bash -x

source /app/.env
# crontab setting
## 59 23 * * * /home/ubuntu/WhoAmI-Today-backend/db_backup/daily_backup.sh >> /home/ubuntu/WhoAmI-Today-backend/db_backup/log/$(date +\%Y-\%m-\%d-\%H-\%M-\%S).log 2>&1

CURR_D=$(realpath $(dirname $0))
DATA_D=$CURR_D/data
DATE=$(date +%Y-%m-%d)
DATE_RM=$(date --date="7 days ago" +%Y-%m-%d)

# dump
PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -Fc -w whoamitoday | gzip > $DATA_D/whoamitoday_${DATE}.backup.gz

# remove backup data older than 1 week
rm -rf $DATA_D/whoamitoday_${DATE_RM}.backup.gz

