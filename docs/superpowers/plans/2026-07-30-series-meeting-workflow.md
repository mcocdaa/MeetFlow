# 系列会议工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **实施状态（2026-07-30）：已完成。** 任务 1–9 及其收尾回归修复位于 `feature/series-meeting-workflow`；按要求，本地 `main` 已恢复为与 `origin/main` 一致。完成快照会保存结束时间并展示会议总实际时长；会议 API 与新快照统一输出带 `Z` 的 UTC，前端兼容按 UTC 解析旧 SQLite 快照的无后缀时间。复选框保留为原始执行模板。

**Goal:** Deliver executable, time-zone-aware meeting series plus a direct meeting workflow, agenda-derived outcomes, persistent minutes, and an improved existing two-column meeting workbench.

**Architecture:** Add structured recurrence fields to `MeetingSeries` and materialized fixed-period fields to `Meeting`; a bounded in-process scheduler creates idempotent draft occurrences while request-time reconciliation covers service downtime. Keep manual and tag-derived outcomes distinguishable by nullable source columns on each outcome table, reconcile derived rows in the agenda save transaction, and preserve the existing `AgendaWorkbench` split layout while changing its lifecycle affordances.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, SQLite, Vue 3, TypeScript, Vite, Vitest, pytest.

---

## File map

- `backend/app/domain/enums.py` — add recurrence and occurrence-source enum values.
- `backend/app/meetings/models.py`, `schemas.py`, `service.py`, `router.py` — persist, validate, serialize, and reconcile series/meeting lifecycle state.
- `backend/app/meetings/recurrence.py` — pure, time-zone-aware recurrence-slot calculation.
- `backend/app/meetings/scheduler.py` and `backend/app/main.py` — one-minute application worker lifecycle.
- `backend/app/agendas/models.py`, `schemas.py`, `service.py` — persist actual agenda duration and reconcile tag-derived outcomes during an agenda save.
- `backend/app/outcomes/models.py`, `service.py`, `schemas.py` — source metadata, serialization, and rejection of manual edits to derived outcomes.
- `backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py` — Alembic schema/data migration.
- `backend/tests/domain/test_meeting_series.py`, `test_meeting_lifecycle.py`, `test_agendas.py`, `test_outcomes.py`, `backend/tests/plugins/test_jobs.py` — backend regressions.
- `frontend/src/domain/meetings.ts`, `components/ProjectCreatePanel.vue`, `AgendaQueue.vue`, `AgendaDetail.vue`, `AgendaWorkbench.vue`, `CompletedMeetingChain.vue`, `views/MeetingWorkspaceView.vue`, `styles.css` — series creation, lifecycle, timings, outcomes, summaries, and interaction states.
- `frontend/src/tests/agenda-workbench.test.ts`, `meeting-workspace.test.ts`, `meeting-lifecycle.test.ts`, plus a new `frontend/src/tests/project-create-panel.test.ts` — frontend regressions.
- `README.md`, `docs/development.md`, `plugins/ai-work-assistant/README.md`, and `backend/app/plugins/README.md` — user, developer, and plugin-contract documentation.

### Task 1: Persist recurrence, occurrence source, duration, and outcome ownership

**Files:**

- Modify: `backend/app/domain/enums.py`
- Modify: `backend/app/meetings/models.py`
- Modify: `backend/app/agendas/models.py`
- Modify: `backend/app/outcomes/models.py`
- Create: `backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py`
- Modify: `backend/tests/migrations/test_wheel_resources.py`
- Test: `backend/tests/domain/test_meeting_series.py`

- [ ] **Step 1: Write the failing model and migration-contract tests**

```python
def test_series_persists_a_daily_rule_and_scheduled_slot(client, project, meeting_users):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        series = MeetingService(session).create_series(
            project.id,
            series_payload(
                admin, member, recorder,
                recurrence_frequency="daily",
                recurrence_interval=1,
                recurrence_local_time=time(21, 30),
                recurrence_timezone="Asia/Shanghai",
                recurrence_anchor_date=date(2026, 7, 30),
            ),
            admin,
        )
        assert series.recurrence_timezone == "Asia/Shanghai"
        assert series.recurrence_frequency.value == "daily"


def test_wheel_schema_contains_recurrence_and_outcome_source_columns(wheel_database):
    columns = table_columns(wheel_database)
    assert {"recurrence_frequency", "recurrence_timezone", "recurrence_local_time"} <= columns["meeting_series"]
    assert {"occurrence_kind", "series_slot_at"} <= columns["meetings"]
    assert "actual_duration_seconds" in columns["agenda_items"]
    for table in ("decisions", "action_items", "open_questions"):
        assert {"source_agenda_item_id", "source_tag_key"} <= columns[table]
```

