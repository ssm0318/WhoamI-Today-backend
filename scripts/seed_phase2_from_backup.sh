#!/usr/bin/env bash
# Seed Phase 2 from pg_dump backups.
#
# Usage:
#   ./scripts/seed_phase2_from_backup.sh <content_dump> [profiles_dump] [--dry-run] [--reset-fakes]
#
# profiles_dump defaults to content_dump (same file used for both queries).
#
# Dump paths are resolved in this order:
#   1. Host filesystem (absolute or relative)
#   2. Inside the web container
#   3. Inside the cron container  (/app/db_backup/data/)
# Files ending in .gz are decompressed automatically.
#
# Examples:
#   # Use the last hourly backup before the 5/18 reset (same file for both):
#   ./scripts/seed_phase2_from_backup.sh \
#     /app/db_backup/data/whoamitoday_2026-05-17_23.backup.gz \
#     --dry-run
#
#   # Full run:
#   ./scripts/seed_phase2_from_backup.sh \
#     /app/db_backup/data/whoamitoday_2026-05-17_23.backup.gz
#
#   # Re-run (delete previous fake users first):
#   ./scripts/seed_phase2_from_backup.sh \
#     /app/db_backup/data/whoamitoday_2026-05-17_23.backup.gz \
#     --reset-fakes
#
# Environment overrides:
#   COMPOSE_FILE   (default: docker-compose.production.yml)
#   DB_SERVICE     (default: db)
#   WEB_SERVICE    (default: web)
#   CRON_SERVICE   (default: cron)
#   DB_USER        (default: postgres)

set -euo pipefail

CONTENT_DUMP="${1:?Usage: $0 <content_dump> [profiles_dump] [--dry-run] [--reset-fakes]}"
shift

# Second arg: if it looks like a flag, treat it as an extra arg (profiles = content)
PROFILES_DUMP="$CONTENT_DUMP"
if [[ "${1:-}" != --* && -n "${1:-}" ]]; then
    PROFILES_DUMP="$1"
    shift
fi

EXTRA_ARGS=("$@")

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
CRON_SERVICE="${CRON_SERVICE:-cron}"
DB_USER="${DB_USER:-postgres}"

CONTENT_DB="whoamitoday_seed_src"
PROFILES_DB="whoamitoday_seed_profiles"
SAME_DUMP=false
[[ "$CONTENT_DUMP" == "$PROFILES_DUMP" ]] && SAME_DUMP=true

echo "=== Phase 2 seed ==="
echo "  Content dump:  $CONTENT_DUMP"
echo "  Profiles dump: $PROFILES_DUMP"
echo "  Same file:     $SAME_DUMP"
echo "  Extra args:    ${EXTRA_ARGS[*]:-<none>}"
echo "  Compose file:  $COMPOSE_FILE"
echo ""

# ── Cleanup on exit ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo "--- Cleanup ---"
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        dropdb -U "$DB_USER" --if-exists "$CONTENT_DB" 2>/dev/null || true
    if ! $SAME_DUMP; then
        docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
            dropdb -U "$DB_USER" --if-exists "$PROFILES_DB" 2>/dev/null || true
    fi
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        bash -c "rm -f /tmp/seed_content.dump /tmp/seed_profiles.dump" 2>/dev/null || true
    rm -f /tmp/_seed_content_raw.dump /tmp/_seed_profiles_raw.dump \
          /tmp/_seed_content_host.dump /tmp/_seed_profiles_host.dump 2>/dev/null || true
    echo "  Done."
}
trap cleanup EXIT

# ── Helper: fetch a dump file to a local host path ──────────────────────── #
# Handles: host paths, web-container paths, cron-container paths, .gz files.
fetch_dump() {
    local src="$1"
    local dest="$2"   # host path to write the raw (non-gz) dump

    local raw_dest="${dest%.dump}_raw.dump"

    # 1. Try host filesystem
    if [[ -f "$src" ]]; then
        echo "  Found on host: $src" >&2
        raw_dest="$src"
    else
        # 2. Try web container
        echo "  Not on host — trying $WEB_SERVICE container..." >&2
        if docker compose -f "$COMPOSE_FILE" cp "$WEB_SERVICE:$src" "$raw_dest" 2>/dev/null; then
            echo "  Copied from $WEB_SERVICE container." >&2
        else
            # 3. Try cron container
            echo "  Not in $WEB_SERVICE — trying $CRON_SERVICE container..." >&2
            if docker compose -f "$COMPOSE_FILE" cp "$CRON_SERVICE:$src" "$raw_dest" 2>/dev/null; then
                echo "  Copied from $CRON_SERVICE container." >&2
            else
                echo "ERROR: '$src' not found on host, in $WEB_SERVICE, or in $CRON_SERVICE." >&2
                exit 1
            fi
        fi
    fi

    # 4. Decompress .gz if needed (check source path, not the copied dest name)
    if [[ "$src" == *.gz ]]; then
        echo "  Decompressing → $dest ..." >&2
        gunzip -c "$raw_dest" > "$dest"
    else
        cp "$raw_dest" "$dest"
    fi
}

# ── Step 1: Fetch dump files to host ────────────────────────────────────── #
echo "--- Step 1: Fetching dump files ---"
fetch_dump "$CONTENT_DUMP"  /tmp/_seed_content_host.dump
echo "  Content dump ready."

if $SAME_DUMP; then
    cp /tmp/_seed_content_host.dump /tmp/_seed_profiles_host.dump
    echo "  Profiles dump = content dump (same file)."
else
    fetch_dump "$PROFILES_DUMP" /tmp/_seed_profiles_host.dump
    echo "  Profiles dump ready."
fi

# ── Step 2: Copy dumps into the db container ────────────────────────────── #
echo "--- Step 2: Copying dumps to db container ---"
docker compose -f "$COMPOSE_FILE" cp /tmp/_seed_content_host.dump  "$DB_SERVICE:/tmp/seed_content.dump"
docker compose -f "$COMPOSE_FILE" cp /tmp/_seed_profiles_host.dump "$DB_SERVICE:/tmp/seed_profiles.dump"
echo "  Copied."

# ── Step 3: Create temp DBs and restore ─────────────────────────────────── #
echo "--- Step 3: Restoring temp DBs ---"

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$CONTENT_DB"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    pg_restore -U "$DB_USER" -d "$CONTENT_DB" --no-owner --no-privileges \
    --no-comments -j 2 /tmp/seed_content.dump
echo "  Content DB ($CONTENT_DB) restored."

if $SAME_DUMP; then
    PROFILES_DB="$CONTENT_DB"
    echo "  Profiles DB = Content DB (skipping second restore)."
else
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        createdb -U "$DB_USER" "$PROFILES_DB"
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        pg_restore -U "$DB_USER" -d "$PROFILES_DB" --no-owner --no-privileges \
        --no-comments -j 2 /tmp/seed_profiles.dump
    echo "  Profiles DB ($PROFILES_DB) restored."
fi

# ── Step 4: Run management command ──────────────────────────────────────── #
echo "--- Step 4: Running management command ---"
docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
    python manage.py seed_phase2_from_backup \
    --content-db "$CONTENT_DB" \
    --profiles-db "$PROFILES_DB" \
    --no-input \
    "${EXTRA_ARGS[@]}"

echo ""
echo "=== Done ==="
