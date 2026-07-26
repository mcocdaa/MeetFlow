# Plugin-owned Editor AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let trusted plugins add AI controls directly to Meeting, Project, and Action editors while the core owns only generic plugin-job infrastructure.

**Architecture:** FastAPI validates and exposes a trusted plugin ESM entry from a constrained directory. Vue loads that entry into a small registry and renders generic editor slots. The plugin owns controls, polling, local errors, and conversion of results into editor changes. Editor values stay local until a human uses the ordinary save or publish control.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Vue 3, TypeScript, Vite, Vitest, pytest, Milkdown/ProseMirror, Docker Compose.

---

## Boundaries and parallel execution

| Module | Files | Owner boundary |
| --- | --- | --- |
| Backend extension contract | `backend/app/plugins/{contracts,manager,router,jobs}.py` | Manifest entry, constrained asset serving, terminal dismissal |
| Core Vue extension host | `frontend/src/plugins/*`, `PluginEditorSlot.vue`, `PluginTaskExtension.vue` | Registry, loader, generic busy and task UI |
| AI Work Assistant | `plugins/ai-work-assistant/*` | Prompts, controls, polling, temporary action drafts |
| Business-surface wiring | meeting/project/outcome Vue components | Slots, persistence remains human-driven |

Create `feature/plugin-owned-editor-ai` in `.worktrees/plugin-owned-editor-ai`. The first two modules may be implemented in parallel worktrees because they change disjoint files. The AI plugin waits for the registry API commit; the business surfaces wait for the generic slot API commit. Do one final integration review and one verification pass only.

### Task 1: Isolate the feature and establish a clean baseline

**Files:** No source changes.

- [ ] Check the root checkout, `git worktree list`, and `git check-ignore -q .worktrees`. Preserve the unrelated root `.env.example` edit.
- [ ] Create the worktree with `git worktree add /home/mcocdaa/AI_CODE/MeetFlow/.worktrees/plugin-owned-editor-ai -b feature/plugin-owned-editor-ai main`.
- [ ] Run `cd backend && pytest -q`, then `cd ../frontend && npm test -- --run && npm run build`. Stop for direction if this baseline fails.

### Task 2: Add the backend module endpoint and terminal dismissal semantics

**Files:**

- Modify: `backend/app/plugins/contracts.py`
- Modify: `backend/app/plugins/manager.py`
- Modify: `backend/app/plugins/router.py`
- Modify: `backend/app/plugins/jobs.py`
- Modify: `backend/tests/plugins/test_discovery.py`
- Modify: `backend/tests/plugins/test_jobs.py`

- [ ] **Write failing tests first.** Add `test_enabled_plugin_frontend_module_is_listed_and_served`: its enabled descriptor has `frontend_entry: frontend/entry.js`; `GET /api/plugins/frontend-modules` returns exactly `{"items": [{"plugin_id": "test-ai", "entry_url": "/api/plugins/test-ai/frontend/entry.js"}]}` and the entry response is the expected JavaScript. Add a path-escape assertion: `/api/plugins/test-ai/frontend/../plugin.yaml` is 404. Parametrize dismissal over `succeeded`, `failed`, `interrupted`, and `canceled`; every un-applied terminal job returns 200. Retain the existing queued-job 409 test.
- [ ] **Run red:** `cd backend && pytest -q tests/plugins/test_discovery.py tests/plugins/test_jobs.py`; expected new endpoint/dismiss tests fail.
- [ ] **Implement the small contract.** Add `frontend_entry: str | None = Field(default=None, max_length=240)` to `PluginManifest`. `PluginManager.frontend_modules()` returns only loaded, enabled descriptors with a real entry below `<plugin>/frontend/`. `PluginManager.frontend_asset(plugin_id, asset_path)` resolves under that same directory and returns no file for an escape, missing item, disabled plugin, or non-file.
- [ ] **Implement routes.** Add authenticated `GET /api/plugins/frontend-modules` and `GET /api/plugins/{plugin_id}/frontend/{asset_path:path}`. Use `FileResponse` only for a manager-approved file; otherwise use the standard 404 envelope. Change `PluginJobService.dismiss` to accept only un-applied, un-dismissed `{succeeded, failed, interrupted, canceled}` jobs.
- [ ] **Verify and commit.** Run the focused tests again; stage only the six listed backend files and commit `feat: expose enabled plugin frontend modules`.

