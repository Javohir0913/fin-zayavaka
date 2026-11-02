#!/usr/bin/env bash
# Kunlik SQLite zaxira nusxa (cron orqali). Oxirgi 14 kun saqlanadi.
set -euo pipefail
APP=/home/azureuser/fin-zayavka
DEST=/home/azureuser/backups/fin-zayavka
mkdir -p "$DEST"
"$APP/.venv/bin/python" - "$APP/data/expenses.db" "$DEST/expenses_$(date +%F).db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
find "$DEST" -name 'expenses_*.db' -mtime +14 -delete
