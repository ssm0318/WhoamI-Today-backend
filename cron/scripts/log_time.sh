#!/bin/bash

LOG_DIR="/app/cron/log"
LOG_FILE="${LOG_DIR}/$(date +\%Y-\%m-\%d).log"

mkdir -p "$LOG_DIR"
echo "$(date +\%Y-\%m-\%d-\%H-\%M-\%S)" >> "$LOG_FILE"
