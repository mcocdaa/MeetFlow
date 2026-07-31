# 会议系列高级搜索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让会议列表的高级搜索可发现，并在从会议系列进入时清楚展示、管理已启用的系列筛选。

**Architecture:** 继续由 `MeetingsView.vue` 保存视图级筛选状态，并在已加载的会议数组上组合关键词、项目、系列和状态过滤。仅 `series_id` 与 URL 同步，以保持项目页系列链接和刷新语义；样式作为现有会议列表工具栏的局部扩展，不改变 API 或数据模型。

**Tech Stack:** Vue 3 Composition API、TypeScript、Vitest、Vue Testing Library、现有全局 CSS。

---

## 文件结构

- Create: `frontend/src/tests/meetings-view.test.ts` — 会议列表高级搜索的用户可见行为回归测试。
- Modify: `frontend/src/views/MeetingsView.vue` — 筛选状态、URL 同步、筛选结果、按钮和高级面板。
- Modify: `frontend/src/styles.css` — 工具栏、激活按钮、展开面板和窄屏布局。
- Modify: `docs/superpowers/plans/2026-07-30-meeting-series-advanced-search.md` — 在每项完成后勾选对应步骤。

### Task 1: 为高级筛选写失败的界面测试

**Files:**
- Create: `frontend/src/tests/meetings-view.test.ts`
- Modify: `frontend/src/views/MeetingsView.vue`

- [x] **Step 1: 写入页面夹具与高级面板入口测试。**

```ts
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MeetingsView from '../views/MeetingsView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('../auth/session', () => ({ session: { user: { id: 'u1', username: 'lin', display_name: '林宇' } } }))
vi.mock('vue-router', () => ({ RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' }, useRouter: () => ({ push: pushMock }) }))

const project = { id: 'p1', name: '平台', slug: 'platform' }
const meetings = [
  { id: 'm1', project, series: { id: 's1', title: '产品周会' }, occurrence_kind: 'scheduled', title: '产品周会 · 第 1 次', purpose_markdown: '', scheduled_start: '2026-08-03T01:00:00Z', scheduled_end: '2026-08-03T02:00:00Z', status: 'ready', host: null, agenda_count: 0, snapshot_count: 0, amendment_count: 0 },
  { id: 'm2', project, series: null, occurrence_kind: 'manual', title: '临时评审', purpose_markdown: '', scheduled_start: '2026-08-04T01:00:00Z', scheduled_end: '2026-08-04T02:00:00Z', status: 'completed', host: null, agenda_count: 0, snapshot_count: 1, amendment_count: 0 },
]

function renderList(search = '') {
  window.history.replaceState(null, '', `/meetings${search}`)
  apiMock.mockImplementation((path: string) => Promise.resolve(path === '/api/projects' ? [project] : { items: meetings }))
  return render(MeetingsView)
}

describe('meeting list advanced search', () => {
  beforeEach(() => { apiMock.mockReset(); pushMock.mockReset() })

  it('keeps advanced filters discoverable and reveals all three fields on demand', async () => {
    renderList()
    const button = await screen.findByRole('button', { name: '高级筛选' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('会议系列')).not.toBeInTheDocument()
    await fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('项目')).toBeVisible()
    expect(screen.getByLabelText('会议系列')).toBeVisible()
    expect(screen.getByLabelText('会议状态')).toBeVisible()
  })
})
```

- [x] **Step 2: 运行测试，确认它因缺少入口而失败。**

Run: `npm --prefix frontend test -- meetings-view.test.ts`

Expected: FAIL，提示找不到名称为“高级筛选”的按钮。

- [x] **Step 3: 追加两个独立行为测试。**

```ts
it('filters by status and exposes the active filter count', async () => {
  renderList()
  await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
  await fireEvent.update(screen.getByLabelText('会议状态'), 'completed')
  expect(screen.getByRole('button', { name: '高级筛选（已启用 1 项）' })).toBeVisible()
  expect(screen.getByText('临时评审')).toBeVisible()
  expect(screen.queryByText('产品周会 · 第 1 次')).not.toBeInTheDocument()
})

it('opens and highlights the series filter from the shared series URL, then clears it', async () => {
  renderList('?series_id=s1')
  expect(await screen.findByText('已启用 1 项')).toBeVisible()
  expect(screen.getByLabelText('会议系列')).toHaveValue('s1')
  await fireEvent.click(screen.getByRole('button', { name: '清除全部高级筛选' }))
  await waitFor(() => expect(window.location.search).toBe(''))
  expect(screen.getByLabelText('会议系列')).toHaveValue('')
})
```

