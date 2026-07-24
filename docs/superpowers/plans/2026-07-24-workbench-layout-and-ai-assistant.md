# Workbench Layout and AI Work Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make empty and populated meeting workbenches visually coherent, normalize Markdown editor baselines, and ship one configured AI assistant plugin with meeting-summary, project-progress, and action-suggestion draft jobs.

**Architecture:** Keep the populated agenda workbench intact and isolate empty-state sizing in `AgendaWorkbench`. Put editor-baseline fixes in reusable Markdown-editor CSS. Extend the existing fixed plugin manager into a persistent job system; one trusted disk-installed `ai-work-assistant` plugin declares three actions, while the core serializes context, queues jobs, polls status, and applies user-edited drafts only through existing domain services.

**Tech Stack:** Vue 3, TypeScript, Vitest, FastAPI, SQLAlchemy 2, SQLite, Alembic, asyncio, httpx, pytest.

---

## File and responsibility map

| File | Responsibility |
| --- | --- |
| `frontend/src/components/AgendaWorkbench.vue` | Compact empty detail card, preserving existing populated layout. |
| `frontend/src/components/MarkdownEditor.vue` | Stable editor root/content hooks for all Markdown fields. |
| `frontend/src/styles.css` | Drawer grid, empty-card alignment, Markdown first-line baseline, task/action styles. |
| `frontend/src/tests/agenda-workbench.test.ts` | Empty and populated workbench hierarchy/layout hooks. |
| `frontend/src/tests/markdown-editor.test.ts` | Top-aligned placeholder/editor contract. |
| `backend/app/plugins/models.py` | Persistent job status, result, context snapshot, dedupe state. |
| `backend/app/plugins/jobs.py` | Race-safe submit/list/cancel/rerun and apply service. |
| `backend/app/plugins/context.py` | Bounded text-only meeting/project serializers. |
| `backend/app/plugins/worker.py` | One in-process persistent job worker and restart recovery. |
| `backend/app/plugins/router.py` | Job, action, result, and explicit-apply endpoints. |
| `backend/app/main.py` | Worker lifespan startup/shutdown. |
| `backend/migrations/versions/0003_plugin_jobs.py` | Non-destructive plugin-job schema migration. |
| `plugins/ai-work-assistant/{plugin.yaml,backend.py,README.md}` | Trusted fixed plugin manifest, OpenAI-compatible request handler, operator instructions. |
| `frontend/src/views/AiTasksView.vue` | Personal task centre with job state and apply controls. |
| `frontend/src/components/PluginActionPanel.vue` | Context-local assistant actions and active-job feedback. |
| `frontend/src/tests/ai-tasks.test.ts` | Job polling and explicit application UI behavior. |
| `backend/tests/plugins/test_jobs.py` | Dedupe, recovery, context boundary, apply tests. |

### Task 1: Make meeting work surfaces compact and aligned

**Files:**
- Modify: `frontend/src/components/AgendaWorkbench.vue`, `frontend/src/views/MeetingWorkspaceView.vue`, `frontend/src/styles.css`
- Test: `frontend/src/tests/agenda-workbench.test.ts`, `frontend/src/tests/meeting-workspace.test.ts`

- [ ] **Step 1: Write failing layout tests.**

```ts
it('renders an empty detail card without the populated-editor minimum height', () => {
  render(AgendaWorkbench, { props: { meeting: emptyMeeting() } })
  expect(screen.getByTestId('agenda-detail')).toHaveClass('agenda-empty-compact')
  expect(screen.getByTestId('agenda-detail')).not.toHaveClass('agenda-detail')
})

it('keeps populated detail before the narrow queue', () => {
  render(AgendaWorkbench, { props: { meeting: meetingFixture() } })
  expect(screen.getByTestId('agenda-detail').compareDocumentPosition(screen.getByTestId('agenda-queue')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})
```

- [ ] **Step 2: Verify the compact-empty test fails.**

Run: `cd frontend && npm test -- --run src/tests/agenda-workbench.test.ts`  
Expected: failure because the empty detail is still a generic oversized workspace section.

