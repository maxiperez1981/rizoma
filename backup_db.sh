#!/bin/bash
# Backup diario de la base de Rizoma (alma_academica). Formato custom de
# pg_dump (-Fc), comprimido, con rotacion de 14 dias.
set -euo pipefail

APP_DIR="/home/alma-academica"
BACKUP_DIR="$APP_DIR/backups/db"
DATABASE_URL="$(grep -E '^DATABASE_URL=' "$APP_DIR/.env" | cut -d= -f2-)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/alma_academica_${STAMP}.dump"

mkdir -p "$BACKUP_DIR"
pg_dump -Fc --no-owner --no-privileges "$DATABASE_URL" > "$OUT_FILE.tmp"
mv "$OUT_FILE.tmp" "$OUT_FILE"

# Rotacion: conserva los ultimos 14 backups.
ls -1t "$BACKUP_DIR"/alma_academica_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Backup OK: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