- [ ] **Step 2: Run the new tests and verify the schema contract fails**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py backend/tests/migrations/test_wheel_resources.py`

Expected: FAIL because the new fields and migration revision do not exist.

- [ ] **Step 3: Add the minimum schema and migration**

Add `RecurrenceFrequency` (`daily`, `weekly`, `monthly`, `yearly`) and `OccurrenceKind` (`scheduled`, `manual`) to `backend/app/domain/enums.py`. Add the following mapped fields with safe defaults/nullability for existing rows:

```python
# MeetingSeries
recurrence_frequency: Mapped[RecurrenceFrequency | None] = mapped_column(
    Enum(RecurrenceFrequency), nullable=True
)
recurrence_interval: Mapped[int] = mapped_column(Integer, default=1)
recurrence_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
recurrence_month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
recurrence_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
recurrence_local_time: Mapped[time | None] = mapped_column(Time, nullable=True)
recurrence_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
recurrence_anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)

# Meeting
occurrence_kind: Mapped[OccurrenceKind] = mapped_column(
    Enum(OccurrenceKind), default=OccurrenceKind.manual, index=True
)
series_slot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# AgendaItem
actual_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

# Decision, ActionItem, OpenQuestion
source_agenda_item_id: Mapped[str | None] = mapped_column(
    ForeignKey("agenda_items.id", ondelete="CASCADE"), nullable=True, index=True
)
source_tag_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

Declare `UniqueConstraint("series_id", "series_slot_at", name="uq_meeting_series_slot")` on `meetings`, and one nullable-source unique constraint on each outcome table: `(source_agenda_item_id, source_tag_key)`. The Alembic upgrade must use `batch_alter_table` for SQLite and create the associated indexes/constraints; downgrade must drop exactly those additions.

- [ ] **Step 4: Run the focused tests and migration wheel test**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py backend/tests/migrations/test_wheel_resources.py`

Expected: PASS.

- [ ] **Step 5: Commit the persistent schema boundary**

```bash
git add backend/app/domain/enums.py backend/app/meetings/models.py backend/app/agendas/models.py backend/app/outcomes/models.py backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py backend/tests/domain/test_meeting_series.py backend/tests/migrations/test_wheel_resources.py
git commit -m "feat: persist series recurrence and agenda sources"
```

### Task 2: Calculate and materialize fixed-period meetings safely

**Files:**

- Create: `backend/app/meetings/recurrence.py`
- Create: `backend/app/meetings/scheduler.py`
- Modify: `backend/app/meetings/schemas.py`
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/meetings/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/domain/test_meeting_series.py`

- [ ] **Step 1: Write failing recurrence and idempotency tests**

```python
def test_monthly_31st_uses_the_last_day_in_february():
    rule = RecurrenceRule.monthly(
        interval=1, month_day=31, local_time=time(9), timezone_name="Asia/Shanghai",
        anchor_date=date(2026, 1, 31),
    )
    assert rule.slot_for(date(2026, 2, 1)) == datetime(2026, 2, 28, 1, tzinfo=timezone.utc)


def test_materialize_due_occurrences_is_idempotent(client, project, meeting_users):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        series = create_daily_series(session, project.id, admin, member, recorder)
        service = MeetingService(session)
        first = service.materialize_due_occurrences(now=datetime(2026, 7, 31, tzinfo=timezone.utc))
        second = service.materialize_due_occurrences(now=datetime(2026, 7, 31, tzinfo=timezone.utc))
        assert len(first) == 1
        assert second == []
        assert first[0].occurrence_kind == OccurrenceKind.scheduled
```

