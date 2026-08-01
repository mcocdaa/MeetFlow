# PR #3 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the valid security, reliability, UI-state, and documentation findings from PR #3 without expanding the plugin contract.

**Architecture:** Keep plugin event payloads and export filenames validated at the core boundary. Make each plugin’s registrations transactional in memory, bound event-handler execution by the existing application setting, and make HomeView apply only the newest optional-resource request. The database-readiness comment is intentionally excluded because production supports SQLite only and its connection uses a finite SQLite busy timeout.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, Vue 3, TypeScript, Vitest.

---

### Task 1: Harden persisted plugin-event and export inputs

**Files:**
- Modify: `backend/app/plugins/events.py:14-81`
- Modify: `backend/app/plugins/exporters.py:19-27`
- Modify: `backend/tests/plugins/test_plugin_events.py:106-132`
- Modify: `backend/tests/plugins/test_exporters.py:25-40`

- [x] **Step 1: Write failing payload and filename regression tests**

```python
@pytest.mark.parametrize("key", ["access_token", "secret_key", "private_key"])
def test_record_event_rejects_compound_sensitive_payload_keys(plugin_client, key):
    with plugin_client.app.state.database.session() as session:
        with pytest.raises(ValueError, match="sensitive"):
            record_plugin_event(session, event_type="test.event", target_type="meeting", target_id="m1", payload={key: "value"})

@pytest.mark.parametrize("filename", [r"..\\secret.txt", "meeting\\draft.md", "meeting\n.md", "meeting\x00.md"])
def test_validate_export_rejects_cross_platform_or_control_filename(filename):
    with pytest.raises(ValueError):
        validate_export(PluginExport(media_type="text/plain", filename=filename, content=b"x"))
```

- [x] **Step 2: Run the two tests and verify they fail because the current validators accept the values**

Run: `PYTHONPATH=backend python -m pytest -q backend/tests/plugins/test_plugin_events.py backend/tests/plugins/test_exporters.py`

- [x] **Step 3: Add minimal boundary checks**

```python
if any(normalized == term or normalized.startswith(f"{term}_") or normalized.endswith(f"_{term}") for term in _SENSITIVE_KEYS):
    raise ValueError("event payload contains sensitive data")

if "\\" in result.filename or any(ord(char) < 32 or ord(char) == 127 for char in result.filename):
    raise ValueError("export filename must be a single safe path segment")
```

- [x] **Step 4: Re-run the focused backend tests and commit**

Run: `PYTHONPATH=backend python -m pytest -q backend/tests/plugins/test_plugin_events.py backend/tests/plugins/test_exporters.py`

Commit: `git add backend/app/plugins/events.py backend/app/plugins/exporters.py backend/tests/plugins/test_plugin_events.py backend/tests/plugins/test_exporters.py && git commit -m "fix: harden plugin event and export validation"`

### Task 2: Publish plugin registrations atomically and enforce runtime limits

**Files:**
- Modify: `backend/app/plugins/manager.py:1-20,248-294,430-440`
- Modify: `backend/tests/plugins/test_manifest_v2.py`

- [x] **Step 1: Write failing manager and worker tests**

```python
def test_v2_plugin_with_undeclared_action_is_not_loaded(plugin_factory, settings):
    plugin_factory("undeclared-action", manifest={"id": "undeclared-action", "name": "Undeclared", "version": "0.1.0", "api_version": 2, "backend_entry": "backend.py", "capabilities": {"actions": []}}, backend="from app.plugins.contracts import MeetingAction\\nasync def handler(context, payload, config): return {}\\ndef register(registry): registry.register_meeting_action(MeetingAction(action_id='undeclared-action.run', label='Run', description='', admin_only=False, input_schema={'type': 'object'}, output_schema={'type': 'object'}, handler=handler))", enabled=True)
    app = create_app(settings)
    with TestClient(app):
        assert app.state.plugin_manager.loaded_actions() == []
        assert any(error.plugin_id == "undeclared-action" for error in app.state.plugin_manager.errors())

def test_failed_plugin_registration_does_not_leave_event_handler(plugin_factory, settings):
    plugin_factory("atomic", manifest={"id": "atomic", "name": "Atomic", "version": "0.1.0", "api_version": 2, "backend_entry": "backend.py", "capabilities": {"event_subscriptions": ["meeting.completed"], "exporters": []}}, backend="async def subscriber(payload, config): pass\\nasync def exporter(context, config): pass\\ndef register(registry):\\n    registry.register_event_subscriber('meeting.completed', subscriber)\\n    registry.register_exporter('atomic.export', exporter)", enabled=True)
    app = create_app(settings)
    with TestClient(app):
        assert app.state.plugin_manager.event_subscribers("meeting.completed") == []

def test_event_handler_obeys_configured_timeout(plugin_factory, settings):
    settings.plugin_timeout_seconds = 0.001
    plugin_factory("slow", manifest={"id": "slow", "name": "Slow", "version": "0.1.0", "api_version": 2, "backend_entry": "backend.py", "capabilities": {"event_subscriptions": ["meeting.completed"]}}, backend="import asyncio\\nasync def subscriber(payload, config): await asyncio.sleep(0.01)\\ndef register(registry): registry.register_event_subscriber('meeting.completed', subscriber)", enabled=True)
    app = create_app(settings)
    with TestClient(app):
        with app.state.database.session() as session:
            with pytest.raises(TimeoutError):
                asyncio.run(app.state.plugin_manager.invoke_event("meeting.completed", {}, session))
```

