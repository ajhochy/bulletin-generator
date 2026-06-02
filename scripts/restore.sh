#!/usr/bin/env bash
# Bulletin Generator — server-mode restore script
# Usage: ./scripts/restore.sh <backup_dir>
# Restores DB from <backup_dir>/db.dump and optionally fonts.
#
# Required env vars:
#   DATABASE_URL  — Postgres connection string
#
# Required args:
#   backup_dir    — path to the timestamped backup directory produced by backup.sh

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup_dir>" >&2
  echo "  backup_dir — path to the timestamped backup produced by backup.sh" >&2
  exit 1
fi

BACKUP_DIR="${1%/}"  # strip trailing slash

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  echo "       Export it before running this script:" >&2
  echo "       export DATABASE_URL='postgres://user:pass@host:5432/dbname'" >&2
  exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "ERROR: Backup directory not found: $BACKUP_DIR" >&2
  exit 1
fi

DUMP_FILE="${BACKUP_DIR}/db.dump"
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ERROR: db.dump not found in backup directory: $DUMP_FILE" >&2
  exit 1
fi

if ! command -v pg_restore &>/dev/null; then
  echo "ERROR: pg_restore not found. Install postgresql-client and try again." >&2
  exit 1
fi

# ── Confirmation prompt ───────────────────────────────────────────────────────
echo "WARNING: This will restore the database from:"
echo "  $DUMP_FILE"
echo ""
echo "  Target: $DATABASE_URL"
echo ""
echo "  --clean --if-exists will DROP and recreate all objects in the dump."
echo ""
read -r -p "Continue? [y/N] " CONFIRM
if [[ "${CONFIRM,,}" != "y" ]]; then
  echo "Restore cancelled."
  exit 0
fi

# ── Database restore ──────────────────────────────────────────────────────────
echo ""
echo "Restoring database..."
pg_restore --clean --if-exists -d "$DATABASE_URL" "$DUMP_FILE"
echo "  [OK] Database restored from $DUMP_FILE"

# ── Font files ────────────────────────────────────────────────────────────────
DATA_DIR="${DATA_DIR:-./data}"

if [[ -d "${BACKUP_DIR}/fonts/user" ]]; then
  mkdir -p "${DATA_DIR}/fonts/user"
  cp -r "${BACKUP_DIR}/fonts/user/." "${DATA_DIR}/fonts/user/"
  USER_COUNT="$(find "${DATA_DIR}/fonts/user" -type f | wc -l | tr -d ' ')"
  echo "  [OK] User fonts restored ($USER_COUNT file(s)) → ${DATA_DIR}/fonts/user/"
else
  echo "  [--] No user fonts in backup — skipping."
fi

if [[ -d "${BACKUP_DIR}/fonts/cache" ]]; then
  mkdir -p "${DATA_DIR}/fonts/cache"
  cp -r "${BACKUP_DIR}/fonts/cache/." "${DATA_DIR}/fonts/cache/"
  CACHE_COUNT="$(find "${DATA_DIR}/fonts/cache" -type f | wc -l | tr -d ' ')"
  echo "  [OK] Font cache restored ($CACHE_COUNT file(s)) → ${DATA_DIR}/fonts/cache/"
else
  echo "  [--] No font cache in backup — skipping."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Restore complete."
echo ""
echo "Next steps:"
echo "  1. Verify the application starts correctly."
echo "  2. Check that projects, songs, and announcements load as expected."
echo "  3. If fonts are missing from the UI, restart the app server so it re-indexes them."
