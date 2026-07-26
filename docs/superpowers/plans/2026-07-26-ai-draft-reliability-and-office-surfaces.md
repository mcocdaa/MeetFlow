# AI Draft Reliability and Office Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist AI draft dismissal, show submitted drafts immediately, and tighten shared work surfaces into a restrained office visual system.

**Architecture:** `PluginJob` owns durable draft disposition. The job endpoint returns pending drafts by default and exposes history only when requested. The action panel emits the returned job to inline draft panels, which track and poll it locally. CSS token changes are shared; AI panels add a small, scoped action rail.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Vue 3, TypeScript, Vitest, Docker Compose.

---

### Task 1: Persist draft dismissal in the backend

**Files:**
- Modify: `backend/app/plugins/models.py`
- Modify: `backend/app/plugins/jobs.py`
- Modify: `backend/app/plugins/router.py`
- Create: `backend/migrations/versions/0004_plugin_job_dismissal.py`
- Test: `backend/tests/plugins/test_jobs.py`

- [ ] Add nullable `dismissed_at` and `dismissed_by` columns to `PluginJob` and an Alembic migration that adds both fields.
- [ ] Add `PluginJobService.dismiss(job, actor_id)`. It accepts only succeeded, unapplied, undismissed jobs, records actor and timestamp, commits, refreshes, and returns the job.
- [ ] Add `POST /api/plugin-jobs/{job_id}/dismiss`; serialize dismissal fields. Add `include_history: bool = False` to job listing. Default lists exclude applied and dismissed jobs; history lists include both.
- [ ] Add backend tests for durable dismissal, default list exclusion, history inclusion, and a conflict for invalid dismissal.
- [ ] Run `python -m pytest backend/tests/plugins/test_jobs.py -q`.

### Task 2: Track submitted jobs in the current page

**Files:**
- Create: `frontend/src/domain/plugin-jobs.ts`
- Modify: `frontend/src/components/PluginActionPanel.vue`
- Modify: `frontend/src/components/InlineAiDrafts.vue`
- Modify: `frontend/src/components/ProjectActivityTab.vue`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/views/AiTasksView.vue`
- Test: `frontend/src/tests/inline-ai-drafts.test.ts`
- Test: `frontend/src/tests/plugin-action-panel.test.ts`

- [ ] Move the shared serialized job type into `domain/plugin-jobs.ts`.
- [ ] Have `PluginActionPanel` emit the job returned by `POST /api/plugin-jobs`.
- [ ] Expose `track(job)` from `InlineAiDrafts`: it accepts only matching targets/actions, prepends or replaces the job, initializes editable state, and relies on existing polling for nonterminal status.
- [ ] Wire meeting and project parents to forward submitted jobs to their local draft panels. Make `AiTasksView` request `include_history=true`.
- [ ] Replace client-only discard with `POST /dismiss`; remove the card only after a successful response. Keep an error visible on failure.
- [ ] Run focused Vitest files, then the full frontend suite; the total remains below 100 tests.

### Task 3: Apply concise metal-office surfaces

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] Replace warm global canvas/paper/line tokens with cool silver-gray equivalents while preserving green as the primary action color.
- [ ] Reduce default panel radii, shadows, and large spacing. Add a shallow cool highlight to persistent chrome and AI/tool surfaces only.
- [ ] Add scoped inline-AI styling with a divider and margin above its primary action rail, so the apply control sits below rather than against the draft editor.
- [ ] Run `npm run build` from `frontend/` and review the generated styles for CSS errors.

### Task 4: Deploy and prove the integrated path

**Files:**
- Modify: none expected

- [ ] Run the focused backend and frontend tests.
- [ ] Build and recreate the Docker Compose service.
- [ ] Query the health endpoint and check migration startup logs for success.
- [ ] Commit production changes in focused commits and report exact verification results.