### Task 3: Create the generic Vue plugin runtime and editor host

**Files:**

- Create: `frontend/src/plugins/contracts.ts`
- Create: `frontend/src/plugins/registry.ts`
- Create: `frontend/src/plugins/runtime.ts`
- Create: `frontend/src/components/PluginEditorSlot.vue`
- Create: `frontend/src/components/PluginTaskExtension.vue`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/views/AiTasksView.vue`
- Create: `frontend/src/tests/plugin-editor-slot.test.ts`
- Modify: `frontend/src/tests/ai-tasks.test.ts`

- [ ] **Write failing tests first.** Register a fake assistant in `meeting-summary-editor`, render the host with `modelValue: '原记录'`, and expect its `插件建议` button. Let the fake emit `update:busy({ active: true, label: '正在生成建议…' })`; expect the generic overlay and `data-busy="true"`. Add a task-page test proving base `error_message` and `error_detail` remain present when no task extension exists.
- [ ] **Run red:** `cd frontend && npm test -- --run src/tests/plugin-editor-slot.test.ts src/tests/ai-tasks.test.ts`; expected missing imports.
- [ ] **Define generic types and loader.** `PluginEditorContext` contains target type, target ID and metadata. `PluginBusyState` is `{ active: boolean; label: string }`. `PluginFrontendApi` exposes only `registerEditorAssistant(slot, component)`, `registerTaskExtension(pluginId, component)`, the existing API client, and required Vue primitives. `registry.ts` owns maps and deduplicates URLs. `runtime.ts` fetches the module list, imports each approved URL using `/* @vite-ignore */`, and calls `register(api)`. A broken module logs once and cannot block the editor.
- [ ] **Implement the generic components.** `PluginEditorSlot` accepts `modelValue`, target information, a slot name and metadata. It renders the regular editor in a scoped `#editor` slot with `{ disabled }`, registered assistants, and only generic `update:modelValue`, `update:busy` and `notice` wiring. The centered progress overlay appears when busy. It contains no action ID or AI plugin ID. `PluginTaskExtension` is optional by `job.plugin_id`; `AiTasksView` renders base status and safe diagnostics before it.
- [ ] **Verify and commit.** Run the two tests and `npm run build`; stage the listed files and commit `feat: add generic plugin editor slots`.

### Task 4: Move AI Work Assistant interaction into its own frontend module

**Files:**

- Modify: `plugins/ai-work-assistant/plugin.yaml`
- Modify: `plugins/ai-work-assistant/backend.py`
- Create: `plugins/ai-work-assistant/frontend/entry.js`
- Create: `plugins/ai-work-assistant/frontend/assistant-ui.js`
- Modify: `backend/tests/plugins/test_actions.py`
- Create: `frontend/src/tests/ai-work-assistant-plugin.test.ts`

- [ ] **Write failing tests first.** Capture the model HTTP body and assert it contains both `当前编辑内容：## 用户原稿` and the server-side `资料：` snapshot. Load the plugin entry with a fake `MeetFlowPluginApi`; assert registration for `meeting-summary-editor`, `project-update-editor`, and `action-composer`. Simulate queued then succeeded job responses and assert real `result.markdown` applies once. Simulate failure and assert neither editor value nor temporary drafts change.
- [ ] **Run red:** `cd backend && pytest -q tests/plugins/test_actions.py` and `cd ../frontend && npm test -- --run src/tests/ai-work-assistant-plugin.test.ts`.
- [ ] **Implement backend input handling.** Declare `frontend_entry: frontend/entry.js`. Each action uses `{"type":"object","properties":{"current_markdown":{"type":"string","maxLength":100000}},"additionalProperties":false}`. Compose the prompt as explicit current-editor text followed by the existing authoritative context. Never add secrets, raw attachment content, or browser-only metadata.
- [ ] **Implement the standalone ESM module.** `entry.js` imports `registerAiWorkAssistant` and exports `register(api)`. `assistant-ui.js` owns the button, local job state, three-second active-only polling, compact failure notices, task extension UI, and result application. It posts `input: { current_markdown }`, locks with `update:busy`, and always unlocks in `finally`. Markdown success emits exactly one `update:modelValue(result.markdown)`, preserving Milkdown's single undo transaction. It never changes content on failure.
- [ ] **Implement temporary action drafts.** The action assistant keeps editable candidates in plugin-owned local state. Only `创建所选行动项` submits normal project action requests. It saves one pre-generation snapshot; Ctrl+Z while focus is within the generated group restores composer content and removes the whole unpersisted group. Closing the composer discards remaining candidates.
- [ ] **Verify and commit.** Run both focused test commands; stage only plugin/tests files and commit `feat: add inline AI assistant plugin UI`.

