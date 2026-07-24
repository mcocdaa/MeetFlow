# Project Workspace Information Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the project detail page into a concise driving dashboard with dedicated tabs for meetings, actions, decisions, files, and activity.

**Architecture:** Preserve the existing FastAPI entities and use the existing project, action, decision, meeting, attachment, and project-update APIs. Split the current page into overview, activity, and record-tab Vue components. The parent owns loading, tab selection, and drawers; each child has a single rendering responsibility and emits explicit events.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vue Router, Vitest, existing FastAPI JSON APIs, CSS Grid.

---

## File map

- Create `frontend/src/components/ProjectOverview.vue`: read-only dashboard cards and source links.
- Create `frontend/src/components/ProjectActivityTab.vue`: project progress composer, inline AI draft, plugin trigger, and update history.
- Create `frontend/src/components/ProjectRecordTabs.vue`: tab-local Meetings, Actions, Decisions, and Files records.
- Modify `frontend/src/views/ProjectDetailView.vue`: header New menu, tabs, drawers, and child composition.
- Modify `frontend/src/domain/projects.ts`: concise project-action summary type.
- Modify `frontend/src/styles.css`: dashboard and record-list responsive layout.
- Modify `frontend/src/tests/project-workspace.test.ts`: dashboard and tab regressions.

### Task 1: Define the dashboard contract with failing tests

**Files:**
- Modify: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Add a test for a read-only overview**

```ts
it('keeps overview focused on project state and actionable summaries', async () => {
  render(ProjectDetailView)
  await screen.findByRole('heading', { name: '项目状态' })
  expect(screen.getByRole('heading', { name: '下一次会议' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '需要处理' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '近期行动项' })).toBeInTheDocument()
  expect(screen.queryByLabelText('进展记录')).not.toBeInTheDocument()
  expect(screen.queryByTestId('project-inline-progress')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the overview test before implementation**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: FAIL because the current overview has a progress editor and inline AI draft.

- [ ] **Step 3: Add destination and creation tests**

```ts
it('places progress editing and AI progress drafts in Activity', async () => {
  render(ProjectDetailView)
  await fireEvent.click(await screen.findByRole('tab', { name: '动态' }))
  expect(screen.getByLabelText('进展记录')).toBeInTheDocument()
  expect(screen.getByTestId('project-inline-progress')).toBeInTheDocument()
})

