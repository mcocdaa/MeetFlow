# Documentation Audience Boundaries Design

- **Date:** 2026-07-29
- **Status:** Approved for implementation
- **Scope:** Restructure the repository documentation without changing application, container, or release behavior.

## Goal

Give each audience one clear starting point:

- End users and server operators begin with the root `README.md`.
- Developers and coding agents begin with `docs/README.md` and follow topic-specific developer documentation.
- Agents also read the root `AGENTS.md` before making changes. It states repository-specific operating rules and points to the relevant developer documentation; it is not a second README.

This separates user-facing instructions from implementation and maintenance details while retaining the established direct Docker deployment contract.

## Information Architecture

| File | Primary audience | Responsibility |
| --- | --- | --- |
| `README.md` | Users | Product orientation, one-command public-image startup, first login, routine account use, quick health check, and links to detailed references. |
| `docs/README.md` | Developers and agents | Documentation index, reading paths by task, and document ownership. |
| `docs/development.md` | Developers and agents | Architecture, local setup, test/build commands, source Compose workflow, and database migration expectations. |
| `docs/operations.md` | Developers and agents operating a server | Production reverse proxy, advanced `.env` use, image updates and rollback, backups and recovery, and externally mounted plugins. |
| `docs/release.md` | Maintainers and agents | CI jobs, release-tag validation, GHCR tags, multi-architecture publishing, and the release checklist. |
| `AGENTS.md` | Agents | Required reading, repository guardrails, verification entry points, and the documentation-boundary rule. |

Existing specialist documentation remains where it is:

- `backend/app/plugins/README.md` stays the plugin implementation contract.
- `plugins/ai-work-assistant/README.md` stays the example plugin's own guide.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` remain design and implementation-history records, rather than primary onboarding documentation.

## Content Moves

The root README will retain only material a user needs to adopt and operate MeetFlow safely:

1. Product purpose and the supported public container image.
2. The command-line-first `docker run` quick start, including `-v "$PWD/data:/app/data"` and the required production variables.
3. First administrator behavior, account-management overview, and a simple health check.
4. Short links to operations, release, and developer documentation.

The following existing sections move out of the README:

| Existing topic | Destination |
| --- | --- |
| Local development and test commands | `docs/development.md` |
| HTTPS proxy and advanced `--env-file` configuration | `docs/operations.md` |
| Image tag rules, update, rollback, backup, recovery, and plugin mounts | `docs/operations.md` |
| GitHub Actions, GHCR publication, and tag creation | `docs/release.md` |
| Database migration limitation | `docs/development.md` |

## Contracts to Preserve

- The default deployment path remains a public GHCR image started with inline Docker `-e` flags; `.env` and `--env-file` remain advanced configuration only.
- Persistent host data remains `-v "$PWD/data:/app/data"`, not a Docker named volume.
- Production guidance retains the persistent `APP_SECRET_KEY`, loopback bind behind HTTPS, strong credentials, and `SECURE_COOKIES=true` requirements.
- Documentation never includes real passwords, API keys, or a committed `.env` file.
- Release behavior stays unchanged: a main-branch push runs CI; a valid `v*` tag runs tests and publishes the public multi-architecture GHCR image.

## Linking and Maintenance Rules

- Each root README link points to a durable `docs/` page, not to a dated plan or spec.
- `docs/README.md` is the canonical developer/agent index and links to all current operational pages.
- `AGENTS.md` links to the index and asks agents to update the relevant audience document when they change behavior, configuration, release automation, or developer workflows.
- Topic pages link outward rather than copying large blocks from another page. The one-command user quick start may be repeated only where an operations procedure needs its exact baseline.

## Verification

Documentation implementation is complete when:

1. `README.md`, `docs/README.md`, and `AGENTS.md` each state their audience and link to the right next document.
2. The user README contains no detailed backup, plugin, source-development, or CI/release procedure.
3. The operations and release pages preserve the tested Docker and GHCR contracts above.
4. Markdown links resolve locally and `git diff --check` introduces no new whitespace errors.
