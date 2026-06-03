#!/usr/bin/env bash
# Bulletin Generator — server-mode backup script
# Usage: ./scripts/backup.sh [backup_dir]
# Creates: <backup_dir>/YYYYMMDD_HHMMSS/db.dump and <backup_dir>/YYYYMMDD_HHMMSS/fonts/
#
# Required env vars:
#   DATABASE_URL  — Postgres connection string (avoids embedding secrets in shell history)
#
# Optional env vars:
#   DATA_DIR      — path to data directory (default: ./data)

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
DATA_DIR="${DATA_DIR:-./data}"
BACKUP_BASE="${1:-${DATA_DIR}/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  echo "       Export it before running this script:" >&2
  echo "       export DATABASE_URL='postgres://user:pass@host:5432/dbname'" >&2
  exit 1
fi

if ! command -v pg_dump &>/dev/null; then
  echo "ERROR: pg_dump not found. Install postgresql-client and try again." >&2
  exit 1
fi

# ── Create backup directory ───────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
echo "Backup directory: $BACKUP_DIR"

# ── Database dump ─────────────────────────────────────────────────────────────
echo "Running pg_dump..."
pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_DIR/db.dump"
echo "  [OK] Database dumped to $BACKUP_DIR/db.dump ($(du -sh "$BACKUP_DIR/db.dump" | cut -f1))"

# ── Font files ────────────────────────────────────────────────────────────────
FONTS_COPIED=0

USER_FONTS="${DATA_DIR}/fonts/user"
if [[ -d "$USER_FONTS" ]]; then
  mkdir -p "$BACKUP_DIR/fonts/user"
  cp -r "$USER_FONTS/." "$BACKUP_DIR/fonts/user/"
  USER_COUNT="$(find "$BACKUP_DIR/fonts/user" -type f | wc -l | tr -d ' ')"
  echo "  [OK] User fonts copied ($USER_COUNT file(s)) → $BACKUP_DIR/fonts/user/"
  FONTS_COPIED=1
else
  echo "  [--] No user fonts directory found at $USER_FONTS — skipping."
fi

CACHE_FONTS="${DATA_DIR}/fonts/cache"
if [[ -d "$CACHE_FONTS" ]]; then
  mkdir -p "$BACKUP_DIR/fonts/cache"
  cp -r "$CACHE_FONTS/." "$BACKUP_DIR/fonts/cache/"
  CACHE_COUNT="$(find "$BACKUP_DIR/fonts/cache" -type f | wc -l | tr -d ' ')"
  echo "  [OK] Font cache copied ($CACHE_COUNT file(s)) → $BACKUP_DIR/fonts/cache/"
  FONTS_COPIED=1
else
  echo "  [--] No font cache directory found at $CACHE_FONTS — skipping."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Backup complete: $BACKUP_DIR"
echo "  Contents:"
echo "    db.dump         — Postgres custom-format dump (restore with pg_restore)"
if [[ $FONTS_COPIED -eq 1 ]]; then
  echo "    fonts/          — Font files"
fi
echo ""
echo "To restore, run:"
echo "  DATABASE_URL='\$DATABASE_URL' ./scripts/restore.sh '$BACKUP_DIR'"