it('opens an action drawer from the global New menu', async () => {
  render(ProjectDetailView)
  await fireEvent.click(await screen.findByRole('button', { name: '新建' }))
  await fireEvent.click(screen.getByRole('menuitem', { name: '行动项' }))
  expect(screen.getByRole('dialog', { name: '添加行动项' })).toBeInTheDocument()
})
```

- [ ] **Step 4: Add an Actions-tab API test**

First add a named fixture helper beside the `project` fixture so this test has no implicit dependency:

```ts
function defaultProjectResponse(path: string) {
  if (path === '/api/projects/p1') return Promise.resolve(project)
  if (path === '/api/attention') return Promise.resolve({ items: [], unread_count: 0, truncated: false })
  return Promise.resolve([])
}
```

```ts
it('loads project actions in the Actions tab', async () => {
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/actions?project_id=p1&status=open') {
      return Promise.resolve({ items: [{ id: 'a1', content: '确认范围', status: 'open', priority: 'high', owner_user_id: 'u1', due_date: '2026-07-25', meeting_id: 'm1' }], total: 1 })
    }
    return defaultProjectResponse(path)
  })
  render(ProjectDetailView)
  await fireEvent.click(await screen.findByRole('tab', { name: '行动项' }))
  expect(await screen.findByText('确认范围')).toBeInTheDocument()
})
```

- [ ] **Step 5: Run the file and commit the red contract**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: FAIL for the missing global menu and tab-local action row.

```bash
git add frontend/src/tests/project-workspace.test.ts
git commit -m "test: define project workspace dashboard contract"
```

### Task 2: Implement the read-only project dashboard

**Files:**
- Create: `frontend/src/components/ProjectOverview.vue`
- Modify: `frontend/src/domain/projects.ts`
- Modify: `frontend/src/views/ProjectDetailView.vue`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Add a concise action type**

```ts
export type ProjectActionSummary = {
  id: string
  content: string
  status: string
  priority: string
  owner_user_id: string | null
  due_date: string | null
  meeting_id: string | null
}
```

- [ ] **Step 2: Create `ProjectOverview.vue` with an explicit read-only interface**

```ts
const props = defineProps<{
  project: ProjectDetail
  attention: AttentionItem[]
  openActions: ProjectActionSummary[]
}>()
const emit = defineEmits<{
  scheduleMeeting: []
  openTab: [tab: 'meetings' | 'actions' | 'decisions' | 'activity']
}>()
```

Render, in order: `项目状态`, `下一次会议`, `需要处理`, `近期行动项`, `近期决策`, and `最近动态`. Cap attention/actions/activity at five and decisions at three. Use `RouterLink` for source records. The component must not import a composer, plugin panel, or inline AI draft.

- [ ] **Step 3: Fetch open project actions in the parent and mount the dashboard**

```ts
const openActions = ref<ProjectActionSummary[]>([])
const [value, attentionValue, actionValue] = await Promise.all([
  api<ProjectDetail>(`/api/projects/${projectId.value}`),
  api<{ items: AttentionItem[] }>('/api/attention'),
  api<Page<ProjectActionSummary>>(`/api/actions?project_id=${projectId.value}&status=open`),
])
openActions.value = actionValue.items
```

Wire `scheduleMeeting` to the existing meeting drawer and `openTab` to parent tab state.

- [ ] **Step 4: Run the project workspace tests and commit**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: PASS for dashboard headings, no overview editor, and source summaries.

```bash
git add frontend/src/components/ProjectOverview.vue frontend/src/domain/projects.ts frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-workspace.test.ts
git commit -m "feat: make project overview a driving dashboard"
```

### Task 3: Move progress and AI work into Activity

**Files:**
- Create: `frontend/src/components/ProjectActivityTab.vue`
- Modify: `frontend/src/views/ProjectDetailView.vue`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Create a focused Activity component**

```ts
const props = defineProps<{ project: ProjectDetail }>()
const emit = defineEmits<{ reload: [] }>()
const progressDrafts = ref<{ reload: () => Promise<void> } | null>(null)

function refreshProgressDrafts() {
  void progressDrafts.value?.reload()
}
```

Render this exact workflow: Activity heading; existing `ProjectUpdateComposer`; `InlineAiDrafts` with `data-testid="project-inline-progress"`; `PluginActionPanel`; reverse-chronological `project.updates`. Bind composer save and AI draft apply to `emit('reload')`; bind plugin submission to `refreshProgressDrafts`.

- [ ] **Step 2: Replace the parent Activity placeholder**

```vue
<ProjectActivityTab
  v-else-if="tab === 'activity'"
  :project="project"
  @reload="load"
/>
```

Remove the three Activity-only imports and the progress-draft ref from the parent. No editor remains in Overview.

- [ ] **Step 3: Run destination regressions and commit**

Run: `npm test -- --run src/tests/project-workspace.test.ts src/tests/inline-ai-drafts.test.ts src/tests/ai-tasks.test.ts`

Expected: PASS; exactly one project progress editor exists, and it is only in Activity.

```bash
git add frontend/src/components/ProjectActivityTab.vue frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-workspace.test.ts
git commit -m "feat: keep project progress work in activity"
```

### Task 4: Implement tab-local records and the New menu

**Files:**
- Create: `frontend/src/components/ProjectRecordTabs.vue`
- Modify: `frontend/src/views/ProjectDetailView.vue`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Create `ProjectRecordTabs.vue`**

```ts
const props = defineProps<{ project: ProjectDetail; tab: 'meetings' | 'actions' | 'decisions' | 'files' }>()
const emit = defineEmits<{ create: [kind: 'meeting' | 'series' | 'decision' | 'action'] }>()

