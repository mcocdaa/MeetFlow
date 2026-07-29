# 核心工作区轻量 UI 统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 MeetFlow 业务流程的前提下，统一登录后核心工作区的导航 SVG、内容层级、首页并列卡和 AI 任务表面状态。

**Architecture:** 保持 Vue 页面与插件边界不变。`@lucide/vue` 在主前端按需导入 SVG；共享 CSS 只收敛空间、控件、卡片和状态规则；AI 插件继续提供动作与 `busyLabel`，`PluginEditorSlot` 继续管理菜单收起和局部施工遮罩。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、Testing Library、Lucide Vue、现有外部 AI 工作助手插件。

---

## 文件结构

| 文件 | 职责 |
| --- | --- |
| `frontend/package.json`、`frontend/package-lock.json` | 声明并锁定按需导入的 `@lucide/vue`。 |
| `frontend/src/components/AppSidebar.vue` | 为工作区和管理员导航绑定语义 SVG，保留原有链接与权限判断。 |
| `frontend/src/views/HomeView.vue` | 为首页两张并列信息卡增加稳定的可访问性命名钩子。 |
| `frontend/src/views/AiTasksView.vue` | 将既有任务状态展示为视觉状态标记，不改轮询或任务操作。 |
| `frontend/src/components/PluginEditorSlot.vue` | 把编辑器 AI 入口替换为 SVG，并保留既有施工态行为。 |
| `frontend/src/views/MeetingsView.vue`、`frontend/src/components/OutcomeComposer.vue`、`frontend/src/components/VersionConflictDialog.vue`、`frontend/src/components/ContextDrawer.vue` | 把已有关闭字符替换为同一套 SVG 图标，不改变按钮语义。 |
| `plugins/ai-work-assistant/frontend/assistant-ui.js` | 去除菜单操作中的装饰性文本 Star，继续只输出动作标签和忙碌状态。 |
| `frontend/src/styles.css` | 定义有限的间距/控件 token，统一工作区卡片、双栏、任务状态与图标按钮样式。 |
| `frontend/src/tests/app-shell.test.ts`、`home-attention.test.ts`、`ai-tasks.test.ts`、`plugin-editor-slot.test.ts`、`ai-work-assistant-plugin.test.ts` | 固化 SVG、页面地标、状态标记和 AI 行为未回归。 |

