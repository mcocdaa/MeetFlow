# Agenda Auto Advance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 开始会议自动开启首个待开始议题；打开待开始议题即开启它；完成当前议题后原子开启并展示下一个待开始议题，同时为当前进行中项提供低干扰的流动背景。

**Architecture:** 状态转换保持在后端服务层。新增无提交的议题状态辅助函数，让 `MeetingService.start()` 与 `AgendaService.complete_and_advance()` 各自在一个事务中完成相关更新；前端只以 API 成功响应更新选择。工作台把队列点击作为唯一的“打开并按需开始”入口，详情页只保留完成操作。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Vue 3 Composition API、TypeScript、Vitest、pytest、CSS animation。

---

## 文件结构

- Create: `backend/app/agendas/lifecycle.py` — 无提交、无路由依赖的议题开始与完成字段更新；由两个服务复用。
- Modify: `backend/app/agendas/service.py` — 使用共享辅助函数，提供原子完成并推进命令。
- Modify: `backend/app/agendas/router.py` — 暴露完成并推进 HTTP 命令并返回下一个议题 ID。
- Modify: `backend/app/meetings/service.py` — 开始会议时在同一提交中自动开启第一项待开始议题。
- Modify: `backend/tests/domain/test_meeting_lifecycle.py` — 覆盖首项自动开启、无议题、结束会议兼容性。
- Modify: `backend/tests/domain/test_agendas.py` — 覆盖完成并推进、未完成项保留、无后续项和冲突无副作用。
- Modify: `frontend/src/components/AgendaWorkbench.vue` — 统一处理队列点击、开始请求、选择和推进响应。
- Modify: `frontend/src/components/AgendaDetail.vue` — 删除开始动作，完成时调用新的原子命令并向工作台返回下一项 ID。
- Modify: `frontend/src/components/AgendaQueue.vue` — 接收工作台开始中的禁用状态，防止重复打开命令。
- Modify: `frontend/src/tests/agenda-workbench.test.ts` — 覆盖点击待开始项开始、移除按钮和完成后的自动选择。
- Modify: `frontend/src/tests/meeting-lifecycle.test.ts` — 覆盖开始会议后的已开启首项工作台状态。
- Modify: `frontend/src/styles.css` — 仅为当前选择的进行中行添加方案 B 的渐变流动，并为完成项保持静态样式与减少动态效果降级。
- Modify: `docs/superpowers/plans/2026-07-30-agenda-auto-advance.md` — 实施完成后勾选步骤并记录验证结果。

### Task 1: 会议开始时原子开启首个待开始议题

**Files:**
- Create: `backend/app/agendas/lifecycle.py`
- Modify: `backend/app/agendas/service.py:37-40, 434-510`
- Modify: `backend/app/meetings/service.py:660-680, 708-750`
- Test: `backend/tests/domain/test_meeting_lifecycle.py:169-221`

- [x] **Step 1: 写出首项自动开启和空队列的失败领域测试**

```python
def test_start_automatically_opens_first_planned_agenda(client, lifecycle_context, monkeypatch):
    admin_id, _, meeting_id = lifecycle_context
    started_at = datetime(2026, 8, 10, 9, tzinfo=timezone.utc)
    monkeypatch.setattr("app.meetings.service.utcnow", lambda: started_at)
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        agendas = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        first = agendas.create(meeting_id, AgendaWrite(title="First", agenda_type="discussion"), actor, expected_meeting_version=meeting.version)
        second = agendas.create(meeting_id, AgendaWrite(title="Second", agenda_type="discussion"), actor, expected_meeting_version=session.get(Meeting, meeting_id).version)
        started = MeetingService(session).start(meeting_id, LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version), actor)
        by_id = {item.id: item for item in started.agenda_items}
        assert by_id[first.id].status == AgendaStatus.in_progress
        assert by_id[first.id].started_at == started_at
        assert by_id[second.id].status == AgendaStatus.planned


def test_start_without_agenda_remains_valid(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meeting = session.get(Meeting, meeting_id)
        started = MeetingService(session).start(meeting_id, LifecycleCommand(expected_version=meeting.version), actor)
        assert started.status == MeetingStatus.in_progress
        assert started.agenda_items == []
```

