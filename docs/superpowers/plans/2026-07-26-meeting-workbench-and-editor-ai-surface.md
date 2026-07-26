# Meeting Workbench and Editor AI Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present a meeting as one scoped workbench followed by summary and tools, preserve all editable meeting content before lifecycle changes, and turn existing AI actions into compact editor-local draft suggestions.

**Architecture:** `AgendaWorkbench` becomes the shared outer surface for the current-topic and queue regions while the existing agenda components retain their data and mutation ownership. `MeetingWorkspaceView` coordinates a dirty agenda flush, a fresh meeting version, a dirty meeting save, and the lifecycle request without route reload. `PluginEditorSlot` becomes an editor chrome with an AI command menu and a host-owned review draft; the existing AI plugin continues to create and poll the same jobs but emits a draft for explicit application.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Vitest, Testing Library for Vue, Milkdown/Crepe, FastAPI meeting and agenda endpoints already present in the application.

---

## File map

| File | Responsibility |
| --- | --- |
| `frontend/src/components/AgendaWorkbench.vue` | Own the single meeting-workbench surface and expose selected-agenda flushing. |
| `frontend/src/components/AgendaDetail.vue` | Track the selected agenda draft, expose `flushIfDirty()`, and preserve existing manual save/conflict behavior. |
| `frontend/src/components/AgendaQueue.vue` | Remain the embedded agenda region; no queue data or mutation behavior changes. |
| `frontend/src/views/MeetingWorkspaceView.vue` | Track the meeting draft baseline, coordinate save-before-lifecycle, and adopt returned meeting data without `load()`. |
| `frontend/src/components/PluginEditorSlot.vue` | Render a compact editor chrome/menu, own pending AI review drafts, and keep the generic busy overlay. |
| `frontend/src/components/ProjectUpdateComposer.vue` | Supply the visible editor label to the generic plugin editor host. |
| `frontend/src/components/OutcomeComposer.vue` | Supply the outcome-specific editor label to the generic plugin editor host. |
| `plugins/ai-work-assistant/frontend/assistant-ui.js` | Emit generated Markdown as an unapplied draft instead of immediately replacing editor content. |
| `frontend/src/styles.css` | Style the shared workbench and remove the independent queue-card/sticky treatment. |
| `frontend/src/tests/agenda-workbench.test.ts` | Assert shared-workbench structure for populated and empty agendas. |
| `frontend/src/tests/meeting-workspace.test.ts` | Assert clean, dirty, and failing save-before-lifecycle flows. |
| `frontend/src/tests/plugin-editor-slot.test.ts` | Assert compact AI chrome/menu, busy overlay, and apply/discard review behavior. |
| `frontend/src/tests/ai-work-assistant-plugin.test.ts` | Assert AI plugin polling produces an unapplied `draft` event and preserves failure behavior. |

No backend file changes are planned. `PUT /api/agenda-items/{id}` already increments the parent meeting version, and the existing `PUT /api/meetings/{id}` plus lifecycle endpoints return a serialized meeting.

### Task 1: Render Current Topic and Agenda as one meeting-workbench surface

**Files:**

- Modify: `frontend/src/components/AgendaWorkbench.vue:1-44`
- Modify: `frontend/src/components/AgendaDetail.vue:52-66`
- Modify: `frontend/src/components/AgendaQueue.vue:114-131`
- Modify: `frontend/src/styles.css:341-345`
- Test: `frontend/src/tests/agenda-workbench.test.ts:66-80`

- [ ] **Step 1: Replace the two layout assertions with failing shared-surface assertions.**

  In `frontend/src/tests/agenda-workbench.test.ts`, replace the first two tests with these tests. They assert the outer scope and the embedded content order for both agenda states.

  ```ts
  it('renders current topic and agenda queue inside one meeting workbench', () => {
    render(AgendaWorkbench, { props: { meeting: meetingFixture() } })

    const workbench = screen.getByTestId('meeting-workbench')
    const detail = screen.getByTestId('agenda-detail')
    const queue = screen.getByTestId('agenda-queue')

    expect(workbench).toHaveClass('workspace-section', 'agenda-workbench')
    expect(workbench).toContainElement(detail)
    expect(workbench).toContainElement(queue)
    expect(detail.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(queue).toHaveClass('agenda-queue-narrow')
  })

  it('keeps the empty topic state inside the same meeting workbench', () => {
    render(AgendaWorkbench, { props: { meeting: emptyMeetingFixture() } })

    const workbench = screen.getByTestId('meeting-workbench')
    const detail = screen.getByTestId('agenda-detail')
    const queue = screen.getByTestId('agenda-queue')

    expect(workbench).toContainElement(detail)
    expect(workbench).toContainElement(queue)
    expect(detail).toHaveClass('agenda-empty-compact')
    expect(detail.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  ```