### Task 1: 安装 SVG 依赖并替换工作区导航与关闭控件

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/components/AppSidebar.vue:1-38`
- Modify: `frontend/src/views/MeetingsView.vue:1-58`
- Modify: `frontend/src/components/OutcomeComposer.vue:1-70`
- Modify: `frontend/src/components/VersionConflictDialog.vue:1-40`
- Modify: `frontend/src/components/ContextDrawer.vue:1-30`
- Test: `frontend/src/tests/app-shell.test.ts:1-62`

- [ ] **Step 1: 为导航 SVG 写失败测试。**

  在 `app-shell.test.ts` 导入 `within`，并在第一条测试中替换单个链接断言为下列循环。当前字符图标实现没有 `svg`，该断言应失败。

  ```ts
  const workspaceNavigation = screen.getByRole('navigation', { name: '工作区导航' })
  for (const label of ['为你', '项目', '会议', '行动项', '决策', '收件箱', 'AI 任务']) {
    const link = within(workspaceNavigation).getByRole('link', { name: label })
    expect(link.querySelector('svg')).not.toBeNull()
  }

  const administratorNavigation = screen.getByRole('navigation', { name: '管理员导航' })
  for (const label of ['用户', '插件', '设置']) {
    const link = within(administratorNavigation).getByRole('link', { name: label })
    expect(link.querySelector('svg')).not.toBeNull()
  }
  ```

- [ ] **Step 2: 运行失败测试确认当前字符图标不满足契约。**

  Run: `npm --prefix frontend test -- src/tests/app-shell.test.ts`

  Expected: `uses workspace navigation` 失败，原因是导航链接内尚无 `svg`。

- [ ] **Step 3: 安装并锁定 Vue SVG 图标依赖。**

  Run: `npm --prefix frontend install @lucide/vue`

  Verify: `frontend/package.json` 的 `dependencies` 包含 `@lucide/vue`，且 `frontend/package-lock.json` 同步更新；不要手工编辑 lockfile。

- [ ] **Step 4: 用按需导入的 Lucide 组件重写 `AppSidebar`。**

  在组件脚本中导入 `type Component` 和实际使用的图标；导航数据保存组件引用，而不是字符串符号。

  ```ts
  import type { Component } from 'vue'
  import {
    Bot, CalendarDays, FolderKanban, Gavel, SquareCheckBig,
    House, Inbox, Puzzle, Settings, UsersRound,
  } from '@lucide/vue'

  type NavigationLink = { to: string; label: string; icon: Component }

  const workspaceLinks: NavigationLink[] = [
    { to: '/', label: '为你', icon: House },
    { to: '/projects', label: '项目', icon: FolderKanban },
    { to: '/meetings', label: '会议', icon: CalendarDays },
    { to: '/actions', label: '行动项', icon: SquareCheckBig },
    { to: '/decisions', label: '决策', icon: Gavel },
    { to: '/inbox', label: '收件箱', icon: Inbox },
    { to: '/ai-tasks', label: 'AI 任务', icon: Bot },
  ]
  const adminLinks: NavigationLink[] = [
    { to: '/admin/users', label: '用户', icon: UsersRound },
    { to: '/admin/plugins', label: '插件', icon: Puzzle },
    { to: '/account', label: '设置', icon: Settings },
  ]
  ```

  在两个 `RouterLink` 内使用相同的可访问性安全标记：

  ```vue
  <component :is="link.icon" class="sidebar-nav-icon" :size="18" :stroke-width="1.8" aria-hidden="true" />
  <span>{{ link.label }}</span>
  ```

- [ ] **Step 5: 将现有关闭字符替换为 `X`。**

  在 `MeetingsView.vue`、`OutcomeComposer.vue`、`VersionConflictDialog.vue` 和 `ContextDrawer.vue` 各自按需导入 `X`，保持原有 `button.icon-button`、`aria-label="关闭"` 和点击处理器。每个原有 `×` 的按钮内容改为：

  ```vue
  <X :size="18" :stroke-width="2" aria-hidden="true" />
  ```

  不修改操作名称、表单开关、抽屉关闭或冲突处理流程。

- [ ] **Step 6: 运行导航测试确认 SVG 和权限行为同时通过。**

  Run: `npm --prefix frontend test -- src/tests/app-shell.test.ts`

  Expected: 该文件全部测试通过；成员角色仍看不到管理员导航。

- [ ] **Step 7: 提交导航与 SVG 依赖。**

  ```bash
  git add frontend/package.json frontend/package-lock.json \
    frontend/src/components/AppSidebar.vue frontend/src/views/MeetingsView.vue \
    frontend/src/components/OutcomeComposer.vue frontend/src/components/VersionConflictDialog.vue \
    frontend/src/components/ContextDrawer.vue frontend/src/tests/app-shell.test.ts
  git commit -m "feat: unify workspace navigation icons"
  ```

### Task 2: 统一首页双栏、页面层级与共享控件节奏

**Files:**
- Modify: `frontend/src/views/HomeView.vue:88-130`
- Modify: `frontend/src/styles.css:1-105`
- Modify: `frontend/src/styles.css:281-346`
- Test: `frontend/src/tests/home-attention.test.ts:15-44`

- [ ] **Step 1: 为首页信息卡地标写失败测试。**

  在 `renders one prioritized subject with translated, coalesced reasons` 的末尾增加：

  ```ts
  const priorityQueue = await screen.findByRole('region', { name: '需要关注' })
  const upcomingMeetings = screen.getByRole('region', { name: '近期会议' })
  expect(priorityQueue).toHaveClass('workspace-section')
  expect(upcomingMeetings).toHaveClass('workspace-section', 'upcoming-panel')
  ```

- [ ] **Step 2: 运行失败测试确认两张卡当前没有稳定的可访问性名称。**

  Run: `npm --prefix frontend test -- src/tests/home-attention.test.ts`

  Expected: 新增的 `region` 查询失败。

- [ ] **Step 3: 为首页并列卡添加命名地标，不改变内容或路由。**

  将首页两个标题和容器调整为：

  ```vue
  <section class="workspace-section" aria-labelledby="priority-queue-title">
    <div class="section-heading">
      <div><p class="eyebrow">Priority queue</p><h2 id="priority-queue-title">需要关注</h2></div>
      <span class="metric"><strong>{{ priorities.length }}</strong> 项</span>
    </div>
    <!-- 保留现有 AttentionCard 与空状态分支 -->
  </section>

  <aside class="workspace-section upcoming-panel" aria-labelledby="upcoming-meetings-title">
    <div class="section-heading">
      <div><p class="eyebrow">Next up</p><h2 id="upcoming-meetings-title">近期会议</h2></div>
      <RouterLink class="text-link" to="/meetings">全部</RouterLink>
    </div>
    <!-- 保留现有会议链接与空状态分支 -->
  </aside>
  ```

- [ ] **Step 4: 收敛共享样式，限制变更到登录后工作区的视觉节奏。**

  在 `:root` 添加以下有限 token，并以它们替换本次触及的工作区数值：

  ```css
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --control-height: 40px;
  --control-height-small: 34px;
  --radius-control: 8px;
  ```

  更新工作区规则，确保只有首页并列卡拉伸等高：

  ```css
  .button { min-height: var(--control-height); transition: background .16s ease, box-shadow .16s ease, color .16s ease; }
  .button:hover:not(:disabled) { transform: none; }
  .button-small { min-height: var(--control-height-small); }
  .icon-button { display: inline-grid; width: 38px; height: 38px; place-items: center; border-radius: 50%; }
  .icon-button:hover, .icon-button:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(11, 106, 88, .14); }

  .workspace-page-heading { margin-bottom: var(--space-6); }
  .workspace-section { padding: 20px; border-radius: 12px; }
  .workspace-section > .section-heading { align-items: flex-start; margin-bottom: var(--space-4); }
  .attention-layout { align-items: stretch; }
  .attention-layout > .workspace-section { min-height: 100%; }
  .upcoming-panel { align-content: start; }
  ```

  保留 `@media (max-width: 950px)` 的单列规则；在此断点不要保留强制等高规则。

- [ ] **Step 5: 运行首页测试确认数据、工作简报和新增地标均通过。**

  Run: `npm --prefix frontend test -- src/tests/home-attention.test.ts`

  Expected: 该文件全部测试通过，且既有流式工作简报断言仍通过。

- [ ] **Step 6: 提交首页与共享层级样式。**

  ```bash
  git add frontend/src/views/HomeView.vue frontend/src/styles.css frontend/src/tests/home-attention.test.ts
  git commit -m "feat: polish workspace content hierarchy"
  ```

### Task 3: 统一 AI 入口、任务状态和既有施工态的表面表达

**Files:**
- Modify: `frontend/src/components/PluginEditorSlot.vue:1-138`
- Modify: `plugins/ai-work-assistant/frontend/assistant-ui.js:127-143`
- Modify: `frontend/src/views/AiTasksView.vue:15-85`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/tests/plugin-editor-slot.test.ts:65-129`
- Test: `frontend/src/tests/ai-work-assistant-plugin.test.ts:40-57`
- Test: `frontend/src/tests/ai-tasks.test.ts:8-60`