- [x] **Step 2: 运行失败测试，确认当前行为尚未开始首项**

Run: `python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py -k 'automatically_opens_first or without_agenda'`  
Expected: 首项测试失败，首项仍为 `planned`；空队列测试通过或成为回归基线。

- [x] **Step 3: 创建可复用、无提交的议题字段转换辅助函数**

Create `backend/app/agendas/lifecycle.py`。它只修改传入项的字段，不提交、不记录活动、不增加会议版本：

```python
from __future__ import annotations

from datetime import datetime, timezone

from app.agendas.models import AgendaItem
from app.domain.enums import AgendaStatus


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def actual_duration_seconds(item: AgendaItem, finished_at: datetime) -> int:
    if item.started_at is None:
        return 0
    return max(0, int((_as_utc(finished_at) - _as_utc(item.started_at)).total_seconds()))


def start_planned_item(item: AgendaItem, *, actor_id: str, at: datetime) -> None:
    item.status = AgendaStatus.in_progress
    item.started_at = at
    item.completed_at = None
    item.actual_duration_seconds = None
    item.updated_by = actor_id
    item.version += 1


def complete_item(item: AgendaItem, *, actor_id: str, at: datetime) -> None:
    item.started_at = item.started_at or at
    item.status = AgendaStatus.completed
    item.completed_at = at
    item.actual_duration_seconds = actual_duration_seconds(item, at)
    item.updated_by = actor_id
    item.version += 1
```

Use callers’ existing UTC-aware `now` value. Keep the existing skip/cancel duration helper unchanged in this task.

- [x] **Step 4: 在 `MeetingService.start()` 中启动排序第一项并记录活动**

After the meeting becomes `in_progress` and before `_commit_meeting_command`, find the first planned row by `(position, id)`, call `start_planned_item`, and record an `agenda.started` activity in the same session. Keep exactly one `_commit_meeting_command` call, so meeting and agenda changes commit together.

```python
first_planned = next(
    (item for item in sorted(meeting.agenda_items, key=lambda row: (row.position, row.id)) if item.status == AgendaStatus.planned),
    None,
)
if first_planned is not None:
    start_planned_item(first_planned, actor_id=actor.id, at=now)
    ActivityRecorder(self.session).record(
        project_id=meeting.project_id, meeting_id=meeting.id, actor_user_id=actor.id,
        event_type="agenda.started", subject_type="agenda_item", subject_id=first_planned.id,
        payload={"title": first_planned.title},
    )
```

Import `start_planned_item` at the top of `backend/app/meetings/service.py`; never call `AgendaService.start()` from this method because that method commits independently.

- [x] **Step 5: 调整结束会议回归测试并验证任务**

In `test_finish_skips_unresolved_agenda_and_records_duration`, remove the explicit `AgendaService(session).start(active.id, ...)` call after `service.start(...)`; preserve the fixed five-minute duration assertion because the automatically started first item must still produce `300` seconds.

Run: `python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py`  
Expected: PASS.

- [x] **Step 6: 提交后端开始行为**

```bash
git add backend/app/agendas/lifecycle.py backend/app/meetings/service.py backend/tests/domain/test_meeting_lifecycle.py
git commit -m "feat: start first agenda with meeting"
```

### Task 2: 原子完成当前议题并开启下一项

**Files:**
- Modify: `backend/app/agendas/service.py:434-516`
- Modify: `backend/app/agendas/router.py:79-106`
- Test: `backend/tests/domain/test_agendas.py:108-156`

- [x] **Step 1: 写出完成并推进的失败测试**

Add the following tests near the existing agenda transition test:

```python
def test_complete_and_advance_starts_next_planned_without_finishing_other_started(client, agenda_context, monkeypatch):
    admin, _, meeting_id = agenda_context
    first_at = datetime(2026, 8, 10, 9, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 10, 9, 5, tzinfo=timezone.utc)
    monkeypatch.setattr("app.agendas.service.utcnow", lambda: completed_at)
    with client.app.state.database.session() as session:
        meetings, agendas = MeetingService(session), AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        current = add_item(agendas, meeting, admin, "Current")
        session.refresh(meeting)
        already_open = add_item(agendas, meeting, admin, "Earlier open")
        session.refresh(meeting)
        next_item = add_item(agendas, meeting, admin, "Next")
        meetings.start(meeting_id, LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version), admin)
        current.started_at = first_at
        already_open.status = AgendaStatus.in_progress
        already_open.started_at = first_at
        session.commit()

        completed, next_id = agendas.complete_and_advance(current.id, AgendaCommand(expected_version=current.version), admin)

        assert completed.status == AgendaStatus.completed
        assert completed.actual_duration_seconds == 300
        assert next_id == next_item.id
        assert session.get(AgendaItem, next_item.id).status == AgendaStatus.in_progress
        assert session.get(AgendaItem, already_open.id).status == AgendaStatus.in_progress


def test_complete_and_advance_returns_none_when_no_later_planned_item(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        meetings, agendas = MeetingService(session), AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(agendas, meeting, admin, "Only")
        meetings.start(meeting_id, LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version), admin)
        completed, next_id = agendas.complete_and_advance(item.id, AgendaCommand(expected_version=item.version), admin)
        assert completed.status == AgendaStatus.completed
        assert next_id is None


def test_complete_and_advance_rejects_a_stale_item_without_starting_next(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        meetings, agendas = MeetingService(session), AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        current = add_item(agendas, meeting, admin, "Current")
        session.refresh(meeting)
        later = add_item(agendas, meeting, admin, "Later")
        meetings.start(meeting_id, LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version), admin)
        with pytest.raises(AppError) as error:
            agendas.complete_and_advance(current.id, AgendaCommand(expected_version=current.version + 1), admin)
        assert error.value.code == "version_conflict"
        assert session.get(AgendaItem, current.id).status == AgendaStatus.in_progress
        assert session.get(AgendaItem, later.id).status == AgendaStatus.planned
```

- [x] **Step 2: 运行失败测试，确认命令尚不存在**

Run: `python -m pytest -q backend/tests/domain/test_agendas.py -k 'complete_and_advance'`  
Expected: FAIL with `AttributeError: 'AgendaService' object has no attribute 'complete_and_advance'`.

- [x] **Step 3: 实现单次提交的服务命令**

Import `complete_item` and `start_planned_item` from `app.agendas.lifecycle`. Add this method to `AgendaService`; it validates like the existing `complete`, finishes the requested item, finds only later `planned` rows, starts the first one, records both activity entries, increments the parent meeting once, and commits once.

```python
def complete_and_advance(self, item_id: str, payload: AgendaCommand, actor: User) -> tuple[AgendaItem, str | None]:
    self._require_active(actor)
    item = self.get(item_id)
    meeting = item.meeting
    self._require_mutable(meeting)
    expected_meeting_version = meeting.version
    require_version(payload.expected_version, item.version)
    if item.status not in {AgendaStatus.planned, AgendaStatus.in_progress}:
        raise AppError(409, "invalid_agenda_transition", "议题状态不可再次结束")
    now = utcnow()
    complete_item(item, actor_id=actor.id, at=now)
    next_item = next((row for row in self.list(meeting.id) if row.position > item.position and row.status == AgendaStatus.planned), None)
    if next_item is not None:
        start_planned_item(next_item, actor_id=actor.id, at=now)
    meeting.updated_by = actor.id
    meeting.version += 1
    self._record(item, actor, "agenda.completed")
    if next_item is not None:
        self._record(next_item, actor, "agenda.started")
    try:
        self.session.commit()
    except StaleDataError as exc:
        self._raise_item_or_meeting_stale(item_id=item_id, expected_item_version=payload.expected_version, meeting_id=meeting.id, expected_meeting_version=expected_meeting_version, exc=exc)
    self.session.refresh(item)
    return item, next_item.id if next_item is not None else None
```