- [ ] **Step 2: Run the focused layout tests and confirm they fail because the outer workbench does not yet exist.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/agenda-workbench.test.ts
  ```

  Expected: the two new tests fail because `data-testid="meeting-workbench"` is absent; existing agenda mutation tests still pass.

- [ ] **Step 3: Make `AgendaWorkbench` the sole outer surface without moving agenda ownership.**

  In `frontend/src/components/AgendaWorkbench.vue`, replace the root template with the shared parent. The child components remain in their existing order and keep their event handlers.

  ```vue
  <template>
    <section class="workspace-section agenda-workbench" data-testid="meeting-workbench">
      <AgendaDetail v-if="selected" :meeting="meeting" :item="selected" @changed="emit('reload')" @advance="advance" />
      <section v-else class="agenda-empty-compact" data-testid="agenda-detail">
        <div><p class="eyebrow">Agenda</p><h2>还没有议题</h2><p>从右侧队列添加本次会议的第一个议题。</p></div>
        <button class="button button-primary" @click="requestAdd">添加议题</button>
      </section>
      <AgendaQueue ref="queue" :meeting="meeting" :selected-id="selectedId" @select="selectedId = $event" @changed="emit('reload')" />
    </section>
  </template>
  ```

  Keep `requestAdd()`, selected-id watches, imports, and `advance()` unchanged.

- [ ] **Step 4: Remove nested card appearance and sticky behavior only within the shared workbench.**

  Replace the current `.agenda-workbench`, `.agenda-detail`, `.agenda-queue-narrow`, and compact-empty CSS rules in `frontend/src/styles.css` with these scoped rules. Keep the existing queue row, outcome, and editor CSS below them.

  ```css
  .agenda-workbench { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 0; min-width: 0; padding: 0; overflow: hidden; }
  .agenda-workbench > .agenda-detail, .agenda-workbench > .agenda-empty-compact { min-width: 0; padding: 20px; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
  .agenda-workbench > .agenda-queue-narrow { position: static; top: auto; min-width: 0; padding: 18px; border: 0; border-left: 1px solid #e5e8ec; border-radius: 0; background: transparent; box-shadow: none; }
  .agenda-empty-compact { min-height: 0; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
  .agenda-empty-compact h2 { margin: 0; }
  .agenda-empty-compact p:last-child { margin-bottom: 0; }
  @media (max-width: 980px) {
    .agenda-workbench { grid-template-columns: 1fr; }
    .agenda-workbench > .agenda-queue-narrow { border-top: 1px solid #e5e8ec; border-left: 0; }
    .agenda-empty-compact { align-items: flex-start; flex-direction: column; }
  }
  ```

  In `AgendaDetail.vue` remove `workspace-section` from the root class, leaving `class="agenda-detail"`. In `AgendaQueue.vue` remove `workspace-section` from the root class, leaving `class="agenda-queue-narrow"`. This prevents generic card spacing from leaking into either embedded region.

- [ ] **Step 5: Run the focused agenda suite and build.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/agenda-workbench.test.ts
  npm run build
  ```

  Expected: the agenda suite passes, including drag reorder, outcome separation, assistant reachability, and deletion guard; the production TypeScript/Vite build exits with code 0.

- [ ] **Step 6: Commit the isolated visual hierarchy change.**

  ```bash
  git add frontend/src/components/AgendaWorkbench.vue frontend/src/components/AgendaDetail.vue frontend/src/components/AgendaQueue.vue frontend/src/styles.css frontend/src/tests/agenda-workbench.test.ts
  git commit -m "feat: unify meeting workbench surface"
  ```

### Task 2: Add a dirty-aware selected-agenda flush contract

**Files:**

- Modify: `frontend/src/components/AgendaDetail.vue:1-66`
- Modify: `frontend/src/components/AgendaWorkbench.vue:1-55`
- Test: `frontend/src/tests/agenda-workbench.test.ts:1-142`

- [ ] **Step 1: Add a failing workbench-harness test for an explicit dirty-agenda flush.**

  Add this harness and test to `frontend/src/tests/agenda-workbench.test.ts`. It tests the component boundary without coupling it to meeting lifecycle behavior, which Task 3 owns.

  ```ts
  const FlushHarness = defineComponent({
    components: { AgendaWorkbench },
    setup() {
      const workbench = ref<{ flushCurrentDraft: () => Promise<boolean> } | null>(null)
      const meeting = meetingFixture()
      async function flush() {
        await workbench.value?.flushCurrentDraft()
      }
      return { flush, meeting, workbench }
    },
    template: '<AgendaWorkbench ref="workbench" :meeting="meeting" /><button type="button" @click="flush">提交当前议题</button>',
  })

  it('flushes a dirty selected agenda through the workbench contract', async () => {
    render(FlushHarness)
    await fireEvent.update(screen.getByLabelText('议题标题'), '发布方案 v2')
    await fireEvent.click(screen.getByRole('button', { name: '提交当前议题' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    expect(apiMock).toHaveBeenNthCalledWith(1, '/api/agenda-items/a1', expect.objectContaining({
      method: 'PUT',
      body: expect.stringContaining('"title":"发布方案 v2"'),
    }))
  })
  ```

- [ ] **Step 2: Run the new test and confirm it fails because `AgendaWorkbench` has no exposed flush operation.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/agenda-workbench.test.ts
  ```

  Expected: the new test fails when the harness calls `flushCurrentDraft()`; the existing agenda tests keep passing.

- [ ] **Step 3: Refactor agenda persistence into explicit manual-save and flush paths.**

  In `AgendaDetail.vue`, import `computed`, make a serializable snapshot, and expose `flushIfDirty`. Preserve the current version-conflict assignment and dialog setup.

  ```ts
  type AgendaDraft = {
    title: string
    agenda_type: AgendaType
    notes_markdown: string
    estimated_minutes: number | null
  }

  function draftFrom(item: AgendaItem): AgendaDraft {
    return {
      title: item.title,
      agenda_type: item.agenda_type as AgendaType,
      notes_markdown: item.notes_markdown,
      estimated_minutes: item.estimated_minutes,
    }
  }

  const draft = reactive<AgendaDraft>(draftFrom(props.item))
  const acceptedDraft = ref<AgendaDraft>(draftFrom(props.item))
  const dirty = computed(() => JSON.stringify(draft) !== JSON.stringify(acceptedDraft.value))

  watch(() => props.item, (item) => {
    const next = draftFrom(item)
    Object.assign(draft, next)
    acceptedDraft.value = next
  }, { deep: true })

  async function persist(expectedVersion = props.item.version) {
    await api(`/api/agenda-items/${props.item.id}`, {
      method: 'PUT',
      body: JSON.stringify({ expected_version: expectedVersion, title: draft.title.trim(), agenda_type: draft.agenda_type, notes_markdown: draft.notes_markdown, estimated_minutes: draft.estimated_minutes }),
    })
    acceptedDraft.value = { ...draft }
    conflict.value = null
  }

  async function flushIfDirty() {
    if (!dirty.value) return false
    saving.value = true
    error.value = ''
    try {
      await persist()
      return true
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'version_conflict') {
        conflict.value = { version: Number(caught.details?.actual_version ?? props.item.version), server: props.item.notes_markdown }
      } else error.value = caught instanceof Error ? caught.message : '议题保存失败'
      throw caught
    } finally {
      saving.value = false
    }
  }

  defineExpose({ flushIfDirty })
  ```

  Replace the existing manual `save()` with this version. It intentionally emits `changed` only for the explicit user save; `flushIfDirty()` stays silent because Task 3 owns the subsequent meeting refresh.

  ```ts
  async function save(expectedVersion = props.item.version) {
    if (!dirty.value || saving.value) return
    saving.value = true
    error.value = ''
    try {
      await persist(expectedVersion)
      emit('changed')
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'version_conflict') {
        conflict.value = { version: Number(caught.details?.actual_version ?? props.item.version), server: props.item.notes_markdown }
      } else error.value = caught instanceof Error ? caught.message : '议题保存失败'
    } finally {
      saving.value = false
    }
  }
  ```

- [ ] **Step 4: Make the workbench forward the exposed agenda operation.**

  In `AgendaWorkbench.vue`, add the following structural ref contract after the current `queue` ref, then add `ref="detail"` to the selected `AgendaDetail` and expose the workbench method. The empty state naturally returns `false` because `detail.value` is null.

  ```ts
  type AgendaDetailHandle = {
    flushIfDirty: () => Promise<boolean>
  }

  const detail = ref<AgendaDetailHandle | null>(null)

  async function flushCurrentDraft() {
    return detail.value ? detail.value.flushIfDirty() : false
  }

  defineExpose({ flushCurrentDraft })
  ```

- [ ] **Step 5: Run the focused agenda suite and commit the agenda flush boundary.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/agenda-workbench.test.ts
  ```

  Expected: the new harness test and existing agenda tests pass; the explicit flush sends one agenda PUT, while Task 3 remains responsible for the later meeting refresh.

  Commit the component boundary and its passing test:

  ```bash
  git add frontend/src/components/AgendaDetail.vue frontend/src/components/AgendaWorkbench.vue frontend/src/tests/agenda-workbench.test.ts
  git commit -m "feat: expose dirty agenda flush for meeting transitions"
  ```

### Task 3: Save all dirty meeting content before changing lifecycle state

**Files:**

- Modify: `frontend/src/views/MeetingWorkspaceView.vue:1-132`
- Modify: `frontend/src/tests/meeting-workspace.test.ts:24-63`

- [ ] **Step 1: Add failing tests for dirty-agenda, clean, and dirty meeting-draft transitions.**

  Add these tests after the dirty-agenda test. They make the request sequence and no-reload rule explicit.

  ```ts
  it('saves a dirty current agenda, refreshes its meeting version, then starts the meeting', async () => {
    const agendaSaved = { ...meeting.agenda_items[0], title: '发布方案 v2', version: 2 }
    const afterAgenda = { ...meeting, version: 3, agenda_items: [agendaSaved] }
    const started = { ...afterAgenda, status: 'in_progress', version: 4 }
    apiMock
      .mockResolvedValueOnce(meeting)
      .mockResolvedValueOnce(agendaSaved)
      .mockResolvedValueOnce(afterAgenda)
      .mockResolvedValueOnce(started)

    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    await fireEvent.update(screen.getByLabelText('议题标题'), '发布方案 v2')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4))
    expect(apiMock).toHaveBeenNthCalledWith(2, '/api/agenda-items/a1', expect.objectContaining({
      method: 'PUT',
      body: expect.stringContaining('"title":"发布方案 v2"'),
    }))
    expect(apiMock).toHaveBeenNthCalledWith(3, '/api/meetings/m1')
    expect(apiMock).toHaveBeenNthCalledWith(4, '/api/meetings/m1/start', {
      method: 'POST',
      body: JSON.stringify({ expected_version: 3 }),
    })
  })

  it('starts a clean meeting from the lifecycle response without a second page load', async () => {
    const started = { ...meeting, status: 'in_progress', version: 3 }
    apiMock.mockResolvedValueOnce(meeting).mockResolvedValueOnce(started)

    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(apiMock).toHaveBeenNthCalledWith(2, '/api/meetings/m1/start', {
      method: 'POST',
      body: JSON.stringify({ expected_version: 2 }),
    })
    expect(apiMock.mock.calls.filter(([url]) => url === '/api/meetings/m1')).toHaveLength(1)
  })

  it('saves a dirty summary before start and preserves it when the transition fails', async () => {
    const saved = { ...meeting, summary_markdown: '## 已保存纪要', version: 3 }
    apiMock
      .mockResolvedValueOnce(meeting)
      .mockResolvedValueOnce(saved)
      .mockRejectedValueOnce(new Error('状态切换失败'))

    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    await fireEvent.update(screen.getByLabelText('会议纪要'), '## 已保存纪要')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await screen.findByRole('alert')
    expect(apiMock).toHaveBeenNthCalledWith(2, '/api/meetings/m1', expect.objectContaining({
      method: 'PUT',
      body: expect.stringContaining('"summary_markdown":"## 已保存纪要"'),
    }))
    expect(apiMock).toHaveBeenNthCalledWith(3, '/api/meetings/m1/start', {
      method: 'POST',
      body: JSON.stringify({ expected_version: 3 }),
    })
    expect(screen.getByLabelText('会议纪要')).toHaveValue('## 已保存纪要')
  })

  it('does not submit a lifecycle request when the dirty agenda save fails', async () => {
    apiMock.mockResolvedValueOnce(meeting).mockRejectedValueOnce(new Error('议题保存失败'))

    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    await fireEvent.update(screen.getByLabelText('议题标题'), '未保存议题')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await screen.findByRole('alert')
    expect(apiMock).toHaveBeenCalledTimes(2)
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
    expect(screen.getByLabelText('议题标题')).toHaveValue('未保存议题')
  })
  ```

- [ ] **Step 2: Run the focused workspace suite and confirm the lifecycle tests fail under the current `POST` then `load()` behavior.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/meeting-workspace.test.ts
  ```

  Expected: the clean test observes an extra GET after the POST, while the dirty tests call the lifecycle endpoint without the required preceding saves.

- [ ] **Step 3: Add meeting-draft baseline helpers and a non-resetting agenda refresh.**

  In `MeetingWorkspaceView.vue`, add these types and helpers directly below `toLocalInput()`.

  ```ts
  type MeetingDraft = {
    title: string
    purpose_markdown: string
    raw_notes_markdown: string
    summary_markdown: string
    scheduled_start: string
    scheduled_end: string
  }

  type AgendaWorkbenchHandle = {
    flushCurrentDraft: () => Promise<boolean>
  }

  const workbench = ref<AgendaWorkbenchHandle | null>(null)
  const acceptedMeetingDraft = ref<MeetingDraft>({ title: '', purpose_markdown: '', raw_notes_markdown: '', summary_markdown: '', scheduled_start: '', scheduled_end: '' })
  const lifecycleAction = ref<'ready' | 'draft' | 'start' | 'finish' | null>(null)

  function draftFrom(meeting: Meeting): MeetingDraft {
    return {
      title: meeting.title,
      purpose_markdown: meeting.purpose_markdown,
      raw_notes_markdown: meeting.raw_notes_markdown,
      summary_markdown: meeting.summary_markdown,
      scheduled_start: toLocalInput(meeting.scheduled_start),
      scheduled_end: toLocalInput(meeting.scheduled_end),
    }
  }

  const meetingDirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(acceptedMeetingDraft.value))

  function acceptMeeting(value: Meeting, resetDraft: boolean) {
    meeting.value = value
    materialItems.value = value.attachments ?? materialItems.value
    if (resetDraft) {
      const next = draftFrom(value)
      draft.value = next
      acceptedMeetingDraft.value = next
    }
  }
  ```

  Update `load()` to call `acceptMeeting(value, true)`. Change `refreshAgenda()` to return `Promise<Meeting>` and call `acceptMeeting(value, false)` so it refreshes the agenda/version without overwriting an unsaved meeting summary.

- [ ] **Step 4: Extract persistence and implement the exact lifecycle coordinator.**

  Replace the existing `saveMeeting()` and `lifecycle()` functions with the following structure. Move the existing unresolved-agenda `ApiError` branch into `handleLifecycleError()`.

  ```ts
  async function persistMeetingDraft(closePreparation: boolean) {
    if (!meeting.value || !meetingDirty.value) return false
    const value = await api<Meeting>(`/api/meetings/${meeting.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        expected_version: meeting.value.version,
        ...draft.value,
        scheduled_start: new Date(draft.value.scheduled_start).toISOString(),
        scheduled_end: new Date(draft.value.scheduled_end).toISOString(),
      }),
    })
    acceptMeeting(value, true)
    if (closePreparation) preparationOpen.value = false
    return true
  }

  async function saveMeeting() {
    saving.value = true
    error.value = ''
    try {
      const saved = await persistMeetingDraft(true)
      if (!saved) preparationOpen.value = false
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '会议保存失败'
    } finally {
      saving.value = false
    }
  }

  function handleLifecycleError(caught: unknown) {
    if (caught instanceof ApiError && caught.code === 'meeting_has_unresolved_agenda') {
      unresolvedIds.value = Array.isArray(caught.details?.agenda_ids) ? caught.details.agenda_ids.map(String) : []
      focusAgendaId.value = unresolvedIds.value[0] ?? ''
      error.value = `还有 ${unresolvedIds.value.length} 个议题未处理`
      return
    }
    error.value = caught instanceof Error ? caught.message : '会议状态更新失败'
  }

  async function lifecycle(action: 'ready' | 'draft' | 'start' | 'finish') {
    if (!meeting.value || saving.value) return
    saving.value = true
    lifecycleAction.value = action
    error.value = ''
    try {
      const agendaWasSaved = await workbench.value?.flushCurrentDraft() ?? false
      if (agendaWasSaved) await refreshAgenda()
      await persistMeetingDraft(false)
      const value = await api<Meeting>(`/api/meetings/${meeting.value.id}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ expected_version: meeting.value.version }),
      })
      acceptMeeting(value, true)
      unresolvedIds.value = []
    } catch (caught) {
      handleLifecycleError(caught)
    } finally {
      lifecycleAction.value = null
      saving.value = false
    }
  }
  ```

  Add `ref="workbench"` to the page's `AgendaWorkbench`. In each header lifecycle button, use `:disabled="saving"` and render the action-specific saving label through a small `lifecycleLabel()` helper, for example `正在保存并开始会议…` when `lifecycleAction === 'start'`.

- [ ] **Step 5: Run the workspace suite and the production build.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/meeting-workspace.test.ts
  npm run build
  ```

  Expected: all workspace tests pass; no successful lifecycle test causes a second `/api/meetings/m1` GET; TypeScript accepts the exposed workbench ref and Vite builds.