- [x] **Step 2: Run the focused tests and verify the three behaviors fail**

Run: `PYTHONPATH=backend python -m pytest -q backend/tests/plugins/test_manifest_v2.py backend/tests/plugins/test_event_worker.py`

- [x] **Step 3: Stage then publish all registrations, validate v2 actions, and apply the configured timeout**

```python
staged_actions = list(registry.actions.items())
staged_subscribers = list(registry.event_subscribers.items())
staged_exporters = list(registry.exporters.items())
# Validate every staged identifier against the v2 manifest and every global
# duplicate before mutating self._actions, self._event_subscribers, or self._exporters.
# Then publish each staged collection.

await asyncio.wait_for(handler(payload, config), timeout=self.plugin_timeout_seconds)
```

The manager constructor receives `Settings.plugin_timeout_seconds` from application setup; no per-plugin timeout is added.

- [x] **Step 4: Re-run focused tests and commit**

Run: `PYTHONPATH=backend python -m pytest -q backend/tests/plugins/test_manifest_v2.py backend/tests/plugins/test_event_worker.py backend/tests/plugins/test_discovery.py`

Commit: `git add backend/app/plugins/manager.py backend/app/main.py backend/tests/plugins/test_manifest_v2.py backend/tests/plugins/test_event_worker.py && git commit -m "fix: make plugin registrations and events resilient"`

### Task 3: Preserve the latest front-end plugin state

**Files:**
- Modify: `frontend/src/views/AdminPluginsView.vue:44-59`
- Modify: `frontend/src/views/HomeView.vue:32-109`
- Modify: `frontend/src/tests/admin-plugins.test.ts`
- Modify: `frontend/src/tests/home-attention.test.ts`

- [x] **Step 1: Write failing UI regressions**

```ts
it('keeps primary failed events visible if the diagnostics refresh fails', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [], errors: [], events: [failedEvent] }).mockRejectedValueOnce(new Error('unavailable'))
  render(AdminPluginsView)
  expect(await screen.findByText(/meeting\.completed/)).toBeInTheDocument()
})

it('ignores a superseded optional work-brief response', async () => {
  let resolveFirst!: (value: { content_markdown: string; generated_at: null }) => void
  const first = new Promise<{ content_markdown: string; generated_at: null }>((resolve) => { resolveFirst = resolve })
  let workBriefCalls = 0
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/attention') return Promise.resolve({ items: [], unread_count: 0, truncated: false })
    if (path === '/api/plugins/actions') return Promise.resolve([{ action_id: 'ai-work-assistant.user_work_brief' }])
    if (path === '/api/work-brief') return ++workBriefCalls === 1 ? first : Promise.resolve({ content_markdown: 'new brief', generated_at: null })
    return Promise.resolve([])
  })
  render(HomeView, { global: { stubs: { RouterLink } } })
  await waitFor(() => expect(workBriefCalls).toBe(1))
  await fireEvent.click(screen.getByRole('button', { name: '刷新' }))
  expect(await screen.findByText('new brief')).toBeInTheDocument()
  resolveFirst({ content_markdown: 'old brief', generated_at: null })
  await waitFor(() => expect(screen.queryByText('old brief')).not.toBeInTheDocument())
})
```

- [x] **Step 2: Run the two frontend tests and verify they fail**

Run: `npm --prefix frontend test -- --run src/tests/admin-plugins.test.ts src/tests/home-attention.test.ts`

- [x] **Step 3: Keep the primary diagnostics fallback and guard optional response writes by revision**

```ts
const optionalLoadRevision = ref(0)
const revision = ++optionalLoadRevision.value
if (revision === optionalLoadRevision.value) workBrief.value = brief
```

Increment the revision before a generate request as well, and only clear `workBriefRunning` when its controller remains current.

- [x] **Step 4: Re-run focused tests and commit**

Run: `npm --prefix frontend test -- --run src/tests/admin-plugins.test.ts src/tests/home-attention.test.ts`

Commit: `git add frontend/src/views/AdminPluginsView.vue frontend/src/views/HomeView.vue frontend/src/tests/admin-plugins.test.ts frontend/src/tests/home-attention.test.ts && git commit -m "fix: preserve current plugin diagnostics and work brief"`

### Task 4: Correct lifecycle documentation and complete integration verification

**Files:**
- Modify: `docs/development.md:12`
- Modify: `docs/superpowers/plans/2026-08-01-pr3-review-fixes.md`

- [x] **Step 1: Restrict the lifecycle description to the implemented `start` and `finish` command path**

```markdown
- `MeetingLifecycleCommands` currently owns the `start` and `finish` transitions through `UnitOfWork`; the remaining lifecycle transitions continue through `MeetingService._commit_meeting_command`.
```

- [ ] **Step 2: Run complete repository checks**

Run: `.venv/bin/python -m pytest -q`

Run: `npm --prefix frontend test`

Run: `npm --prefix frontend run build`

Run: `git diff --check`

- [ ] **Step 3: Commit the documentation and push the current PR branch**

Commit: `git add docs/development.md docs/superpowers/plans/2026-08-01-pr3-review-fixes.md && git commit -m "docs: clarify lifecycle command scope"`

Push: `git push origin feature/plugin-operability`