Keep `complete()` and `/complete` unchanged for compatibility. Make `start()` call `start_planned_item`, so explicit starts and automatic starts use identical timestamp and item-version updates.

- [x] **Step 4: 暴露完整且稳定的 HTTP 响应**

Add an explicit route before generic `_command` registrations in `backend/app/agendas/router.py`:

```python
@router.post("/api/agenda-items/{item_id}/complete-and-advance")
def complete_and_advance_agenda_item(
    item_id: str,
    payload: AgendaCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AgendaService(session)
    completed, next_agenda_item_id = service.complete_and_advance(item_id, payload, user)
    return {
        "agenda_item": service.detail(completed.id),
        "next_agenda_item_id": next_agenda_item_id,
    }
```

The response keeps the completed record consistent with existing commands and gives browser and future CLI callers an explicit nullable next ID.

- [x] **Step 5: 运行领域测试并提交推进命令**

Run: `python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_meeting_lifecycle.py`  
Expected: PASS.

```bash
git add backend/app/agendas/lifecycle.py backend/app/agendas/service.py backend/app/agendas/router.py backend/tests/domain/test_agendas.py
git commit -m "feat: advance agenda on completion"
```

### Task 3: 工作台以点击开始待开始议题，并自动选择推进结果

**Files:**
- Modify: `frontend/src/components/AgendaWorkbench.vue:1-47`
- Modify: `frontend/src/components/AgendaDetail.vue:1-111`
- Modify: `frontend/src/components/AgendaQueue.vue:1-111`
- Modify: `frontend/src/tests/agenda-workbench.test.ts:99-245`
- Modify: `frontend/src/tests/meeting-lifecycle.test.ts:57-81`

- [x] **Step 1: 写出前端失败测试**

Replace the manual-start test with these focused tests:

```ts
it('starts a planned topic when it is opened during a live meeting', async () => {
  apiMock.mockResolvedValueOnce({ ...meetingFixture().agenda_items[1], status: 'in_progress', version: 2 })
  render(AgendaWorkbench, { props: { meeting: meetingFixture() } })

  await fireEvent.click(screen.getByTestId('agenda-row-a2').querySelector('.agenda-select')!)

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a2/start', {
    method: 'POST', body: JSON.stringify({ expected_version: 1 }),
  }))
  expect(screen.getByLabelText('议题标题')).toHaveValue('发布方案')
})

it('does not render a separate start-topic action', () => {
  const planned = meetingFixture().agenda_items[1]
  render(AgendaDetail, { props: { meeting: meetingFixture(), item: planned } })
  expect(screen.queryByRole('button', { name: '开始此议题' })).not.toBeInTheDocument()
})

it('completes through the atomic advance command and reports its next topic', async () => {
  const advanced = vi.fn()
  apiMock.mockResolvedValueOnce({ agenda_item: meetingFixture().agenda_items[0], next_agenda_item_id: 'a2' })
  render(AgendaDetail, { props: { meeting: meetingFixture(), item: meetingFixture().agenda_items[0] }, attrs: { onAdvance: advanced } })
  await fireEvent.click(screen.getByRole('button', { name: '完成议题并进入下一项' }))
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1/complete-and-advance', {
    method: 'POST', body: JSON.stringify({ expected_version: 2 }),
  }))
  expect(advanced).toHaveBeenCalledWith('a2')
})
```

Update the post-start `MeetingWorkspaceView` fixture to include its first agenda item as `in_progress`, then assert that after clicking “开始会议” the workspace has no “开始此议题” control.