- [ ] **Step 6: Commit the completed save-before-lifecycle behavior.**

  ```bash
  git add frontend/src/components/AgendaDetail.vue frontend/src/components/AgendaWorkbench.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/meeting-workspace.test.ts
  git commit -m "fix: save meeting drafts before lifecycle changes"
  ```

### Task 4: Replace the standalone AI toolbar row with editor chrome and a command menu

**Files:**

- Modify: `frontend/src/components/PluginEditorSlot.vue:1-53`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue:114-126`
- Modify: `frontend/src/components/ProjectUpdateComposer.vue:38-40`
- Modify: `frontend/src/components/OutcomeComposer.vue:53-55`
- Test: `frontend/src/tests/plugin-editor-slot.test.ts:1-38`

- [ ] **Step 1: Replace the generic host test with a failing compact-chrome/menu test.**

  In `frontend/src/tests/plugin-editor-slot.test.ts`, make the fake assistant visible only after the menu opens and assert that the old placement marker is gone.

  ```ts
  it('places registered assistants in compact editor chrome and keeps busy feedback local', async () => {
    registerEditorAssistant('meeting-summary-editor', FakeAssistant)

    render(PluginEditorSlot, {
      props: {
        modelValue: '原记录',
        targetType: 'meeting',
        targetId: 'meeting-1',
        slot: 'meeting-summary-editor',
        editorLabel: '会议纪要',
        metadata: {},
      },
      slots: { editor: '<textarea aria-label="编辑器" />' },
    })

    expect(screen.getByText('会议纪要')).toBeVisible()
    expect(screen.getByRole('button', { name: 'AI 工具' })).toBeVisible()
    expect(screen.queryByRole('button', { name: '插件建议' })).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
    await fireEvent.click(screen.getByRole('button', { name: '插件建议' }))

    const host = screen.getByText('正在生成建议…').closest('.plugin-editor-slot')
    expect(host).toHaveAttribute('data-busy', 'true')
    expect(host?.querySelector('.plugin-editor-assistants')).toBeNull()
    expect(host?.querySelector('.plugin-editor-chrome')).not.toBeNull()
  })
  ```

- [ ] **Step 2: Run the focused host test and confirm it fails because `editorLabel` and the AI tool menu do not exist.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/plugin-editor-slot.test.ts
  ```

  Expected: the test cannot find the visible editor label or the `AI 工具` button.

