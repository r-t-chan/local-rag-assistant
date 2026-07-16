#!/usr/bin/env bash
# Backs up the sqlite vector db using SQLite's own online backup API (via
# Python's sqlite3 module) rather than a plain `cp` — safe to run while the
# app is concurrently writing to the database. Prunes backups older than
# RETENTION_DAYS. Works identically for a Docker deployment (the db is
# bind-mounted to ./data on the host) and a bare-metal/systemd deployment.
set -euo pipefail

DB_PATH="${DB_PATH:-./data/db/vectors.db}"
BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [ ! -f "$DB_PATH" ]; then
  echo "No database at $DB_PATH — nothing to back up." >&2
  exit 0
fi

mkdir -p "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="$BACKUP_DIR/vectors-$timestamp.db"

python3 - "$DB_PATH" "$backup_path" <<'PYEOF'
import sqlite3
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
with dst:
    src.backup(dst)
dst.close()
src.close()
PYEOF

gzip "$backup_path"
find "$BACKUP_DIR" -name 'vectors-*.db.gz' -mtime "+$RETENTION_DAYS" -delete

echo "Backed up $DB_PATH -> $backup_path.gz"
