# Inline AI Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated AI work appear as editable, explicit-confirmation drafts in the source meeting or project instead of requiring the AI task centre for normal work.

**Architecture:** Keep `PluginJob` as the persistent source of truth. Add target-scoped job listing and structured action-candidate application in the backend. Create a focused inline-draft component that loads and polls only source-local jobs, then mount it in meeting and project work surfaces; retain `/ai-tasks` for history, recovery, and links.

**Tech Stack:** Vue 3, TypeScript, Vitest, FastAPI, SQLAlchemy, SQLite, pytest.

---

## File and responsibility map

| File | Responsibility |
| --- | --- |
| `backend/app/plugins/router.py` | Target-scoped job list and structured apply request validation. |
| `backend/app/plugins/jobs.py` | Apply selected, user-edited action candidates through `OutcomeService`. |
| `backend/tests/plugins/test_jobs.py` | Target list authorization and edited action-candidate application contract. |
| `frontend/src/components/InlineAiDrafts.vue` | Source-local task loading, polling, pending/error/draft states, discard UI, and explicit apply controls. |
| `frontend/src/views/MeetingWorkspaceView.vue` | Meeting-summary and action-suggestion inline destinations. |
| `frontend/src/views/ProjectDetailView.vue` | Project-progress inline destination. |
| `frontend/src/views/AiTasksView.vue` | Recovery/history-only view, linking unresolved tasks back to their source. |
| `frontend/src/tests/inline-ai-drafts.test.ts` | Inline draft task lifecycle and selected action candidate interactions. |
| `frontend/src/tests/meeting-workspace.test.ts` | Meeting-local AI destination mounting. |
| `frontend/src/tests/project-workspace.test.ts` | Project-local AI destination mounting. |

### Task 1: Expose source-local job history and accept edited action candidates

**Files:**
- Modify: `backend/app/plugins/router.py`
- Modify: `backend/app/plugins/jobs.py`
- Test: `backend/tests/plugins/test_jobs.py`

- [ ] **Step 1: Write failing target-list and edited-candidate tests.**

```python
def test_list_jobs_can_be_scoped_to_one_meeting(plugin_client, plugin_meeting_id):
    response = plugin_client.get(
        f"/api/plugin-jobs?target_type=meeting&target_id={plugin_meeting_id}"
    )
    assert response.status_code == 200
    assert all(item["target_id"] == plugin_meeting_id for item in response.json()["items"])


def test_action_suggestions_apply_uses_edited_selected_candidates(
    plugin_client, succeeded_action_job
):
    response = plugin_client.post(
        f"/api/plugin-jobs/{succeeded_action_job.id}/apply",
        json={
            "candidates": [
                {
                    "index": 1,
                    "content": "发送已确认纪要",
                    "owner_user_id": None,
                    "due_date": "2026-07-30",
                    "priority": "high",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["created_count"] == 1
```

- [ ] **Step 2: Verify that the new tests fail.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: the current list ignores target query parameters and `JobApplyRequest` rejects or ignores `candidates`.

- [ ] **Step 3: Add a validated action-candidate request model and a scoped list query.**

```python
class AppliedActionCandidate(BaseModel):
    index: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=1000)
    owner_user_id: str | None = Field(default=None, max_length=64)
    due_date: date | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


@jobs_router.get("")
def list_jobs(
    target_type: Literal["meeting", "project"] | None = None,
    target_id: str | None = None,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(PluginJob).where(PluginJob.created_by == user.id)
    if (target_type is None) != (target_id is None):
        raise AppError(422, "invalid_plugin_target_filter", "任务筛选参数不完整")
    if target_type is not None:
        statement = statement.where(
            PluginJob.target_type == target_type, PluginJob.target_id == target_id
        )
    jobs = session.scalars(statement.order_by(PluginJob.created_at.desc(), PluginJob.id.desc()))
    return {"items": [serialize_job(job) for job in jobs]}
```

Add `candidates: list[AppliedActionCandidate]` to `JobApplyRequest`; retain
`selected_indexes` temporarily only for backwards compatibility with existing
task-centre history, preferring non-empty structured candidates when present.

