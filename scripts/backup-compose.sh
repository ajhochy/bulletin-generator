#!/usr/bin/env bash
# Bulletin Generator — Docker Compose backup wrapper
# Usage: ./scripts/backup-compose.sh [backup_dir]
#
# Runs backup.sh inside the running app container via docker compose exec.
# DATABASE_URL is passed from the host environment (or .env file) into the
# container without writing it to shell history.
#
# Prerequisites:
#   - docker compose is running (docker compose up -d)
#   - DATABASE_URL is set in the host environment or in your .env file
#
# Example:
#   export DATABASE_URL='postgres://user:pass@db:5432/bulletin'
#   ./scripts/backup-compose.sh
#   # or with a custom destination inside the container:
#   ./scripts/backup-compose.sh /app/data/backups

set -euo pipefail

BACKUP_DIR="${1:-/app/data/backups}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set on the host." >&2
  echo "       Export it or add it to your .env file:" >&2
  echo "       export DATABASE_URL='postgres://user:pass@db:5432/bulletin'" >&2
  exit 1
fi

echo "Running backup inside app container (backup dir: $BACKUP_DIR)..."
docker compose exec \
  -e DATABASE_URL="$DATABASE_URL" \
  app \
  ./scripts/backup.sh "$BACKUP_DIR"