- [ ] **Step 2: Run the recurrence tests and verify they fail**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py -k 'monthly_31st or materialize_due'`

Expected: FAIL because `RecurrenceRule` and `materialize_due_occurrences` do not exist.

- [ ] **Step 3: Implement pure recurrence calculation and the scheduler seam**

Create `RecurrenceRule` in `recurrence.py` using `zoneinfo.ZoneInfo`, accepting only the four stored frequencies. Its `slots_through(now)` method returns UTC slots from `recurrence_anchor_date` through `now`; it uses `calendar.monthrange` for a short month.

Implement these service methods:

```python
def materialize_due_occurrences(self, *, now: datetime) -> list[Meeting]:
    """Create missing scheduled slots for active series; safe to call repeatedly."""

def reconcile_series(self, series_id: str, *, now: datetime) -> list[Meeting]:
    """Materialize due slots for one series before returning its detail or starting it."""

def _create_series_occurrence(
    self, series: MeetingSeries, *, slot_at: datetime, created_by: str
) -> Meeting:
    """Copy the series defaults/standing items and set occurrence_kind=scheduled."""
```

`create_occurrence` must set `occurrence_kind=OccurrenceKind.manual`; it remains the API for a user-created temporary meeting. Catch only the unique-constraint collision around scheduled creation and reload the existing slot, so concurrent workers do not expose duplicate errors.

Create `MeetingSeriesScheduler` with `serve()` waiting on `asyncio.Event.wait()` with a 60-second timeout, calling `database.session()` and `MeetingService(session).materialize_due_occurrences(now=utcnow())`. Add it beside `PluginJobWorker` in the FastAPI lifespan, start it outside test mode, and cancel/stop it in the existing `finally` block.

- [ ] **Step 4: Add request-time reconciliation and API serialization**

Validate recurrence fields in `MeetingSeriesWrite` and `MeetingSeriesEdit`: a non-null frequency requires a valid IANA zone, positive interval, anchor date, local time, and the matching weekly/monthly/yearly selectors. Include all recurrence fields plus `occurrence_kind` and `series_slot_at` in the series/meeting serializers. Call `reconcile_series` before `series_detail`, `list_series`, and the start path for a scheduled meeting.

- [ ] **Step 5: Run recurrence, API, and existing series tests**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py`

Expected: PASS, including daily/weekly/monthly/yearly serialization, UTC conversion, short-month behavior, duplicate prevention, manual occurrence preservation, and request-time catch-up.

- [ ] **Step 6: Commit recurrence materialization**

```bash
git add backend/app/meetings/recurrence.py backend/app/meetings/scheduler.py backend/app/meetings/schemas.py backend/app/meetings/service.py backend/app/meetings/router.py backend/app/main.py backend/tests/domain/test_meeting_series.py
git commit -m "feat: materialize scheduled meeting series"
```

### Task 3: Make meeting start and finish a direct, complete lifecycle

**Files:**

- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/agendas/service.py`
- Modify: `backend/app/meetings/schemas.py`
- Modify: `backend/app/meetings/router.py`
- Test: `backend/tests/domain/test_meeting_lifecycle.py`
- Test: `backend/tests/domain/test_agendas.py`

- [ ] **Step 1: Write failing lifecycle and duration tests**

```python
def test_starting_next_scheduled_occurrence_finishes_the_previous_slot(client, series_with_two_slots):
    with client.app.state.database.session() as session:
        actor, previous, current = series_with_two_slots(session)
        started = MeetingService(session).start(
            current.id, LifecycleCommand(expected_version=current.version), actor
        )
        session.refresh(previous)
        assert started.status == MeetingStatus.in_progress
        assert previous.status == MeetingStatus.completed
        assert all(item.status == AgendaStatus.skipped for item in previous.agenda_items)


def test_finish_skips_unresolved_agenda_and_records_duration(client, lifecycle_context, monkeypatch):
    now = datetime(2026, 8, 10, 9, 5, tzinfo=timezone.utc)
    monkeypatch.setattr("app.meetings.service.utcnow", lambda: now)
    # Seed one planned item and one item started at 09:00, then finish.
    completed = finish_context_meeting(client, lifecycle_context)
    assert [item.status for item in completed.agenda_items] == [AgendaStatus.skipped, AgendaStatus.skipped]
    assert completed.agenda_items[0].actual_duration_seconds == 0
    assert completed.agenda_items[1].actual_duration_seconds == 300
```

- [ ] **Step 2: Run the lifecycle tests and verify the unresolved-agenda behavior fails**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py backend/tests/domain/test_agendas.py -k 'next_scheduled or skips_unresolved or duration'`