- [ ] **Step 4: Apply edited selected candidates through the ordinary action service.**

```python
def apply_action_suggestions(
    self, job: PluginJob, candidates: list[AppliedActionCandidate], actor: User
) -> dict:
    stored = (job.result_json or {}).get("candidates")
    requested = list({candidate.index: candidate for candidate in candidates}.values())
    if not requested or not isinstance(stored, list):
        raise ValueError("invalid action candidate selection")
    if any(candidate.index >= len(stored) for candidate in requested):
        raise ValueError("invalid action candidate selection")
    meeting = self.session.get(Meeting, job.target_id)
    if meeting is None or job.target_type != "meeting":
        raise ValueError("meeting target is missing")
    for candidate in requested:
        OutcomeService(self.session).create_action(
            meeting.project_id,
            ActionWrite(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                content=candidate.content,
                owner_user_id=candidate.owner_user_id,
                due_date=candidate.due_date,
                priority=candidate.priority,
            ),
            actor,
        )
```

Validate job action, terminal success status, single application, and all
candidate indexes before creating the first row. Mark the job applied only
after all selected rows have been created.

- [ ] **Step 5: Verify and commit.**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`  
Expected: PASS, with the plugin test suite remaining below 100 tests.

```bash
git add backend/app/plugins/router.py backend/app/plugins/jobs.py backend/tests/plugins/test_jobs.py
git commit -m "feat: support inline AI action drafts"
```

### Task 2: Build the reusable inline draft surface

**Files:**
- Create: `frontend/src/components/InlineAiDrafts.vue`
- Create: `frontend/src/tests/inline-ai-drafts.test.ts`

- [ ] **Step 1: Write failing component tests for pending, draft, discard, and selected actions.**

```ts
it('renders a succeeded meeting draft inline and applies only after confirmation', async () => {
  apiMock.mockResolvedValueOnce({ items: [summaryJob] })
  render(InlineAiDrafts, { props: { targetType: 'meeting', targetId: 'm1', mode: 'summary' } })
  await fireEvent.update(await screen.findByLabelText('AI 会议纪要草稿'), '# 已确认纪要')
  await fireEvent.click(screen.getByRole('button', { name: '应用到会议纪要' }))
  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-1/apply', expect.objectContaining({ method: 'POST' }))
})

it('sends only checked edited action candidates', async () => {
  apiMock.mockResolvedValueOnce({ items: [actionJob] })
  render(InlineAiDrafts, { props: { targetType: 'meeting', targetId: 'm1', mode: 'actions', participants: [] } })
  await fireEvent.update(await screen.findByLabelText('行动项：发送纪要'), '发送最终纪要')
  await fireEvent.click(screen.getByRole('button', { name: '创建已选 1 项' }))
  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-2/apply', expect.objectContaining({
    body: expect.stringContaining('发送最终纪要'),
  }))
})
```

- [ ] **Step 2: Verify the tests fail.**

Run: `cd frontend && npm test -- --run src/tests/inline-ai-drafts.test.ts`  
Expected: module-not-found for `InlineAiDrafts.vue`.

- [ ] **Step 3: Implement target-local loading and bounded polling.**

```ts
const jobs = ref<PluginJob[]>([])
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  const query = new URLSearchParams({ target_type: props.targetType, target_id: props.targetId })
  const response = await api<{ items: PluginJob[] }>(`/api/plugin-jobs?${query}`)
  jobs.value = response.items.filter((job) => actionIds[props.mode].includes(job.action_id))
}