- [x] **Step 2: 运行失败测试，确认旧按钮和路由仍在使用**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts meeting-lifecycle.test.ts`  
Expected: FAIL because the old detail button is rendered and `/complete-and-advance` is not requested.

- [x] **Step 3: 让工作台处理“打开并开始”**

In `AgendaWorkbench.vue`, import `api`, add `openingId` and `openError`, and replace inline `@select="selectedId = $event"` with `@select="openAgenda"`. Only a `planned` item selected while the meeting is live sends `/start`; every other status only changes selection. Do not select a planned item before its start request succeeds.

```ts
async function openAgenda(itemId: string) {
  const item = props.meeting.agenda_items.find((row) => row.id === itemId)
  if (!item || openingId.value) return
  openError.value = ''
  if (props.meeting.status !== 'in_progress' || item.status !== 'planned') {
    selectedId.value = itemId
    return
  }
  openingId.value = itemId
  try {
    await api(`/api/agenda-items/${item.id}/start`, {
      method: 'POST', body: JSON.stringify({ expected_version: item.version }),
    })
    selectedId.value = itemId
    emit('reload')
  } catch (caught) {
    openError.value = caught instanceof Error ? caught.message : '议题开始失败'
  } finally {
    openingId.value = ''
  }
}

function advance(nextId: string | null) {
  if (nextId) selectedId.value = nextId
  emit('reload')
}
```

Pass `:opening-id="openingId"` and `:open-error="openError"` to `AgendaQueue`. In `AgendaQueue.vue`, declare the optional props, disable `.agenda-select` while a different ID is opening, and render `openError` through its existing error notice. A rejected request therefore leaves the current detail selected and visible.

- [x] **Step 4: 删除详情页开始按钮并改用推进响应**

In `AgendaDetail.vue`, change the emitted `advance` payload to `string | null`, remove `'start'` from `flow`, and request the new endpoint only from the existing completion button:

```ts
type AgendaAdvanceResult = { next_agenda_item_id: string | null }

async function complete() {
  saving.value = true
  error.value = ''
  try {
    const result = await api<AgendaAdvanceResult>(`/api/agenda-items/${props.item.id}/complete-and-advance`, {
      method: 'POST', body: JSON.stringify({ expected_version: currentVersion.value }),
    })
    emit('advance', result.next_agenda_item_id)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题状态更新失败'
  } finally {
    saving.value = false
  }
}
```

Keep save and conflict handling unchanged. Replace the footer with one conditional completion button:

```vue
<footer v-if="item.status === 'in_progress'" class="agenda-flow-actions" data-testid="flow-actions">
  <button class="button button-primary" :disabled="saving" @click="complete">完成议题并进入下一项</button>
</footer>
```

- [x] **Step 5: 运行组件测试并提交工作台交互**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts meeting-lifecycle.test.ts meeting-workspace.test.ts`  
Expected: PASS.

```bash
git add frontend/src/components/AgendaWorkbench.vue frontend/src/components/AgendaDetail.vue frontend/src/components/AgendaQueue.vue frontend/src/tests/agenda-workbench.test.ts frontend/src/tests/meeting-lifecycle.test.ts
git commit -m "feat: start and advance agendas from queue"
```

### Task 4: 让当前进行中项使用方案 B 动效，完成项保持静态

**Files:**
- Modify: `frontend/src/styles.css:370-390`
- Test: `frontend/src/tests/agenda-workbench.test.ts:99-115`

- [x] **Step 1: 写出队列状态类的失败断言**

Extend the shared-workbench test after rendering its fixture:

```ts
expect(screen.getByTestId('agenda-row-a1')).toHaveClass('selected', 'agenda-status-in_progress')
expect(screen.getByTestId('agenda-row-a2')).toHaveClass('agenda-status-planned')
```

Add a completed fixture variant, select it, and assert it has `agenda-status-completed` but not `agenda-status-in_progress`. This checks the markup boundary consumed by the CSS animation.