- [ ] **Step 3: Render a dedicated compact empty detail.**

```vue
<section v-else class="workspace-section agenda-empty-compact" data-testid="agenda-detail">
  <div>
    <p class="eyebrow">Agenda</p>
    <h2>还没有议题</h2>
    <p>从右侧队列添加本次会议的第一个议题。</p>
  </div>
  <button class="button button-primary" @click="emit('requestAdd')">添加议题</button>
</section>
```

Forward `requestAdd` through `MeetingWorkspaceView` to the queue’s existing add flow; do not create a second agenda API.

- [ ] **Step 4: Add desktop and responsive alignment rules.**

```css
.agenda-empty-compact { min-height: 0; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.agenda-empty-compact h2 { margin: 0; }
@media (max-width: 980px) { .agenda-empty-compact { align-items: flex-start; flex-direction: column; } }
```

Keep `.agenda-workbench` as the two-column owner and leave `.agenda-detail` unchanged for populated meetings.

- [ ] **Step 5: Verify and commit.**

```bash
cd frontend && npm test -- --run src/tests/agenda-workbench.test.ts src/tests/meeting-workspace.test.ts
git add frontend/src/components/AgendaWorkbench.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/styles.css frontend/src/tests/agenda-workbench.test.ts frontend/src/tests/meeting-workspace.test.ts
git commit -m "fix: compact the empty agenda workbench"
```

### Task 2: Normalize every Markdown editor's first text line

**Files:**
- Modify: `frontend/src/components/MarkdownEditor.vue`, `frontend/src/styles.css`
- Test: `frontend/src/tests/markdown-editor.test.ts`

- [ ] **Step 1: Add a failing baseline-hook test.**

```ts
it('uses a shared top-aligned content hook for empty and typed editors', () => {
  render(MarkdownEditor, { props: { modelValue: '', label: '会议记录', placeholder: '记录讨论上下文…' } })
  expect(screen.getByLabelText('会议记录').closest('.markdown-editor-root')).toHaveClass('markdown-editor-top-aligned')
})
```

- [ ] **Step 2: Verify it fails.**

Run: `cd frontend && npm test -- --run src/tests/markdown-editor.test.ts`  
Expected: failure because the editor root has no shared baseline class.

- [ ] **Step 3: Add the root hook and scoped first-paragraph rules.**

```vue
<div class="markdown-editor-root markdown-editor-top-aligned" :aria-label="label">
```

```css
.markdown-editor-top-aligned .ProseMirror,
.markdown-editor-top-aligned .milkdown { padding-top: 14px; }
.markdown-editor-top-aligned .ProseMirror > :first-child,
.markdown-editor-top-aligned .milkdown .editor > :first-child { margin-top: 0; }
.markdown-editor-top-aligned .ProseMirror p.is-editor-empty:first-child::before { top: 0; }
```

Retain each editor’s existing minimum writing height. Do not vertically center the content or placeholder.

- [ ] **Step 4: Verify and commit.**

```bash
cd frontend && npm test -- --run src/tests/markdown-editor.test.ts
git add frontend/src/components/MarkdownEditor.vue frontend/src/styles.css frontend/src/tests/markdown-editor.test.ts
git commit -m "fix: align Markdown editor first lines"
```

### Task 3: Add persistent, deduplicated plugin jobs

**Files:**
- Create: `backend/migrations/versions/0003_plugin_jobs.py`, `backend/app/plugins/jobs.py`
- Modify: `backend/app/plugins/models.py`, `backend/app/plugins/router.py`
- Test: `backend/tests/plugins/test_jobs.py`

- [ ] **Step 1: Write failing active-job deduplication and cancellation tests.**

