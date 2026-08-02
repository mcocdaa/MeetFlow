# Agenda Notes AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI assistant to the agenda-notes editor that returns an editable draft for the selected agenda item without bypassing normal agenda saving.

**Architecture:** Add `agenda_item` as a first-class plugin-job target, resolving it server-side through its meeting and project permissions and building a bounded authoritative context with `current_agenda_item`. Register `ai-work-assistant.agenda_notes` against that target, then mount the existing `PluginEditorSlot` around `AgendaDetail`'s Markdown editor so results stay local until the user saves.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Vue 3, TypeScript, Vitest, existing first-party plugin ESM/Python.

---

## File structure

- `backend/app/plugins/context.py`: selected, bounded agenda-item context.
- `backend/app/plugins/jobs.py` and `backend/app/plugins/router.py`: agenda target authorization, job lifecycle and filtering.
- `plugins/ai-work-assistant/backend.py`: agenda-record draft action.
- `plugins/ai-work-assistant/frontend/assistant-ui.js` and `frontend/src/components/AgendaDetail.vue`: assistant registration and editor surface.
- `backend/tests/conftest.py`, `backend/tests/plugins/test_jobs.py`, `backend/tests/plugins/test_discovery.py`, `backend/tests/plugins/test_actions.py`: target, context and action tests.
- `frontend/src/tests/ai-work-assistant-plugin.test.ts`, `frontend/src/tests/agenda-workbench.test.ts`: registration, job payload and local-save behavior.
- `backend/app/plugins/README.md`, `plugins/ai-work-assistant/README.md`, `plugins/ai-work-assistant/plugin.yaml`: contract and user-facing documentation.

### Task 1: Add server-side `agenda_item` plugin-job targets

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/plugins/test_jobs.py`
- Modify: `backend/app/plugins/context.py`
- Modify: `backend/app/plugins/jobs.py`
- Modify: `backend/app/plugins/router.py`

- [ ] **Step 1: Write failing context, access, dedupe and filter tests**

Add tests that create two agenda items in one meeting and exercise the new target:

```python
context = PluginContextBuilder(session).agenda_item(first.id, actor)
assert context["current_agenda_item"]["id"] == first.id
assert context["current_agenda_item"]["title"] == "First agenda"

first_job, created = service.submit("test-ai.summarize", "agenda_item", first.id, {}, actor.id)
duplicate, duplicate_created = service.submit("test-ai.summarize", "agenda_item", first.id, {}, actor.id)
second_job, second_created = service.submit("test-ai.summarize", "agenda_item", second.id, {}, actor.id)
assert created is True and duplicate_created is False and second_created is True
assert duplicate.id == first_job.id
assert second_job.id != first_job.id
```

Also add an API test for `GET /api/plugin-jobs?target_type=agenda_item&target_id=<agenda id>` and an invited, non-project member submitting an agenda job receiving 403.

Extend the test-only `test-ai.summarize` registration in `backend/tests/conftest.py` to declare `target_types=("meeting", "agenda_item")`; this fixture change lets the test isolate core target support without changing any production action.

- [ ] **Step 2: Run the new tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/plugins/test_jobs.py -k 'agenda_plugin_context or agenda_plugin_jobs'
```

Expected: FAIL because `PluginContextBuilder` and `PluginJobService` do not support `agenda_item`.

- [ ] **Step 3: Build server-authoritative agenda context**

In `backend/app/plugins/context.py`, import `AgendaItem` and `AppError`; implement:

```python
def agenda_item(self, agenda_item_id: str, user: User) -> dict[str, Any]:
    agenda = self.session.get(AgendaItem, agenda_item_id)
    if agenda is None:
        raise AppError(404, "agenda_item_not_found", "议题不存在")
    WorkspaceAccess(self.session).require_meeting_view(agenda.meeting_id, user)
    context = MeetingService(self.session).plugin_context(agenda.meeting_id, user)
    current = next(item for item in context["agenda_items"] if item["id"] == agenda.id)
    return self._bounded({"current_agenda_item": current, **context})
```

Keep `_bounded()` as the final limiter; do not accept agenda identity or note text from browser metadata.

- [ ] **Step 4: Authorize and route agenda jobs**