Expected: FAIL because finishing currently raises `meeting_has_unresolved_agenda` and duration is not assigned.

- [ ] **Step 3: Implement direct start, automatic predecessor finish, and duration calculation**

Keep legacy `ready` acceptance in `MeetingService.start`, but remove `mark_ready`/`mark_draft` from the supported user workflow and router. Before setting a scheduled meeting to `in_progress`, find the immediately preceding scheduled slot for the same series and call a private transaction-local finalizer.

Extract the terminal work into a non-committing helper used by both explicit finish and predecessor auto-finish:

```python
def _finish_in_session(self, meeting: Meeting, *, actor: User, now: datetime) -> None:
    for item in meeting.agenda_items:
        if item.status in {AgendaStatus.planned, AgendaStatus.in_progress}:
            item.status = AgendaStatus.skipped
            item.completed_at = now
            item.actual_duration_seconds = (
                max(0, int((now - item.started_at).total_seconds()))
                if item.started_at else 0
            )
            item.version += 1
    self._validate_outcome_source_chain(meeting)
    self._append_snapshot(meeting, actor)
    meeting.status = MeetingStatus.completed
    meeting.completed_at = now
```

Update `AgendaService._transition` to set `actual_duration_seconds` for completed/skipped/canceled terminal states. Do not expose a public skip command in the workbench; retain the backend `skip` only for compatibility/admin flows. `finish` must call `_finish_in_session` and commit exactly once.

- [ ] **Step 4: Run lifecycle and agenda test modules**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py backend/tests/domain/test_agendas.py`

Expected: PASS, including direct draft start, legacy ready start, predecessor finalization, zero/nonzero elapsed duration, unchanged independent agenda versions, snapshots, and reopened-meeting behavior.

- [ ] **Step 5: Commit lifecycle changes**

```bash
git add backend/app/meetings/service.py backend/app/agendas/service.py backend/app/meetings/schemas.py backend/app/meetings/router.py backend/tests/domain/test_meeting_lifecycle.py backend/tests/domain/test_agendas.py
git commit -m "feat: finalize unresolved agendas when meetings end"
```

### Task 4: Reconcile agenda tags into derived outcomes without touching manual outcomes

**Files:**

- Create: `backend/app/agendas/outcome_tags.py`
- Modify: `backend/app/agendas/service.py`
- Modify: `backend/app/outcomes/models.py`
- Modify: `backend/app/outcomes/service.py`
- Modify: `backend/app/meetings/service.py`
- Test: `backend/tests/domain/test_agendas.py`
- Test: `backend/tests/domain/test_outcomes.py`

- [ ] **Step 1: Write failing tag parser and ownership tests**

```python
def test_saving_agenda_reconciles_tagged_outcomes_and_preserves_manual_rows(client, agenda_context):
    with client.app.state.database.session() as session:
        actor, agenda = agenda_context(session)
        manual = OutcomeService(session).create_action(
            agenda.project_id, ActionWrite(content="手动行动", meeting_id=agenda.meeting_id, agenda_item_id=agenda.id), actor
        )
        saved = AgendaService(session).update(
            agenda.id,
            AgendaEdit(expected_version=agenda.version, notes_markdown="@决策: 采用方案 A\n@行动: 发布\n@开放问题: 谁负责？"),
            actor,
        )
        assert [row.source_tag_key for row in saved.decisions] == ["decision:0"]
        assert manual.id in {row.id for row in saved.actions}


def test_removing_a_tag_deletes_only_its_derived_outcome(client, agenda_context):
    # Save a tagged action, then save notes without that line.
    assert derived_action_is_deleted_and_manual_action_remains(client, agenda_context)
```

- [ ] **Step 2: Run tag tests and verify they fail**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py -k 'tagged_outcomes or removing_a_tag'`

Expected: FAIL because no parser or derived source columns are used by agenda updates.

- [ ] **Step 3: Implement the strict line parser and reconciliation helper**

Create `parse_outcome_tags(markdown: str) -> list[TaggedOutcome]` in `outcome_tags.py`. Match only lines whose stripped text starts with exactly one of `@决策:`、`@行动:`、`@开放问题:`; reject an empty payload with `AppError(422, "invalid_agenda_outcome_tag", ...)`. Number each tag independently by kind and expose `source_tag_key` values `decision:0`, `action:0`, and `question:0`.