```python
def test_same_active_action_returns_the_existing_job(session, manager, member, meeting):
    first, created = PluginJobService(session, manager).submit("ai-work-assistant.meeting_summary", "meeting", meeting.id, {}, member)
    second, duplicate = PluginJobService(session, manager).submit("ai-work-assistant.meeting_summary", "meeting", meeting.id, {}, member)
    assert created is True
    assert duplicate is False
    assert second.id == first.id

def test_queued_job_can_be_canceled(session, manager, member, meeting):
    job, _ = PluginJobService(session, manager).submit("ai-work-assistant.meeting_summary", "meeting", meeting.id, {}, member)
    assert PluginJobService(session, manager).cancel(job.id, member).status == "canceled"
```

- [ ] **Step 2: Verify failure.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: import failure for `PluginJobService`.

- [ ] **Step 3: Add model, migration, and race-safe submission.**

```python
class PluginJobStatus(StrEnum):
    QUEUED = "queued"
    REQUESTING = "requesting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELED = "canceled"

class PluginJob(Base):
    __tablename__ = "plugin_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(String(120), index=True)
    action_id: Mapped[str] = mapped_column(String(160), index=True)
    target_type: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(20), default=PluginJobStatus.QUEUED)
```

The migration creates a SQLite partial unique index over `dedupe_key` for `queued` and `requesting` only. On `IntegrityError`, roll back and select the active job; do not pre-check for duplicates.

- [ ] **Step 4: Add scoped APIs.**

```text
GET  /api/plugin-actions?target_type=meeting|project&target_id=<id>
POST /api/plugin-jobs                         {action_id,target_type,target_id,input}
GET  /api/plugin-jobs?status=&limit=&cursor=
GET  /api/plugin-jobs/{id}
POST /api/plugin-jobs/{id}/cancel
POST /api/plugin-jobs/{id}/rerun
```

All endpoints require an active account. List/detail authorize through the target project membership. Submission returns `201` for a new job and `200` for an active duplicate.

- [ ] **Step 5: Verify and commit.**

```bash
python -m pytest backend/tests/plugins/test_jobs.py -q
git add backend/app/plugins backend/migrations/versions/0003_plugin_jobs.py backend/tests/plugins/test_jobs.py
git commit -m "feat: add persistent plugin jobs"
```

### Task 4: Serialize bounded context and run jobs in one worker

**Files:**
- Create: `backend/app/plugins/context.py`, `backend/app/plugins/worker.py`
- Modify: `backend/app/main.py`, `backend/app/plugins/jobs.py`
- Test: `backend/tests/plugins/test_jobs.py`

- [ ] **Step 1: Add failing context and restart-recovery tests.**

```python
def test_meeting_context_has_attachment_metadata_but_never_bytes(session, meeting_with_attachment, member):
    context = PluginContextBuilder(session).meeting(meeting_with_attachment.id, member)
    assert context["attachments"][0]["original_name"] == "architecture.png"
    assert "content" not in context["attachments"][0]

def test_recovery_interrupts_inflight_jobs(session, worker):
    job = make_job(session, status="requesting")
    worker.recover()
    assert session.get(PluginJob, job.id).status == "interrupted"
```

- [ ] **Step 2: Verify failure.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: missing `PluginContextBuilder` and `PluginJobWorker`.

- [ ] **Step 3: Implement bounded serializers.**

`PluginContextBuilder.meeting()` serializes meeting/project labels, participants, purpose, raw notes, summary, agenda notes, outcomes, comments, amendments, and attachment metadata. `project()` serializes project metadata, updates, recent meetings, decisions, and open actions. Apply deterministic per-field and total-character limits; include `truncated: true` when data is clipped. Do not read attachment content, access a filesystem path, attach a database session, or expose an HTTP client in the context.

- [ ] **Step 4: Implement single-worker lifecycle.**

```python
async def recover(self) -> None:
    self.session.execute(update(PluginJob).where(PluginJob.status == "requesting").values(status="interrupted", error_code="process_restarted"))
    self.session.commit()

async def run_once(self) -> bool:
    job = self.claim_oldest_queued()
    if job is None:
        return False
    result = await self.manager.invoke(job.action_id, job.context_snapshot, job.input_json, self.session)
    self.complete(job.id, result)
    return True
```

`main.py` starts one worker task after plugin discovery; shutdown stops it. Requesting jobs are never replayed automatically after a process restart.

