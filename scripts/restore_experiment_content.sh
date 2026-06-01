#!/usr/bin/env bash
# Restore Period-1 (pre-swap) content from a backup and move everyone to Ver.W.
#
# Usage:
#   ./scripts/restore_experiment_content.sh <dump> [--dry-run] [--skip-version-set] [--skip-regen]
#
# <dump> is resolved in order: host path → web container → cron container.
# Supports both plain-text SQL dumps (*.sql, loaded with psql) and pg_dump
# custom-format archives (*.dump/*.backup[.gz], loaded with pg_restore).
#
# Restore + the management command run from the CRON container (it has the same
# pg client version that created the dump), connecting to the DB service —
# avoids version mismatch with the db container's older client.
#
# Environment overrides:
#   COMPOSE_FILE   (default: docker-compose.production.yml)
#   DB_SERVICE     (default: db)
#   WEB_SERVICE    (default: web)
#   CRON_SERVICE   (default: cron)
#   DB_USER        (default: postgres)

set -euo pipefail

DUMP_SRC="${1:?Usage: $0 <dump_path> [--dry-run] [--skip-version-set] [--skip-regen]}"
shift
EXTRA_ARGS=("$@")

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
CRON_SERVICE="${CRON_SERVICE:-cron}"
DB_USER="${DB_USER:-postgres}"

RESTORE_DB="whoamitoday_restore_src"

echo "=== Restore experiment content ==="
echo "  Dump:        $DUMP_SRC"
echo "  Extra args:  ${EXTRA_ARGS[*]:-<none>}"
echo "  Compose:     $COMPOSE_FILE"
echo ""

# ── Cleanup on exit ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo "--- Cleanup ---"
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        dropdb -U "$DB_USER" --if-exists "$RESTORE_DB" 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
        bash -c "rm -f /tmp/_restore_src.dump" 2>/dev/null || true
    echo "  Done."
}
trap cleanup EXIT

# ── Step 1: Locate the dump file ─────────────────────────────────────────── #
echo "--- Step 1: Locating dump file ---"

DUMP_LOC=""   # "host" | "cron" | "web"
DUMP_PATH=""  # resolved path (on host or inside DUMP_LOC container)

if [[ -f "$DUMP_SRC" ]]; then
    DUMP_LOC="host"; DUMP_PATH="$DUMP_SRC"; echo "  Found on host."
elif docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
        bash -c "test -f '$DUMP_SRC'" 2>/dev/null; then
    DUMP_LOC="cron"; DUMP_PATH="$DUMP_SRC"; echo "  Found in $CRON_SERVICE container."
elif docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
        bash -c "test -f '$DUMP_SRC'" 2>/dev/null; then
    echo "  Found in $WEB_SERVICE — copying to $CRON_SERVICE..."
    docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
        bash -c "cat '$DUMP_SRC'" \
        | docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" \
            bash -c "cat > /tmp/_restore_src.dump"
    DUMP_LOC="cron"; DUMP_PATH="/tmp/_restore_src.dump"; echo "  Copied."
else
    echo "ERROR: '$DUMP_SRC' not found on host, in $CRON_SERVICE, or in $WEB_SERVICE." >&2
    exit 1
fi

# Decide loader by the *original* filename extension (the copied temp file
# drops its extension, so key off DUMP_SRC, not DUMP_PATH).
LOADER="pg_restore"
case "$DUMP_SRC" in
    *.sql|*.sql.gz) LOADER="psql" ;;
esac
echo "  Loader: $LOADER"

# ── Step 2: Create temp DB ───────────────────────────────────────────────── #
echo "--- Step 2: Creating temp DB ($RESTORE_DB) ---"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$RESTORE_DB"
echo "  Created."

# ── Step 3: Restore via cron container's client ─────────────────────────── #
echo "--- Step 3: Restoring $RESTORE_DB (via $CRON_SERVICE) ---"

if [[ "$DUMP_PATH" == *.gz ]]; then READ_CMD="zcat"; else READ_CMD="cat"; fi

if [[ "$LOADER" == "psql" ]]; then
    LOAD_CMD="PGPASSWORD=\$DB_PASSWORD psql -h $DB_SERVICE -U \$DB_USER -d $RESTORE_DB -v ON_ERROR_STOP=0"
else
    LOAD_CMD="PGPASSWORD=\$DB_PASSWORD pg_restore -h $DB_SERVICE -U \$DB_USER -d $RESTORE_DB --no-owner --no-privileges"
fi

if [[ "$DUMP_LOC" == "cron" ]]; then
    docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" bash -c \
        "$READ_CMD '$DUMP_PATH' | $LOAD_CMD" \
        && echo "  Restored." || echo "  (restore finished with warnings — usually OK)"
else
    "$READ_CMD" "$DUMP_PATH" \
        | docker compose -f "$COMPOSE_FILE" exec -T "$CRON_SERVICE" bash -c "$LOAD_CMD" \
        && echo "  Restored." || echo "  (restore finished with warnings — usually OK)"
fi

# ── Step 4: Run management command ──────────────────────────────────────── #
echo "--- Step 4: Running management command ---"
docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
    python manage.py restore_experiment_content \
    --content-db "$RESTORE_DB" \
    --no-input \
    "${EXTRA_ARGS[@]}"

echo ""
echo "=== Done ==="