### Task 5: Attach slots to Meeting, Project, and Action editors

**Files:**

- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/components/ProjectActivityTab.vue`
- Modify: `frontend/src/components/ProjectUpdateComposer.vue`
- Modify: `frontend/src/components/OutcomeComposer.vue`
- Delete: `frontend/src/components/InlineAiDrafts.vue`
- Delete: `frontend/src/components/PluginActionPanel.vue`
- Modify: `frontend/src/tests/meeting-workspace.test.ts`
- Modify: `frontend/src/tests/project-workspace.test.ts`
- Modify: `frontend/src/tests/workflow-components.test.ts`
- Delete: `frontend/src/tests/inline-ai-drafts.test.ts`

- [ ] **Write failing surface tests.** Require `data-testid="meeting-summary-editor"` and `project-update-editor`; assert `meeting-inline-summary` no longer exists. Verify a generated meeting value changes only `draft.summary_markdown` until `saveMeeting()` runs. Verify project progress uses `MarkdownEditor`, and action mode supplies project, meeting, agenda and participant metadata. Keep decision and question flows unchanged.
- [ ] **Run red:** `cd frontend && npm test -- --run src/tests/meeting-workspace.test.ts src/tests/project-workspace.test.ts src/tests/workflow-components.test.ts`.
- [ ] **Integrate the meeting summary.** Add the persistent summary editor inside `PluginEditorSlot` named `meeting-summary-editor`, binding it to `draft.summary_markdown`; the scoped editor must use `:disabled="saving || disabled"`. `saveMeeting()` stays the only write path.
- [ ] **Integrate project and action editing.** Replace ProjectUpdateComposer's textarea with `MarkdownEditor` inside `project-update-editor` while retaining existing `submit()` persistence. In `OutcomeComposer`, render `action-composer` only for action mode. Its metadata includes project ID, meeting ID, agenda ID, and participants. No AI operation may alter unrelated form fields or scroll position.
- [ ] **Remove old core-specific UI.** Delete `InlineAiDrafts`, `PluginActionPanel`, and their obsolete tests. Verify `rg "InlineAiDrafts|PluginActionPanel|ai-work-assistant\." frontend/src` finds no core business-page reference.
- [ ] **Verify and commit.** Run `cd frontend && npm test -- --run && npm run build`, stage the listed files, and commit `feat: embed plugin AI controls in editors`.

### Task 6: One integration verification, Docker smoke test, merge, and cleanup

**Files:** Modify only a verified regression; no unrelated refactor.

- [ ] Run `cd backend && pytest -q`; then `cd ../frontend && npm test -- --run && npm run build`; then `git diff --check`.
- [ ] Run `docker compose build`, `docker compose up -d --force-recreate`, and `curl --fail http://127.0.0.1:${MEETFLOW_PORT:-8000}/api/health`. Using configured admin credentials, verify an enabled module is listed; a deliberately failed/credit-exhausted request unlocks its editor; task history shows a dismissible failed record and safe technical detail. Never print API keys.
- [ ] Perform one final integration review only: core contains no action-ID coupling; failures preserve values; one Ctrl+Z restores pre-AI Markdown; failed terminal jobs dismiss; disabling the plugin leaves all ordinary editors usable.
- [ ] From the main checkout, fast-forward merge `feature/plugin-owned-editor-ai`, remove `.worktrees/plugin-owned-editor-ai`, delete the feature branch, and verify `git worktree list`. Keep unrelated root `.env.example` changes untouched.
