# PR #2 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the PR #2 correctness, lifecycle, scheduling, migration, and timezone regressions without changing the approved meeting-series workflow.

**Architecture:** `AgendaDetail` persists drafts before terminal lifecycle actions. Recurrence stays pure and receives a finite backfill cutoff from `MeetingService`; list paths scope catch-up to one project, while the scheduler stays global and isolates synchronous database work. Migration and outcome tests protect schema/source ownership contracts.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, SQLite, Vue 3, TypeScript, Vitest, pytest.

---

## File map

- `frontend/src/components/AgendaDetail.vue`, `views/MeetingsView.vue`, `components/ProjectCreatePanel.vue` — completion persistence, canceled visibility, local anchors.
- `frontend/src/tests/agenda-workbench.test.ts`, `meetings-view.test.ts`, `project-create-panel.test.ts` — front-end regression coverage.
- `backend/app/meetings/recurrence.py`, `scheduler.py`, `service.py`, `schemas.py` — bounded recurrence and resilient scheduled lifecycle.
- `backend/app/agendas/service.py`, `backend/app/outcomes/service.py` — shared durations and derived outcome ownership.
- `backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py` and migration tests — schema parity.
- `backend/app/plugins/README.md` and dated records — contract documentation.

### Task 1: Preserve dirty agenda edits before completion

**Files:**

- Modify: `frontend/src/components/AgendaDetail.vue:81-96`
- Test: `frontend/src/tests/agenda-workbench.test.ts`

- [x] **Step 1: Write a failing regression test**

```ts
it('saves pending notes before completing and advancing', async () => {
  // Type a new @决策 line, click 完成议题并进入下一项, and capture requests.
  // Assert PATCH /api/agenda-items/:id precedes complete-and-advance and
  // carries the new notes_markdown.
})
```

- [x] **Step 2: Run the test and verify the expected failure**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts`

Expected: the completion request is issued without a preceding PATCH.

- [x] **Step 3: Implement the minimal persistence gate**

```ts
async function complete() {
  try {
    markdownEditor.value?.flush()
    await persistIfDirty()
  } catch {
    return
  }
  saving.value = true
  // Preserve the existing complete-and-advance request using currentVersion.
}
```

- [x] **Step 4: Re-run the focused test and commit**

Run: `npm --prefix frontend test -- agenda-workbench.test.ts`

Expected: PASS.

```bash
git add frontend/src/components/AgendaDetail.vue frontend/src/tests/agenda-workbench.test.ts
git commit -m "fix: persist agenda edits before completion"
```

### Task 2: Correct visible status results and local anchor dates

**Files:**

- Modify: `frontend/src/views/MeetingsView.vue:51-55`
- Modify: `frontend/src/components/ProjectCreatePanel.vue:20-24`
- Test: `frontend/src/tests/meetings-view.test.ts`
- Test: `frontend/src/tests/project-create-panel.test.ts`

- [x] **Step 1: Write failing filter and request-payload tests**

```ts
it('renders canceled meetings when 已取消 is selected', async () => {
  // Return a canceled meeting, choose 已取消, then assert its title is rendered.
})

it('submits recurrence_anchor_date for a weekly series', async () => {
  // Submit the form and require recurrence_anchor_date in the JSON body.
})
```

- [x] **Step 2: Run the tests and verify the expected failures**

Run: `npm --prefix frontend test -- meetings-view.test.ts project-create-panel.test.ts`

Expected: the canceled meeting is not in any group and the payload assertion is absent.

- [x] **Step 3: Add local formatting and a canceled group**

```ts
function todayLocalDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

const recurrenceAnchorDate = ref(todayLocalDate())