function endpoint() {
  if (props.tab === 'meetings') return `/api/meetings?project_id=${props.project.id}`
  if (props.tab === 'actions') return `/api/actions?project_id=${props.project.id}&status=open`
  return `/api/decisions?project_id=${props.project.id}`
}
watch(() => props.tab, () => void load(), { immediate: true })
```

For Meetings show next meeting, series, and fetched meeting rows. For Actions show content, status, owner, due date, priority, and source meeting. For Decisions show title, state, and source meeting. For Files use existing `AttachmentPanel`. Each tab header exposes only its relevant create action(s).

- [ ] **Step 2: Add the header New menu in `ProjectDetailView.vue`**

Maintain `newMenuOpen` state and render a semantic menu:

```vue
<button class="button button-primary" aria-haspopup="menu" :aria-expanded="newMenuOpen" @click="newMenuOpen = !newMenuOpen">新建</button>
<div v-if="newMenuOpen" role="menu" class="project-new-menu">
  <button role="menuitem" @click="openCreate('meeting')">会议</button>
  <button role="menuitem" @click="openCreate('series')">系列会议</button>
  <button role="menuitem" @click="openCreate('decision')">决策</button>
  <button role="menuitem" @click="openCreate('action')">行动项</button>
  <button role="menuitem" @click="tab = 'activity'; newMenuOpen = false">进展</button>
  <button role="menuitem" @click="tab = 'files'; newMenuOpen = false">文件</button>
</div>
```

`openCreate` assigns `drawerKind` and closes the menu. Keep `Edit project` secondary.

- [ ] **Step 3: Apply responsive layout rules**

```css
.project-overview-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(18rem, .9fr); gap: 18px; align-items: start; }
.project-dashboard-list, .project-record-list { display: grid; gap: 10px; }
.project-record-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; }
.project-header-new { position: relative; }
.project-new-menu { position: absolute; z-index: 5; display: grid; gap: 4px; }
@media (max-width: 900px) { .project-overview-grid { grid-template-columns: 1fr; } }
```

Delete the old `.project-update-section { grid-row: span 2; }` rule. Do not set content-derived cards to fixed heights.

- [ ] **Step 4: Run project tests and commit**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: PASS for the New menu, in-page Actions tab, Activity destination, and original meeting drawer.

```bash
git add frontend/src/components/ProjectRecordTabs.vue frontend/src/views/ProjectDetailView.vue frontend/src/styles.css frontend/src/tests/project-workspace.test.ts
git commit -m "feat: add dedicated project record tabs"
```

### Task 5: Verify and deploy

**Files:**
- Modify: no source files expected.

- [ ] **Step 1: Run focused frontend regressions**

Run: `npm test -- --run src/tests/project-workspace.test.ts src/tests/inline-ai-drafts.test.ts src/tests/ai-tasks.test.ts`

Expected: all selected tests pass.

- [ ] **Step 2: Run complete frontend verification**

Run: `npm test -- --run && npm run build`

Expected: fewer than 100 tests, zero failures, and successful typecheck/build.

- [ ] **Step 3: Run backend plugin regression**

Run: `python -m pytest backend/tests/plugins/test_jobs.py -q`

Expected: all plugin source-scope and apply tests pass.

- [ ] **Step 4: Rebuild and recreate Docker**

Run: `docker compose up -d --build --force-recreate`

Expected: service container is recreated and healthy.

- [ ] **Step 5: Smoke test the deployed application**

Run:

```bash
curl --fail --silent http://127.0.0.1:8000/api/health
curl --fail --silent http://127.0.0.1:8000/ | rg -o '<title>[^<]+'
```

Log in with configured administrator credentials without printing them, request `/api/plugins/actions`, and expect meeting summary, project progress, and action suggestions.

- [ ] **Step 6: Confirm clean handoff**

Run: `git status --short --branch`

Expected: no uncommitted changes; report commits and test evidence.
