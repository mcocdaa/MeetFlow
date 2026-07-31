# Plugin Event Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Allow an administrator to requeue one failed plugin outbox event without changing its idempotency identity or executing plugin code inside the HTTP request.

**Architecture:** Add a small `retry_plugin_event` command beside the existing event-recording helper. The admin router calls this command and returns the existing redacted event shape; the worker remains the only component that invokes subscribers. The Vue admin page adds one per-event retry action and reloads the diagnostic list after a successful reset.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, pytest, Vue 3, TypeScript, Vitest, Testing Library.

---

### Task 1: Define the failing backend retry command tests

**Files:**
- Modify: `backend/tests/plugins/test_plugin_events.py`
- Reference: `backend/app/plugins/events.py`
- Reference: `backend/app/plugins/models.py`

- [ ] **Step 1: Add a database fixture helper for an event in each relevant state**

Extend the existing event test module with a small helper that inserts a `PluginEvent` using the existing `plugin_client.app.state.database`, preserving a stable payload such as `{"meeting_id": "m1"}`. Use `utcnow()` for timestamps and set `claimed_at`, `finished_at`, and `last_error` explicitly on the failed fixture so the reset assertions prove those fields change.

- [ ] **Step 2: Write the failed-event reset test**

Add a test with the following assertions against `retry_plugin_event`:

```python
with database.session() as session:
    event = add_failed_event(session, event_id="evt-retry")
    session.commit()
    retried = retry_plugin_event(session, "evt-retry")
    assert retried.event_id == "evt-retry"
    assert retried.payload_json == {"meeting_id": "m1"}
    assert retried.status == PluginEventStatus.queued
    assert retried.attempts == 0
    assert retried.claimed_at is None
    assert retried.finished_at is None
    assert retried.last_error is None
    assert retried.next_attempt_at is not None
```

- [ ] **Step 3: Add invalid-state and missing-event tests**

Verify that a missing ID raises `KeyError`, and that events in `queued`, `processing`, or `succeeded` state raise `ValueError` with a message indicating only failed events can be retried. Assert that the non-failed rows remain unchanged after each rejected call.

- [ ] **Step 4: Run the new tests before implementation**

Run:

```bash
PYTHONPATH=backend:. python -m pytest -q backend/tests/plugins/test_plugin_events.py
```

Expected: FAIL because `retry_plugin_event` does not exist yet.

### Task 2: Implement the backend retry command

**Files:**
- Modify: `backend/app/plugins/events.py`
- Test: `backend/tests/plugins/test_plugin_events.py`

- [ ] **Step 1: Implement the minimal command next to `record_plugin_event`**

Add:

```python
def retry_plugin_event(session: Session, event_id: str) -> PluginEvent:
    event = session.get(PluginEvent, event_id)
    if event is None:
        raise KeyError(event_id)
    if event.status != PluginEventStatus.failed:
        raise ValueError("only failed plugin events can be retried")
    event.status = PluginEventStatus.queued
    event.attempts = 0
    event.next_attempt_at = utcnow()
    event.claimed_at = None
    event.finished_at = None
    event.last_error = None
    session.commit()
    session.refresh(event)
    return event
```

The function must not accept a payload or arbitrary status, and must not generate a new event ID. The caller owns authorization; this function only enforces event-state invariants.

- [ ] **Step 2: Run the event tests and worker regression**

Run:

```bash
PYTHONPATH=backend:. python -m pytest -q backend/tests/plugins/test_plugin_events.py backend/tests/plugins/test_event_worker.py
```

Expected: all tests pass, including existing idempotence, redaction, retry, and recovery behavior.

- [ ] **Step 3: Commit the domain command**

```bash
git add backend/app/plugins/events.py backend/tests/plugins/test_plugin_events.py
git commit -m "feat: add plugin event retry command"
```

### Task 3: Add the administrator retry endpoint

**Files:**
- Modify: `backend/app/plugins/router.py`
- Test: `backend/tests/plugins/test_plugin_events.py` or the existing admin plugin API test module discovered with `rg "admin/plugins/events" backend/tests`

- [ ] **Step 1: Add the route beside `GET /api/admin/plugins/events`**

Import `retry_plugin_event` and add:

```python
@admin_router.post("/events/{event_id}/retry")
def retry_plugin_event_endpoint(
    event_id: str,
    _admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        event = retry_plugin_event(session, event_id)
    except KeyError as exc:
        raise AppError(404, "plugin_event_not_found", "插件事件不存在") from exc
    except ValueError as exc:
        raise AppError(409, "plugin_event_not_retryable", "只有失败事件可以重试") from exc
    return serialize_event(event)
```

