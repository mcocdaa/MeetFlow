#!/usr/bin/env bash
set -euo pipefail

image="${1:?usage: scripts/ci-container-smoke.sh IMAGE}"
work_dir="$(mktemp -d)"
container_name="meetflow-ci-${RANDOM}${RANDOM}"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT

mkdir -p "$work_dir/data"
image_env="$(docker image inspect "$image" --format '{{range .Config.Env}}{{println .}}{{end}}')"
for expected in \
  'DATABASE_URL=sqlite:////app/data/meetflow.db' \
  'DATA_DIR=/app/data' \
  'PLUGINS_DIR=/app/plugins' \
  'FRONTEND_DIST=/app/frontend-dist'; do
  grep -Fxq "$expected" <<<"$image_env" || {
    echo "Missing runtime image default: $expected" >&2
    exit 1
  }
done

docker run -d --name "$container_name" --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart no \
  -p 127.0.0.1::8000 \
  -v "$work_dir/data:/app/data" \
  -e APP_ENV=production \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=container-smoke-admin-password \
  -e APP_SECRET_KEY=container-smoke-persistent-secret-key-2026 \
  -e ALLOW_REGISTRATION=false \
  -e SECURE_COOKIES=true \
  -e TRUSTED_ORIGINS=https://meetflow.test \
  "$image" >/dev/null

for _ in $(seq 1 45); do
  health="$(docker inspect --format '{{.State.Health.Status}}' "$container_name")"
  if [[ "$health" == "healthy" ]]; then
    docker exec "$container_name" python -c "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2); assert response.status == 200"
    test -f "$work_dir/data/meetflow.db"
    exit 0
  fi
  if [[ "$health" == "unhealthy" ]]; then
    docker logs "$container_name" >&2
    exit 1
  fi
  sleep 1
done

docker logs "$container_name" >&2
echo "Timed out waiting for MeetFlow health check" >&2
exit 1
