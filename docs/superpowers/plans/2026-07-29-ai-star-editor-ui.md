# AI Star Editor UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every plugin-backed editor a contextual AI Star menu that retracts when a task starts and a consistent, restrained construction-state overlay while AI work is in progress.

**Architecture:** `PluginEditorSlot` remains the generic owner of Star state, editor locking, menu visibility, accessibility, and the busy overlay. The AI Work Assistant plugin retains its job submission and polling logic, but provides menu-specific title and action markup for each registered editor slot. This keeps the core independent of AI action IDs while giving the existing AI plugin a polished contextual menu.

**Tech Stack:** Vue 3 Composition API, Vue scoped CSS, plugin ESM frontend module, Vitest, Vue Testing Library, TypeScript, Vite.

---

## File structure and ownership

| File | Responsibility |
| --- | --- |
| `frontend/src/components/PluginEditorSlot.vue` | Generic Star state, safe menu retraction while a plugin request is still mounted, editor lock, accessible construction overlay, and all shared AI editor styling. |
| `plugins/ai-work-assistant/frontend/assistant-ui.js` | Slot-specific menu heading and action labels, plus the existing task submission, polling, error, and result-write behavior. |
| `frontend/src/tests/plugin-editor-slot.test.ts` | Generic host interaction test: opening Star, immediate retraction, editor disabling, accessible busy state, and overlay structure. |
| `frontend/src/tests/ai-work-assistant-plugin.test.ts` | Plugin menu labels/classes for every registered slot, plus the existing job-polling and success/failure behavior. |

The root checkout currently has unrelated active changes, including `frontend/src/styles.css` and plugin/backend files. Do not stage, modify, discard, or include them in this feature. At execution time, create an isolated worktree from the current `main` commit before editing these four files.

### Task 1: Establish an isolated baseline and add the host behavior test

**Files:**

- Modify: `frontend/src/tests/plugin-editor-slot.test.ts:1-125`
- Modify later in this task: `frontend/src/components/PluginEditorSlot.vue:1-96`

- [ ] **Step 1: Create the isolated feature worktree and capture the baseline.**

  Run from the repository root:

  ```bash
  git status --short
  git worktree add .worktrees/ai-star-editor-ui -b feature/ai-star-editor-ui main
  cd .worktrees/ai-star-editor-ui/frontend
  ln -s ../../../frontend/node_modules node_modules
  npm test -- --run src/tests/plugin-editor-slot.test.ts src/tests/ai-work-assistant-plugin.test.ts
  npm run build
  ```

  Expected: the focused tests and build pass before the new assertions exist. The root status captured by the first command is a record of concurrent work; leave every root change untouched and make all feature edits only inside `.worktrees/ai-star-editor-ui`.

- [ ] **Step 2: Write the failing generic-host test.**

  In `frontend/src/tests/plugin-editor-slot.test.ts`, import `h` from Vue. In the first test, replace the string editor slot with a render function so its disabled state is observable:

  ```ts
  slots: {
    editor: ({ disabled }: { disabled: boolean }) => h('textarea', {
      'aria-label': '编辑器',
      disabled,
    }),
  },
  ```

  Rename that test to `retracts the AI menu into its busy Star and keeps construction feedback local`. After clicking `插件建议`, add these assertions:

  ```ts
  const host = screen.getByText('正在生成建议…').closest('.plugin-editor-slot')
  const trigger = screen.getByRole('button', { name: 'AI 工具，正在处理' })

  expect(host).toHaveAttribute('data-busy', 'true')
  expect(host).toHaveAttribute('aria-busy', 'true')
  expect(trigger).toBeDisabled()
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  expect(trigger).toHaveClass('is-active')
  expect(screen.getByRole('status')).toHaveTextContent('正在生成建议…')
  expect(screen.getByLabelText('编辑器')).toBeDisabled()
  expect(host?.querySelector('.editor-assistant-menu')).toHaveStyle({ display: 'none' })
  expect(host?.querySelector('.plugin-editor-busy-rail')).not.toBeNull()
  expect(host?.querySelector('.plugin-editor-busy-card')).toBeNull()
  ```

  Keep the existing checks that the menu is absent before Star is opened and Escape closes an idle menu. Remove the stale `.plugin-editor-assistants` assertion because that class is not part of the current host.