- [ ] **Step 3: Implement one compact generic control, preserving component registration and busy events.**

  In `PluginEditorSlot.vue`, add `editorLabel` to the props, `menuOpen` state, and the following template structure. Keep forwarding `update:modelValue`, `update:busy`, and `notice` exactly as before.

  ```vue
  <template>
    <section class="plugin-editor-slot" :data-busy="busy.active || undefined" @keydown.esc="menuOpen = false">
      <div v-if="assistants.length" class="plugin-editor-chrome">
        <span class="plugin-editor-label">{{ editorLabel }}</span>
        <div class="plugin-editor-menu">
          <button
            type="button"
            class="editor-assistant-trigger"
            aria-label="AI 工具"
            :aria-expanded="menuOpen"
            aria-haspopup="true"
            :disabled="busy.active"
            @click="menuOpen = !menuOpen"
          >✦</button>
          <div v-if="menuOpen" aria-label="AI 操作" class="editor-assistant-menu">
            <component
              :is="assistant"
              v-for="(assistant, index) in assistants"
              :key="index"
              :model-value="modelValue"
              :context="context"
              :disabled="busy.active"
              @update:model-value="emit('update:modelValue', $event)"
              @update:busy="updateBusy"
              @notice="emit('notice', $event)"
            />
          </div>
        </div>
      </div>
      <slot name="editor" :disabled="busy.active" />
      <div v-if="busy.active" class="plugin-editor-busy" role="status" aria-live="polite"><p>{{ busy.label }}</p></div>
    </section>
  </template>
  ```

  Use scoped CSS to attach the chrome to the editor surface: a 32px near-white row, a left label in muted text, a right compact trigger, a bounded elevated command panel, and no full-width assistant divider. Do not use page-header, floating-action, or fixed-position styles. The trigger remains keyboard-focusable, and Escape closes its command panel.