Implement a non-committing `AgendaService._reconcile_derived_outcomes(item, tags, actor)` that:

```python
# For each tag kind, locate rows where source_agenda_item_id == item.id.
# Update the row with the same source_tag_key, create a missing row, and
# delete derived rows whose source_tag_key no longer occurs in the notes.
# Never select or modify rows with source_agenda_item_id is None.
```

Set `project_id`, `meeting_id`, and `agenda_item_id` from the agenda for every derived row. Use `Decision(title=content, decision_markdown=content)`, `ActionItem(content=content)`, and `OpenQuestion(question_markdown=content)`. Call the helper from `AgendaService.update` after validation and before its single `session.commit()`.

In `OutcomeService.update_decision`, `update_action`, and `update_question`, reject rows with a non-null `source_agenda_item_id` using `409 derived_outcome_read_only`. Include `source_agenda_item_id`, `source_tag_key`, and a boolean `is_derived` in every outcome serialization and in meeting snapshots.

- [ ] **Step 4: Run agenda/outcome tests and the complete meeting snapshot tests**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py backend/tests/domain/test_meeting_lifecycle.py`

Expected: PASS, proving validation atomicity, tag edits/deletions, no duplicates, manual-outcome isolation, derived-row edit rejection, and snapshot inclusion.

- [ ] **Step 5: Commit tag-derived outcomes**

```bash
git add backend/app/agendas/outcome_tags.py backend/app/agendas/service.py backend/app/outcomes/models.py backend/app/outcomes/service.py backend/app/meetings/service.py backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py backend/tests/domain/test_meeting_lifecycle.py
git commit -m "feat: derive agenda outcomes from tagged notes"
```

### Task 5: Extend the trusted plugin context with agenda workflow data

**Files:**

- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/plugins/context.py`
- Modify: `plugins/ai-work-assistant/backend.py`
- Test: `backend/tests/plugins/test_jobs.py`
- Test: `frontend/src/tests/agenda-workbench.test.ts`

- [ ] **Step 1: Write failing plugin-context tests**

```python
def test_meeting_plugin_context_contains_tag_rules_and_agenda_timing(ai_plugin_client, ai_plugin_meeting_id):
    context = PluginContextBuilder(session).meeting(ai_plugin_meeting_id, actor)
    assert context["agenda_outcome_tags"] == ["@决策:", "@行动:", "@开放问题:"]
    assert context["agenda_items"][0]["actual_duration_seconds"] == 300
    assert context["agenda_items"][0]["decisions"][0]["is_derived"] is True
```

- [ ] **Step 2: Run the focused plugin test and verify it fails**

Run: `.venv/bin/python -m pytest -q backend/tests/plugins/test_jobs.py -k 'agenda_timing or tag_rules'`

Expected: FAIL because the canonical meeting plugin context lacks the tag instruction and timing/source fields.

- [ ] **Step 3: Build the context from server state, not frontend metadata**

Extend `MeetingService.plugin_context` with a bounded `agenda_outcome_tags` list and the serialized agenda fields from Tasks 1–4. Keep `PluginContextBuilder._bounded` as the final size limiter. In `plugins/ai-work-assistant/backend.py`, include these context keys in the user message supplied to agenda action, decision, and open-question suggestion actions; preserve its existing no-direct-write behavior.

Do not accept note text, duration, source identity, or outcomes as client-supplied plugin input. Existing `PluginEditorSlot` metadata may identify the selected agenda but the server meeting package remains authoritative.

- [ ] **Step 4: Run backend plugin and frontend assistant interaction tests**

Run: `.venv/bin/python -m pytest -q backend/tests/plugins/test_jobs.py && npm --prefix frontend test -- agenda-workbench.test.ts`

Expected: PASS, including the existing suggestion/apply behavior and the new trusted context fields.

- [ ] **Step 5: Commit plugin-context additions**

```bash
git add backend/app/meetings/service.py backend/app/plugins/context.py plugins/ai-work-assistant/backend.py backend/tests/plugins/test_jobs.py frontend/src/tests/agenda-workbench.test.ts
git commit -m "feat: provide agenda workflow context to AI plugins"
```

### Task 6: Expose structured series creation and temporary series occurrences

**Files:**