- [ ] **Step 3: Run the focused test and verify it is red.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui/frontend
  npm test -- --run src/tests/plugin-editor-slot.test.ts
  ```

  Expected: FAIL because the trigger still has the label `AI 工具`, `updateBusy` leaves the menu open, the slot has no `aria-busy`, and the existing centered overlay has no construction rail.

- [ ] **Step 4: Implement safe menu retraction and the generic construction overlay.**

  In `frontend/src/components/PluginEditorSlot.vue`, make `updateBusy` close the visible menu before setting the new state:

  ```ts
  function updateBusy(state: PluginBusyState) {
    if (state.active) menuOpen.value = false
    busy.value = state
  }
  ```

  Keep the assistant component mounted during an active request so the async plugin component can emit its final `update:busy(false)` event. Replace the current menu and overlay section with this structure:

  ```vue
  <section
    class="plugin-editor-slot"
    :data-busy="busy.active || undefined"
    :aria-busy="busy.active ? 'true' : undefined"
    @keydown.esc="menuOpen = false"
  >
    <div v-if="assistants.length" class="plugin-editor-chrome">
      <span class="plugin-editor-label">{{ editorLabel }}</span>
      <div class="plugin-editor-menu">
        <button
          type="button"
          class="editor-assistant-trigger"
          :class="{ 'is-active': menuOpen || busy.active }"
          :aria-label="busy.active ? 'AI 工具，正在处理' : 'AI 工具'"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :disabled="busy.active"
          @click="menuOpen = !menuOpen"
        >✦</button>
        <div
          v-if="menuOpen || busy.active"
          v-show="menuOpen"
          class="editor-assistant-menu"
          role="menu"
          aria-label="AI 操作"
          :aria-hidden="!menuOpen"
        >
          <component
            :is="assistant"
            v-for="(assistant, index) in assistants"
            :key="index"
            :model-value="modelValue"
            :context="context"
            :disabled="busy.active"
            @update:model-value="writeAssistantResult"
            @update:busy="updateBusy"
            @notice="emit('notice', $event)"
          />
        </div>
      </div>
    </div>
    <slot name="editor" :disabled="busy.active" :register-editor="registerEditor" />
    <div v-if="busy.active" class="plugin-editor-busy" role="status" aria-live="polite">
      <div class="plugin-editor-busy-stripes" aria-hidden="true"></div>
      <div class="plugin-editor-busy-activity">
        <span class="plugin-editor-busy-rail" aria-hidden="true"></span>
        <p>{{ busy.label }}</p>
        <span class="plugin-editor-busy-hint">请稍候</span>
      </div>
    </div>
  </section>
  ```

  Replace the current compact chrome CSS with the following behavior, using the existing global `--green`, `--green-dark`, `--green-soft`, `--ink`, `--muted`, `--line`, and `--paper` tokens:

  ```css
  .plugin-editor-slot { position: relative; }
  .plugin-editor-chrome { align-items: center; display: flex; height: 34px; justify-content: space-between; padding: 0 .4rem 0 .65rem; border: 1px solid var(--line); border-bottom: 0; border-radius: 8px 8px 0 0; background: var(--paper); }
  .plugin-editor-label { overflow: hidden; color: var(--muted); font-size: .76rem; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
  .plugin-editor-menu { position: relative; }
  .editor-assistant-trigger { display: inline-grid; width: 27px; height: 27px; place-items: center; padding: 0; border: 0; border-radius: 8px; color: var(--green); background: #edf7f1; cursor: pointer; font-size: 1rem; line-height: 1; transition: background .16s ease, box-shadow .16s ease, color .16s ease; }
  .editor-assistant-trigger:hover:not(:disabled), .editor-assistant-trigger:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(11, 106, 88, .16); }
  .editor-assistant-trigger.is-active { color: white; background: var(--green); box-shadow: 0 4px 10px rgba(11, 106, 88, .22); }
  .editor-assistant-trigger:disabled { cursor: wait; opacity: 1; }
  .editor-assistant-menu { position: absolute; z-index: 3; top: calc(100% + .35rem); right: 0; width: min(15.25rem, calc(100vw - 2rem)); padding: .5rem; border: 1px solid #cfded5; border-radius: 11px; background: var(--paper); box-shadow: 0 14px 32px rgba(18, 55, 36, .16); }
  .plugin-editor-busy { position: absolute; z-index: 2; inset: 34px 0 0; display: grid; align-items: end; overflow: hidden; background: rgba(246, 250, 247, .67); backdrop-filter: blur(2px); pointer-events: auto; }
  .plugin-editor-busy-stripes { position: absolute; inset: -60%; opacity: .56; background: repeating-linear-gradient(135deg, transparent 0 22px, rgba(11, 106, 88, .16) 22px 25px, transparent 25px 49px); animation: plugin-editor-construction-scan 2.4s linear infinite; }
  .plugin-editor-busy-activity { position: relative; display: flex; align-items: center; gap: .5rem; min-height: 38px; padding: .6rem .8rem; border-top: 1px solid rgba(11, 106, 88, .2); color: var(--green-dark); background: rgba(247, 252, 249, .56); font-size: .72rem; font-weight: 750; }
  .plugin-editor-busy-activity p { margin: 0; line-height: 1.25; }
  .plugin-editor-busy-hint { color: var(--muted); font-weight: 500; }
  .plugin-editor-busy-rail { flex: 0 0 auto; width: 19px; height: 5px; border-radius: 999px; background: repeating-linear-gradient(135deg, var(--green) 0 4px, #cfe8d9 4px 8px); background-size: 14px 14px; animation: plugin-editor-construction-rail .65s linear infinite; }
  @keyframes plugin-editor-construction-scan { to { transform: translate(49px, -49px); } }
  @keyframes plugin-editor-construction-rail { to { background-position: 14px 0; } }
  @media (prefers-reduced-motion: reduce) { .plugin-editor-busy-stripes, .plugin-editor-busy-rail { animation: none; } }
  ```

  Do not add a centered card or a separate “处理中” element. Do not move these styles into `frontend/src/styles.css`; the component owns them and that global file is currently being changed independently.

- [ ] **Step 5: Run the host test and commit the generic behavior.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui/frontend
  npm test -- --run src/tests/plugin-editor-slot.test.ts
  git diff --check
  cd ..
  git add frontend/src/components/PluginEditorSlot.vue frontend/src/tests/plugin-editor-slot.test.ts
  git commit -m "feat: refine AI editor busy state"
  ```

  Expected: the focused test passes, the diff check has no output, and the commit contains only the generic host and its test.

### Task 2: Give the AI Work Assistant a contextual, compact menu action

**Files:**

- Modify: `frontend/src/tests/ai-work-assistant-plugin.test.ts:36-139`
- Modify later in this task: `plugins/ai-work-assistant/frontend/assistant-ui.js:4-134`

- [ ] **Step 1: Write the failing menu-label test.**

  Add this test after the registration test in `frontend/src/tests/ai-work-assistant-plugin.test.ts`:

  ```ts
  it.each([
    ['meeting-summary-editor', 'AI 协助纪要', '生成会议纪要'],
    ['project-update-editor', 'AI 协助进展', '总结项目进展'],
    ['action-composer', 'AI 协助行动项', '生成行动项建议'],
    ['decision-composer', 'AI 协助决策', '生成决策建议'],
    ['question-composer', 'AI 协助问题', '梳理开放问题'],
  ])('renders the %s contextual menu action', (slot, title, actionLabel) => {
    const registered = registerAssistant()
    renderAssistant(registered, slot)

    expect(screen.getByText(title)).toHaveClass('ai-work-assistant-menu-title')
    expect(screen.getByText('当前编辑块')).toHaveClass('ai-work-assistant-menu-tag')
    expect(screen.getByRole('button', { name: actionLabel })).toHaveClass('ai-work-assistant-menu-action', 'is-primary')
  })
  ```

  Update the existing click expectations to use the new visible action labels: `生成会议纪要`, `生成行动项建议`, `生成决策建议`, and `梳理开放问题`. Keep every existing request-body, busy-event, success, and failure assertion unchanged.

- [ ] **Step 2: Run the plugin test and verify it is red.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui/frontend
  npm test -- --run src/tests/ai-work-assistant-plugin.test.ts
  ```

  Expected: FAIL because each plugin control still renders only a generic `button button-quiet` and the old `AI …` labels.

- [ ] **Step 3: Implement slot-specific menu labels without changing task behavior.**

  In `plugins/ai-work-assistant/frontend/assistant-ui.js`, replace the five `label` values and add `menuTitle` values exactly as follows:

  ```js
  { slot: 'meeting-summary-editor', menuTitle: 'AI 协助纪要', actionId: 'ai-work-assistant.meeting_summary', label: '生成会议纪要', busyLabel: '正在生成会议纪要…', targetType: 'meeting' }
  { slot: 'project-update-editor', menuTitle: 'AI 协助进展', actionId: 'ai-work-assistant.project_progress', label: '总结项目进展', busyLabel: '正在总结项目进展…', targetType: 'project' }
  { slot: 'action-composer', menuTitle: 'AI 协助行动项', actionId: 'ai-work-assistant.action_suggestions', label: '生成行动项建议', busyLabel: '正在建议行动项…', targetType: 'meeting' }
  { slot: 'decision-composer', menuTitle: 'AI 协助决策', actionId: 'ai-work-assistant.decision_suggestions', label: '生成决策建议', busyLabel: '正在生成决策建议…', targetType: 'meeting' }
  { slot: 'question-composer', menuTitle: 'AI 协助问题', actionId: 'ai-work-assistant.open_question_suggestions', label: '梳理开放问题', busyLabel: '正在梳理开放问题…', targetType: 'meeting' }
  ```

  Replace the current render function return with a plugin-owned menu heading and a single primary action. Keep `run`, `running`, `setBusy`, polling, result validation, `notice`, and the `finally` block unchanged:

  ```js
  return () => h('div', { class: 'ai-work-assistant-control' }, [
    h('div', { class: 'ai-work-assistant-menu-heading' }, [
      h('span', { class: 'ai-work-assistant-menu-title' }, definition.menuTitle),
      h('span', { class: 'ai-work-assistant-menu-tag' }, '当前编辑块'),
    ]),
    h('button', {
      type: 'button',
      class: 'ai-work-assistant-menu-action is-primary',
      disabled: running.value,
      onClick: run,
    }, [
      h('span', { class: 'ai-work-assistant-menu-spark', 'aria-hidden': 'true' }, '✦'),
      h('span', running.value ? definition.busyLabel : definition.label),
    ]),
  ])
  ```

  Add these scoped deep selectors to `PluginEditorSlot.vue` after `.editor-assistant-menu`; they style plugin markup without importing the AI plugin into the core:

  ```css
  .editor-assistant-menu :deep(.ai-work-assistant-control) { display: grid; gap: .35rem; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-heading) { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .15rem .15rem .25rem; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-title) { color: var(--ink); font-size: .76rem; font-weight: 800; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-tag) { padding: .15rem .35rem; border-radius: 999px; color: var(--green-dark); background: var(--green-soft); font-size: .62rem; font-weight: 750; white-space: nowrap; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-action) { display: flex; width: 100%; min-height: 38px; align-items: center; gap: .45rem; padding: .45rem .55rem; border: 1px solid transparent; border-radius: 8px; color: var(--ink); background: transparent; cursor: pointer; font: inherit; font-size: .75rem; font-weight: 750; text-align: left; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-action.is-primary) { color: var(--green-dark); background: #eef8f2; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-action:hover:not(:disabled)), .editor-assistant-menu :deep(.ai-work-assistant-menu-action:focus-visible) { border-color: #b8d7c4; outline: 0; box-shadow: 0 0 0 3px rgba(11, 106, 88, .1); }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-action:disabled) { cursor: wait; opacity: .65; }
  .editor-assistant-menu :deep(.ai-work-assistant-menu-spark) { color: var(--green); font-size: .9rem; }
  ```

  The current plugin registers one grouped assistant per slot, so its heading appears once per menu. Do not add speculative extra actions or change the plugin registration contract.

- [ ] **Step 4: Run the plugin test and commit the contextual menu.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui/frontend
  npm test -- --run src/tests/ai-work-assistant-plugin.test.ts
  git diff --check
  cd ..
  git add frontend/src/components/PluginEditorSlot.vue plugins/ai-work-assistant/frontend/assistant-ui.js frontend/src/tests/ai-work-assistant-plugin.test.ts
  git commit -m "feat: polish AI editor action menu"
  ```

  Expected: all plugin tests pass, the request payloads and busy-label lifecycle still match existing coverage, and the commit contains only the listed files.

### Task 3: Run the UI regression suite, build, and inspect the real surface

**Files:** No new source files. Modify a file only if a verification failure proves a regression in the files changed by Tasks 1–2.

- [ ] **Step 1: Run complete frontend verification.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui/frontend
  npm test -- --run
  npm run build
  git diff --check
  ```

  Expected: all frontend tests pass, Vue type checking and Vite production build succeed, and `git diff --check` has no output.

- [ ] **Step 2: Perform a real-browser visual regression check in an isolated application instance.**

  Use the `testing-isolated-web-ui` skill before launching the application. Start a throwaway instance with a fresh data directory and the AI plugin loaded, then sign in and inspect one each of a decision, action, question, meeting-summary, and project-update editor.

  For each editor, verify the following manually:

  1. The Star opens a right-aligned menu with the expected contextual heading and exactly that editor’s registered action.
  2. Selecting the action retracts the menu before the request settles; the Star remains green and active.
  3. The editor content area, not its toolbar, receives a light blur and subtle moving diagonal construction texture; the bottom rail shows the exact busy label.
  4. There is no centered card or separate “处理中” popup, and the page layout does not jump.
  5. The editor cannot be changed or retriggered while busy; success updates only the local draft and failure preserves it.
  6. With reduced-motion enabled, the stripes and rail stop moving while the static busy state remains understandable.

- [ ] **Step 3: Record final evidence and integrate only the feature commits.**

  Run:

  ```bash
  cd .worktrees/ai-star-editor-ui
  git log --oneline -2
  git status --short
  git diff main...HEAD --check
  git diff --name-only main...HEAD
  ```

  Expected: the two feature commits are `feat: refine AI editor busy state` and `feat: polish AI editor action menu`; the changed-file list contains only the four files in this plan; the worktree is clean. Do not merge or delete the worktree until the user chooses the desired integration path.
