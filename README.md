<div align="center">

# MeetFlow

**Collaborative meeting workspace with live agenda timing, structured outcome extraction, and headless AI note ingestion.**

[![Family: *Flow](https://img.shields.io/badge/Family-*Flow-8A2BE2?style=flat-square)](https://github.com/mcocdaa)
[![CI](https://github.com/mcocdaa/MeetFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/mcocdaa/MeetFlow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/mcocdaa/MeetFlow?display_name=tag&sort=semver&style=flat-square)](https://github.com/mcocdaa/MeetFlow/releases)
[![GHCR Image](https://img.shields.io/badge/GHCR-ghcr.io%2Fmcocdaa%2Fmeetflow-0b6a58?style=flat-square&logo=docker)](https://github.com/mcocdaa/MeetFlow/pkgs/container/meetflow)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](compose.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

[**English**](README.md) · [**简体中文**](README_CN.md)

<img src="docs/assets/demo_meetflow.gif" alt="MeetFlow Demo" width="840">

</div>

---

## ✨ Highlights

- **Live Agenda Workbench & Focus Mode**: Run structured meetings (`Planned → In Progress → Completed`) with per-agenda countdown timers, actual duration tracking, optimistic concurrency protection (`expected_version`), and read-only completion snapshots.
- **Inline Structured Outcome Extraction**: Write `@决策:` (Decision), `@行动:` (Action Item), and `@开放问题:` (Open Question) directly inside agenda Markdown notes to automatically reconcile cross-meeting trackers while preserving manual items.
- **Headless AI Note Ingestion API**: Push meeting transcripts or LLM summaries in a single atomic call via `POST /api/v1/meetings/{id}/ingest` authenticated with Personal Access Tokens (`X-API-Key: mf_...`) or `Authorization: Bearer mf_...`.
- **Recurring Series & Calendar Subscriptions**: Schedule daily, weekly, monthly, or yearly recurring meeting series with IANA timezone support, ad-hoc session support, and subscribable `.ics` calendar feeds.
- **Role-Based Project Governance & Webhooks**: Fine-grained project roles (`lead`, `member`, `stakeholder`), meeting-level guest invitations, and outbound webhook notifications for Feishu, WeCom, DingTalk, and generic HTTP endpoints.
- **Hardened Single-Container Deployment**: Ships as a multi-arch (`linux/amd64`, `linux/arm64`) read-only container (`ghcr.io/mcocdaa/meetflow`) backed by FastAPI, Vue 3 + Naive UI, SQLite WAL, and built-in background workers.

---

## 🚀 Quick Start

### Option 1: Pre-built Container Image (Recommended)

Copy `.env.example`, set a strong `ADMIN_PASSWORD` (12+ chars), `APP_SECRET_KEY`, and `TRUSTED_ORIGINS`, then launch on `127.0.0.1:8000`:

```bash
cp .env.example .env && chmod 600 .env
# Edit .env: set ADMIN_PASSWORD, APP_SECRET_KEY (python3 -c "import secrets; print(secrets.token_urlsafe(48))"), TRUSTED_ORIGINS
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v "$PWD/data:/app/data" --env-file .env \
  ghcr.io/mcocdaa/meetflow:latest
```

 Or start from source with Docker Compose:

```bash
MEETFLOW_IMAGE=ghcr.io/mcocdaa/meetflow:latest docker compose up -d
curl http://127.0.0.1:8000/api/health
```

### Option 2: Local Development

Requires **Python 3.12+** and **Node.js 22+**:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
npm --prefix frontend ci
./scripts/start.sh local
```

- **Backend API & OpenAPI**: `http://127.0.0.1:8000` (`/api/health`)
- **Frontend Dev Server**: `http://localhost:5173`

---

## 🤖 AI Note Ingestion API

Generate a Personal Access Token (`mf_...`) in **Personal Center → API Keys** (or via `POST /api/v1/auth/tokens`) and ingest structured Markdown notes plus outcome tags in one atomic request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/meetings/<MEETING_ID>/ingest" \
  -H "X-API-Key: mf_your_personal_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "agenda_title": "Architecture & Release Sync",
    "auto_complete_agenda": true,
    "notes_markdown": "### Key Takeaways\n- @决策: Adopt single-container SQLite deployment for v1.0\n- @行动: Finalize reverse-proxy TLS checklist @admin\n- @开放问题: Should webhook retries support custom backoff?"
  }'
```

MeetFlow automatically creates or updates the target agenda item, extracts `@决策:` / `@行动:` / `@开放问题:` records into the project's global trackers, and records an audit event.

---

## 🛠️ Verification & Tests

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

---

## 📚 Documentation & License

- **[Operations Guide](docs/operations.md)**: HTTPS reverse proxy, `.env` security boundaries, upgrades, rollbacks, backups, and plugin mounts.
- **[Release Guide](docs/release.md)**: GitHub Actions CI/CD, multi-arch GHCR image publishing, and semantic version tagging.
- **[Developer & Agent Guide](docs/README.md)**: Architecture index, database migrations ([docs/development.md](docs/development.md)), and plugin contracts ([backend/app/plugins/README.md](backend/app/plugins/README.md)).
- **License**: Released under the [MIT License](LICENSE).