- [ ] **Step 1: 为编辑器 SVG 入口和任务状态标记写失败测试。**

  在 `plugin-editor-slot.test.ts` 的第一条测试中、取得 `trigger` 后加入：

  ```ts
  expect(trigger.querySelector('svg')).not.toBeNull()
  expect(trigger).not.toHaveTextContent('✦')
  ```

  在 `ai-tasks.test.ts` 的成功任务测试中加入：

  ```ts
  const status = await screen.findByText('已生成')
  expect(status).toHaveClass('status-pill', 'ai-task-status')
  expect(status).toHaveAttribute('data-status', 'ready')
  ```

  在 `ai-work-assistant-plugin.test.ts` 的菜单测试中加入：

  ```ts
  expect(screen.queryByText('✦')).not.toBeInTheDocument()
  ```

- [ ] **Step 2: 运行三个失败测试，确认当前 UI 仍依赖文本 Star 且任务没有状态标记。**

  Run: `npm --prefix frontend test -- src/tests/plugin-editor-slot.test.ts src/tests/ai-work-assistant-plugin.test.ts src/tests/ai-tasks.test.ts`

  Expected: 新增 SVG、无文本 Star 和 `ai-task-status` 断言失败；既有任务提交、轮询和结果写回测试仍通过。

- [ ] **Step 3: 用 `Sparkles` 替换宿主 Star，移除插件内装饰字符。**

  在 `PluginEditorSlot.vue` 添加 `import { Sparkles } from '@lucide/vue'`，并将触发器内容替换为：

  ```vue
  <Sparkles :size="15" :stroke-width="2" aria-hidden="true" />
  ```

  保持 `aria-label`、`aria-expanded`、`disabled`、`updateBusy`、`v-show="menuOpen"` 和施工遮罩 DOM 不变。在插件 `assistant-ui.js` 中，删除 `ai-work-assistant-menu-spark` 的 `span`，只保留动作文本：

  ```js
  h('span', running.value ? definition.busyLabel : definition.label),
  ```

  同时删除 `PluginEditorSlot.vue` 中仅为该已删除 class 服务的 `:deep(.ai-work-assistant-menu-spark)` 样式。