- [x] **Step 4: 再次运行测试，确认新增断言在实现前失败。**

Run: `npm --prefix frontend test -- meetings-view.test.ts`

Expected: FAIL，包含缺少“会议状态”选择器、自动展开或“清除全部高级筛选”控件的断言。

- [x] **Step 5: 提交仅包含测试的红灯提交。**

```bash
git add frontend/src/tests/meetings-view.test.ts
git commit -m "test: cover meeting advanced search"
```

### Task 2: 实现可组合的高级筛选和系列 URL 状态

**Files:**
- Modify: `frontend/src/views/MeetingsView.vue`
- Test: `frontend/src/tests/meetings-view.test.ts`

- [x] **Step 1: 在现有筛选状态后声明状态筛选、展开态和系列选项。**

```ts
const projectFilter = ref('')
const activeSeriesFilter = ref(new URLSearchParams(window.location.search).get('series_id') ?? '')
const statusFilter = ref<MeetingStatus | ''>('')
const advancedOpen = ref(Boolean(activeSeriesFilter.value))
const seriesOptions = computed(() => {
  const seen = new Map<string, { id: string; title: string }>()
  meetings.value.forEach((item) => { if (item.series) seen.set(item.series.id, item.series) })
  return [...seen.values()].sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
})
const advancedFilterCount = computed(() => [projectFilter.value, activeSeriesFilter.value, statusFilter.value].filter(Boolean).length)
```

- [x] **Step 2: 用单一的组合谓词替换现有 `visible`，并实现清除语义。**

```ts
const visible = computed(() => meetings.value.filter((item) => (
  (!projectFilter.value || item.project.id === projectFilter.value)
  && (!activeSeriesFilter.value || item.series?.id === activeSeriesFilter.value)
  && (!statusFilter.value || item.status === statusFilter.value)
  && (!search.value || `${item.title} ${item.project.name} ${item.series?.title ?? ''}`.toLowerCase().includes(search.value.toLowerCase()))
)))

function syncSeriesFilterToUrl() {
  const url = new URL(window.location.href)
  if (activeSeriesFilter.value) url.searchParams.set('series_id', activeSeriesFilter.value)
  else url.searchParams.delete('series_id')
  window.history.replaceState(null, '', url)
}

function clearAdvancedFilters() {
  projectFilter.value = ''
  activeSeriesFilter.value = ''
  statusFilter.value = ''
  syncSeriesFilterToUrl()
}
```

- [x] **Step 3: 把现有 `meeting-list-filters` 模板替换为按钮和条件面板。**

```vue
<section class="meeting-list-filters" aria-label="会议搜索与筛选">
  <label class="search-box"><span aria-hidden="true">⌕</span><input v-model.trim="search" aria-label="搜索会议" placeholder="搜索会议、项目或系列" /></label>
  <button class="button button-quiet meeting-advanced-toggle" type="button" :class="{ 'is-active': advancedFilterCount }" :aria-label="advancedFilterCount ? `高级筛选（已启用 ${advancedFilterCount} 项）` : '高级筛选'" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
    高级筛选<span v-if="advancedFilterCount" class="meeting-filter-count">{{ advancedFilterCount }}</span>
  </button>
  <section v-if="advancedOpen" class="meeting-advanced-panel" aria-label="高级筛选条件">
    <header><div><strong>高级筛选</strong><span v-if="advancedFilterCount">已启用 {{ advancedFilterCount }} 项</span></div><button v-if="advancedFilterCount" class="button button-quiet button-small" type="button" aria-label="清除全部高级筛选" @click="clearAdvancedFilters">清除全部</button></header>
    <div class="meeting-advanced-fields">
      <label>项目<select v-model="projectFilter"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
      <label>会议系列<select v-model="activeSeriesFilter" @change="syncSeriesFilterToUrl"><option value="">全部系列</option><option v-for="series in seriesOptions" :key="series.id" :value="series.id">{{ series.title }}</option></select></label>
      <label>会议状态<select v-model="statusFilter"><option value="">全部状态</option><option value="draft">草稿</option><option value="ready">待开始</option><option value="in_progress">进行中</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label>
    </div>
    <p>当前显示 {{ visible.length }} 场会议。</p>
  </section>
</section>
```

