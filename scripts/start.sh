#!/usr/bin/env bash
set -euo pipefail

mode="${1:-local}"

case "$mode" in
  local)
    .venv/bin/python -m uvicorn app.main:app \
      --app-dir backend \
      --host 0.0.0.0 \
      --port 8000 \
      --reload &
    backend_pid=$!
    trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM
    npm --prefix frontend run dev
    ;;
  docker)
    if [[ ! -f .env ]]; then
      echo "Missing .env; run: cp .env.example .env" >&2
      exit 1
    fi
    mkdir -p data
    docker compose up --build
    ;;
  docker-detached)
    if [[ ! -f .env ]]; then
      echo "Missing .env; run: cp .env.example .env" >&2
      exit 1
    fi
    mkdir -p data
    docker compose up --build --detach
    ;;
  *)
    echo "Usage: $0 {local|docker|docker-detached}" >&2
    exit 2
    ;;
esac
