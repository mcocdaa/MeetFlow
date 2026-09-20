#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
echo "==> [MeetFlow] Backend pytest..."
.venv/bin/python -m pytest -q
echo "==> [MeetFlow] Frontend test & build..."
npm --prefix frontend test
npm --prefix frontend run build
echo "✓ 全部检查通过 (MeetFlow)"
