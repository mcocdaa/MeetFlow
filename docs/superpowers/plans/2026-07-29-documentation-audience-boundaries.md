# Documentation Audience Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users, developers, and agents separate documentation entry points while preserving the tested direct-Docker and GHCR release contracts.

**Architecture:** Keep the repository root as the user-facing entry point, create a small `docs/` handbook for development and operational maintenance, and add a short root `AGENTS.md` that routes agents to the handbook. Move information rather than changing product behavior; the README retains the exact command-line-first Docker quick start while detailed procedures live in topic pages.

**Tech Stack:** Markdown, GitHub Actions YAML references, Docker CLI, FastAPI/Vue repository tooling.

---

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `README.md` | Modify | User-facing product overview, direct Docker quick start, first-use guidance, and concise links to detailed references. |
| `docs/README.md` | Create | Developer and agent documentation index, reading paths, and ownership boundaries. |
| `docs/development.md` | Create | Architecture, local source setup, tests, source Compose workflow, and migration expectations. |
| `docs/operations.md` | Create | HTTPS, advanced environment-file configuration, updates, rollback, backup/recovery, and production plugin mounts. |
| `docs/release.md` | Create | CI, tag-triggered public image release, tags, and maintainer release checklist. |
| `AGENTS.md` | Create | Agent-only repository instructions, reading order, safety boundaries, and verification commands. |

### Task 1: Create the development handbook

**Files:**
- Create: `docs/development.md`
- Reference: `Dockerfile`
- Reference: `compose.yaml`
- Reference: `pyproject.toml`
- Reference: `frontend/package.json`

- [ ] **Step 1: Write the developer-facing scope and architecture section**

  Create `docs/development.md` with this title and audience statement:

  ```markdown
  # MeetFlow 开发指南

  本文面向修改 MeetFlow 源码的开发者和 agent。服务端部署请阅读 [运维指南](operations.md)，发布镜像请阅读 [发布指南](release.md)。
  ```

  Add a compact architecture list naming the FastAPI/SQLAlchemy backend, Vue 3/Vite frontend, SQLite plus local attachments, production `/app/data`, and externally mounted read-only `/app/plugins`.

- [ ] **Step 2: Move the local source workflow from the user README**

  Add sections `## 本地开发` and `## 测试与构建` containing these exact commands:

  ```bash
  python -m venv .venv
  .venv/bin/python -m pip install -e '.[test]'
  npm --prefix frontend ci
  ./scripts/start.sh local

  .venv/bin/python -m pytest -q
  npm --prefix frontend test
  npm --prefix frontend run build
  ```

  State the Vite and backend health URLs, and explain that frontend npm commands run with `--prefix frontend` (or from `frontend/`).

- [ ] **Step 3: Document source-only Compose and schema expectations**

  Add `## 从源码使用 Docker Compose` with `cp .env.example .env`, `./scripts/start.sh docker-detached`, `docker compose ps`, and `docker compose down`. Mark this as source-development/advanced maintenance, not the default public-image deployment method.

  Add `## 数据库迁移` stating that Alembic migrations in `backend/migrations/` are the mechanism for persisted schema changes; do not rely on a fresh install workflow to mutate real production data.

- [ ] **Step 4: Verify the new development document has its required sections**

  Run:

  ```bash
  rg -n '^## (本地开发|测试与构建|从源码使用 Docker Compose|数据库迁移)$' docs/development.md
  ```

  Expected: four matching headings, one for each required section.

- [ ] **Step 5: Commit the focused developer handbook**

  ```bash
  git add docs/development.md
  git commit -m "docs: add development handbook"
  ```

### Task 2: Create operations and release references

**Files:**
- Create: `docs/operations.md`
- Create: `docs/release.md`
- Reference: `.env.example`
- Reference: `.github/workflows/ci.yml`
- Reference: `.github/workflows/release.yml`
- Reference: `scripts/backup.py`
- Reference: `scripts/ci-container-smoke.sh`

- [ ] **Step 1: Write production configuration and HTTPS guidance**

  Create `docs/operations.md` with this audience statement:

  ```markdown
  # MeetFlow 运维指南

  本文面向部署或维护 MeetFlow 服务器的开发者和 agent。普通使用者先阅读仓库根目录的 [README](../README.md)。
  ```

  Move the HTTPS/Caddy reverse-proxy guidance and the production implications of loopback binding, `SECURE_COOKIES=true`, `TRUSTED_ORIGINS`, and `MAX_UPLOAD_BYTES` from the root README. Retain the Caddy example exactly.