- [ ] **Step 5: Verify and commit.**

```bash
python -m pytest backend/tests/plugins/test_jobs.py -q
git add backend/app/plugins/context.py backend/app/plugins/worker.py backend/app/plugins/jobs.py backend/app/main.py backend/tests/plugins/test_jobs.py
git commit -m "feat: run plugin jobs with bounded context"
```

### Task 5: Install the fixed AI Work Assistant plugin

**Files:**
- Create: `plugins/ai-work-assistant/plugin.yaml`, `plugins/ai-work-assistant/backend.py`, `plugins/ai-work-assistant/README.md`
- Modify: `plugins/plugins.yaml`, `backend/tests/plugins/test_jobs.py`

- [ ] **Step 1: Add failing manifest/action tests.**

```python
def test_ai_work_assistant_declares_three_scoped_actions(manager):
    manager.load_enabled()
    assert {action.action_id for action in manager.loaded_actions()} == {
        "ai-work-assistant.meeting_summary",
        "ai-work-assistant.project_progress",
        "ai-work-assistant.action_suggestions",
    }
```

- [ ] **Step 2: Verify failure.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: the `ai-work-assistant` plugin directory is absent.

- [ ] **Step 3: Create manifest and handler contract.**

```yaml
id: ai-work-assistant
name: AI 工作助手
version: 1.0.0
api_version: 1
description: 生成可编辑的会议纪要、项目进展和行动项建议
config_schema:
  fields:
    - { key: base_url, type: string, required: true }
    - { key: model, type: string, required: true }
    - { key: timeout_seconds, type: integer, required: true }
  secrets:
    - { key: api_key, type: string, required: true }
```

Register the three action IDs. Each handler calls only the configured OpenAI-compatible chat-completions endpoint with a fixed action-specific instruction and the bounded context. It returns a Markdown draft plus an optional `candidates` array for action suggestions. It does not issue tools, make web requests beyond the configured model endpoint, or mutate MeetFlow data.

- [ ] **Step 4: Document deployment behavior.**

The README states: copy the fixed plugin directory, register it in `plugins.yaml`, restart the container, configure its URL/model/key as administrator, enable it, restart once if required, then create tasks. It calls out that output remains a draft.

- [ ] **Step 5: Verify and commit.**

```bash
python -m pytest backend/tests/plugins/test_discovery.py backend/tests/plugins/test_actions.py backend/tests/plugins/test_jobs.py -q
git add plugins/ai-work-assistant plugins/plugins.yaml backend/tests/plugins/test_jobs.py
git commit -m "feat: add AI work assistant plugin"
```

### Task 6: Add AI task centre and contextual action triggers

**Files:**
- Create: `frontend/src/views/AiTasksView.vue`, `frontend/src/composables/usePluginJobPolling.ts`, `frontend/src/tests/ai-tasks.test.ts`
- Modify: `frontend/src/components/PluginActionPanel.vue`, `frontend/src/views/MeetingWorkspaceView.vue`, `frontend/src/views/ProjectDetailView.vue`, `frontend/src/router.ts`, `frontend/src/styles.css`

- [ ] **Step 1: Write failing task UI tests.**