- [ ] **Step 4: Pass visible field labels at every existing plugin-editor call site.**

  Add one `editor-label` attribute to each existing host; retain every existing target, metadata, slot, model, and notice binding:

  ```vue
  <!-- MeetingWorkspaceView.vue -->
  <PluginEditorSlot
    editor-label="会议纪要"
    v-model="draft.summary_markdown"
    data-testid="meeting-summary-editor"
    target-type="meeting"
    :target-id="meeting.id"
    slot="meeting-summary-editor"
    :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, participants: meeting.participants.map((participant) => participant.user) }"
    @notice="error = $event"
  >

  <!-- ProjectUpdateComposer.vue -->
  <PluginEditorSlot
    editor-label="进展记录"
    v-model="content"
    data-testid="project-update-editor"
    target-type="project"
    :target-id="projectId"
    slot="project-update-editor"
    :metadata="{ projectId }"
    @notice="error = $event"
  >

  <!-- OutcomeComposer.vue -->
  <PluginEditorSlot
    :editor-label="`${labels}内容`"
    v-model="content"
    :data-testid="assistantSlot"
    target-type="meeting"
    :target-id="meeting.id"
    :slot="assistantSlot"
    :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, agendaId: item.id, participants: meeting.participants.map((participant) => participant.user) }"
    @notice="error = $event"
  >
  ```

  Retain the `MarkdownEditor` `label` prop because it remains the accessible textbox name.