- Modify: `frontend/src/domain/meetings.ts`
- Modify: `frontend/src/components/ProjectCreatePanel.vue`
- Modify: `frontend/src/components/ProjectRecordTabs.vue`
- Modify: `frontend/src/views/MeetingsView.vue`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/tests/project-create-panel.test.ts`

- [ ] **Step 1: Write failing series-form tests**

```ts
it('submits a weekly series with an explicit timezone and local start time', async () => {
  render(ProjectCreatePanel, { props: { kind: 'series', project } })
  await fireEvent.update(screen.getByLabelText('系列标题'), '产品周会')
  await fireEvent.update(screen.getByLabelText('重复频率'), 'weekly')
  await fireEvent.update(screen.getByLabelText('每周星期'), '1')
  await fireEvent.update(screen.getByLabelText('开始时间'), '10:00')
  await fireEvent.update(screen.getByLabelText('时区'), 'Asia/Shanghai')
  await fireEvent.click(screen.getByRole('button', { name: '添加系列' }))
  expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/meeting-series', expect.objectContaining({ method: 'POST' }))
  expect(JSON.parse(apiMock.mock.calls[0][1].body)).toMatchObject({ recurrence_frequency: 'weekly', recurrence_weekday: 1, recurrence_timezone: 'Asia/Shanghai' })
})
```

- [ ] **Step 2: Run the new frontend test and verify it fails**

Run: `npm --prefix frontend test -- project-create-panel.test.ts`

Expected: FAIL because the series form only has free-text `重复说明`.

- [ ] **Step 3: Implement series and temporary-occurrence UI contracts**

Replace the free-text recurrence control in `ProjectCreatePanel.vue` with frequency, interval, date/weekday/month selectors, local time, timezone, anchor date, and default duration fields. Submit the exact `MeetingSeriesWrite` structure from Task 2. Keep `recurrence_description` display-only by deriving it from selected form values.

Add a series row action in `ProjectRecordTabs.vue` and the `MeetingsView.vue` filter/detail path that opens a temporary occurrence form. Its POST uses `/api/meeting-series/{series_id}/occurrences`, carries user-entered title/start/end, and never sends `occurrence_kind`; the backend assigns `manual`. Extend TypeScript meeting/series types with recurrence fields, `occurrence_kind`, `series_slot_at`, and `actual_duration_seconds`.

- [ ] **Step 4: Run series UI and full frontend tests**

Run: `npm --prefix frontend test -- project-create-panel.test.ts && npm --prefix frontend test`

Expected: PASS.

- [ ] **Step 5: Commit series interface work**

```bash
git add frontend/src/domain/meetings.ts frontend/src/components/ProjectCreatePanel.vue frontend/src/components/ProjectRecordTabs.vue frontend/src/views/MeetingsView.vue frontend/src/styles.css frontend/src/tests/project-create-panel.test.ts
git commit -m "feat: configure and create meeting series occurrences"
```

### Task 7: Update the existing workbench lifecycle, timing, and outcome affordances

**Files:**

- Modify: `frontend/src/components/AgendaQueue.vue`
- Modify: `frontend/src/components/AgendaDetail.vue`
- Modify: `frontend/src/components/AgendaWorkbench.vue`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/tests/agenda-workbench.test.ts`
- Modify: `frontend/src/tests/meeting-workspace.test.ts`

- [ ] **Step 1: Write failing interaction tests**

```ts
it('adds an agenda with a five-minute default and no standalone skip control', async () => {
  render(AgendaQueue, { props: { meeting: meetingFixture() } })
  await fireEvent.click(screen.getByRole('button', { name: '+ 议题' }))
  expect(screen.getByLabelText('预计时长')).toHaveValue(5)
  expect(screen.queryByRole('button', { name: /跳过/ })).not.toBeInTheDocument()
})

it('starts a draft meeting directly and leaves finish enabled with unresolved agendas', async () => {
  apiMock.mockResolvedValueOnce(meetingFixture({ status: 'draft' }))
  render(MeetingWorkspaceView)
  await screen.findByRole('button', { name: '开始会议' })
  await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))
  expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
  expect(screen.getByRole('button', { name: '结束会议' })).not.toBeDisabled()
})
```