- [ ] **Step 2: Preserve the command-line-first advanced configuration contract**

  Add `## 高级配置：使用 .env` and document `cp .env.example .env`, `--env-file ./.env`, and the full advanced `docker run` command. State explicitly that inline `-e` flags are the default quick-start mechanism and `.env` is advanced configuration; never include a real secret or say that `.env` should be committed.

- [ ] **Step 3: Move lifecycle, recovery, and plugin procedures**

  Add the following operation sections and retain the exact commands and restrictions from the current README:

  ```markdown
  ## 镜像更新与回滚
  ## 备份与恢复
  ## 生产插件挂载
  ```

  The update section must distinguish stable and prerelease tags, preserve `./data/` plus `APP_SECRET_KEY`, and never recommend rolling back to `latest`. The backup section must use the in-container `scripts/backup.py` command and restore after stopping the container. The plugin section must use `-v "$PWD/plugins:/app/plugins:ro"`, explain that it shadows the image plugin directory, and link to `../backend/app/plugins/README.md`.

- [ ] **Step 4: Create the maintainer release guide**

  Create `docs/release.md` with three sections:

  ```markdown
  # MeetFlow 发布指南
  ## 持续集成
  ## 发布镜像
  ## 发布前检查清单
  ```

  Describe `ci.yml` as the main-push/PR backend, frontend, and restricted direct-container smoke suite. Describe `release.yml` as valid-`v*`-tag validation, test, QEMU/Buildx multi-architecture (`linux/amd64`, `linux/arm64`) GHCR publication, provenance, and SBOM. Document stable exact/version/minor/SHA/`latest` tags and the prerelease rule that excludes `latest` and the minor channel. Include `git tag vX.Y.Z` and `git push origin vX.Y.Z` only in this maintainer page.

- [ ] **Step 5: Verify the operations and release contracts**

  Run:

  ```bash
  rg -n '\$PWD/data:/app/data|--env-file \./\.env|APP_SECRET_KEY|\$PWD/plugins:/app/plugins:ro' docs/operations.md
  rg -n 'linux/amd64|linux/arm64|vX.Y.Z|latest|SBOM' docs/release.md
  ```

  Expected: operations output covers all four deployment-critical tokens; release output covers the architecture targets, tag procedure, stable-tag behavior, and SBOM.

- [ ] **Step 6: Commit the operations and release references**

  ```bash
  git add docs/operations.md docs/release.md
  git commit -m "docs: add operations and release guides"
  ```

### Task 3: Add developer and agent entry points

**Files:**
- Create: `docs/README.md`
- Create: `AGENTS.md`
- Reference: `docs/development.md`
- Reference: `docs/operations.md`
- Reference: `docs/release.md`
- Reference: `backend/app/plugins/README.md`
- Reference: `plugins/ai-work-assistant/README.md`

- [ ] **Step 1: Write the developer and agent documentation index**

  Create `docs/README.md` with the title `# MeetFlow 开发与维护文档`. Add a reading-path table with these rows:

  | Task | Read first |
  | --- | --- |
  | 修改应用代码或本地调试 | `development.md` |
  | 部署、备份、恢复或插件挂载 | `operations.md` |
  | 修改 CI、容器发布或创建版本 | `release.md` |
  | 修改插件运行时契约 | `../backend/app/plugins/README.md` |

  State that dated `docs/superpowers/specs/` and `docs/superpowers/plans/` records explain historical decisions and do not replace the current handbook.

- [ ] **Step 2: Write concise agent instructions**

  Create root `AGENTS.md` with these sections:

  ```markdown
  # MeetFlow Agent Instructions
  ## Read first
  ## Repository rules
  ## Verification
  ## Documentation ownership
  ```

  Require agents to read `docs/README.md`, then the relevant topic page before editing. Include the project architecture, `./data` persistence and `.env`/secret safety boundaries, the default `docker run` contract, and the required test/build commands from `docs/development.md`. Require changes to deployment, release, configuration, or developer workflows to update the corresponding user/developer/agent document rather than duplicating it in all three places.

- [ ] **Step 3: Check that entry points route to every current handbook page**

  Run:

  ```bash
  rg -n 'development\.md|operations\.md|release\.md' docs/README.md AGENTS.md
  ```

  Expected: the index links to all three topic pages; `AGENTS.md` directs agents to the index and applicable references.