- [ ] **Step 5: Run host and representative editor tests, then commit the placement change.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/plugin-editor-slot.test.ts src/tests/meeting-workspace.test.ts src/tests/agenda-workbench.test.ts
  npm run build
  ```

  Expected: registered assistants are reachable through the compact command menu; no assertion depends on the old `.plugin-editor-assistants` row; build exits with code 0.

  ```bash
  git add frontend/src/components/PluginEditorSlot.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/components/ProjectUpdateComposer.vue frontend/src/components/OutcomeComposer.vue frontend/src/tests/plugin-editor-slot.test.ts
  git commit -m "feat: move AI actions into editor chrome"
  ```

### Task 5: Require explicit Apply or Discard for generated AI editor drafts

**Files:**

- Modify: `frontend/src/components/PluginEditorSlot.vue:1-100`
- Modify: `plugins/ai-work-assistant/frontend/assistant-ui.js:48-105`
- Test: `frontend/src/tests/plugin-editor-slot.test.ts:1-80`
- Test: `frontend/src/tests/ai-work-assistant-plugin.test.ts:49-134`

- [ ] **Step 1: Add a failing host test that keeps generated content out of the editor until Apply.**

  Before importing `PluginEditorSlot` in `plugin-editor-slot.test.ts`, mock `MarkdownEditor` so the review test can inspect a normal textarea instead of creating Milkdown:

  ```ts
  vi.mock('../components/MarkdownEditor.vue', () => ({
    default: {
      props: ['modelValue', 'label'],
      emits: ['update:modelValue'],
      template: '<textarea :aria-label="label" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    },
  }))
  ```

  Add a second fake assistant and this test. It exercises the host-owned review flow independently of the actual plugin's timer.

  ```ts
  const DraftAssistant = defineComponent({
    emits: ['draft'],
    template: '<button type="button" @click="$emit(\'draft\', \'# AI 草稿\')">生成草稿</button>',
  })

  it('keeps an AI draft editable until the user applies or discards it', async () => {
    registerEditorAssistant('project-update-editor', DraftAssistant)
    const { emitted } = render(PluginEditorSlot, {
      props: { modelValue: '原内容', targetType: 'project', targetId: 'p1', slot: 'project-update-editor', editorLabel: '进展记录' },
      slots: { editor: '<textarea aria-label="编辑器" />' },
    })

    await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
    await fireEvent.click(screen.getByRole('button', { name: '生成草稿' }))

    expect(emitted()['update:modelValue']).toBeUndefined()
    expect(screen.getByLabelText('AI 草稿')).toHaveValue('# AI 草稿')
    await fireEvent.update(screen.getByLabelText('AI 草稿'), '# 修改后的草稿')
    await fireEvent.click(screen.getByRole('button', { name: '应用草稿' }))
    expect(emitted()['update:modelValue']).toEqual([['# 修改后的草稿']])

    await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
    await fireEvent.click(screen.getByRole('button', { name: '生成草稿' }))
    await fireEvent.click(screen.getByRole('button', { name: '放弃' }))
    expect(screen.queryByLabelText('AI 草稿')).not.toBeInTheDocument()
    expect(emitted()['update:modelValue']).toEqual([['# 修改后的草稿']])
  })
  ```

- [ ] **Step 2: Change the AI plugin contract test before changing plugin behavior.**

  In `frontend/src/tests/ai-work-assistant-plugin.test.ts`, rename the successful-output tests and replace their direct-model assertions with draft assertions. For the meeting-summary test, retain the exact job request assertions and use:

  ```ts
  expect(emitted()['update:modelValue']).toBeUndefined()
  expect(emitted().draft).toEqual([['# 真实 AI 结果']])
  ```

  Make the action, decision, and question cases assert their generated Markdown through `emitted().draft` as well. Keep the failure test asserting no `draft`, no `update:modelValue`, and the same `notice` message.

- [ ] **Step 3: Run the host and plugin tests and confirm both fail before implementation.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/plugin-editor-slot.test.ts src/tests/ai-work-assistant-plugin.test.ts
  ```

  Expected: the host cannot render `AI 草稿` or Apply/Discard, and the plugin still emits `update:modelValue` instead of `draft`.

- [ ] **Step 4: Let the generic host own the editable review draft.**

  In `PluginEditorSlot.vue`, import `MarkdownEditor` and add these state and handlers. Keep compatibility for any non-AI registered assistant that still emits `update:modelValue`.

  ```ts
  const pendingDraft = ref<string | null>(null)

  function receiveDraft(markdown: string) {
    pendingDraft.value = markdown
    menuOpen.value = false
  }

  function applyDraft() {
    if (pendingDraft.value === null) return
    emit('update:modelValue', pendingDraft.value)
    pendingDraft.value = null
  }

  function discardDraft() {
    pendingDraft.value = null
  }
  ```

  Add `@draft="receiveDraft"` to registered assistant components. Change the editor slot disabled binding to `busy.active || pendingDraft !== null`, then render the review surface after the normal editor slot:

  ```vue
  <section v-if="pendingDraft !== null" class="plugin-editor-draft-review">
    <header><span>AI 草稿</span><button type="button" class="button button-small button-quiet" @click="discardDraft">放弃</button></header>
    <MarkdownEditor v-model="pendingDraft" label="AI 草稿" placeholder="检查并编辑 AI 草稿…" />
    <footer><button type="button" class="button button-primary" @click="applyDraft">应用草稿</button></footer>
  </section>
  ```

  Style it as a compact local panel below the editor: top divider, neutral background, no modal, no fixed positioning, and no page-level title. The original editor is disabled only while this unapplied review draft is visible, preventing an Apply operation from overwriting newly typed content.

- [ ] **Step 5: Emit drafts from the existing AI action instead of overwriting the editor.**

  In `plugins/ai-work-assistant/frontend/assistant-ui.js`, change the component event list and successful-result branch only:

  ```js
  emits: ['draft', 'update:busy', 'notice'],
  ```

  ```js
  if (typeof job.result?.markdown !== 'string') {
    notice('AI 未返回可用草稿')
    return
  }
  emit('draft', job.result.markdown)
  ```

  Keep the existing job action IDs, input payload, polling interval, busy labels, duplicate-click guard, and failure handling unchanged. Do not add a server-side Apply endpoint: applying remains a local editor update followed by the existing ordinary Save/Publish action.

- [ ] **Step 6: Run the two focused suites, full frontend suite, and production build.**

  Run from `frontend/`:

  ```bash
  npm test -- src/tests/plugin-editor-slot.test.ts src/tests/ai-work-assistant-plugin.test.ts
  npm test
  npm run build
  ```

  Expected: focused and full Vitest suites exit with code 0; `AI 草稿` does not alter the parent model until Apply; Discard and job failures preserve source text; TypeScript and Vite build successfully.

- [ ] **Step 7: Commit the explicit AI review behavior.**

  ```bash
  git add frontend/src/components/PluginEditorSlot.vue plugins/ai-work-assistant/frontend/assistant-ui.js frontend/src/tests/plugin-editor-slot.test.ts frontend/src/tests/ai-work-assistant-plugin.test.ts
  git commit -m "feat: review AI editor drafts before apply"
  ```

### Task 6: Perform final cross-surface verification

**Files:**

- Verify only: files changed in Tasks 1 through 5

- [ ] **Step 1: Run the complete frontend test suite from the frontend directory.**

  ```bash
  npm test
  ```

  Expected: exit code 0 with all frontend test files passing.

- [ ] **Step 2: Run the production frontend build.**

  ```bash
  npm run build
  ```

  Expected: exit code 0; Vue TypeScript checking and Vite asset build complete without errors.

- [ ] **Step 3: Inspect the committed worktree and verify no unrelated file was staged.**

  Run from the repository root:

  ```bash
  git status --short --branch
  git log --oneline -5
  git diff HEAD~5..HEAD --check
  ```

  Expected: the five feature commits correspond to the workbench, agenda-flush boundary, save-before-lifecycle, AI chrome, and AI review tasks. Preserve any pre-existing unrelated untracked file rather than staging or deleting it.

## Plan self-review

### Spec coverage

- One shared `Current topic + Agenda` workbench surface: Task 1.
- Normal document scrolling and mobile stack rather than a fixed viewport: Task 1 CSS rules.
- Save agenda, refresh meeting version, save meeting, then transition: Tasks 2 and 3.
- No lifecycle call after a failed save and no page-level reload after a successful one: Task 3 tests and coordinator.
- Editor-local compact AI control, no global AI chat pane: Task 4.
- Editable AI draft with explicit Apply/Discard and unchanged plugin-job transport: Task 5.
- Focused, regression, full-suite, build, and worktree evidence: Tasks 1 through 6.

### Placeholder scan

The plan contains no TBD/TODO markers, skipped final tests, new backend endpoint, or unspecified command. Every code change names a concrete file, test, function, or template structure.

### Type and boundary consistency

- `AgendaDetail.flushIfDirty()` returns `Promise<boolean>`; `AgendaWorkbench.flushCurrentDraft()` forwards the same result; `MeetingWorkspaceView` consumes it before refreshing the meeting.
- `PluginEditorSlot` continues to accept `modelValue`, `targetType`, `targetId`, `slot`, and `metadata`; `editorLabel` is the only added call-site prop.
- The AI plugin emits `draft` with a Markdown string; the generic host owns Apply/Discard and remains backward-compatible with existing `update:modelValue` assistants.