- [ ] **Step 2: Run the workbench tests and verify they fail**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts meeting-workspace.test.ts`

Expected: FAIL because the add form lacks a duration field, skip controls are rendered, and draft meetings display the two-step ready action.

- [ ] **Step 3: Implement the direct workflow in the current split layout**

In `AgendaQueue.vue`, add `estimatedMinutes = ref(5)`, post it as `estimated_minutes`, render localized status plus expected/actual time, and remove `skip` from both the queue menu and command union.

In `AgendaDetail.vue`, remove `<span class="muted">版本 {{ currentVersion }}</span>` and the skip footer button. Render derived outcome rows with `来自议题记录` and do not offer a composer edit path for derived rows. Keep item-local `currentVersion` solely for API requests.

In `MeetingWorkspaceView.vue`, remove ready/draft buttons from the template and only render `开始会议` for draft/legacy-ready meetings. Remove the unresolved-agenda disabled state from finish. Add an explicit `保存纪要` button that calls `persistMeetingDraft()` and a visible saved/error state. Bind `:class="{ 'meeting-workspace-live': meeting.status === 'in_progress' }"` to the existing main workbench.

In `AgendaWorkbench.vue`, wrap the keyed `AgendaDetail` in a Vue `<Transition name="agenda-detail-swap" mode="out-in">` while retaining the existing left/right grid and selected queue row.

- [ ] **Step 4: Add the CSS behavior without changing layout geometry**

Add shared button states:

```css
.button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(22, 52, 40, .16); }
.button:active:not(:disabled) { transform: translateY(0); box-shadow: 0 2px 6px rgba(22, 52, 40, .16); }
.button:focus-visible { outline: 3px solid rgba(14, 107, 77, .28); outline-offset: 2px; }
.agenda-detail-swap-enter-active, .agenda-detail-swap-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.agenda-detail-swap-enter-from, .agenda-detail-swap-leave-to { opacity: 0; transform: translateY(4px); }
@media (prefers-reduced-motion: reduce) { .button, .agenda-detail-swap-enter-active, .agenda-detail-swap-leave-active { transition: none; } }
```

Change `.agenda-empty-compact` to `align-items: flex-start`, keep the left eyebrow as `Current topic`, and add a shallow background/status emphasis only under `.meeting-workspace-live`; do not change `.agenda-workbench` grid columns.

- [ ] **Step 5: Run focused and complete frontend tests**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts meeting-workspace.test.ts && npm --prefix frontend test`

Expected: PASS.

- [ ] **Step 6: Commit workbench interaction changes**

```bash
git add frontend/src/components/AgendaQueue.vue frontend/src/components/AgendaDetail.vue frontend/src/components/AgendaWorkbench.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/styles.css frontend/src/tests/agenda-workbench.test.ts frontend/src/tests/meeting-workspace.test.ts
git commit -m "feat: streamline agenda meeting workflow"
```

### Task 8: Render persisted minutes and agenda records in completed meetings

**Files:**