Name the route function `retry_plugin_event_endpoint` so it does not shadow the imported domain command. Keep the response based on `serialize_event`; never include `payload_json`.

- [ ] **Step 2: Add route-level contract tests where the repository fixture allows TestClient**

Cover:

```text
POST failed event → 200, status queued, attempts 0
POST missing event → 404, plugin_event_not_found
POST queued event → 409, plugin_event_not_retryable
```

If the existing authenticated TestClient fixture hangs in this environment, retain the pure command tests and run `compileall`; record the integration-test limitation rather than claiming it passed.

- [ ] **Step 3: Run backend route/domain checks**

Run:

```bash
PYTHONPATH=backend:. python -m pytest -q backend/tests/plugins/test_plugin_events.py backend/tests/plugins/test_event_worker.py
python -m compileall -q backend/app backend/tests
```

- [ ] **Step 4: Commit the endpoint**

```bash
git add backend/app/plugins/router.py backend/tests/plugins
git commit -m "feat: add admin plugin event retry endpoint"
```

### Task 4: Add the frontend retry interaction

**Files:**
- Modify: `frontend/src/views/AdminPluginsView.vue`
- Modify: `frontend/src/tests/admin-plugins.test.ts`

- [ ] **Step 1: Extend the event type and add retry state**

Keep the existing event shape and add:

```ts
const retryingEvent = ref('')

async function retryEvent(eventId: string) {
  retryingEvent.value = eventId
  error.value = ''
  try {
    await api(`/api/admin/plugins/events/${encodeURIComponent(eventId)}/retry`, { method: 'POST' })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '插件事件重试失败'
  } finally {
    retryingEvent.value = ''
  }
}
```

The action must encode the event ID and must not expose payload data. The existing `load()` path remains the single refresh path.

- [ ] **Step 2: Add the button to each failed event row**

Render a button inside the existing failed-event loop:

```vue
<button
  type="button"
  class="button button-small"
  :disabled="retryingEvent !== ''"
  @click="retryEvent(event.event_id)"
>
  {{ retryingEvent === event.event_id ? '重试中…' : '重试' }}
</button>
```

Keep the error text visible if the request fails. On success, the refreshed failed list removes a now-queued/succeeded event.

- [ ] **Step 3: Add frontend tests before implementation changes are considered complete**

Add tests that mock the initial plugin list, failed-event list, retry POST, and refreshed empty list. Assert the endpoint and method, the temporary `重试中…` label while the POST promise is pending, and that the event disappears after refresh. Add a rejected POST case and assert the original event plus the error message remain visible.

- [ ] **Step 4: Run the focused frontend test**

Run:

```bash
npm --prefix frontend test -- --run src/tests/admin-plugins.test.ts
```

Expected: all admin plugin tests pass with no Vue unhandled errors.

- [ ] **Step 5: Commit the frontend interaction**

```bash
git add frontend/src/views/AdminPluginsView.vue frontend/src/tests/admin-plugins.test.ts
git commit -m "feat: add plugin event retry control"
```

### Task 5: Full verification and handoff

**Files:**
- Verify: `docs/superpowers/specs/2026-07-31-plugin-event-retry-design.md`
- Verify: `git status`, recent branch log

- [ ] **Step 1: Run the complete frontend suite and production build**

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: all frontend tests pass and Vite builds successfully. Preserve the existing large-chunk warning as a separate future optimization unless this change unexpectedly alters it.

- [ ] **Step 2: Run backend plugin and migration regressions**

```bash
PYTHONPATH=backend:. python -m pytest -q \
  backend/tests/plugins/test_plugin_events.py \
  backend/tests/plugins/test_event_worker.py \
  backend/tests/plugins/test_exporters.py \
  backend/tests/migrations/test_fresh_baseline.py \
  backend/tests/migrations/test_wheel_resources.py \
  backend/tests/plugins/test_worker.py
python -m compileall -q backend/app backend/tests plugins/meeting-export/backend.py
git diff --check
```

Expected: the focused backend suite passes; compileall and whitespace checks pass. Do not claim the full backend integration suite if the known TestClient hang recurs.

- [ ] **Step 3: Confirm branch and clean worktree**

```bash
git branch --show-current
git status --short --branch
git log --oneline -5
```

Expected: branch is `feature/plugin-operability`, worktree is clean, and all new commits are on that branch rather than `main`.

- [ ] **Step 4: Report evidence and remaining follow-ups**

Report the commit IDs, exact test counts/commands, any integration-test limitation, and the next independent optimization candidates: event retry audit history, exporter capability discovery, and frontend chunk splitting. Keep CLI work deferred to its own package.
