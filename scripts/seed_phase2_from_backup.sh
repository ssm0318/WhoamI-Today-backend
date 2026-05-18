#!/usr/bin/env bash
# Seed Phase 2 from pg_dump backups.
#
# Usage:
#   ./scripts/seed_phase2_from_backup.sh <dump> [--dry-run] [--reset-fakes] [--skip-notes-with-images]
#
# <dump> is resolved in order: host path → web container → cron container.
# The same file is used for both content and profile queries.
#
# pg_restore is run from the CRON container (has the same pg version that
# created the dump), connecting to the DB service — avoids version mismatch
# with the db container's older pg_restore.
#
# Environment overrides:
#   COMPOSE_FILE   (default: docker-compose.production.yml)
#   DB_SERVICE     (default: db)
#   WEB_SERVICE    (default: web)
#   CRON_SERVICE   (default: cron)
#   DB_USER        (default: postgres)

set -euo pipefail

DUMP_SRC="${1:?Usage: $0 <dump_path> [--dry-run] [--reset-fakes] [--skip-notes-with-images]}"
shift
EXTRA_ARGS=("$@")

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
CRON_SERVICE="${CRON_SERVICE:-cron}"
DB_USER="${DB_USER:-postgres}"

SEED_DB="whoamitoday_seed_src"

echo "=== Phase 2 seed ==="
echo "  Dump:        $DUMP_SRC"
echo "  Extra args:  ${EXTRA_ARGS[*]:-<none>}"
echo "  Compose:     $COMPOSE_FILE"
echo ""

# ── Cleanup on exit ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo "--- Cleanup ---"
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        dropdb -U "$DB_USER" --if-exists "$SEED_DB" 2>/dev/null || true
    # Remove any temp file we may have copied to cron container
    docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
        bash -c "rm -f /tmp/_seed_restore.dump" 2>/dev/null || true
    echo "  Done."
}
trap cleanup EXIT

# ── Step 1: Locate the dump file ─────────────────────────────────────────── #
echo "--- Step 1: Locating dump file ---"

DUMP_LOC=""   # "host" | "cron" | "web"
DUMP_PATH=""  # resolved path (on host or inside DUMP_LOC container)

if [[ -f "$DUMP_SRC" ]]; then
    DUMP_LOC="host"
    DUMP_PATH="$DUMP_SRC"
    echo "  Found on host."
elif docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
        bash -c "test -f '$DUMP_SRC'" 2>/dev/null; then
    DUMP_LOC="cron"
    DUMP_PATH="$DUMP_SRC"
    echo "  Found in $CRON_SERVICE container."
elif docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
        bash -c "test -f '$DUMP_SRC'" 2>/dev/null; then
    # Copy from web to cron so cron's pg_restore can read it
    echo "  Found in $WEB_SERVICE — copying to $CRON_SERVICE..."
    docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
        bash -c "cat '$DUMP_SRC'" \
        | docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
            bash -c "cat > /tmp/_seed_restore.dump"
    DUMP_LOC="cron"
    DUMP_PATH="/tmp/_seed_restore.dump"
    echo "  Copied."
else
    echo "ERROR: '$DUMP_SRC' not found on host, in $CRON_SERVICE, or in $WEB_SERVICE." >&2
    exit 1
fi

# ── Step 2: Create temp DB ───────────────────────────────────────────────── #
echo "--- Step 2: Creating temp DB ($SEED_DB) ---"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$SEED_DB"
echo "  Created."

# ── Step 3: Restore via cron container's pg_restore ─────────────────────── #
# The cron container has the same pg version that created the dump,
# so it can read the archive format. It connects to the db service directly.
echo "--- Step 3: Restoring $SEED_DB (via $CRON_SERVICE pg_restore) ---"

# Decompress .gz on the fly if needed, pipe into pg_restore
if [[ "$DUMP_LOC" == "cron" ]]; then
    if [[ "$DUMP_PATH" == *.gz ]]; then
        READ_CMD="zcat '$DUMP_PATH'"
    else
        READ_CMD="cat '$DUMP_PATH'"
    fi
    docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" bash -c \
        "$READ_CMD | PGPASSWORD=\$DB_PASSWORD pg_restore \
        -h $DB_SERVICE -U \$DB_USER -d $SEED_DB \
        --no-owner --no-privileges" \
        && echo "  Restored." || echo "  (pg_restore finished with warnings — usually OK)"
else
    # File is on host — stream into cron's pg_restore via stdin
    if [[ "$DUMP_PATH" == *.gz ]]; then
        zcat "$DUMP_PATH"
    else
        cat "$DUMP_PATH"
    fi | docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" bash -c \
        "PGPASSWORD=\$DB_PASSWORD pg_restore \
        -h $DB_SERVICE -U \$DB_USER -d $SEED_DB \
        --no-owner --no-privileges" \
        && echo "  Restored." || echo "  (pg_restore finished with warnings — usually OK)"
fi

# ── Step 4: Run management command ──────────────────────────────────────── #
echo "--- Step 4: Running management command ---"
docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
    python manage.py seed_phase2_from_backup \
    --content-db "$SEED_DB" \
    --profiles-db "$SEED_DB" \
    --no-input \
    "${EXTRA_ARGS[@]}"

echo ""
echo "=== Done ==="