- [ ] **Step 4: Commit the entry points**

  ```bash
  git add docs/README.md AGENTS.md
  git commit -m "docs: add developer and agent entry points"
  ```

### Task 4: Slim the user README and connect the document graph

**Files:**
- Modify: `README.md`
- Reference: `docs/README.md`
- Reference: `docs/operations.md`
- Reference: `docs/release.md`

- [ ] **Step 1: Retain the user-facing product and direct-start content**

  Keep the product introduction, public-image statement, secret-generation command, complete inline-`-e` `docker run` command, explanation of `./data`, persistent `APP_SECRET_KEY`, first-administrator behavior, account-management overview, and `docker ps`/health-check command.

- [ ] **Step 2: Replace detailed maintenance sections with a documentation links section**

  Remove the current detailed sections for local development, HTTPS proxy, advanced `.env`, image tags/update/rollback, source Compose, backup/recovery, plugins, GitHub Actions, and database migration. Add this concise section before the account-management overview:

  ```markdown
  ## 进一步文档

  - [运维指南](docs/operations.md)：HTTPS、高级配置、更新回滚、备份恢复与生产插件挂载。
  - [发布指南](docs/release.md)：GitHub Actions、GHCR 镜像和版本标签。
  - [开发与维护文档](docs/README.md)：架构、本地开发、测试与 agent 工作入口。
  ```

  The user README must not contain a tag-creation command, source Compose procedure, backup/restore procedure, or plugin-mount procedure after this edit.

- [ ] **Step 3: Check the README boundary**

  Run:

  ```bash
  rg -n '^## (本地开发|HTTPS 反向代理|高级配置：使用 `.env`|镜像标签、更新和回滚|从源码使用 Docker Compose|备份与恢复|插件|GitHub Actions|当前数据库升级约束)$' README.md
  ```

  Expected: no matches. Then run:

  ```bash
  rg -n 'ghcr\.io/mcocdaa/meetflow|\$PWD/data:/app/data|进一步文档|账号管理' README.md
  ```

  Expected: the quick start, persistent-data mapping, documentation links, and account-management section remain present.

- [ ] **Step 4: Commit the user README migration**

  ```bash
  git add README.md
  git commit -m "docs: focus readme on user onboarding"
  ```

### Task 5: Validate the complete documentation graph

**Files:**
- Verify: `README.md`
- Verify: `AGENTS.md`
- Verify: `docs/README.md`
- Verify: `docs/development.md`
- Verify: `docs/operations.md`
- Verify: `docs/release.md`

- [ ] **Step 1: Validate local Markdown links**

  Run:

  ```bash
  python - <<'PY'
  import pathlib
  import re

  root = pathlib.Path.cwd()
  files = [root / 'README.md', root / 'AGENTS.md', *sorted((root / 'docs').glob('*.md'))]
  missing = []
  for file in files:
      for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
          target = target.split('#', 1)[0]
          if not target or '://' in target or target.startswith('mailto:'):
              continue
          if not (file.parent / target).resolve().exists():
              missing.append(f'{file.relative_to(root)} -> {target}')
  if missing:
      raise SystemExit('\n'.join(missing))
  print(f'validated {len(files)} Markdown entry-point files')
  PY
  ```

  Expected: `validated 6 Markdown entry-point files`.

- [ ] **Step 2: Check only the documentation migration for whitespace errors**

  Run:

  ```bash
  git diff 94589b6..HEAD --check -- README.md AGENTS.md docs/README.md docs/development.md docs/operations.md docs/release.md
  ```

  Expected: no output and exit code 0. `94589b6` is the design commit immediately before this migration; limiting the file list keeps unrelated parallel commits out of the check.

- [ ] **Step 3: Review the release workflow against the release guide**

  Run:

  ```bash
  python -m pytest -q backend/tests/test_release_workflow.py
  ```

  Expected: `1 passed`. This verifies that the workflow claims documented in `docs/release.md` remain backed by a repository test.

- [ ] **Step 4: Commit any validation-only documentation correction**

  If validation requires a documentation correction, commit only the corrected documentation files:

  ```bash
  git add README.md AGENTS.md docs/README.md docs/development.md docs/operations.md docs/release.md
  git commit -m "docs: validate documentation boundaries"
  ```

  If no correction is required, do not create an empty commit.