- [x] **Step 2: 运行组件测试，确认状态边界存在**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts`  
Expected: PASS for the queue state-class assertions. The visual rule itself is verified in Steps 4 and 5 by build and browser evidence.

- [x] **Step 3: 添加仅作用于当前进行中行的渐变流动**

Append the following rules beside existing agenda status rules in `frontend/src/styles.css`. The selector requires both `selected` and `agenda-status-in_progress`; no completed selector has an animation assignment.

```css
.agenda-queue-row.agenda-status-completed { background: #fcfdfc; }
.agenda-queue-row.selected.agenda-status-in_progress {
  border-color: #72a98f;
  background: linear-gradient(105deg, #fff 0%, #eaf7ef 40%, #f7fcf9 62%, #fff 100%);
  background-size: 220% 100%;
  animation: agenda-current-wash 3.6s ease-in-out infinite;
}
@keyframes agenda-current-wash {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
@media (prefers-reduced-motion: reduce) {
  .agenda-queue-row.selected.agenda-status-in_progress { animation: none; }
}
```

Merge the last selector into the existing reduced-motion rule rather than creating a competing reset. Keep completed, planned, skipped and canceled rows static.

- [x] **Step 4: 构建前端并在隔离浏览器验证完整体验**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts meeting-lifecycle.test.ts && npm --prefix frontend run build`  
Expected: tests and production build PASS; the existing Vite chunk-size warning may remain.

Use the `testing-isolated-web-ui` skill with a temporary image, container, port and data directory. In the browser: create a meeting with at least three topics; start it; verify the first row is selected and computed `animationName` is `agenda-current-wash`; click the third planned row and verify it starts without completing the first; complete the third row and verify the next planned row opens; select a completed row and verify computed `animationName` is `none`. Remove only the exact temporary container, image and temporary directory afterwards.

- [x] **Step 5: 提交视觉状态**

```bash
git add frontend/src/styles.css frontend/src/tests/agenda-workbench.test.ts
git commit -m "style: animate current agenda state"
```

### Task 5: 全量验证、计划记录与交付检查

**Files:**
- Modify: `docs/superpowers/plans/2026-07-30-agenda-auto-advance.md`

- [x] **Step 1: 运行仓库规定的完整验证**

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q backend/tests/test_release_workflow.py
git diff --check
```

Expected: every test command exits `0`; production build succeeds (existing Vite chunk-size warning is non-failing); `git diff --check` has no output.

- [x] **Step 2: 记录实际验证结果并勾选计划步骤**

Replace every completed `- [ ]` in this plan with `- [x]`. Then append an `## 实施验证记录` heading followed by one bullet for each command in Step 1 and one browser bullet. Each bullet must quote the literal observed pass count or successful completion and, for the browser, name the observed start, manual-open, auto-advance and static-completed results. Do not write a result until the corresponding command or browser run has completed.

- [x] **Step 3: 提交计划记录**

```bash
git add docs/superpowers/plans/2026-07-30-agenda-auto-advance.md
git commit -m "docs: complete agenda auto advance plan"
```

## 实施验证记录

- `python -m pytest -q`：`142 passed in 142.29s (0:02:22)`。
- `npm --prefix frontend test`：`22 passed (22)` 个测试文件、`92 passed (92)` 个测试。
- `npm --prefix frontend run build`：生产构建成功，`✓ built in 14.86s`；仅保留既有的 chunk-size 非阻断警告。
- `python -m pytest -q backend/tests/test_release_workflow.py`：`1 passed in 0.02s`。
- `git diff --check`：成功，无输出。
- 隔离浏览器：以临时镜像 `meetflow-agenda-auto-advance:5f6a40f`、独立数据目录和 `127.0.0.1:45336` 运行；登录前插件模块请求为 401、登录后重试为 200 且插件控件可见。创建四项议题后，开始会议自动选中议题一并显示 `agenda-current-wash`；打开议题三不会结束议题一；完成议题三后自动打开议题四；选择已完成的议题三时计算动画为 `none`；刷新后议题一、议题四仍为进行中，议题三仍为已完成。临时容器、镜像、数据和截图均已清理，原有 `meetflow-series-smoke` 容器保持不变。