{ id: 'canceled', title: '已取消', items: visible.value
  .filter((item) => item.status === 'canceled')
  .sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
```

- [x] **Step 4: Re-run the focused tests and commit**

Run: `npm --prefix frontend test -- meetings-view.test.ts project-create-panel.test.ts`

Expected: PASS.

```bash
git add frontend/src/views/MeetingsView.vue frontend/src/components/ProjectCreatePanel.vue frontend/src/tests/meetings-view.test.ts frontend/src/tests/project-create-panel.test.ts
git commit -m "fix: render canceled meetings and local anchors"
```

### Task 3: Bound and scope recurrence materialization

**Files:**

- Modify: `backend/app/meetings/recurrence.py:113-208`
- Modify: `backend/app/meetings/service.py:487-545,1412-1430`
- Modify: `backend/app/meetings/schemas.py:252-416`
- Test: `backend/tests/domain/test_meeting_series.py`

- [x] **Step 1: Write failing recurrence and project-isolation tests**

```python
def test_slots_through_ignores_slots_before_earliest_cutoff():
    rule = RecurrenceRule.daily(
        interval=1,
        local_time=time(9),
        timezone_name="UTC",
        anchor_date=date(2024, 1, 1),
    )
    slots = rule.slots_through(
        datetime(2026, 7, 3, 9, tzinfo=timezone.utc),
        earliest=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert all(slot >= datetime(2026, 7, 1, tzinfo=timezone.utc) for slot in slots)
```

- [x] **Step 2: Run the tests and verify the expected failures**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py -k 'earliest_cutoff or requested_project'`

Expected: slots have no cutoff and list materializes every active series.

- [x] **Step 3: Implement finite, project-aware materialization**

```python
MAX_RECURRENCE_BACKFILL = timedelta(days=90)

def slots_through(self, now: datetime, *, earliest: datetime | None = None) -> list[datetime]:
    # Normalize both values to UTC and skip candidates before earliest.

def materialize_due_occurrences(
    self, *, now: datetime, project_id: str | None = None
) -> list[Meeting]:
    # Add MeetingSeries.project_id predicate only when project_id is present.
```

`_materialize_series` loads existing slots once, normalizes them with `as_utc`, and creates only missing slots. `list_series` and `list_meetings` pass `project_id`; `RecurrenceRule.__post_init__` raises `ValueError` for missing selectors and documents its DST behavior.

- [x] **Step 4: Re-run the focused suite and commit**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py`

Expected: PASS.

```bash
git add backend/app/meetings/recurrence.py backend/app/meetings/service.py backend/app/meetings/schemas.py backend/tests/domain/test_meeting_series.py
git commit -m "fix: bound and scope series materialization"
```

### Task 4: Harden scheduler execution and fixed-instance closure

**Files:**

- Modify: `backend/app/meetings/scheduler.py:21-34`
- Modify: `backend/app/meetings/service.py:709-746`
- Test: `backend/tests/domain/test_meeting_series.py`

- [x] **Step 1: Write failing scheduler and lifecycle tests**

```python
def test_start_scheduled_meeting_finishes_all_older_open_slots(
    client, project, meeting_users, monkeypatch
):
    # Extend the existing next-scheduled-occurrence fixture to materialize three
    # daily slots, start the newest with LifecycleCommand(expected_version=1),
    # and assert the first two Meeting.status values are completed.
```

- [x] **Step 2: Run the tests and verify the expected failures**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py -k 'all_older_open_slots or continues_after_one_run_failure'`

Expected: only one old slot is closed and `serve` exits after an error.

- [x] **Step 3: Implement all-row closure and isolated scheduler execution**

```python
previous_ids = list(self.session.scalars(
    select(Meeting.id)
    .where(
        Meeting.series_id == meeting.series_id,
        Meeting.occurrence_kind == OccurrenceKind.scheduled,
        Meeting.series_slot_at < meeting.series_slot_at,
        Meeting.status.in_([MeetingStatus.draft, MeetingStatus.ready, MeetingStatus.in_progress]),
    )
    .order_by(Meeting.series_slot_at)
))
for previous_id in previous_ids:
    self._finish_in_session(self._meeting_for_snapshot(previous_id), actor=actor, now=now)

try:
    await asyncio.to_thread(self.run_once)
except asyncio.CancelledError:
    raise
except Exception:
    logger.exception("meeting series scheduler run failed")
```

- [x] **Step 4: Re-run focused tests and commit**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py`

Expected: PASS.

```bash
git add backend/app/meetings/scheduler.py backend/app/meetings/service.py backend/tests/domain/test_meeting_series.py
git commit -m "fix: harden series scheduling lifecycle"
```

### Task 5: Preserve duration, derived-outcome, and migration contracts

**Files:**

- Modify: `backend/app/agendas/service.py`, `backend/app/meetings/service.py`, `backend/app/outcomes/service.py`
- Modify: `backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py`
- Test: `backend/tests/domain/test_agendas.py`, `test_outcomes.py`, `test_meeting_lifecycle.py`
- Test: `backend/tests/migrations/test_fresh_baseline.py`, `backend/tests/plugins/test_jobs.py`

- [x] **Step 1: Write failing duration, source-chain, and metadata-parity tests**

```python
def test_finish_uses_shared_agenda_duration_lifecycle(client, meeting, meeting_users):
    # Use the existing lifecycle fixture, set its started_at to T0, invoke finish
    # at T0 + timedelta(minutes=5), and assert actual_duration_seconds == 300.
```

- [x] **Step 2: Run targeted tests and verify the expected failures**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py backend/tests/migrations/test_fresh_baseline.py backend/tests/plugins/test_jobs.py`

Expected: direct duration assignment/schema defaults or source migration violates the new assertions.

- [x] **Step 3: Reuse one duration function and preserve source ownership**

```python
from app.agendas.lifecycle import actual_duration_seconds, complete_item, start_planned_item

item.actual_duration_seconds = actual_duration_seconds(item, now)
```

Use the shared helper in both services. Agenda migration must skip source-owned outputs unless it updates their `agenda_item_id`, source fields, and reconciliation state atomically. The plugin context test completes through lifecycle functions instead of assigning duration directly.

- [x] **Step 4: Align migration types and temporary defaults**

```python
sa.Enum(RecurrenceFrequency, name="recurrencefrequency")
sa.Enum(OccurrenceKind, name="occurrencekind")
batch_op.alter_column("recurrence_interval", server_default=None)
batch_op.alter_column("occurrence_kind", server_default=None)
```

- [x] **Step 5: Re-run targeted tests and commit**

Run: `.venv/bin/python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py backend/tests/domain/test_meeting_lifecycle.py backend/tests/migrations/test_fresh_baseline.py backend/tests/plugins/test_jobs.py`

Expected: PASS.

```bash
git add backend/app/agendas/service.py backend/app/meetings/service.py backend/app/outcomes/service.py backend/migrations/versions/0007_series_recurrence_and_agenda_outcomes.py backend/tests/domain/test_agendas.py backend/tests/domain/test_outcomes.py backend/tests/domain/test_meeting_lifecycle.py backend/tests/migrations/test_fresh_baseline.py backend/tests/plugins/test_jobs.py
git commit -m "fix: preserve agenda outcome persistence contracts"
```

### Task 6: State public plugin fields and perform full verification

**Files:**

- Modify: `backend/app/plugins/README.md:9`
- Modify: `docs/superpowers/specs/2026-07-30-agenda-auto-advance-design.md:14`
- Modify: `docs/superpowers/plans/2026-07-30-series-meeting-workflow.md:3-4`
- Modify: `docs/superpowers/plans/2026-07-31-pr2-review-fixes.md`

- [x] **Step 1: Correct the contract records**

List `agenda_outcome_tags`, `estimated_minutes`, `actual_duration_seconds`, `source_agenda_item_id`, `source_tag_key`, and `is_derived` in plugin context documentation. Correct the older design record to acknowledge the persisted duration migration, and remove the blank line between its predecessor plan's two blockquote lines.

- [x] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q backend/tests/test_release_workflow.py
git diff --check
```

Expected: each command exits `0`; only the existing frontend chunk-size advisory may remain.

- [x] **Step 3: Record results, mark completed task checkboxes, and commit**

```bash
git add backend/app/plugins/README.md docs/superpowers/specs/2026-07-30-agenda-auto-advance-design.md docs/superpowers/plans/2026-07-30-series-meeting-workflow.md docs/superpowers/plans/2026-07-31-pr2-review-fixes.md
git commit -m "docs: record review fix verification"
```

## Plan self-review

- **Spec coverage:** Tasks 1–5 map one-to-one to each in-scope section of `2026-07-31-pr2-review-fixes-design.md`; Task 6 covers documentation and release verification.
- **Deferred scope:** return annotations, status-label extraction, `SeriesStatus` narrowing, reactive route synchronization, and generic helper extraction remain out of scope.
- **TDD integrity:** Every runtime task begins with a named failing regression and requires an observed RED run before implementation.

## Execution record (2026-07-31)

- Task 1 focused test: `npm --prefix frontend test -- agenda-workbench.test.ts` — 17 passed.
- Task 2 focused tests: `npm --prefix frontend test -- meetings-view.test.ts project-create-panel.test.ts` — 6 passed.
- Tasks 3–4 focused test: `python -m pytest -q backend/tests/domain/test_meeting_series.py` — 19 passed.
- Task 5 focused regressions passed for derived-outcome ownership, lifecycle duration, fresh migration schema parity, and plugin meeting context.
- Full verification (the local checkout has no `.venv`, so `python` is the active test interpreter):
  - `python -m pytest -q` — 149 passed in 149.71s.
  - `npm --prefix frontend test` — 22 files and 95 tests passed.
  - `npm --prefix frontend run build` — passed; Vite reports only its existing chunk-size advisory.
  - `python -m pytest -q backend/tests/test_release_workflow.py` — 1 passed.
  - `git diff --check` — passed.