- [ ] **Step 4: 为任务状态建立纯展示映射并调整任务标题结构。**

  在 `AiTasksView.vue` 紧邻 `statusLabel` 定义展示色调，顺序与现有优先级完全一致：

  ```ts
  function statusTone(job: PluginJob) {
    if (job.dismissed_at) return 'dismissed'
    if (job.applied_at) return 'applied'
    if (job.status === 'queued' || job.status === 'requesting') return 'processing'
    if (job.status === 'succeeded') return 'ready'
    if (job.status === 'canceled') return 'canceled'
    return 'failed'
  }
  ```

  将任务卡左侧标题改为，不改 `source`、`cancel`、`rerun` 或 `PluginTaskExtension`：

  ```vue
  <div>
    <p class="eyebrow">{{ job.plugin_id }} · {{ job.action_id }}</p>
    <div class="ai-task-title-row">
      <h2>AI 任务</h2>
      <span class="status-pill ai-task-status" :data-status="statusTone(job)">{{ statusLabel(job) }}</span>
    </div>
  </div>
  ```

- [ ] **Step 5: 为 AI 任务卡与 SVG 入口添加局部样式，不重写施工交互。**

  在共享 CSS 增加任务卡层级和状态色；`processing` 只表达活动状态，不创建新动画：

  ```css
  .task-list { display: grid; gap: var(--space-4); }
  .ai-task-card { display: grid; gap: var(--space-3); }
  .ai-task-title-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
  .ai-task-title-row h2 { margin: 0; }
  .ai-task-status { align-items: center; }
  .ai-task-status[data-status="processing"] { color: #785318; background: #f8e8c8; }
  .ai-task-status[data-status="ready"], .ai-task-status[data-status="applied"] { color: var(--green-dark); background: var(--green-soft); }
  .ai-task-status[data-status="dismissed"], .ai-task-status[data-status="canceled"] { color: #59615c; background: #e9e9e4; }
  .ai-task-status[data-status="failed"] { color: #8d312a; background: #f6deda; }
  .editor-assistant-trigger svg { display: block; }
  ```

  保留 `.plugin-editor-busy`、滚动斜纹、施工轨和 `prefers-reduced-motion` 规则；只允许在不改变它们语义的情况下微调其 token 引用或对比度。