In `PluginJobService.submit()`, add an `agenda_item` branch that loads `AgendaItem`, calls `WorkspaceAccess.require_meeting_view(agenda.meeting_id, actor)`, then requires contribution on that meeting's project before calling `context_builder.agenda_item(target_id, actor)`. Keep the current dedupe construction unchanged so it becomes `action_id:agenda_item:agenda_id`.

In `require_job_target_access()` in `backend/app/plugins/router.py`, mirror the meeting/project checks for stored agenda jobs. Extend `list_jobs()` to:

```python
target_type: Literal["meeting", "project", "agenda_item"] | None = None
```

All unsupported stored or submitted targets must still return/behave as `invalid_plugin_target`.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/plugins/test_jobs.py
git add backend/app/plugins/context.py backend/app/plugins/jobs.py backend/app/plugins/router.py backend/tests/conftest.py backend/tests/plugins/test_jobs.py
git commit -m "feat: support agenda plugin job targets"
```

Expected: plugin-job tests pass and the commit contains only Task 1 files.

### Task 2: Register the first-party agenda-notes draft action

**Files:**
- Modify: `backend/tests/plugins/test_actions.py`
- Modify: `backend/tests/plugins/test_discovery.py`
- Modify: `plugins/ai-work-assistant/backend.py`

- [ ] **Step 1: Write failing action and discovery tests**

Add a mocked-provider test for the new action and an action-discovery assertion:

```python
result = asyncio.run(
    ai_work_assistant_backend.agenda_notes(
        {"current_agenda_item": {"id": "a1", "title": "发布范围"}},
        {"current_markdown": "已有讨论"},
        config,
    )
)
assert result == {"markdown": "## 整理后的议题记录", "model": "test-model"}
assert "当前议题" in captured["json"]["messages"][1]["content"]
assert actions["ai-work-assistant.agenda_notes"].target_types == ("agenda_item",)
```

- [ ] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/plugins/test_actions.py backend/tests/plugins/test_discovery.py -k 'agenda_notes or declares_editor'
```

Expected: FAIL because the handler and registration do not yet exist.

- [ ] **Step 3: Implement the action with the existing bounded editor input**

Add this handler to `plugins/ai-work-assistant/backend.py`:

```python
async def agenda_notes(context, payload, config):
    return await _draft(
        "根据 current_agenda_item 及会议资料整理当前议题记录。"
        "输出完整、可编辑的 Markdown；保留资料明确支持的事实和标签，"
        "资料不足时不得编造，不要输出多个候选方案或额外说明。",
        context,
        payload,
        config,
    )
```

Register `MeetingAction` with `action_id="ai-work-assistant.agenda_notes"`, `label="AI 整理议题记录"`, `target_types=("agenda_item",)`, `input_schema=editor_input`, `output_schema=common_output`, and `handler=agenda_notes`. Do not add an `apply_handler`.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/plugins/test_actions.py backend/tests/plugins/test_discovery.py
git add plugins/ai-work-assistant/backend.py backend/tests/plugins/test_actions.py backend/tests/plugins/test_discovery.py
git commit -m "feat: add AI agenda note drafts"
```

Expected: every editor action has the bounded `current_markdown` input schema, and none can directly apply a domain write.

### Task 3: Expose the assistant on the agenda record editor

**Files:**
- Modify: `frontend/src/tests/ai-work-assistant-plugin.test.ts`
- Modify: `frontend/src/tests/agenda-workbench.test.ts`
- Modify: `plugins/ai-work-assistant/frontend/assistant-ui.js`
- Modify: `frontend/src/components/AgendaDetail.vue`

- [ ] **Step 1: Write failing registration and explicit-save tests**

Add `agenda-notes-editor` to registration expectations and verify its request payload:

```ts
expect(registered.apiMock).toHaveBeenNthCalledWith(1, '/api/plugin-jobs', {
  method: 'POST',
  body: JSON.stringify({
    action_id: 'ai-work-assistant.agenda_notes',
    target_type: 'agenda_item',
    target_id: 'target-1',
    input: { current_markdown: '原有内容' },
  }),
})
```

In `agenda-workbench.test.ts`, register a small `agenda-notes-editor` assistant that emits Markdown. After activating it, assert `议题记录` has the generated text and `apiMock` has not sent a PUT. Click `保存议题`, then assert the request to `/api/agenda-items/a1` contains the generated `notes_markdown`.

- [ ] **Step 2: Run RED**

Run:

```bash
npm --prefix frontend test -- ai-work-assistant-plugin.test.ts agenda-workbench.test.ts
```

Expected: FAIL because no agenda assistant slot is registered or rendered.

- [ ] **Step 3: Register the agenda editor assistant**

Add to `assistantDefinitions` in `plugins/ai-work-assistant/frontend/assistant-ui.js`:

```js
{
  slot: 'agenda-notes-editor',
  actionId: 'ai-work-assistant.agenda_notes',
  menuTitle: 'AI 协助议题',
  label: '整理议题记录',
  busyLabel: '正在整理议题记录…',
  targetType: 'agenda_item',
},
```

Reuse the existing generic polling/result component; it already preserves the editor on job failure.

- [ ] **Step 4: Wrap only the contributor-side `AgendaDetail` editor**

Import `PluginEditorSlot` and replace the contributor editor with:

```vue
<PluginEditorSlot v-if="canContribute" v-model="draft.notes_markdown" editor-label="议题记录" data-testid="agenda-notes-editor" target-type="agenda_item" :target-id="item.id" slot="agenda-notes-editor" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, agendaId: item.id }" @notice="error = $event">
  <template #editor="{ disabled, registerEditor }">
    <MarkdownEditor ref="notesEditor" v-model="draft.notes_markdown" label="议题记录" placeholder="记录讨论上下文、材料和过程…" :disabled="saving || disabled" :register-editor="registerEditor" />
  </template>