- [x] **Step 4: 运行目标测试，确认三项行为全部变绿。**

Run: `npm --prefix frontend test -- meetings-view.test.ts`

Expected: PASS，3 tests passed。

- [x] **Step 5: 提交 Vue 实现。**

```bash
git add frontend/src/views/MeetingsView.vue frontend/src/tests/meetings-view.test.ts
git commit -m "feat: add meeting advanced search"
```

### Task 3: 完成激活层级和响应式布局

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/tests/meetings-view.test.ts`

- [x] **Step 1: 在会议列表样式区追加局部样式。**

```css
.meeting-list-filters { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; margin: 20px 0 30px; }
.meeting-list-filters .search-box { width: 100%; }
.meeting-advanced-toggle { min-width: 132px; }
.meeting-advanced-toggle.is-active { border-color: #79aa96; color: var(--green-dark); background: var(--green-soft); box-shadow: 0 0 0 3px rgba(11, 106, 88, .08); }
.meeting-filter-count { min-width: 19px; height: 19px; display: inline-grid; place-items: center; border-radius: 999px; color: white; background: var(--green); font-size: .68rem; }
.meeting-advanced-panel { grid-column: 1 / -1; display: grid; gap: 14px; padding: 16px; border: 1px solid #cfe1d8; border-radius: 12px; background: #fbfdfc; box-shadow: 0 10px 24px rgba(21, 47, 37, .06); }
.meeting-advanced-panel header, .meeting-advanced-panel header > div { display: flex; align-items: center; gap: 9px; }.meeting-advanced-panel header { justify-content: space-between; }.meeting-advanced-panel header span, .meeting-advanced-panel > p { margin: 0; color: var(--green-dark); font-size: .78rem; font-weight: 700; }
.meeting-advanced-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }.meeting-advanced-fields label { display: grid; gap: 6px; color: #626c79; font-size: .78rem; }.meeting-advanced-fields select { min-width: 0; }
@media (max-width: 720px) { .meeting-list-filters { grid-template-columns: 1fr; }.meeting-advanced-toggle { width: 100%; }.meeting-advanced-fields { grid-template-columns: 1fr; }.meeting-advanced-panel header { align-items: flex-start; flex-direction: column; }.meeting-advanced-panel header .button { width: 100%; } }
```

- [x] **Step 2: 扩展入口测试，锁定激活类和可见结果文本。**

```ts
expect(screen.getByRole('button', { name: '高级筛选（已启用 1 项）' })).toHaveClass('is-active')
expect(screen.getByText('当前显示 1 场会议。')).toBeVisible()
```

- [x] **Step 3: 运行前端目标测试并生产构建。**

Run: `npm --prefix frontend test -- meetings-view.test.ts && npm --prefix frontend run build`

Expected: 测试全部通过；构建退出码为 0。

- [x] **Step 4: 以隔离服务做浏览器验证。**

Use `testing-isolated-web-ui`：创建临时数据和服务，确认默认搜索仅有可见的高级入口、从项目系列链接进入自动展开且按钮显示计数、在 375px 宽度下输入框和按钮均完整可操作。完成后停止临时服务并删除临时数据。

- [x] **Step 5: 提交样式和最终测试。**

```bash
git add frontend/src/styles.css frontend/src/tests/meetings-view.test.ts
git commit -m "style: clarify meeting advanced filters"
```

### Task 4: 全量验证与文档交付

**Files:**
- Modify: `docs/superpowers/plans/2026-07-30-meeting-series-advanced-search.md`

- [x] **Step 1: 运行仓库要求的全量验证。**

Run:

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q backend/tests/test_release_workflow.py
git diff --check
```

Expected: 每条命令退出码为 0；若构建仅报告既有 chunk-size 警告，记录为非阻塞警告。

- [x] **Step 2: 在本计划中勾选实际已完成步骤并提交计划状态。**

```bash
git add docs/superpowers/plans/2026-07-30-meeting-series-advanced-search.md
git commit -m "docs: complete meeting advanced search plan"
```
