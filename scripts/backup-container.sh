#!/usr/bin/env bash
set -euo pipefail

backup_name="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ ! "$backup_name" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "Backup name must use UTC format YYYYMMDDTHHMMSSZ" >&2
  exit 2
fi

destination="backups/$backup_name"
if [[ -e "$destination" ]]; then
  echo "Backup already exists: $destination" >&2
  exit 1
fi

container_backup="/app/data/.backup-export/$backup_name"
cleanup() {
  docker compose exec -T meetflow rm -rf "$container_backup" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose exec -T meetflow python /app/scripts/backup.py \
  --database /app/data/meetflow.db \
  --uploads /app/data/uploads \
  --output /app/data/.backup-export \
  --name "$backup_name" >/dev/null

mkdir -p backups
docker compose cp "meetflow:$container_backup" "$destination"
echo "$destination"