```ts
it('submits a meeting-summary job once and polls until success', async () => {
  apiMock.mockResolvedValueOnce({ id: 'j1', status: 'queued' })
  render(PluginActionPanel, { props: { targetType: 'meeting', targetId: 'm1' } })
  await fireEvent.click(screen.getByRole('button', { name: '生成会议纪要' }))
  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs', expect.objectContaining({ method: 'POST' }))
})

it('does not apply an AI draft until the user explicitly confirms', async () => {
  render(AiTasksView)
  expect(apiMock).not.toHaveBeenCalledWith(expect.stringMatching(/apply/), expect.anything())
  await fireEvent.click(screen.getByRole('button', { name: '应用到会议纪要' }))
  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/j1/apply', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 2: Verify failure.**

Run: `cd frontend && npm test -- --run src/tests/ai-tasks.test.ts`  
Expected: module-not-found for the task centre or missing apply control.

- [ ] **Step 3: Implement polling and task history.**

`usePluginJobPolling(jobId)` fetches `GET /api/plugin-jobs/{id}` every 3 seconds only while status is `queued` or `requesting`, and stops at any terminal state. `AiTasksView` shows action label, source link, state, safe failure message, editable draft textarea, rerun/cancel controls when applicable, and explicit apply controls.

- [ ] **Step 4: Integrate source-local actions.**

Meeting local tools render **生成会议纪要** and **建议行动项**. Project progress renders **总结项目进展** near updates. Buttons are absent when `GET /api/plugin-actions` reports no runtime-enabled action. On submit, disable only the matching action while the active deduplicated job exists.

- [ ] **Step 5: Verify and commit.**

```bash
cd frontend && npm test -- --run src/tests/ai-tasks.test.ts src/tests/admin-plugins.test.ts
git add frontend/src/views/AiTasksView.vue frontend/src/composables/usePluginJobPolling.ts frontend/src/components/PluginActionPanel.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/views/ProjectDetailView.vue frontend/src/router.ts frontend/src/styles.css frontend/src/tests/ai-tasks.test.ts
git commit -m "feat: add AI task centre and work actions"
```

### Task 7: Apply drafts through explicit domain operations and release

**Files:**
- Modify: `backend/app/plugins/jobs.py`, `backend/app/plugins/router.py`, `backend/tests/plugins/test_jobs.py`
- Test: full backend/frontend suites

- [ ] **Step 1: Add failing explicit-apply tests.**

```python
def test_meeting_summary_apply_updates_only_after_confirmation(client, succeeded_summary_job):
    response = client.post(f"/api/plugin-jobs/{succeeded_summary_job.id}/apply", json={"edited_markdown": "# 已确认纪要", "expected_version": 1})
    assert response.status_code == 200
    assert response.json()["summary_markdown"] == "# 已确认纪要"

def test_action_suggestions_apply_creates_only_selected_rows(client, succeeded_actions_job):
    response = client.post(f"/api/plugin-jobs/{succeeded_actions_job.id}/apply", json={"selected_indexes": [0], "expected_version": 1})
    assert response.status_code == 200
    assert response.json()["created_count"] == 1
```

- [ ] **Step 2: Verify failure.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: `apply` route is absent.

- [ ] **Step 3: Implement action-specific application.**

`meeting_summary` invokes the ordinary meeting update service with the user-edited Markdown and version check. `project_progress` invokes the ordinary project-update service with user-edited Markdown. `action_suggestions` validates requested indexes against the stored result, then calls the ordinary action-creation service once per selected candidate. Store `applied_at` and `applied_by`; a second apply returns `409 plugin_job_already_applied`.

- [ ] **Step 4: Run release verification and deploy.**

```bash
python -m pytest -q backend/tests/plugins backend/tests/meetings backend/tests/domain backend/tests/migrations
cd frontend && npm test && npm run build
cd .. && docker compose up -d --build --force-recreate
curl --max-time 10 -sS -i http://127.0.0.1:8000/api/health
git status --short
```

Expected: all test groups pass with fewer than 100 tests per suite; the Docker container becomes healthy; health returns `200` with `{"status":"ok"}`; generated runtime data remains untracked.

- [ ] **Step 5: Commit any verification fixes.**

If verification changes a source file, stage that exact file together with its matching test before committing. For example:

```bash
git add backend/app/plugins/jobs.py backend/tests/plugins/test_jobs.py
git commit -m "fix: harden AI work assistant release"
```

## Plan self-review

- Layout requirements are covered by Tasks 1–2 without changing populated workbench behavior.
- The three requested AI functions are a single fixed plugin in Task 5, while Tasks 3–4 and 6–7 provide its persistent, reviewable, explicit-apply operating model.
- No attachment content parsing, tool calling, agents, hot plugin installation, or automatic domain writes are introduced.
- Tests are behavior-focused and the plan preserves the under-100-tests-per-suite project constraint.