</PluginEditorSlot>
<MarkdownEditor v-else ref="notesEditor" v-model="draft.notes_markdown" label="议题记录" placeholder="记录讨论上下文、材料和过程…" :disabled="true" />
```

Do not change `persistIfDirty()`, dirty/version logic, or the normal “保存议题” handler.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
npm --prefix frontend test -- ai-work-assistant-plugin.test.ts agenda-workbench.test.ts plugin-editor-slot.test.ts
git add plugins/ai-work-assistant/frontend/assistant-ui.js frontend/src/components/AgendaDetail.vue frontend/src/tests/ai-work-assistant-plugin.test.ts frontend/src/tests/agenda-workbench.test.ts
git commit -m "feat: expose AI assistance for agenda notes"
```

Expected: the generated record is local until the user explicitly saves it.

### Task 4: Document and verify the complete feature

**Files:**
- Modify: `backend/app/plugins/README.md`
- Modify: `plugins/ai-work-assistant/README.md`
- Modify: `plugins/ai-work-assistant/plugin.yaml`

- [ ] **Step 1: Update plugin documentation**

Document that `agenda_item` jobs are selected server-side from their owning meeting, require contribution permission, and return drafts only. In the AI plugin guide, say “整理议题记录” returns text to the selected editor and only “保存议题” persists it. Update the manifest description to include `议题记录`.

- [ ] **Step 2: Check documentation diff**

Run:

```bash
git diff --check
```

Expected: exit 0 without whitespace errors.

- [ ] **Step 3: Run required full verification**

Run:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m pytest -q backend/tests/test_release_workflow.py
```

Expected: every command exits 0; record actual totals in the handoff.

- [ ] **Step 4: Build and smoke-test the container**

Run from the implementation worktree:

```bash
MEETFLOW_IMAGE=meetflow:agenda-notes-ai docker compose build
MEETFLOW_IMAGE=meetflow:agenda-notes-ai docker compose up -d --force-recreate
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
curl --fail --silent --show-error http://127.0.0.1:8000/api/health/ready
```

Expected: the image starts healthy; health returns `{"status":"ok"}` and readiness reports database, plugins, and worker as ready. Do not use a real provider API key.

- [ ] **Step 5: Commit documentation and inspect the branch**

Run:

```bash
git add backend/app/plugins/README.md plugins/ai-work-assistant/README.md plugins/ai-work-assistant/plugin.yaml
git commit -m "docs: describe AI agenda note drafts"
git status --short --branch
git log --oneline origin/main..HEAD
```

Expected: a clean feature branch with only the focused commits above.