- [ ] **Step 6: 运行 AI 聚焦测试确认数据与忙碌行为未回归。**

  Run: `npm --prefix frontend test -- src/tests/plugin-editor-slot.test.ts src/tests/ai-work-assistant-plugin.test.ts src/tests/ai-tasks.test.ts`

  Expected: 三个文件全部通过；忙碌时菜单仍隐藏、触发器和编辑器仍禁用、状态区域仍聚焦，失败任务仍保留错误详情与重新运行条件。

- [ ] **Step 7: 提交 AI 表面统一。**

  ```bash
  git add frontend/src/components/PluginEditorSlot.vue plugins/ai-work-assistant/frontend/assistant-ui.js \
    frontend/src/views/AiTasksView.vue frontend/src/styles.css \
    frontend/src/tests/plugin-editor-slot.test.ts frontend/src/tests/ai-work-assistant-plugin.test.ts \
    frontend/src/tests/ai-tasks.test.ts
  git commit -m "feat: polish AI task status surfaces"
  ```

### Task 4: 完整验证与隔离的视觉回归检查

**Files:**
- Verify only: 前三项任务的前端文件与测试。

- [ ] **Step 1: 运行完整前端测试套件。**

  Run: `npm --prefix frontend test`

  Expected: Vitest 以退出码 0 完成；记录实际测试文件数和断言结果。

- [ ] **Step 2: 运行生产构建。**

  Run: `npm --prefix frontend run build`

  Expected: `vue-tsc -b && vite build` 退出码为 0；如仅出现现有 bundle 大小警告，将其作为已知警告记录而非失败。

- [ ] **Step 3: 检查提交前差异边界。**

  Run: `git diff --check && git status --short && git diff --stat HEAD~3..HEAD`

  Expected: 无空白错误；差异仅覆盖本计划声明的前端依赖、组件、插件、样式与测试文件。

- [ ] **Step 4: 用隔离容器检查真实登录工作区，不触碰当前 8000 服务或共享数据。**

  先记录现有服务：

  ```bash
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  ```

  然后在一次性目录和固定的非默认端口启动新镜像：

  ```bash
  test_dir=$(mktemp -d /tmp/meetflow-core-workspace-ui.XXXXXX)
  mkdir -p "$test_dir/data"
  docker build --tag meetflow:core-workspace-ui-check .
  docker run --detach --rm --name meetflow-core-workspace-ui-check \
    --publish 127.0.0.1:18029:8000 \
    --volume "$test_dir/data:/app/data" \
    --env ADMIN_USERNAME=ui-check \
    --env ADMIN_PASSWORD=ui-check-admin-password \
    --env APP_SECRET_KEY=ui-check-app-secret-key-20260729-0123456789 \
    meetflow:core-workspace-ui-check
  ```

  使用 `testing-isolated-web-ui` 的真实浏览器流程登录 `ui-check`，在桌面与 390px 视口确认：侧栏 SVG 对齐、首页两张并列卡桌面等高/窄屏单列、AI 任务页的标题与任务卡有清晰分隔。AI 施工态的真实交互继续用现有组件测试验证，除非隔离实例已确定性启用了 AI 插件；不得使用真实 AI 密钥。

- [ ] **Step 5: 清理精确的临时资源并确认原服务不受影响。**

  ```bash
  docker stop meetflow-core-workspace-ui-check
  docker image rm meetflow:core-workspace-ui-check
  rm -rf "$test_dir"
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  ```

  Expected: 原有 `meetflow-meetflow-1` 仍在 `127.0.0.1:8000`，临时容器、镜像和数据目录均不存在。

## 规格覆盖自检

| 规格要求 | 实施任务 |
| --- | --- |
| 克制的深蓝/浅灰工作区、统一空间与控件层级 | Task 2 |
| 工作区与管理员侧栏的开源 SVG | Task 1 |
| Priority queue 与 Next up 等高、窄屏单列 | Task 2、Task 4 |
| 页面说明、卡片头部、列表与空状态的层级 | Task 2 |
| AI SVG 入口、施工遮罩保持局部且无额外浮窗 | Task 3 |
| AI 任务状态、恢复操作与可访问性不回归 | Task 3、Task 4 |
| 无路由/API/插件任务语义变更 | Task 1–3 的测试与代码边界 |
