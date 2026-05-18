#!/usr/bin/env bash
# Seed Phase 2 from pg_dump backups.
#
# Usage:
#   ./scripts/seed_phase2_from_backup.sh <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]
#
# Arguments:
#   content_dump   Host path to the pre-reset content dump  (e.g. /app/adoorback/backups/whoamitoday_pre_reset_20260518_000011.dump)
#   profiles_dump  Host path to the pre-profile-reset dump  (e.g. /app/adoorback/backups/whoamitoday_pre_reset_20260518_000402.dump)
#   --dry-run      Pass through to the management command (counts only, no DB writes)
#   --reset-fakes  Delete existing fake_*@whoami.test users before seeding
#
# Environment variables (override defaults):
#   COMPOSE_FILE   docker-compose file (default: docker-compose.production.yml)
#   DB_SERVICE     docker compose service name for postgres (default: db)
#   WEB_SERVICE    docker compose service name for django (default: web)
#   DB_USER        postgres superuser (default: postgres)
#
# Run from the repo root (same directory as docker-compose.*.yml).

set -euo pipefail

CONTENT_DUMP="${1:?Usage: $0 <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]}"
PROFILES_DUMP="${2:?Usage: $0 <content_dump> <profiles_dump> [--dry-run] [--reset-fakes]}"
EXTRA_ARGS="${*:3}"  # everything after the two positional args, e.g. --dry-run --reset-fakes

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
WEB_SERVICE="${WEB_SERVICE:-web}"
DB_USER="${DB_USER:-postgres}"

CONTENT_DB="whoamitoday_seed_src"
PROFILES_DB="whoamitoday_seed_profiles"

echo "=== Phase 2 seed ==="
echo "  Content dump:  $CONTENT_DUMP"
echo "  Profiles dump: $PROFILES_DUMP"
echo "  Extra args:    ${EXTRA_ARGS:-<none>}"
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
        rm -f /tmp/seed_content.dump /tmp/seed_profiles.dump 2>/dev/null || true
    echo "  Done."
}
trap cleanup EXIT

# ── Step 1: Copy dumps into the db container ────────────────────────────── #
echo "--- Step 1: Copying dumps to db container ---"
docker compose -f "$COMPOSE_FILE" cp "$CONTENT_DUMP"  "$DB_SERVICE:/tmp/seed_content.dump"
docker compose -f "$COMPOSE_FILE" cp "$PROFILES_DUMP" "$DB_SERVICE:/tmp/seed_profiles.dump"
echo "  Copied."

# ── Step 2: Create temp DBs and restore ─────────────────────────────────── #
echo "--- Step 2: Restoring temp DBs ---"

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$CONTENT_DB"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    pg_restore -U "$DB_USER" -d "$CONTENT_DB" --no-owner --no-privileges \
    --no-comments -j 2 /tmp/seed_content.dump
echo "  Content DB restored."

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    createdb -U "$DB_USER" "$PROFILES_DB"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE" \
    pg_restore -U "$DB_USER" -d "$PROFILES_DB" --no-owner --no-privileges \
    --no-comments -j 2 /tmp/seed_profiles.dump
echo "  Profiles DB restored."

# ── Step 3: Run management command ──────────────────────────────────────── #
echo "--- Step 3: Running management command ---"
docker compose -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" \
    python manage.py seed_phase2_from_backup \
    --content-db "$CONTENT_DB" \
    --profiles-db "$PROFILES_DB" \
    --no-input \
    $EXTRA_ARGS

echo ""
echo "=== Done ==="