- Modify: `frontend/src/components/CompletedMeetingChain.vue`
- Modify: `frontend/src/domain/meetings.ts`
- Modify: `frontend/src/tests/meeting-lifecycle.test.ts`
- Modify: `backend/app/meetings/schemas.py`
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/tests/domain/test_meeting_lifecycle.py`

- [ ] **Step 1: Write failing completed-record tests**

```ts
it('shows saved minutes and each frozen agenda record after completion', async () => {
  render(MeetingWorkspaceView)
  const minutes = await screen.findByTestId('completed-meeting-summary')
  expect(minutes).toHaveTextContent('本轮范围已经确认')
  const agenda = screen.getByTestId('completed-agenda-a1')
  expect(agenda).toHaveTextContent('议题记录正文')
  expect(agenda).toHaveTextContent('实际 5 分钟')
  expect(agenda).toHaveTextContent('采用灰度发布')
})
```

- [ ] **Step 2: Run the completion tests and verify they fail**

Run: `npm --prefix frontend test -- meeting-lifecycle.test.ts && .venv/bin/python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py`

Expected: FAIL because the current completed component omits frozen agenda notes/duration and does not expose the saved summary test id.

- [ ] **Step 3: Include the new fields in snapshots and render them from the snapshot only**

Add `actual_duration_seconds`, `source_agenda_item_id`, and `source_tag_key` to the strict snapshot schemas and `_snapshot_document` columns. Do not read mutable live outcome rows in the completed component.

In `CompletedMeetingChain.vue`, render `snapshot.meeting.summary_markdown` inside `data-testid="completed-meeting-summary"`. For each frozen agenda entry, render the markdown notes, localized final status, expected duration, computed display of `actual_duration_seconds`, and its frozen decisions/actions/questions. Preserve the existing amendment/reopen controls.

- [ ] **Step 4: Run completed-record and full lifecycle tests**

Run: `npm --prefix frontend test -- meeting-lifecycle.test.ts && .venv/bin/python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py`

Expected: PASS.

- [ ] **Step 5: Commit completed-record rendering**

```bash
git add frontend/src/components/CompletedMeetingChain.vue frontend/src/domain/meetings.ts frontend/src/tests/meeting-lifecycle.test.ts backend/app/meetings/schemas.py backend/app/meetings/service.py backend/tests/domain/test_meeting_lifecycle.py
git commit -m "feat: show minutes and agenda records after completion"
```

### Task 9: Synchronize user, developer, plugin documentation and run release-level verification

**Files:**

- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `plugins/ai-work-assistant/README.md`
- Modify: `backend/app/plugins/README.md`
- Modify: `backend/tests/test_release_workflow.py` only if its assertions enumerate changed documentation or worker files

- [ ] **Step 1: Write documentation-link and behavior assertions where the repository already tests them**

```python
def test_readme_describes_series_schedule_and_persistent_data():
    readme = Path("README.md").read_text()
    assert "会议系列" in readme
    assert "时区" in readme
    assert "结束会议" in readme
```

- [ ] **Step 2: Run the documentation/release test and verify it fails if coverage exists**

Run: `.venv/bin/python -m pytest -q backend/tests/test_release_workflow.py`

Expected: PASS when no documentation contract test exists; otherwise FAIL until the new user-facing terms are documented.

- [ ] **Step 3: Update each audience-owned document**

Add to `README.md` a concise user workflow: create a series with its time zone, distinguish automatic fixed meetings from temporary series meetings, start directly, and explain that ending a meeting skips unresolved agendas.

Add to `docs/development.md` the Alembic revision, the in-process one-minute scheduler, request-time reconciliation, and the commands for recurrence/lifecycle tests.

Add to `plugins/ai-work-assistant/README.md` the three agenda tag lines, the source-of-truth rule, and the fact that the plugin receives context but cannot mutate stored outcomes.

Add to `backend/app/plugins/README.md` the stable meeting-context keys `agenda_outcome_tags`, agenda duration fields, derived-source metadata, and the rule that context comes from server state.

- [ ] **Step 4: Validate documentation and the full application contract**

Run:

```bash
git diff --check
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q backend/tests/test_release_workflow.py
```

Expected: every command exits 0; `git diff --check` has no output.

- [ ] **Step 5: Run the isolated browser smoke path**

Build a uniquely tagged image from the checkout and start it with a new temporary data directory and unused loopback port. In the disposable browser run, create a weekly `Asia/Shanghai` series, verify a generated draft occurrence, add a temporary occurrence, add an agenda with the five-minute default, save a tagged record, start and finish the meeting with unresolved agendas, reload, and verify the frozen minutes/agenda records. Stop only the temporary container/image/data resources after preserving screenshots and response traces.

- [ ] **Step 6: Commit documentation and final verification changes**

```bash
git add README.md docs/development.md plugins/ai-work-assistant/README.md backend/app/plugins/README.md backend/tests/test_release_workflow.py
git commit -m "docs: explain scheduled meeting workflow"
```

## Plan self-review

- **Spec coverage:** Tasks 1–3 cover executable series, time zones, automatic materialization, direct start, predecessor finalization, agenda duration, and finish behavior. Tasks 4–5 cover tag-derived outcomes, manual isolation, and AI context. Tasks 6–8 cover the current UI, feedback, visible minutes, and completed agenda records. Task 9 covers all required documentation and full verification.
- **Placeholder scan:** The plan contains no deferred implementation markers or unspecified files; every production task names its tests, commands, affected files, and implementation boundary.
- **Type consistency:** `RecurrenceFrequency`, `OccurrenceKind`, `series_slot_at`, `actual_duration_seconds`, `source_agenda_item_id`, and `source_tag_key` use the same names in persistence, serializers, frontend types, snapshots, tests, and documentation tasks.
