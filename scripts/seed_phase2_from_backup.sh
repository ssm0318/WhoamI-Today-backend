#!/usr/bin/env bash
# Seed Phase 2 from pg_dump backups.
#
# Usage:
#   ./scripts/seed_phase2_from_backup.sh <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]
#
# Dump paths are resolved in this order:
#   1. Host filesystem (absolute or relative path)
#   2. Inside the web container  (e.g. /app/adoorback/backups/whoamitoday_pre_reset_*.dump)
#
# Examples:
#   # Dry-run (counts only, no DB writes):
#   ./scripts/seed_phase2_from_backup.sh \
#     /app/adoorback/backups/whoamitoday_pre_reset_20260518_000011.dump \
#     /app/adoorback/backups/whoamitoday_pre_reset_20260518_000402.dump \
#     --dry-run
#
#   # Full run:
#   ./scripts/seed_phase2_from_backup.sh \
#     /app/adoorback/backups/whoamitoday_pre_reset_20260518_000011.dump \
#     /app/adoorback/backups/whoamitoday_pre_reset_20260518_000402.dump
#
#   # Re-run cleanly (delete previous fake users first):
#   ./scripts/seed_phase2_from_backup.sh dump1 dump2 --reset-fakes
#
# Environment overrides:
#   COMPOSE_FILE   (default: docker-compose.production.yml)
#   DB_SERVICE     (default: db)
#   WEB_SERVICE    (default: web)
#   DB_USER        (default: postgres)

set -euo pipefail

CONTENT_DUMP="${1:?Usage: $0 <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]}"
PROFILES_DUMP="${2:?Usage: $0 <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]}"
shift 2
EXTRA_ARGS=("$@")   # everything after the two positional args

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
DB_USER="${DB_USER:-postgres}"

CONTENT_DB="whoamitoday_seed_src"
PROFILES_DB="whoamitoday_seed_profiles"

echo "=== Phase 2 seed ==="
echo "  Content dump:  $CONTENT_DUMP"
echo "  Profiles dump: $PROFILES_DUMP"
echo "  Extra args:    ${EXTRA_ARGS[*]:-<none>}"
echo "  Compose file:  $COMPOSE_FILE"
echo ""

# ── Cleanup on exit ─────────────────────────────────────────────────────── #
cleanup() {
    echo ""
    echo "--- Cleanup ---"
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        dropdb -U "$DB_USER" --if-exists "$CONTENT_DB" 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        dropdb -U "$DB_USER" --if-exists "$PROFILES_DB" 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
        bash -c "rm -f /tmp/seed_content.dump /tmp/seed_profiles.dump" 2>/dev/null || true
    rm -f /tmp/seed_content_host.dump /tmp/seed_profiles_host.dump 2>/dev/null || true
    echo "  Done."
}
trap cleanup EXIT

# ── Helper: resolve a dump path to a local host file ────────────────────── #
# If the path exists on the host, use it directly.
# Otherwise, try to copy it from the web container.
resolve_dump() {
    local src="$1"
    local dest="$2"   # host temp path to copy to if needed

    if [[ -f "$src" ]]; then
        echo "$src"
        return
    fi

    echo "  '$src' not found on host — trying web container..." >&2
    docker compose -f "$COMPOSE_FILE" cp "$WEB_SERVICE:$src" "$dest"
    echo "$dest"
}

# ── Step 1: Resolve dump files ───────────────────────────────────────────── #
echo "--- Step 1: Resolving dump files ---"
CONTENT_HOST=$(resolve_dump "$CONTENT_DUMP"  /tmp/seed_content_host.dump)
PROFILES_HOST=$(resolve_dump "$PROFILES_DUMP" /tmp/seed_profiles_host.dump)
echo "  Content:  $CONTENT_HOST"
echo "  Profiles: $PROFILES_HOST"

# ── Step 2: Copy dumps into the db container ────────────────────────────── #
echo "--- Step 2: Copying dumps to db container ---"
docker compose -f "$COMPOSE_FILE" cp "$CONTENT_HOST"  "$DB_SERVICE:/tmp/seed_content.dump"
docker compose -f "$COMPOSE_FILE" cp "$PROFILES_HOST" "$DB_SERVICE:/tmp/seed_profiles.dump"
echo "  Copied."

# ── Step 3: Create temp DBs and restore ─────────────────────────────────── #
echo "--- Step 3: Restoring temp DBs ---"

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$CONTENT_DB"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    pg_restore -U "$DB_USER" -d "$CONTENT_DB" --no-owner --no-privileges \
    --no-comments -j 2 /tmp/seed_content.dump
echo "  Content DB ($CONTENT_DB) restored."

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$PROFILES_DB"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    pg_restore -U "$DB_USER" -d "$PROFILES_DB" --no-owner --no-privileges \
    --no-comments -j 2 /tmp/seed_profiles.dump
echo "  Profiles DB ($PROFILES_DB) restored."

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
