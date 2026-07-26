# AI Task Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist safe, actionable AI-provider failure diagnostics and display them in the task centre.

**Architecture:** The worker maps typed provider and plugin exceptions to a stable code, user message, and sanitized detail before it writes the job. The existing job serializer exposes the detail. The task card keeps the concise message visible and reveals the detail only on demand.

**Tech Stack:** Python, httpx, SQLAlchemy, Alembic, FastAPI, Vue 3, TypeScript, Vitest.

---

### Task 1: Classify and persist execution diagnostics

**Files:**
- Modify: `backend/app/plugins/worker.py`
- Modify: `backend/app/plugins/models.py`
- Modify: `backend/app/plugins/router.py`
- Create: `backend/migrations/versions/0005_plugin_job_error_detail.py`
- Test: `backend/tests/plugins/test_worker.py`

- [ ] Write tests that pass HTTP 401, 402, 429, timeout, and a bearer-token-bearing exception through the worker classifier. Assert codes, Chinese messages, and redacted detail.
- [ ] Run the worker test and confirm the classifier is absent.
- [ ] Add `error_detail` to `PluginJob`, migrate it, serialize it, and implement one classifier that maps HTTP and `httpx` request errors to safe values.
- [ ] Run `python -m pytest backend/tests/plugins/test_worker.py -q` and commit the backend change.

### Task 2: Reveal safe detail in AI task history

**Files:**
- Modify: `frontend/src/domain/plugin-jobs.ts`
- Modify: `frontend/src/views/AiTasksView.vue`
- Test: `frontend/src/tests/ai-tasks.test.ts`

- [ ] Write a task-centre test with a failed job containing `error_detail`; assert the detail is hidden until “查看技术详情” is expanded.
- [ ] Run the test and confirm it fails because no detail is rendered.
- [ ] Add the optional field to the shared job type and an accessible `<details>` block to the failed task card.
- [ ] Run the focused Vitest file and commit the frontend change.

### Task 3: Verify production delivery

**Files:**
- Modify: none expected

- [ ] Run focused backend and frontend tests, then the complete frontend suite.
- [ ] Build and recreate Docker Compose, query the health endpoint, and confirm Alembic reaches `0005`.
- [ ] Report the current incident as a 402 insufficient-balance error, not a token error.