onMounted(() => {
  void load()
  timer = setInterval(() => {
    if (jobs.value.some((job) => ['queued', 'requesting'].includes(job.status))) void load()
  }, 3000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
```

Use `mode: 'summary' | 'progress' | 'actions'` to keep action-specific UI
separate while sharing lifecycle behavior. Keep local draft edits keyed by job
ID. `discardedJobIds` is component-local state: hide it from this surface only;
never call cancel for a succeeded draft.

- [ ] **Step 4: Implement concise source-local states.**

Render one compact card per unresolved job:

```vue
<article class="inline-ai-draft" :data-status="job.status">
  <p class="eyebrow">AI 建议 · 尚未应用</p>
  <p v-if="job.status === 'queued'">AI 任务排队中…</p>
  <p v-else-if="job.status === 'requesting'">正在生成草稿…</p>
  <p v-else-if="job.status === 'failed'" class="notice notice-error">{{ job.error_message }}</p>
  <RouterLink :to="`/ai-tasks?job=${job.id}`">在 AI 任务中打开</RouterLink>
</article>
```

For summary/progress, use an accessible labelled textarea and the existing
apply endpoints. For actions, map stored candidates into editable local rows:

```ts
type DraftAction = {
  index: number
  selected: boolean
  content: string
  owner_user_id: string | null
  due_date: string
  priority: 'low' | 'normal' | 'high' | 'urgent'
}
```

Use project/meeting participant `UserRef` values for an owner select. Add/remove
is local only until **创建已选 N 项** sends `candidates` to the apply endpoint.
Place original AI Markdown in a closed `<details><summary>查看 AI 依据</summary>`
section. Do not render a second full-size textarea for action suggestions.

- [ ] **Step 5: Verify and commit.**

Run: `cd frontend && npm test -- --run src/tests/inline-ai-drafts.test.ts`  
Expected: PASS.

```bash
git add frontend/src/components/InlineAiDrafts.vue frontend/src/tests/inline-ai-drafts.test.ts
git commit -m "feat: add inline AI draft surface"
```

### Task 3: Mount drafts into meeting and project work surfaces

**Files:**
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/views/ProjectDetailView.vue`
- Modify: `frontend/src/components/PluginActionPanel.vue`
- Test: `frontend/src/tests/meeting-workspace.test.ts`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Write failing source-destination tests.**

```ts
it('places meeting summary and action drafts in the meeting work surface', async () => {
  render(MeetingWorkspaceView)
  await screen.findByText('Current topic')
  expect(screen.getByTestId('meeting-inline-summary')).toBeInTheDocument()
  expect(screen.getByTestId('meeting-inline-actions')).toBeInTheDocument()
})

it('places project progress drafts beside project updates', async () => {
  render(ProjectDetailView)
  await screen.findByText('最近进展')
  expect(screen.getByTestId('project-inline-progress')).toBeInTheDocument()
})
```

- [ ] **Step 2: Verify the tests fail.**

Run: `cd frontend && npm test -- --run src/tests/meeting-workspace.test.ts src/tests/project-workspace.test.ts`  
Expected: missing `data-testid` destinations.

- [ ] **Step 3: Mount each inline destination where the user works.**

```vue
<!-- MeetingWorkspaceView.vue, below the meeting's active work content -->
<section data-testid="meeting-inline-summary">
  <InlineAiDrafts target-type="meeting" :target-id="meeting.id" mode="summary" />
</section>
<section data-testid="meeting-inline-actions">
  <InlineAiDrafts
    target-type="meeting"
    :target-id="meeting.id"
    mode="actions"
    :participants="meeting.participants.map((item) => item.user)"
    @applied="refreshAgenda"
  />
</section>
```

```vue
<!-- ProjectDetailView.vue, inside the latest-progress section -->
<section data-testid="project-inline-progress">
  <InlineAiDrafts target-type="project" :target-id="project.id" mode="progress" @applied="load" />
</section>
```

Keep `PluginActionPanel` as the action trigger only: on a successful job
submission, emit `submitted` so the closest source surface can refresh its
inline drafts immediately. Do not navigate to `/ai-tasks` after submission.

- [ ] **Step 4: Add source-local trigger refresh.**

```ts
const inlineDrafts = ref<InstanceType<typeof InlineAiDrafts> | null>(null)

function refreshInlineDrafts() {
  inlineDrafts.value?.reload()
}
```

Expose `reload()` from `InlineAiDrafts` with `defineExpose({ reload: load })`,
then pass `@submitted="refreshInlineDrafts"` from each mounted trigger. This
gives the user immediate pending feedback without waiting for the next poll.

- [ ] **Step 5: Verify and commit.**

Run: `cd frontend && npm test -- --run src/tests/meeting-workspace.test.ts src/tests/project-workspace.test.ts src/tests/inline-ai-drafts.test.ts`  
Expected: PASS.

```bash
git add frontend/src/views/MeetingWorkspaceView.vue frontend/src/views/ProjectDetailView.vue frontend/src/components/PluginActionPanel.vue frontend/src/tests/meeting-workspace.test.ts frontend/src/tests/project-workspace.test.ts
git commit -m "feat: show AI drafts in meeting and project context"
```

### Task 4: Simplify task centre into history and recovery

**Files:**
- Modify: `frontend/src/views/AiTasksView.vue`
- Modify: `frontend/src/tests/ai-tasks.test.ts`

- [ ] **Step 1: Write a failing task-centre recovery test.**

```ts
it('links an unresolved draft back to its source instead of exposing the primary editor', async () => {
  apiMock.mockResolvedValue({ items: [summaryJob] })
  render(AiTasksView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  expect(await screen.findByRole('link', { name: '回到会议处理草稿' })).toBeInTheDocument()
  expect(screen.queryByLabelText('编辑会议纪要草稿')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Verify it fails.**

Run: `cd frontend && npm test -- --run src/tests/ai-tasks.test.ts`  
Expected: the existing task centre still renders editable draft controls.

- [ ] **Step 3: Keep only status/history/recovery controls.**

Remove source-draft textareas, candidate checkboxes, and apply buttons from
`AiTasksView`. Preserve status, failure message, cancel for queued jobs, rerun
for terminal jobs, applied confirmation, and source-specific recovery links:

```vue
<RouterLink class="button button-primary" :to="source(job)">
  {{ job.target_type === 'meeting' ? '回到会议处理草稿' : '回到项目处理草稿' }}
</RouterLink>
```

Do not remove task polling; it still provides useful queued/running history.

- [ ] **Step 4: Verify and commit.**

Run: `cd frontend && npm test -- --run src/tests/ai-tasks.test.ts`  
Expected: PASS.

```bash
git add frontend/src/views/AiTasksView.vue frontend/src/tests/ai-tasks.test.ts
git commit -m "refactor: keep AI task centre for recovery"
```

### Task 5: Release verification and Docker redeployment

**Files:**
- Verify only unless tests expose a defect.

- [ ] **Step 1: Run backend verification.**

Run: `python -m pytest backend/tests/plugins backend/tests/meetings backend/tests/domain backend/tests/migrations -q`  
Expected: PASS; no suite exceeds 100 tests.

- [ ] **Step 2: Run frontend verification and build.**

Run: `cd frontend && npm test && npm run build`  
Expected: all tests pass and Vite emits `dist/index.html`.

- [ ] **Step 3: Rebuild and restart the single Docker service.**

Run:

```bash
docker compose up -d --build --force-recreate
curl --max-time 15 -fsS http://127.0.0.1:8000/api/health
```

Expected: the container becomes healthy and returns `{"status":"ok"}`.

- [ ] **Step 4: Confirm the production plugin action contract after restart.**

Log in with the configured administrator account without printing credentials,
then run:

```bash
curl --max-time 10 -fsS -b "$cookie" http://127.0.0.1:8000/api/plugins/actions
```

Expected: the response contains `ai-work-assistant.meeting_summary`,
`ai-work-assistant.project_progress`, and
`ai-work-assistant.action_suggestions`.

- [ ] **Step 5: Commit only release fixes, if any.**

If a verification defect changes source, stage that source and its matching
test together. Do not commit runtime data, Docker volumes, or generated build
assets.

## Plan self-review

- Target-local retrieval, inline pending/success/failure states, discard UI,
  edited action rows, and task-centre recovery are covered in Tasks 1–4.
- Every domain write remains behind explicit confirmation and ordinary existing
  services.
- The plan adds no agent, tool-call, streaming, or automatic-write behavior.
- Tests are scoped to behavior and remain comfortably below the requested
  100-test suite limit.
