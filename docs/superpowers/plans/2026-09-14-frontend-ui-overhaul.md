# MeetFlow 前端 UI 全面改版实施计划（Naive UI + 后端能力对齐）

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐条执行本计划。步骤使用 checkbox（`- [ ]`）语法跟踪。
> 每个任务结束时本任务涉及的测试必须通过；每个阶段末尾有“阶段门禁”任务，必须全量 `npm --prefix frontend test` 与 `npm --prefix frontend run build` 双绿才能进入下一阶段。

**规格来源（唯一事实来源）：** [2026-09-14-frontend-ui-overhaul-design.md](../specs/2026-09-14-frontend-ui-overhaul-design.md)（第 15 节全部未决问题已裁决）
**日期：** 2026-09-15
**Goal：** 在前端-only 前提下引入 Naive UI 浅色设计系统，统一图标/头像/反馈/表单模式，并把 14 条路由的页面逻辑与后端既有 API 能力完全对齐；后端契约、错误码、消息、响应结构零改动。
**Architecture：** 保持 Vue 3 + Vite + 既有 reactive 单例状态模式；`src/theme/naive.ts` 承载 `themeOverrides` 与状态色映射；`StatusPill` 收敛为 `NTag` 薄封装；创建/编辑统一右侧 `n-drawer` 表单，确认统一 `n-popconfirm`/`n-dialog`，瞬时反馈统一 `n-message`，页面错误保留行内 `n-alert`；稠密全局列表（行动项/决策/管理员用户/插件事件）改 `n-data-table` + 服务端筛选分页；富内容面（首页/项目/会议/工作区）保留卡片/行布局；权限渲染只读服务端 `capabilities`。
**Tech Stack：** Vue 3.5、TypeScript、Vite 6、Vitest 3 + @testing-library/vue + jsdom、Naive UI 2.x（浅色）、`@lucide/vue`、Milkdown Crepe、marked + DOMPurify。

---

## 一、分支与 PR 策略（执行前必读）

- 每个阶段一个分支：`feature/ui-overhaul-p0` 至 `feature/ui-overhaul-p7`（每阶段一个，共 8 个），从最新的 `main` 切出。
- 每阶段结束时（阶段门禁任务）在该分支上运行全量前端测试与构建，双绿后推送并创建该阶段自己的 PR，**等待用户合并后再开始下一阶段**。不要把多个阶段塞进同一个 PR。
- 同一阶段内的任务按顺序执行；阶段内测试未绿不得开启下一阶段。
- 提交粒度：每个任务末尾给出建议的 `git add` + `git commit`（本计划不强制 squash）；PR 描述必须列出本阶段“有意更新的既有测试断言”（规格 §11.2）。
- 后端文件（`backend/**`、迁移、`scripts/**`、`Dockerfile`、发布工作流）不得出现在任何阶段的 diff 中；每个阶段门禁都要检查 `git status --short backend/` 输出为空。
- 不实施第 8 节 #35（复制来源投影）与 #36（开放问题放弃写入口）；不新增路由；不新增后端端点。若实现中发现规格与后端当前代码冲突，**以后端当前代码为准**，在 PR 中标注并将该项降级为只读或延期，不凭摘要实现。

## 二、验证基线（执行前先记录）

在干净工作区（或每个阶段分支起点）运行以下命令并记录结果，作为本计划的比较基线：

```bash
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m pytest -q
```

预期基线（2026-09-15 实测）：

- `npm --prefix frontend test`：`Test Files 25 passed (25)`、`Tests 124 passed (124)`（`frontend/src/tests/` 下 25 个测试文件 + `setup.ts`）。
- `npm --prefix frontend run build`：`vue-tsc -b && vite build` 退出码 0；`✓ built in ~16s`。最大 chunk `dist/assets/index-*.js` 约 `1,655.00 kB │ gzip: 524.46 kB`（已知体积警告，不作为失败）。
- `.venv/bin/python -m pytest -q`：`219 passed, 1 failed`。唯一失败是已知环境性失败 `backend/tests/migrations/test_wheel_resources.py::test_wheel_contains_and_runs_migrations_outside_source_tree`（本计划全程不触碰后端，预期结果不变）。
- `frontend/src/styles.css` 当前 336 行；`naive-ui` 尚未安装。

本计划新增测试文件后文件数会增长（预计最终 32 个测试文件）：新增规格 §10 的 4 个（`project-questions`、`series-manage`、`project-activity`、`decision-workflow`）+ 本计划补充的 3 个基础设施测试（`ui-foundation`、`versioned-save`、`inbox-unread`，见“假设与本计划裁决”）。判断绿的标准是 `Test Files N passed (N)` 且 `Tests M passed (M)`、无 failed/skipped，不是固定的 25/124。

## 三、全局约束（每个任务都必须遵守）

1. **前端-only**：不改任何后端代码、端点、错误码、消息、响应结构、数据库迁移；`src/api/client.ts` 不改；`src/plugins/**` 契约不改。
2. **技术栈边界**：不引入 Pinia、Tailwind、ESLint、暗色主题、i18n 多语言；仅接入 Naive 的 `zhCN`/`dateZhCN`。保留 Milkdown Crepe 编辑器与 marked + DOMPurify 渲染。
3. **状态模式**：保留既有 reactive 单例模式（`auth/session.ts`、新 `useInboxUnread`、`useUserNameMap`）。
4. **保存语义**：会议工作区保留显式保存按钮与 `useMeetingWorkspace` 的 dirty/409 语义；不改为自动保存。
5. **图标**：功能图标一律 `@lucide/vue` 组件 + `NIcon` 包装，禁止新增 Unicode/emoji 图标字形；图标按钮必须有 `aria-label`。
6. **头像**：字母头像必须走 `AppAvatar` 并优先使用后端 `avatar_color`；品牌 “M” 字标保留。
7. **权限渲染**：写入入口只由服务端 `capabilities`（`can_manage/can_contribute/can_comment`）与逐项 `can_delete/can_edit/can_resolve` 控制；禁止在项目/会议视图中用 `session.user.role` 推导能力；`role === 'admin'` 只允许出现在管理员路由守卫、管理员导航与管理员页内部。
8. **动作门控**：派生行动项/决策/开放问题（`is_derived === true`）不渲染编辑与状态流转入口。
9. **反馈**：瞬时反馈 `n-message`（经 `useMessage()`，错误文案取自 `apiErrorMessage`/`ApiError.message`）；页面级错误保留行内 `n-alert`；同一失败不同时弹 message 又刷 alert。
10. **刷新策略**：默认 refetch-on-success；乐观更新只用于本地 UI 态（菜单开合、选中行、插件开关）。
11. **测试兼容约定**（规格 §11.1，P0 落地后全局适用）：
    - 弹出层（drawer/dialog/popconfirm/dropdown）Teleport 到 `document.body`：一律用 `screen.findByRole(...)`、`screen.findByText(...)` 等全局查询，不依赖 `container`。
    - `n-data-table` 在 jsdom 下宽度为 0：不启用固定列与虚拟滚动；需要 `scroll-x` 时给表格显式 `min-width`；分页只断言请求参数（`limit/offset`）与 `itemCount` 渲染，不测滚动行为。
    - 弹出层异步渲染：操作后 `await screen.findBy...`；消息断言用 `findByText` 匹配 `n-message` 文案。
    - 保留既有查询约定：角色优先（`getByRole`）、`getByLabelText`、关键 `data-testid`（`meeting-workbench`、`agenda-detail`、`agenda-queue`、`flow-actions`、各编辑器 testid、`agenda-row-*`）。
12. **构建**：每个阶段末 `npm --prefix frontend run build`（`vue-tsc -b` 严格）必须通过；`naive-ui` 组件一律具名 ESM 导入（Vite tree-shaking），不新增 `unplugin-auto-import`/`unplugin-vue-components`。

## 四、文件与组件总览

**新增（规格 §10 之外的本计划新增以 “+” 标注）：**

| 文件 | 阶段 | 职责 |
| --- | --- | --- |
| `frontend/src/theme/naive.ts` | P0 | `naiveThemeOverrides` + `statusTone()` / `priorityTone()` |
| `frontend/src/components/AppAvatar.vue` | P0 | 基于 `n-avatar` 的字母头像（`avatar_color`） |
| `frontend/src/utils/capabilities.ts` | P0 | `can(source, capability)` 能力判定唯一入口 |
| `frontend/src/utils/activity.ts` | P0 | `activityLabel(event_type, payload)` 事件文案 |
| `frontend/src/composables/useInboxUnread.ts` | P1 | 壳层未读单例（60s 轮询 + 路由/前台刷新） |
| `frontend/src/composables/useVersionedSave.ts` | P1 | 409 `version_conflict` 统一处理 |
| `frontend/src/components/SeriesEditDrawer.vue` | P5 | 系列编辑/归档/常设议题 |
| `frontend/src/components/DecisionDetailDrawer.vue` | P5 | 决策详情与评审流转 |
| `frontend/src/components/ActionEditDrawer.vue` | P5 | 行动项编辑（全局与项目 Tab 复用） |
| `frontend/src/components/ProjectQuestionsTab.vue` | P5 | 开放问题生命周期 Tab |
| `frontend/src/components/MeetingParticipantEditor.vue` + | P3 | 参与人（成员 + 角色）可复用编辑器 |
| `frontend/src/components/MeetingCreateDrawer.vue` + | P3 | 会议创建抽屉（全局会议列表与项目页复用） |
| `frontend/src/composables/useUserNameMap.ts` + | P6 | 姓名聚合字典（`/api/projects` memberships） |
| `frontend/src/tests/project-questions.test.ts` | P5 | 规格 §10 新增测试 |
| `frontend/src/tests/series-manage.test.ts` | P5 | 规格 §10 新增测试 |
| `frontend/src/tests/project-activity.test.ts` | P5 | 规格 §10 新增测试 |
| `frontend/src/tests/decision-workflow.test.ts` | P5 | 规格 §10 新增测试 |
| `frontend/src/tests/ui-foundation.test.ts` + | P0 | 主题/jsdom 补丁/provider 冒烟/StatusPill/能力/活动文案 |
| `frontend/src/tests/versioned-save.test.ts` + | P1 | `useVersionedSave` + `VersionConflictDialog` |
| `frontend/src/tests/inbox-unread.test.ts` + | P1 | 未读单例轮询与回退 |
| `frontend/src/tests/helpers.ts` + | P0 | `renderWithProviders()`（Provider 包裹的 render） |

**不新增**：路由（14 条保持不变）、后端文件、`ContextDrawer.vue` 的扩展（改用 `n-drawer` 后该组件仅在 P7 清理或删除）、`ProjectCreatePanel.vue` 的扩展（按实体拆分为抽屉表单）。

**类型封装修正（按阶段）：** `src/api/meetings.ts`（P4 扩展 `LifecycleAction` 与 `MeetingUpdate`）；`src/domain/meetings.ts`（P4 补 `carry_from_open_question_id`、`started_at/completed_at`、`MeetingSeriesDetail`、参与人写入类型）；`src/domain/outcomes.ts`（P5 补 `reviewers[]`、`decided_by`、`completed_at`、开放问题来源字段）；`src/auth/session.ts`（P0 补 `avatar_color`）。

---

# P0 基础设施（依赖、主题、测试底座）

> 阶段分支：`feature/ui-overhaul-p0`。本阶段不迁移任何页面，只搭底座并保持既有 25 个测试文件 / 124 个用例全绿（本阶段新增 1 个基础设施测试文件，门禁预期 26 个文件）。

### Task P0-1：安装 naive-ui 并记录构建体积基线

**目标：** 声明并锁定 `naive-ui` 依赖；确认不引入任何自动导入插件；记录构建体积基线供 P7 对比。

**涉及文件：**
- 修改 `frontend/package.json`、`frontend/package-lock.json`

**实现步骤：**
- [ ] 1. 从仓库根运行 `npm --prefix frontend install naive-ui`；不要手工编辑 lockfile。
- [ ] 2. 确认 `frontend/package.json` 的 `dependencies` 出现 `"naive-ui": "^2.x"`（安装时的实际 2.x caret 版本），且 `devDependencies` 未新增 `unplugin-auto-import`/`unplugin-vue-components`。
- [ ] 3. 运行构建并记录主 chunk 体积，与基线对比（页面尚未使用 naive，体积变化应接近 0）：

```bash
npm --prefix frontend run build
```

预期：退出码 0，输出包含 `✓ built in`，主 chunk 仍约 `1,65x kB │ gzip: 52x kB`；记录实际数值到 PR 描述。

**测试/验证：**

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

预期：`Test Files 25 passed (25)`、`Tests 124 passed (124)`；构建退出码 0。

**完成标准：** lockfile 已更新；测试与构建双绿；未添加自动导入插件。

**注意事项/已知风险：** `npm install` 可能顺带更新少量传递依赖，属正常；只提交 `package.json` + `package-lock.json` 两个文件。

- [ ] 提交：`git add frontend/package.json frontend/package-lock.json && git commit -m "chore: add naive-ui dependency"`

### Task P0-2：新建 `src/theme/naive.ts`（themeOverrides + statusTone）

**目标：** 建立 Naive 主题映射与状态色单一函数，品牌值对齐 `styles.css` 的 `:root`。

**涉及文件：**
- 新建 `frontend/src/theme/naive.ts`
- 新建 `frontend/src/tests/ui-foundation.test.ts`（本计划新增测试文件，规格 §10 未列；理由：`statusTone`/`naiveThemeOverrides` 需要直接单测；后续 P0 任务继续向该文件追加 describe）

**实现步骤：**
- [ ] 1. 先写失败测试：在 `ui-foundation.test.ts` 新增 `describe('naive theme', ...)`，导入 `{ naiveThemeOverrides, statusTone, priorityTone }`，断言：
  - `naiveThemeOverrides.common?.primaryColor === '#0b6a58'`；
  - `statusTone('in_progress') === 'success'`、`statusTone('proposed') === 'warning'`、`statusTone('completed') === 'completed'`、`statusTone('rejected') === 'error'`、`statusTone('disabled') === 'muted'`、`statusTone('unknown-status') === 'muted'`；
  - `priorityTone('urgent') === 'error'`、`priorityTone('high') === 'warning'`、`priorityTone('normal') === 'muted'`、`priorityTone('low') === 'completed'`。
- [ ] 2. 运行 `npm --prefix frontend test -- src/tests/ui-foundation.test.ts`，预期模块不存在导致失败。
- [ ] 3. 实现 `frontend/src/theme/naive.ts`：
  - 导出 `type StatusTone = 'success' | 'warning' | 'completed' | 'error' | 'muted'`；
  - 导出 `naiveThemeOverrides: GlobalThemeOverrides`（`import type { GlobalThemeOverrides } from 'naive-ui'`），按规格 §4.2 映射表逐项赋值：`common` 的 `primaryColor/primaryColorHover/primaryColorPressed/primaryColorSuppl`、`successColor/warningColor/errorColor/infoColor`、`borderRadius`、`textColorBase/textColor1/textColor2/textColor3`、`borderColor/dividerColor`、`bodyColor/cardColor/modalColor/popoverColor/tableColor`、`fontFamily`；`Button.heightMedium/heightSmall/borderRadiusMedium/fontWeight`、`Tag.borderRadius`、`Card.borderRadius`、`DataTable.thColor/tdColor/borderColor`、`Input.borderRadius`；
  - 文件头注释标注：品牌唯一权威值仍在 `styles.css` 的 `:root`，此处为同值字面量，修改时两处同步；
  - `statusTone(status)` 按规格 §4.2 四组状态表返回 tone：绿色组 `active/in_progress/final/done/resolved/applied/approved/on_track/succeeded → 'success'`；琥珀组 `pending/draft/ready/planned/open/proposed/scheduled/queued/requesting/at_risk/changes_requested → 'warning'`；完成组 `completed/skipped/interrupted → 'completed'`；红灰组 `rejected/canceled/withdrawn/superseded/dropped/failed/off_track → 'error'`，`disabled/archived/dismissed → 'muted'`；未知状态统一 `'muted'`（本计划裁决：未知回退中性色，不误报错误）；
  - `priorityTone(priority)`：`urgent→'error'`、`high→'warning'`、`normal→'muted'`、`low→'completed'`。
- [ ] 4. 运行聚焦测试通过。

**测试/验证：**

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts
npm --prefix frontend run build
```

预期：该文件全部通过；构建退出码 0（`theme/naive.ts` 类型被 `vue-tsc` 校验）。

**完成标准：** 映射与规格 §4.2 逐项一致；`statusTone`/`priorityTone` 单测通过。

**注意事项/已知风险：** `naiveThemeOverrides` 的键名必须以 Naive 2.x 类型为准（`vue-tsc` 会兜底）；不要删除 `:root` 里的既有 token。

- [ ] 提交：`git add frontend/src/theme/naive.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: add naive theme overrides and status tones"`

### Task P0-3：测试底座（jsdom 补丁 + `renderWithProviders` + Naive 冒烟）

**目标：** 落实规格 §11.1 的 jsdom 适配与弹出层/data-table 测试约定，并提供可复用 provider 包裹渲染器。

**涉及文件：**
- 修改 `frontend/src/tests/setup.ts`
- 新建 `frontend/src/tests/helpers.ts`
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加“naive smoke”describe）

**实现步骤：**
- [ ] 1. 在 `ui-foundation.test.ts` 追加失败测试：
  - 全局补丁断言：`expect(typeof window.matchMedia).toBe('function')`、`expect(typeof ResizeObserver).toBe('function')`、`expect(typeof Element.prototype.scrollTo).toBe('function')`；
  - provider 冒烟：用 `renderWithProviders` 渲染一个只含 `n-button` 的探针组件，`await screen.findByRole('button', { name: '冒烟' })`；
  - Teleport 冒烟：渲染一个在 `NDialogProvider` 内、点击后 `useDialog().warning({ title: '冒烟对话框' })` 的探针组件，`await screen.findByText('冒烟对话框')`；
  - data-table 冒烟：渲染 `NDataTable`，两列两行、`:pagination="{ page: 1, pageSize: 10, itemCount: 2 }"`、**不设置 `fixed` 列、不开启虚拟滚动**，断言 `await screen.findByText('行一')` 且 `document.querySelector('.n-data-table')` 非空。
- [ ] 2. 修改 `frontend/src/tests/setup.ts`（保留现有 `cleanup()`），在 `afterEach` 之前加入全局补丁：
  - `ResizeObserver`：空实现类（`observe`/`unobserve`/`disconnect` 三个 noop 方法）；
  - `window.matchMedia`：用 `Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: (query: string) => ({ matches: false, media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }) })`；
  - `Element.prototype.scrollTo`：noop（同时覆盖 `HTMLElement`；规格 §9 写 `HTMLElement.prototype.scrollTo`，§11.1 写 `Element.prototype.scrollTo`，本计划裁决在 `Element.prototype` 上定义以避免遗漏）。
- [ ] 3. 新建 `frontend/src/tests/helpers.ts`：导出 `renderWithProviders(component, options?)`，内部用 `@testing-library/vue` 的 `render` 包裹 `NConfigProvider(:theme-overrides="naiveThemeOverrides" :locale="zhCN" :date-locale="dateZhCN") → NMessageProvider → NDialogProvider`，透传 `options`（含 `props`/`global.stubs`/`global.mocks`）并返回原 render 结果；文件头注释写明“弹出层用全局 `screen` 查询；表格不测滚动”。
- [ ] 4. **测试/验证：**运行聚焦测试与全量测试：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts
npm --prefix frontend test
```

预期：`ui-foundation.test.ts` 全绿；全量 `Test Files 26 passed (26)`（25 + 1）、无 failed。

**完成标准：** 三个 jsdom 补丁生效；provider/Teleport/data-table 冒烟通过；既有 25 个文件不受影响。

**注意事项/已知风险：** 不要在 `setup.ts` 里 monkey-patch `@testing-library/vue` 的 `render`；后续阶段由各任务把需要的测试文件显式改用 `renderWithProviders`。`matchMedia` stub 的 `addListener/removeListener` 不能省略（Naive 内部仍可能调用旧 API）。

- [ ] 提交：`git add frontend/src/tests/setup.ts frontend/src/tests/helpers.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "test: add naive jsdom setup and provider render helper"`

### Task P0-4：App.vue Provider 接入 + `AppAvatar` + `SessionUser.avatar_color`

**目标：** 让 `useMessage()/useDialog()` 在全应用可用；头像统一组件化并使用后端 `avatar_color`。

**涉及文件：**
- 修改 `frontend/src/App.vue`
- 修改 `frontend/src/auth/session.ts`
- 新建 `frontend/src/components/AppAvatar.vue`
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加 `AppAvatar` 断言）
- （`frontend/src/main.ts` 不改：provider 放在根组件 `App.vue` 即覆盖登录/注册与工作区，规格 §5.1 结构如此；如实现时发现必须挂载级 provider，再补 `main.ts` 并在 PR 说明）

**实现步骤：**
- [ ] 1. `session.ts`：`SessionUser` 增加 `avatar_color?: string`；`loadSession()` 逻辑不变。
- [ ] 2. 新建 `AppAvatar.vue`：props `{ name: string; color?: string | null; size?: number }`（默认 `size = 30`）；模板为 `<n-avatar class="app-avatar" :size="size" :color="color ?? undefined" :style="color ? undefined : { background: 'var(--green-soft)', color: 'var(--green-dark)' }" :aria-label="name">{{ initial }}</n-avatar>`，`initial = name.trim().slice(0, 1).toUpperCase() || '?'`；`n-avatar` 具名导入。
- [ ] 3. `App.vue` 模板外层包裹 `NConfigProvider`（`:theme-overrides="naiveThemeOverrides"`、`:locale="zhCN"`、`:date-locale="dateZhCN"`）→ `NMessageProvider` → `NDialogProvider`，内部保留现有 `.app-shell` 与 `RouterView` 分支；具名导入 `NConfigProvider/NMessageProvider/NDialogProvider/zhCN/dateZhCN` 与 `naiveThemeOverrides`。
- [ ] 4. 顶栏把 `<span class="avatar avatar-small">{{ session.user.display_name.slice(0, 1).toUpperCase() }}</span>` 替换为 `<AppAvatar :name="session.user.display_name" :color="session.user.avatar_color" :size="30" />`，保留 `RouterLink` 到 `/account` 与 display_name 文本。
- [ ] 5. 在 `ui-foundation.test.ts` 追加：用 `renderWithProviders(AppAvatar, { props: { name: '林宇', color: '#123456' } })` 断言可见文本 `林` 且根节点带 `n-avatar` class；缺省 color 时根节点 style 含 `green-soft`（断言 style 字符串包含 `green-soft` 即可，不测具体色值）。
- [ ] 6. **测试/验证：**运行聚焦与全量测试：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts src/tests/app-shell.test.ts
npm --prefix frontend test
```

预期：`app-shell.test.ts` 5 个用例仍全绿（导航、管理员门控、退出、会话过期、插件加载）；全量无 failed。

**完成标准：** 根组件渲染于 Naive provider 内；顶栏使用 `AppAvatar`；`app-shell` 测试保持通过。

**注意事项/已知风险：** `app-shell.test.ts` mock 了 `vue-router`，App.vue 新增的 provider 导入不影响；`NMessageProvider` 需要 DOM，jsdom 已由 P0-3 覆盖。若 `NAvatar` 的 `style` 合并行为与预期不同，改为在外层包 `<span class="app-avatar-fallback">`，但必须保留 `n-avatar` class。

- [ ] 提交：`git add frontend/src/App.vue frontend/src/auth/session.ts frontend/src/components/AppAvatar.vue frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: wrap app in naive providers and add avatar component"`

### Task P0-5：`StatusPill` 重构为 `NTag` 薄封装 + 旧状态色 CSS 收敛

**目标：** 保留组件名/props/`data-status` 兼容既有测试与调用点，视觉交给 `NTag` + `statusTone`。

**涉及文件：**
- 修改 `frontend/src/components/StatusPill.vue`
- 修改 `frontend/src/styles.css`（删除 `.status-pill[data-status]` 四组规则与 `.ai-task-status[data-status]` 覆盖组）
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加 `StatusPill` 断言）
- 既有测试（`ai-tasks.test.ts` 等）预期不改、保持全绿

**实现步骤：**
- [ ] 1. 在 `ui-foundation.test.ts` 追加失败测试：`renderWithProviders(StatusPill, { props: { status: 'in_progress' } })` 后，`const pill = screen.getByText('进行中')`；断言 `pill` 有 class `status-pill`、有 `n-tag` class、`toHaveAttribute('data-status', 'in_progress')`；再用 `{ status: 'completed', kind: 'agenda' }` 断言文案来自 `utils/labels.ts`。
- [ ] 2. 重写 `StatusPill.vue`：保留 props `{ status: string; kind?: StatusKind; label?: string }`（默认 `kind: 'meeting'`）与 `text` computed；用 `NTag` 渲染，`:type` 由 `statusTone(props.status)` 映射（`'success'→'success'`、`'warning'→'warning'`、`'error'→'error'`、`'completed'→'default'` 且 `:color="{ color: 'var(--green-soft)', textColor: 'var(--green-dark)', borderColor: 'transparent' }"`、`'muted'→'default'`）；`class="status-pill"`、`:data-status="status"`、`:bordered="false"`、`:size="'small'"` 必须落地；`priority` kind 用 `priorityTone` 自定义 `:color`（红/琥珀/灰/浅灰）。
- [ ] 3. `styles.css`：删除 `.status-pill` 基础块与四组 `[data-status]` 颜色规则、`.ai-task-status[data-status]` 四条覆盖规则；保留 `.tag[data-priority]`（P6 处理）。文件里留一行注释说明状态色单一来源是 `theme/naive.ts::statusTone`。
- [ ] 4. **测试/验证：**运行受影响既有测试与全量测试：

```bash
npm --prefix frontend test -- src/tests/ai-tasks.test.ts src/tests/meetings-view.test.ts src/tests/home-attention.test.ts src/tests/admin-plugins.test.ts src/tests/account-admin.test.ts src/tests/project-workspace.test.ts src/tests/agenda-workbench.test.ts src/tests/ui-foundation.test.ts
npm --prefix frontend test
```

预期：既有断言（`toHaveClass('status-pill','ai-task-status')`、`data-status`）不变仍通过；全量无 failed。

**完成标准：** `StatusPill` 输出 `NTag` + `status-pill` + `data-status`；CSS 中不再有旧状态色分组。

**注意事项/已知风险：** Naive `NTag` 的属性透传必须落到根节点；若 `data-status` 丢失，用外层 `<span>` 包裹并同时保留 class 与属性（不可丢弃 `data-status`，既有测试依赖它）。

- [ ] 提交：`git add frontend/src/components/StatusPill.vue frontend/src/styles.css frontend/src/tests/ui-foundation.test.ts && git commit -m "refactor: rebuild status pill on naive tag"`

### Task P0-6：`utils/capabilities.ts` + `utils/activity.ts`

**目标：** 提供权限判定唯一入口与活动台账事件文案映射，供 P4/P5/P6 直接复用。

**涉及文件：**
- 新建 `frontend/src/utils/capabilities.ts`
- 新建 `frontend/src/utils/activity.ts`
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加能力与文案断言）

**实现步骤：**
- [ ] 1. 追加失败测试：
  - `can({ capabilities: { can_manage: false, can_contribute: false, can_comment: false } }, 'contribute') === false`；`can({ capabilities: { can_manage: true, can_contribute: true, can_comment: true } }, 'manage') === true`；`can(null, 'view') === false`；`can({}, 'comment') === false`（缺字段即无权限）。
  - `activityLabel('project.created', { name: 'MeetFlow' })` 返回中文且包含 `MeetFlow`；`activityLabel('agenda.started', { title: '发布方案' })` 包含 `发布方案`；`activityLabel('unknown.event', {})` 原样返回 `'unknown.event'`。
- [ ] 2. 实现 `utils/capabilities.ts`：

  ```ts
  export type WorkspaceCapability = 'manage' | 'contribute' | 'comment' | 'view'
  export function can(
    source: { capabilities?: Partial<Record<`can_${WorkspaceCapability}`, boolean>> } | null | undefined,
    capability: WorkspaceCapability,
  ): boolean
  ```

  实现为读取 `source?.capabilities?.[`can_${capability}`] === true`；不读取 `session.user.role`。
- [ ] 3. 实现 `utils/activity.ts`：`activityLabel(eventType: string, payload?: Record<string, unknown> | null): string`，用模板表覆盖后端实际产生的全部事件类型（已核对后端 `event_type=` 调用点）：`project.created/project.updated/project.progress_posted/project.progress_updated/project.deleted`、`meeting.created/meeting.updated/meeting.amended/meeting.canceled/meeting.completed/meeting.reopened`、`agenda.started/agenda.reordered/agenda.converted_to_question/agenda.copied/agenda.outcomes_migrated`、`attachment.uploaded/attachment.deleted`、`decision.created/decision.updated/decision.reviewed/decision.finalized/decision.withdrawn/decision.superseded`、`action.created`、`question.created/question.updated/question.scheduled/question.resolved`；文案参数优先取 `payload.title`、其次 `payload.name`、`payload.filename`；未知类型返回 `eventType` 原文。所有模板必须容忍缺参（缺参时省略括号内容而不是输出 `undefined`）。
- [ ] 4. **测试/验证：**运行聚焦测试与构建：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts
npm --prefix frontend run build
```

预期：聚焦测试全绿；构建退出码 0。

**完成标准：** 两个工具函数签名稳定；测试覆盖“缺 capabilities 即 false”与“未知事件回退原文”。

**注意事项/已知风险：** 不要在这两个工具里发起网络请求；`activityLabel` 是纯函数，便于 P5 台账单测。

- [ ] 提交：`git add frontend/src/utils/capabilities.ts frontend/src/utils/activity.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: add capability and activity label helpers"`

### Task P0-7：阶段门禁（全量测试 + 构建 + 后端未动检查）

**目标：** 确认 P0 底座在既有全量测试上无回归，且后端零改动，可合并为第一个 PR。

**涉及文件：** 无源码新增；验证 P0-1 至 P0-6 涉及的全部文件。

**实现步骤：**
- [ ] 1. **测试/验证：**运行全量前端测试并记录实际文件数/用例数：

```bash
npm --prefix frontend test
```

预期：`Test Files 26 passed (26)`（25 + `ui-foundation.test.ts`），无 failed。

- [ ] 2. 运行生产构建：

```bash
npm --prefix frontend run build
```

预期：退出码 0；仅有已知 chunk 体积警告。

- [ ] 3. 检查改动边界与后端零改动：

```bash
git diff --check
git status --short backend/
git status --short
```

预期：`git diff --check` 无输出；`backend/` 无任何文件。

- [ ] 4. 推送分支并创建阶段 PR，描述中包含：基线 25/124 → 当前文件/用例数、构建体积对比、`naive-ui` 版本、无自动导入插件的说明。**等待用户合并后再开始 P1。**

**完成标准：** 测试/构建双绿、diff 边界正确、PR 已创建并等待合并。

**注意事项/已知风险：** 若任何既有测试因 `StatusPill`/provider 变更失败，必须在本阶段修好，不得带入 P1。

---

# P1 壳层与通用原语

> 阶段分支：`feature/ui-overhaul-p1`。完成侧边栏/顶栏骨架、未读徽标数据流、统一冲突对话框与页面标题收敛。

### Task P1-1：`useInboxUnread` 未读单例

**目标：** 登录后维护壳层未读数（来源 `GET /api/inbox/changes?cursor=0&limit=1` 的 `unread_count`），支持 60s 轮询、路由切换、回到前台与已读操作刷新。

**涉及文件：**
- 新建 `frontend/src/composables/useInboxUnread.ts`
- 新建 `frontend/src/tests/inbox-unread.test.ts`（本计划新增测试文件，规格 §10 未列；理由：轮询节奏与回退策略需要确定性单测）

**实现步骤：**
- [ ] 1. 先写失败测试（`vi.useFakeTimers()` + mock `../api/client`）：
  - `startUnreadPolling(fakeRouter)` 立即请求一次 `/api/inbox/changes?cursor=0&limit=1`，把 `unread_count: 3` 写入导出的 `unreadCount`；
  - `vi.advanceTimersByTime(60_000)` 后请求次数 +1；
  - 触发 `document` 的 `visibilitychange`（`Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })`）后请求次数再 +1；
  - `fakeRouter.afterEach` 捕获的回调被调用时也会刷新；
  - 首选请求 reject 时回退 `GET /api/inbox` 的 `unread_count`；
  - `resetUnread()` 归零；调用 `startUnreadPolling` 返回的停止函数后清掉定时器（advance 不再新增请求）。
- [ ] 2. 实现模块级单例（不引入 Pinia）：

  ```ts
  export const unreadCount = ref(0)
  export async function refreshUnread(): Promise<void>
  export function resetUnread(): void
  export function startUnreadPolling(router: { afterEach: (cb: () => void) => void }): () => void
  ```

  `refreshUnread()` 先请求 `/api/inbox/changes?cursor=0&limit=1` 取 `unread_count`；失败则请求 `/api/inbox` 取 `unread_count`；两者都失败静默保留旧值（不打断页面）。`startUnreadPolling` 立即刷新一次、`setInterval` 60s、注册 `router.afterEach` 与 `visibilitychange` 监听，返回的清理函数移除监听与定时器（可重复调用幂等）。
- [ ] 3. **测试/验证：**运行聚焦测试：

```bash
npm --prefix frontend test -- src/tests/inbox-unread.test.ts
```

预期：全绿（fake timers 下无真实等待）。

**完成标准：** 单例导出 `unreadCount`/`refreshUnread`/`resetUnread`/`startUnreadPolling`；回退链与轮询节奏符合规格 §5.3。

**注意事项/已知风险：** 收件箱页面**不持有定时器**（双轮询禁止）；`startUnreadPolling` 只由壳层调用。测试结束务必 `vi.useRealTimers()` 并调用停止函数。

- [ ] 提交：`git add frontend/src/composables/useInboxUnread.ts frontend/src/tests/inbox-unread.test.ts && git commit -m "feat: add shell inbox unread singleton"`

### Task P1-2：`AppSidebar` 改 `n-layout-sider` + `n-menu` + 收件箱徽标

**目标：** 侧边栏结构迁移到 Naive，保留既有导航地标与角色门控，并显示未读数。

**涉及文件：**
- 修改 `frontend/src/components/AppSidebar.vue`
- 修改 `frontend/src/tests/app-shell.test.ts`
- 修改 `frontend/src/tests/ui-foundation.test.ts`（如需 NMenu 冒烟补充）

**实现步骤：**
- [ ] 1. 先更新 `app-shell.test.ts` 断言（有意更新，规格 §11.2 允许）：导航地标改为 `<nav aria-label="工作区导航">`/`<nav aria-label="管理员导航">` 包裹的 `NMenu`，链接仍按名字可查：
  - 工作区菜单项 `为你/项目/会议/行动项/决策/收件箱/AI 任务`，每项渲染为 `RouterLink`（`renderLabel` 返回 `h(RouterLink, { to: link.to }, { default: () => link.label })`），因此 `within(nav).getByRole('link', { name: label })` 仍成立；
  - 每项 `renderIcon` 返回 `h(NIcon, null, { default: () => h(icon) })`，保留 `link.querySelector('svg') !== null` 断言；
  - 管理员分组仍 `session.user?.role === 'admin'` 条件渲染；
  - 新增：当 `unreadCount > 0` 时收件箱链接内出现 `NBadge` 且可读文本包含数字（badge 用 `aria-hidden="true"` 包裹，避免污染链接可访问名，链接改为显式 `aria-label="收件箱"`）。
- [ ] 2. **测试/验证：**运行 `npm --prefix frontend test -- src/tests/app-shell.test.ts`，预期新断言失败（当前是纯 `<aside>` + `RouterLink`）。
- [ ] 3. 重写 `AppSidebar.vue`：
  - 外层 `NLayoutSider`（`:width="232"`、`:native-scrollbar="false"`），保留品牌区 “M” 字标 + “MeetFlow / 团队会议工作区”；
  - `NMenu` 通过 `:options` 传入 `{ key, label, icon, to }`，`renderLabel` 渲染 `RouterLink`、`renderIcon` 渲染 `NIcon` + Lucide；高亮用 `useRoute()`（测试 mock 需补 `useRoute: () => ({ path: '/' })`），也可用 `:value="route.path"`；
  - 管理员分组用第二个 `NMenu` 前的分组标签承载；
  - 收件箱项 `renderLabel` 里包 `NBadge :value="unreadCount" :show="unreadCount > 0"`；
  - 从 `useInboxUnread` 导入 `unreadCount`（**不在侧边栏启动轮询**，轮询在 P1-3 的 App.vue 统一启动）。
- [ ] 4. 更新测试 mock（`vue-router` 增加 `useRoute`），运行聚焦与全量：

```bash
npm --prefix frontend test -- src/tests/app-shell.test.ts
npm --prefix frontend test
```

预期：`app-shell.test.ts` 5 个用例 + 新增徽标用例全绿；全量无 failed。

**完成标准：** 导航可访问性地标与链接语义不变；管理员门控不变；未读数可在侧边栏显示。

**注意事项/已知风险：** `NMenu` 默认渲染 `div` 而非链接，必须通过 `renderLabel` 包 `RouterLink`；若 `NLayoutSider` 在 jsdom 下需要显式高度，样式放到 `styles.css` 的侧边栏类即可，不改测试。

- [ ] 提交：`git add frontend/src/components/AppSidebar.vue frontend/src/tests/app-shell.test.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: rebuild sidebar with naive menu and unread badge"`

### Task P1-3：`App.vue` 顶栏用户下拉 + 铃铛 + 轮询接入

**目标：** 顶栏改为用户 `n-dropdown`（账号设置/退出登录）+ 未读铃铛；壳层统一启动未读轮询。

**涉及文件：**
- 修改 `frontend/src/App.vue`
- 修改 `frontend/src/tests/app-shell.test.ts`

**实现步骤：**
- [ ] 1. 先更新 `app-shell.test.ts`：
  - “退出登录”用例改为：点击触发器 `getByRole('button', { name: '账户菜单' })` → `await screen.findByText('退出登录')`（`NDropdown` 菜单项 Teleport）→ 点击菜单项 → 断言 `apiMock` 收到 `/api/auth/logout`、`session.user` 为 null、`pushMock('/login')`；
  - 新增铃铛用例：mock `/api/inbox/changes?cursor=0&limit=1` 返回 `{ notifications: [], next_cursor: 4, has_more: false, unread_count: 2 }`，渲染 App 后 `await waitFor` 断言 `getByRole('button', { name: '收件箱' })` 存在且其容器文本包含 `2`；点击后 `pushMock('/inbox')`；
  - `vue-router` mock 补 `useRoute: () => ({ path: '/' })`、`afterEach` 记录回调。
- [ ] 2. 修改 `App.vue`：
  - 顶栏右侧用 `NDropdown`（options：`账号设置`、`退出登录`，`:trigger="'click'"`），触发器为 `<button type="button" aria-label="账户菜单"><AppAvatar .../><span>{{ session.user.display_name }}</span></button>`；`onSelect` 分发到 `router.push('/account')` 与 `logout()`；
  - 铃铛：`<button type="button" aria-label="收件箱" @click="router.push('/inbox')"><NIcon><Bell :size="18" aria-hidden="true" /></NIcon></button>`，用 `NBadge :value="unreadCount" :show="unreadCount > 0"` 包裹 `Bell`；
  - 用 `watch(() => session.user, ...)` 管理轮询：有用户时保存 `startUnreadPolling(router)` 返回的停止函数；登出/`clearSession()`/会话过期时调用停止函数 + `resetUnread()`；`onBeforeUnmount` 同样停止；
  - 移除现有纯文本“退出”按钮与旧 `.account-menu` 结构，保留 `workspace-topbar` 容器与“共享工作区”标签。
- [ ] 3. **测试/验证：**运行聚焦与全量：

```bash
npm --prefix frontend test -- src/tests/app-shell.test.ts src/tests/inbox-unread.test.ts
npm --prefix frontend test
```

预期：全绿；退出、会话过期、插件加载、管理员导航用例保持。

**完成标准：** 顶栏只有下拉式账号入口与铃铛；未读轮询只在壳层启动/停止；登出清零。

**注意事项/已知风险：** `NDropdown` 的菜单项渲染在 body，测试必须用 `findByText`；`apiMock` 对 `/api/inbox/changes` 的 mock 要覆盖 App 挂载时的一次刷新，否则会出现未处理的 reject（用 `mockImplementation` 兜底返回 `{ unread_count: 0 }`）。

- [ ] 提交：`git add frontend/src/App.vue frontend/src/tests/app-shell.test.ts && git commit -m "feat: add topbar account dropdown and inbox bell"`

### Task P1-4：`VersionConflictDialog` → `n-modal` + `useVersionedSave`

**目标：** 统一 409 `version_conflict` 处理原语，保持既有 props/emits 与双栏对比语义。

**涉及文件：**
- 修改 `frontend/src/components/VersionConflictDialog.vue`
- 新建 `frontend/src/composables/useVersionedSave.ts`
- 新建 `frontend/src/tests/versioned-save.test.ts`（本计划新增测试文件，规格 §10 未列；理由：composable 与对话框需要独立单测）
- 修改 `frontend/src/tests/agenda-workbench.test.ts`（仅在断言依赖旧 `.conflict-dialog` DOM 时；当前无此断言，预期不改）

**实现步骤：**
- [ ] 1. 先写失败测试 `versioned-save.test.ts`：
  - composable：save 回调抛 `ApiError(409, 'version_conflict', '内容已更新', { actual_version: 4 })`，断言 `conflict.value` 为真且含 `actualVersion: 4`；调用 `retryWith(4)` 后 save 回调收到 `4` 且 `conflict` 清空；`reset()` 清空；非 409 错误不进入 conflict（进入 `error`）。
  - 对话框：用 `renderWithProviders(VersionConflictDialog, { props: { localMarkdown: '本地', serverMarkdown: '服务器', actualVersion: 4 } })`，断言 `await screen.findByText('内容已被其他成员更新')`、`本地草稿`/`服务器版本` 两栏、`复制本地草稿`/`载入服务器版本`/`用本地草稿覆盖` 三个按钮可点并发出对应 `close/reload/overwrite(4)` 事件。
- [ ] 2. 实现 `useVersionedSave.ts`：

  ```ts
  export function useVersionedSave<T>(save: (version: number) => Promise<T>, getVersion: () => number): {
    conflict: Ref<{ actualVersion: number; error: unknown } | null>
    saving: Ref<boolean>
    error: Ref<string>
    submit: () => Promise<T | null>
    retryWith: (actualVersion: number) => Promise<T | null>
    reset: () => void
  }
  ```

  判定条件严格为 `error instanceof ApiError && error.status === 409 && error.code === 'version_conflict'`；`actualVersion` 取 `Number(error.details?.actual_version ?? getVersion())`。**本计划不修改 `src/api/client.ts`**；`ApiError` 从 `../api/client` 具名导入即可。
- [ ] 3. 重写 `VersionConflictDialog.vue`：用 `NModal`（`preset="card"`、`:show="true"`、`:mask-closable="false"`、`:auto-focus="false"`、`:title="'内容已被其他成员更新'"`、`style="width: min(900px, 100%)"`），保留 props `{ localMarkdown, serverMarkdown, actualVersion }` 与 emits `{ close, reload, overwrite: [version: number] }`；内容保留 `<pre>` 双栏与三个按钮文案；关闭按钮改为 `NButton quaternary` + `X` 图标 + `aria-label="关闭"`。
- [ ] 4. **测试/验证：**运行聚焦与相关测试：

```bash
npm --prefix frontend test -- src/tests/versioned-save.test.ts src/tests/agenda-workbench.test.ts src/tests/use-meeting-workspace.test.ts
```

预期：全绿；`AgendaDetail` 的冲突恢复路径行为不变（`@reload="emit('changed')"` 等）。

**完成标准：** `useVersionedSave` 供 P5/P6 所有 `expected_version` 实体复用；对话框行为与文案与规格 §6.2 一致。

**注意事项/已知风险：** `NModal` 内 `pre` 的滚动由 CSS 控制，jsdom 不测滚动；`NModal` 默认有动画，测试一律 `findByText`。

- [ ] 提交：`git add frontend/src/components/VersionConflictDialog.vue frontend/src/composables/useVersionedSave.ts frontend/src/tests/versioned-save.test.ts && git commit -m "refactor: unify version conflict handling"`

### Task P1-5：`PageHeader` 字号收敛 + 抽屉/确认模式约定落地

**目标：** 页面标题从巨型 `clamp(2.4rem, 5vw, 4rem)` 收敛为 28/20/16/14 层级；把规格 §6.1 抽屉表单与 §4.5 确认模式固化为可复用约定（样式注释 + 组件结构模板）。

**涉及文件：**
- 修改 `frontend/src/components/PageHeader.vue`
- 修改 `frontend/src/styles.css`（`.workspace-page-heading h1` 字号、`h1` 全局 clamp、`.page` 布局宽度）
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加 PageHeader 断言）

**实现步骤：**
- [ ] 1. `ui-foundation.test.ts` 追加：`renderWithProviders(PageHeader, { props: { eyebrow: 'E', title: '标题', summary: '摘要' } })`，断言 `getByRole('heading', { level: 1, name: '标题' })` 存在、class `workspace-page-heading` 存在、摘要文本可见。
- [ ] 2. `PageHeader.vue`：不改 props/slot 结构，保留 `workspace-page-heading`、`page-header-actions`、`#meta`/`#actions` 插槽。
- [ ] 3. `styles.css`：
  - `.workspace-page-heading h1 { font-size: 28px; line-height: 1.2; letter-spacing: -.02em; }`；`h2` 20px、`h3` 16px、正文 14px/1.65；
  - 全局 `h1` 巨型 `clamp` 移除后，为 `.auth-intro h1` 与 `.auth-card h1` 显式保留现有字号；
  - 在文件顶部注释块写明 §6.1 约定：创建/编辑用右侧 `n-drawer`（`:width="'min(560px, 100vw)'"`、`label-placement="top"`、脚部取消 + 主按钮 `:loading`、`:mask-closable="!saving"`）；确认用 `n-popconfirm`，不够用时 `n-dialog`；瞬时反馈 `useMessage()`；错误面保留行内 `n-alert`。
- [ ] 4. **测试/验证：**运行相关测试与全量：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts src/tests/home-attention.test.ts src/tests/project-workspace.test.ts src/tests/app-shell.test.ts
npm --prefix frontend test
```

预期：全绿（这些页面标题断言均为 `getByRole('heading', { name })`，不依赖字号）。

**完成标准：** 工作区页头字号 28px；登录品牌区字号不退化；约定写入样式注释供后续任务引用。

**注意事项/已知风险：** 不要在 P1 迁移所有页面到抽屉（P2-P6 各自完成）；本任务只收敛标题与建立约定。

- [ ] 提交：`git add frontend/src/components/PageHeader.vue frontend/src/styles.css frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: converge page header typography"`

### Task P1-6：阶段门禁

**目标：** 确认 P1 壳层与通用原语在全量测试与构建下无回归，产出可合并的 P1 PR。

**涉及文件：** 无新增源码；验证 P1-1 至 P1-5 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. `npm --prefix frontend test`：预期 `Test Files 28 passed (28)`（26 + `versioned-save` + `inbox-unread`），无 failed。
- [ ] 2. `npm --prefix frontend run build`：退出码 0。
- [ ] 3. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 4. 推送 `feature/ui-overhaul-p1` 并创建 PR（描述含：壳层说明、`app-shell` 有意更新的断言、未读轮询策略）。等待用户合并后再开始 P2。

**完成标准：** 全量测试与构建双绿、后端零改动、P1 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；PR 描述必须列出有意更新的测试断言。

---

# P2 认证与账号

> 阶段分支：`feature/ui-overhaul-p2`。三页迁 `n-form` + `n-input`，错误用 `n-alert`，成功提示用 `n-message`。

### Task P2-1：`LoginView` 迁移 `n-form`

**目标：** 登录表单获得校验反馈，错误改为 `n-alert type="error"`，保留左品牌区 + 右卡片布局与文案。

**涉及文件：**
- 修改 `frontend/src/views/LoginView.vue`
- 修改 `frontend/src/tests/auth.test.ts`

**实现步骤：**
- [ ] 1. 更新 `auth.test.ts`：所有 `render(LoginView)` 改为 `renderWithProviders(LoginView, ...)`（从 `./helpers` 具名导入）；保留 `getByLabelText('用户名')`/`getByLabelText('密码')`（Naive `n-form-item` 自动 `for` 关联；若查询失败则给 `n-input` 加同名 `aria-label`）；错误文案断言 `await screen.findByRole('alert')`；新增“空表单提交不请求后端”用例：点击提交后 `expect(apiMock).not.toHaveBeenCalled()`。
- [ ] 2. **测试/验证：**运行 `npm --prefix frontend test -- src/tests/auth.test.ts`，预期 provider/控件相关断言失败。
- [ ] 3. 重写 `LoginView.vue`：
  - `n-form`（`label-placement="top"`、`:show-require-mark="false"`）+ `n-form-item`（rules：用户名必填、密码必填）+ `n-input`（用户名 `autocomplete="username"`；密码 `type="password" show-password-on="click"`）+ 提交 `n-button type="primary" block :loading="saving"`；
  - 本页错误沿用规格 §7.1：行内 `n-alert type="error"`；错误码 `invalid_credentials`、`account_pending/rejected/disabled` 的 `error.message` 原文展示；
  - 保留 `.auth-layout`/`.auth-intro` 左品牌区与 `.auth-card` 右卡片结构、全部品牌文案；
  - 移除手写 `<form>` 校验与自定义 notice（`.notice-error` 类保留到 P7 清理）。
- [ ] 4. 运行聚焦与全量：

```bash
npm --prefix frontend test -- src/tests/auth.test.ts src/tests/registration-error.test.ts
npm --prefix frontend test
```

预期：登录成功跳转与错误码用例全绿；全量无 failed。

**完成标准：** 空表单不触发请求；错误码原文展示；布局与文案不变。

**注意事项/已知风险：** `n-form` 校验是异步的，测试提交后需 `await`；`useMessage()` 若在本页使用，测试必须走 `renderWithProviders`。

- [ ] 提交：`git add frontend/src/views/LoginView.vue frontend/src/tests/auth.test.ts && git commit -m "feat: move login form to naive"`

### Task P2-2：`RegisterView` 迁移 `n-form`

**目标：** 注册表单校验与错误展示迁移；保留注册关闭/用户名占用错误原文。

**涉及文件：**
- 修改 `frontend/src/views/RegisterView.vue`
- 修改 `frontend/src/tests/registration-error.test.ts`

**实现步骤：**
- [ ] 1. 更新 `registration-error.test.ts`：改用 `renderWithProviders`；保留 `registration_closed`/`username_taken` 的 `role="alert"` 断言；新增空表单不请求断言。
- [ ] 2. 重写表单：字段与后端契约一致（用户名、显示名称、密码 min 12）；`n-form` rules 必填与密码长度 ≥12；密码 `n-input type="password" show-password-on="click"`；提交 `n-button type="primary" block :loading`；错误 `n-alert type="error"`。
- [ ] 3. 保留成功态结构（成功图标 `✓` 字形留到 P7 图标清扫处理，本任务不得删除）；**测试/验证：** 运行：

```bash
npm --prefix frontend test -- src/tests/registration-error.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 注册成功/失败路径与错误码展示不变；仅控件与校验实现变化。

**注意事项/已知风险：** 密码规则只做“至少 12 位”的前端提示，不新增后端没有的确认字段。

- [ ] 提交：`git add frontend/src/views/RegisterView.vue frontend/src/tests/registration-error.test.ts && git commit -m "feat: move registration form to naive"`

### Task P2-3：`AccountView` 迁移 + 成功提示

**目标：** 账号设置页校验新密码并显式提示“密码已修改，请重新登录”后再跳转登录。

**涉及文件：**
- 修改 `frontend/src/views/AccountView.vue`
- 修改 `frontend/src/tests/account-admin.test.ts`

**实现步骤：**
- [ ] 1. 更新 `account-admin.test.ts` 的账号设置部分：`renderWithProviders`；新增成功路径断言 `await screen.findByText('密码已修改，请重新登录')`（`n-message` 渲染在 body，用全局 `findByText`）并断言跳转 `/login`；保留 `wrong_password` 原文行内展示。
- [ ] 2. 重写 `AccountView.vue`：`n-card` + `n-form`；新密码 rules 必填且 ≥12；提交 `n-button type="primary" :loading`；成功后 `useMessage().success('密码已修改，请重新登录')` 再执行现有登出/跳转；`wrong_password` 行内 `n-alert type="error"` 原文。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/account-admin.test.ts src/tests/app-shell.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 成功提示在跳转前可见；无新增状态库。

**注意事项/已知风险：** `useMessage` 的 API 不返回 promise；若组件在跳转前被卸载导致消息不可见，先同步调用 message 并延后一个 tick 再跳转（`await nextTick()` 或 `setTimeout(0)`），不要去掉提示。

- [ ] 提交：`git add frontend/src/views/AccountView.vue frontend/src/tests/account-admin.test.ts && git commit -m "feat: move account settings to naive form"`

### Task P2-4：阶段门禁

**目标：** 确认 P2 认证与账号三页在表单迁移后无回归，产出可合并的 P2 PR。

**涉及文件：** 无新增源码；验证 P2-1 至 P2-3 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. `npm --prefix frontend test` → `Test Files 28 passed (28)`，无 failed。
- [ ] 2. `npm --prefix frontend run build` → 退出码 0。
- [ ] 3. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 4. 推送并创建 `feature/ui-overhaul-p2` PR；等待用户合并后再开始 P3。

**完成标准：** 全量测试与构建双绿、后端零改动、P2 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；确认登录/注册错误码文案未被削弱。

---

# P3 首页与会议列表

> 阶段分支：`feature/ui-overhaul-p3`。首页卡片化 + 未读徽标 + `generated_at`；会议列表服务端筛选分页 + 创建抽屉。

### Task P3-1：`AttentionCard` 改版

**目标：** 关注卡使用 `n-thing` 结构、`attention-kind` 徽标与 `ChevronRight` 图标，保留原因文案聚合。

**涉及文件：**
- 修改 `frontend/src/components/AttentionCard.vue`
- 修改 `frontend/src/tests/home-attention.test.ts`

**实现步骤：**
- [ ] 1. `home-attention.test.ts` 增加断言：关注卡内不再有 `→` 文本（`expect(screen.queryByText('→')).not.toBeInTheDocument()`），且 `document.querySelector('.attention-card svg')` 非空；保留 `测试 reward`、`已逾期 · 有新回复` 文案断言。
- [ ] 2. 重写 `AttentionCard.vue`：外层 `RouterLink class="attention-card"`；内部用 `n-thing`（`:title`、description slot 放原因文案）；左侧保留 `attention-kind` 徽标（保留 `data-kind`；`AttentionItem` 暂无 actor 字段，本任务不新增字段）；右侧 `NIcon` + `ChevronRight`，`aria-hidden="true"`。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/home-attention.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 卡片视觉由 Naive 组件承载；`→` 字形从该组件移除。

**注意事项/已知风险：** `home-attention.test.ts` 用 `{ global: { stubs: { RouterLink } } }` 渲染 `HomeView`，若 `n-thing` 内 RouterLink 断言失败，改用 `renderWithProviders` 并保留 stub。

- [ ] 提交：`git add frontend/src/components/AttentionCard.vue frontend/src/tests/home-attention.test.ts && git commit -m "feat: restyle attention card"`

### Task P3-2：`HomeView` 卡片化 + 未读徽标 + 简报生成时间

**目标：** 三块内容用 `n-card`/`n-skeleton`/`n-empty`；头部显示 `/api/attention` 未读数；工作简报显示 `generated_at`。

**涉及文件：**
- 修改 `frontend/src/views/HomeView.vue`
- 修改 `frontend/src/tests/home-attention.test.ts`

**实现步骤：**
- [ ] 1. 先在 `home-attention.test.ts` 增加失败断言：
  - attention 响应带 `unread_count: 3` 时头部出现 `3 条未读提醒`；
  - work-brief 响应 `generated_at: '2026-07-29T02:00:00Z'` 时出现 `上次生成于` 前缀文本；
  - 加载态保留 `正在整理你的工作区…` 文案且可查询骨架（`document.querySelector('.n-skeleton')` 非空或在请求 resolve 前断言文案）。
- [ ] 2. 修改 `HomeView.vue`：
  - 保留 `<section aria-labelledby="priority-queue-title">` 与 `<aside aria-labelledby="upcoming-meetings-title">` 地标（测试依赖 `region`/`complementary` 与 `workspace-section`/`upcoming-panel` 类），内部内容改用 `n-card`；
  - 头部未读徽标：刷新按钮旁独立 `<span>未读提醒</span>` + `<NBadge :value="response.unread_count" :show="response.unread_count > 0" />`（避免污染按钮可访问名）；
  - 加载态用 `n-skeleton`（3 行）并保留“正在整理你的工作区…”；空态用 `n-empty` 并保留既有 `目前没有需要立即处理的事项`、`未来七天没有需要你参加的会议。` 文案；
  - 简报头增加 `generated_at` 显示：`<span v-if="workBrief?.generated_at">上次生成于 {{ formatDateTime(workBrief.generated_at) }}</span>`；
  - 保留 `PluginSlot slot="home.secondary-card"` 与 SSE 流式逻辑（`streamPluginAction`）、`workBriefRevision` 竞态保护不动。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/home-attention.test.ts
npm --prefix frontend test
```

预期：7 个既有用例 + 新断言全绿。

**完成标准：** 未读徽标与生成时间可见；SSE 与竞态行为不变。

**注意事项/已知风险：** 现有断言 `workBriefPanel.closest('aside') === null`——`n-card` 不得渲染为 `aside`；保持其父级 `section`。

- [ ] 提交：`git add frontend/src/views/HomeView.vue frontend/src/tests/home-attention.test.ts && git commit -m "feat: restyle home and surface unread and brief time"`

### Task P3-3：`MeetingParticipantEditor` 共享参与人编辑器

**目标：** 提供可复用的“成员 + 角色”参与人行编辑器，供会议创建抽屉（P3-4）与准备抽屉（P4-2）共用。

**涉及文件：**
- 新建 `frontend/src/components/MeetingParticipantEditor.vue`
- 修改 `frontend/src/utils/labels.ts`（新增 `PARTICIPATION_ROLE_LABELS`）
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加组件单测）

**实现步骤：**
- [ ] 1. 定义组件契约：props `{ modelValue: Array<{ user_id: string; participation_role: ParticipationRole }>; memberOptions: UserRef[]; disabled?: boolean }`，emits `{ 'update:modelValue': [value] }`；每行 `n-select`（成员，可搜索）+ `n-select`（角色：`host/recorder/presenter/attendee` → `主持/记录/主讲/参与`）+ 删除按钮（`X` 图标 + `aria-label="移除参与人"`）；底部 `n-button quaternary`“添加参与人”（默认角色 `attendee`）；`memberOptions` 去重并排除已选成员（保留当前已选）。
- [ ] 2. `ui-foundation.test.ts` 追加单测：给定两个成员，点“添加参与人”出现两行；“移除参与人”后 `modelValue` 更新事件被触发；`disabled` 时没有添加/删除按钮。
- [ ] 3. 在 `utils/labels.ts` 增加 `PARTICIPATION_ROLE_LABELS: Record<ParticipationRole, string>` 并在组件中使用。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts
npm --prefix frontend run build
```

预期：全绿；构建通过。

**完成标准：** 组件受控、纯展示/编辑，不自行请求数据（成员列表由宿主传入）。

**注意事项/已知风险：** 不要在组件内调用 API；参与者保存由宿主提交完整数组（后端全量替换）。

- [ ] 提交：`git add frontend/src/components/MeetingParticipantEditor.vue frontend/src/utils/labels.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: add reusable meeting participant editor"`

### Task P3-4：`MeetingCreateDrawer` + `MeetingsView` 服务端筛选分页

**目标：** 会议列表改服务端参数与“加载更多”；创建会议改右侧抽屉（含参与人角色选择）；搜索/系列筛选降级为“已加载页内”并注明范围。

**涉及文件：**
- 新建 `frontend/src/components/MeetingCreateDrawer.vue`
- 修改 `frontend/src/views/MeetingsView.vue`
- 修改 `frontend/src/tests/meetings-view.test.ts`
- 修改 `frontend/src/tests/global-workspace.test.ts`

**实现步骤：**
- [ ] 1. 先更新测试（有意更新，规格 §11.2）：
  - `meetings-view.test.ts`：mock 响应改为 `{ items: meetings, total: 3, limit: 50, offset: 0 }`；移除“当前显示 1 场会议。”断言，改为断言固定文案 `已加载 1 / 共 3 场会议` 与 `搜索与系列筛选仅作用于已加载页`；状态筛选断言改为 `waitFor` 检查 `apiMock` 调用路径包含 `status=completed`（`expect.stringContaining`）；`series_id` 用例保留（已加载页内过滤）。
  - `global-workspace.test.ts` 的“creates a meeting through its project-scoped endpoint”用例：改为打开 `新建会议` 抽屉后填写 `所属项目/会议标题/开始时间/结束时间`，断言 POST 载荷包含 `participants` 数组且含 `{ user_id: 'u1', participation_role: 'host' }`、`scheduled_start`/`scheduled_end` 为 ISO 字符串，再断言跳转 `/meetings/m2`。
- [ ] 2. 新建 `MeetingCreateDrawer.vue`：props `{ show: boolean; projects: Array<{ id: string; name: string }>; memberOptions: UserRef[]; defaultProjectId?: string }`，emits `{ close, created: [meeting] }`；`n-drawer placement="right" :width="'min(560px, 100vw)'"` + `n-form label-placement="top"`：所属项目 `n-select`（必填）、标题 `n-input`（必填）、开始/结束 `n-date-picker type="datetime"`（结束晚于开始校验）、会议目的 `n-input type="textarea"`、参与人 `MeetingParticipantEditor`（默认含当前用户为 host）；提交 `POST /api/projects/{projectId}/meetings`，载荷字段：`title/purpose_markdown/scheduled_start/scheduled_end/host_user_id/recorder_user_id/summary_markdown:''/raw_notes_markdown:''/participants`；提交中 `:mask-closable="!saving"`。
- [ ] 3. 修改 `MeetingsView.vue`：
  - 数据：`load(reset = true)` 请求 `/api/meetings?limit=50&offset=${offset}` + 服务器参数 `status/project_id/participant_user_id/start_after/start_before`；`加载更多` 在 `meetings.length < total` 时显示，`offset += 50` 追加；分组由已加载数据派生并显示范围说明；
  - 高级筛选面板：项目（服务器）、会议状态（服务器）、参与者（服务器 `participant_user_id`，选项来自 `/api/projects` 的 `memberships[].user` 聚合去重）、时间窗起止（`n-date-picker type="datetime"`，服务器）；系列筛选保留并注明范围；移除客户端状态/项目过滤；
  - 创建入口改为 `MeetingCreateDrawer`（不再内联表单）；`⌕` 字形改为 `NIcon` + `Search`（保留输入 `aria-label="搜索会议"`）。
- [ ] 4. **测试/验证：**运行聚焦与全量：

```bash
npm --prefix frontend test -- src/tests/meetings-view.test.ts src/tests/global-workspace.test.ts
npm --prefix frontend test
```

预期：全绿；`高级筛选` 的 `aria-expanded`/计数语义保留。

**完成标准：** 列表用服务端参数与加载更多；创建为抽屉且提交完整参与人数组；范围说明文案存在。

**注意事项/已知风险：** `n-date-picker` 的 `v-model` 是时间戳（`number | null`），提交前用 `new Date(ts).toISOString()` 转 ISO；既有测试的 `fireEvent.update` 对 Naive 日期选择器不生效。**本计划裁决：** 日期控件优先 `n-date-picker`；若 jsdom 驱动成本过高，允许在该抽屉内降级为受控 `input type="datetime-local"`（仅容器用 Naive），并在本任务 PR 说明原因。

- [ ] 提交：`git add frontend/src/components/MeetingCreateDrawer.vue frontend/src/views/MeetingsView.vue frontend/src/tests/meetings-view.test.ts frontend/src/tests/global-workspace.test.ts && git commit -m "feat: paginate meetings and add creation drawer"`

### Task P3-5：阶段门禁

**目标：** 确认 P3 首页与会议列表改版无回归，产出可合并的 P3 PR。

**涉及文件：** 无新增源码；验证 P3-1 至 P3-4 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. `npm --prefix frontend test` → `Test Files 28 passed (28)`，无 failed。
- [ ] 2. `npm --prefix frontend run build` → 退出码 0。
- [ ] 3. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 4. 推送并创建 `feature/ui-overhaul-p3` PR；等待用户合并后再开始 P4。

**完成标准：** 全量测试与构建双绿、后端零改动、P3 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；确认会议列表的范围说明文案存在且不误导。

---

# P4 会议工作区

> 阶段分支：`feature/ui-overhaul-p4`。最大阶段：生命周期操作、准备抽屉参与人编辑、议题命令、议题附件与元信息、材料/评论抽屉、完成链。执行顺序不能乱：先生命周期与准备抽屉，再议题，再附件/评论，最后完成链。

### Task P4-1：生命周期操作（取消 / 重开）+ API 封装

**目标：** 按状态渲染 `cancel`/`reopen` 操作；`canceled` 无重开入口；确认文案不承诺跳过议题或生成快照。

**涉及文件：**
- 修改 `frontend/src/api/meetings.ts`
- 修改 `frontend/src/views/MeetingWorkspaceView.vue`
- 修改 `frontend/src/tests/meeting-lifecycle.test.ts`
- 修改 `frontend/src/tests/meeting-workspace.test.ts`

**实现步骤：**
- [ ] 1. 扩展 `api/meetings.ts`：`export type LifecycleAction = 'start' | 'finish' | 'cancel' | 'reopen'`；`runMeetingLifecycle` 签名不变（`POST /api/meetings/{id}/{action}` + `{ expected_version }`）。
- [ ] 2. 更新/新增测试：
  - `draft`/`ready`：`开始会议` 与 `取消会议` 都在；点击 `取消会议` → 确认 → 断言 `POST /api/meetings/m1/cancel` body `{ expected_version: 4 }`；
  - `in_progress`：`取消会议` 确认文案只包含“会议将标记为已取消且不可重开”，不包含“跳过”“快照”字样；
  - `completed`：`重新打开` 存在，确认后断言 `POST /api/meetings/m1/reopen`；
  - `canceled`：不渲染 `重新打开`、`开始会议`、`结束会议`（fixture 增加 canceled 状态）；
  - `can_contribute: false`：三个操作都不渲染（沿用只读模式断言）；
  - 既有 `it.each` 的 `completed` 行“添加更正”断言保持不变（不劣化）。
- [ ] 3. 修改 `MeetingWorkspaceView.vue` 页头操作区（规格 §7.7 表）：`draft/ready` 准备信息 + 开始会议（primary）+ 取消会议（`n-popconfirm`，`ready` 与 `draft` 同等对待）；`in_progress` 结束会议（primary，保留“结束后，未结束议题会记为跳过。”提示）+ 取消会议；`completed` 重新打开（`n-popconfirm`）+ 导出保留；`canceled` 仅查看与导出。所有状态变更成功后用返回的 `Meeting` 替换本地对象；`expected_version` 取 `meeting.version`。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/meeting-lifecycle.test.ts src/tests/meeting-workspace.test.ts
npm --prefix frontend test
```

预期：全绿；`ready` 用例行为不劣化。

**完成标准：** 四种状态操作矩阵与规格一致；`canceled` 无重开入口；确认文案准确。

**注意事项/已知风险：** `n-popconfirm` 渲染在 body，测试用 `await screen.findByRole('button', { name: '确认' })` 或按实际确认文案定位；不要改动 `useMeetingWorkspace` 的生命周期 flush 语义（start/finish 前仍 flush 草稿）。

- [ ] 提交：`git add frontend/src/api/meetings.ts frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/meeting-lifecycle.test.ts frontend/src/tests/meeting-workspace.test.ts && git commit -m "feat: add meeting cancel and reopen actions"`

### Task P4-2：准备抽屉迁移 `n-drawer` + 参与人/主持/记录编辑

**目标：** `ContextDrawer` 换成 `n-drawer`；准备信息可编辑标题/时间窗/目的/主持/记录/参与人，提交 `PUT /api/meetings/{id}`。

**涉及文件：**
- 修改 `frontend/src/views/MeetingWorkspaceView.vue`
- 修改 `frontend/src/api/meetings.ts`（`MeetingUpdate` 增加 `host_user_id?`、`recorder_user_id?`、`participants?`）
- 修改 `frontend/src/domain/meetings.ts`（补 `started_at/completed_at` 可选与参与人写入类型）
- 修改 `frontend/src/tests/meeting-workspace.test.ts`

**实现步骤：**
- [ ] 1. 更新 `meeting-workspace.test.ts`：“keeps preparation fields on demand instead of above the active agenda”用例改为点击 `准备信息` 后出现抽屉（`await screen.findByText('会议准备')`；若 Naive 抽屉可查询到 `role="dialog"` 则同时断言）；字段包括 `会议标题`、`开始时间`、`结束时间`、`会议目的`、`主持`、`记录`、`添加参与人`；新增“修改参与人并保存”用例：改一行角色为 `presenter`、删除一行、点 `保存准备信息` → 断言 `PUT /api/meetings/m1` body 含完整 `participants` 数组与 `expected_version: 4`。
- [ ] 2. 成员数据源：加载时并行请求 `GET /api/projects/{meeting.project.id}`；成功用 `memberships[].user` 作为 `memberOptions`；403/失败退化为“当前参与人 + host/recorder 去重列表”，抽屉内提示“成员列表不可用，仅显示当前参与人”。（本计划裁决：会议参与人可能非项目成员，项目读取失败不得阻断准备信息。）
- [ ] 3. 改写准备区：`n-drawer placement="right" :width="'min(560px, 100vw)'" :show="preparationOpen" :title="'准备信息'" :mask-closable="!saving"` + `n-form`：标题 `n-input`；开始/结束 `n-date-picker type="datetime"`（成对提交，结束晚于开始）；会议目的保留 `PluginEditorSlot` 包裹的 `MarkdownEditor`（编辑器栈不变）；主持/记录 `n-select clearable`（可清空 → 提交 `null`）；参与人 `MeetingParticipantEditor`；`can_contribute` 为 false 或状态 `completed/canceled` 时禁用（后端 409 `meeting_locked` 的 `error.message` 用 `useMessage().error` 展示）；保存 `PUT /api/meetings/{id}` body `{ expected_version, title, purpose_markdown, scheduled_start, scheduled_end, host_user_id, recorder_user_id, participants }`，成功后替换 `meeting` 并关闭。
- [ ] 4. 材料/评论抽屉同步改用 `n-drawer`（本任务只换容器，内容迁移在 P4-5/P4-6）；移除本文件对 `ContextDrawer` 的 import。
- [ ] 5. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/meeting-workspace.test.ts src/tests/meeting-lifecycle.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 准备信息为 Naive 抽屉；参与人/主持/记录可编辑并全量提交；只读与锁定状态正确。

**注意事项/已知风险：** `meeting.host/recorder` 与参与人行的 `participation_role` 是两组独立字段，UI 不得混用（规格 §7.7）；准备字段独立于 `useMeetingWorkspace` 会议级草稿，关闭抽屉不触发会议保存。

- [ ] 提交：`git add frontend/src/views/MeetingWorkspaceView.vue frontend/src/api/meetings.ts frontend/src/domain/meetings.ts frontend/src/tests/meeting-workspace.test.ts && git commit -m "feat: migrate preparation drawer and participant editing"`

### Task P4-3：议题队列 `n-dropdown` + 跳过 / 移动 + 既有断言有意更新

**目标：** 队列行菜单改为 Naive 下拉；新增独立跳过与移动议题；保留删除守卫（迁移产出或改取消）。

**涉及文件：**
- 修改 `frontend/src/components/AgendaQueue.vue`
- 修改 `frontend/src/domain/meetings.ts`（如需 `started_at/completed_at` 展示字段）
- 修改 `frontend/src/tests/agenda-workbench.test.ts`
- 修改 `frontend/src/tests/meeting-workspace.test.ts`（如需）

**实现步骤：**
- [ ] 1. **有意更新**既有断言（规格 §11.2 点名）：`agenda-workbench.test.ts:161-164` 用例改为：仍断言不出现版本号（`queryByText(/版本\s*2/)` 不存在）；改为断言存在跳过动作——点击 `议题“进展同步”的更多操作` → `await screen.findByRole('button', { name: '跳过' })`；点击后确认 → 断言 `POST /api/agenda-items/a1/skip` body `{ expected_version: 2 }`；用例名改为“不暴露议题记录版本号，但提供独立跳过动作并提交 /skip”。
- [ ] 2. `AgendaQueue.vue`：用 `NDropdown`（options：`编辑详情`、`跳过`、`取消议题`、`移动议题`、`删除议题`；`trigger="click"`）替换 `•••`，触发器保留 `aria-label="议题“{title}”的更多操作"` 与 `aria-expanded`；触发器内容为 `NIcon` + `MoreHorizontal`。
- [ ] 3. 跳过：`n-popconfirm` 确认后 `POST /api/agenda-items/{id}/skip` body `{ expected_version: item.version }`，成功后 `emit('reload')`（沿用队列现有事件）。
- [ ] 4. 移动：`n-drawer` 选择目标会议（`GET /api/meetings?project_id={meeting.project.id}&limit=200`，排除当前会议）与可选位置（`n-input-number`，≥0，可空）；提交 `POST /api/agenda-items/{id}/move`，body 严格为：

  ```json
  { "target_meeting_id": "m2", "position": null, "expected_version": 2,
    "expected_source_meeting_version": 4, "expected_target_meeting_version": 1 }
  ```

  `expected_source_meeting_version` 取当前 `meeting.version`；`expected_target_meeting_version` 从所选目标会议读取（若列表项无 `version`，选中后 `GET /api/meetings/{id}` 再取）。
- [ ] 5. 删除守卫保留：409 `agenda_has_outcomes` 时展示既有提示“议题已有产出，请先迁移产出，或将议题标记为取消。”与“改为取消”按钮（`agenda-workbench.test.ts:382-390` 保持通过）。
- [ ] 6. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/agenda-workbench.test.ts src/tests/meeting-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 跳过与移动有独立入口且载荷字段完整；版本号仍不暴露；删除守卫文案保留。

**注意事项/已知风险：** `NDropdown` 菜单 Teleport，测试用全局 `findByRole('button', { name: '跳过' })`；`AgendaQueue` 同时承载拖拽排序（`dragStart/drop`），迁移菜单不得破坏既有拖拽测试。

- [ ] 提交：`git add frontend/src/components/AgendaQueue.vue frontend/src/domain/meetings.ts frontend/src/tests/agenda-workbench.test.ts frontend/src/tests/meeting-workspace.test.ts && git commit -m "feat: extend agenda queue with skip and move"`

### Task P4-4：议题详情元信息 + 附件区块 + 迁移/转问题/复制

**目标：** 详情展示并编辑提案人/主讲人/预计时长，显示实际用时与 carry 来源；新增议题附件区块；补齐迁移产出/转为开放问题/复制到其他会议三个命令。

**涉及文件：**
- 修改 `frontend/src/components/AgendaDetail.vue`
- 修改 `frontend/src/domain/meetings.ts`（`AgendaItem` 补 `carry_from_open_question_id?: string | null`、`started_at?/completed_at?`）
- 修改 `frontend/src/tests/agenda-workbench.test.ts`
- 修改 `frontend/src/tests/meeting-workspace.test.ts`（如需）

**实现步骤：**
- [ ] 1. 新增测试：
  - 元信息：fixture 带 `proposer/presenter` 时详情出现“提案人/主讲人”；保存时 `PUT /api/agenda-items/a1` body 含 `proposer_user_id`、`presenter_user_id`（下拉数据源：会议参与人 + 项目成员）；
  - 实际用时：`status: 'completed', actual_duration_seconds: 95` 时显示“实际用时 1 分 35 秒”；`in_progress` 且 `meeting.started_at` 存在时显示“已进行 hh:mm:ss”；
  - carry 徽标：`carry_from_open_question_id: 'q1'` 时显示“来自开放问题”；
  - 附件区块：详情底部存在 `data-testid="agenda-attachments"` 且渲染 `AttachmentPanel`（可 mock 为探针或断言“还没有附件”文案）；
  - 命令：迁移产出 → 选目标议题 → `POST /api/agenda-items/a1/migrate-outcomes` body `{ target_agenda_item_id, expected_source_version: 2, expected_target_version: 1, expected_source_meeting_version: 4, expected_target_meeting_version: 4 }`；转为开放问题确认 → `POST /api/agenda-items/a1/convert-to-question` body `{ expected_source_version: 2, expected_source_meeting_version: 4 }`；复制到其他会议 → `POST /api/agenda-items/a1/copy-to-meeting` body `{ target_meeting_id, expected_source_version: 2, expected_source_meeting_version: 4, expected_target_meeting_version: 1 }`。
- [ ] 2. `AgendaDetail.vue` 元信息行：`n-select`（proposer/presenter，clearable，选项为参与人 + 项目成员去重）+ `n-input-number`（预计时长 1–480）；保存仍走现有 `PUT /api/agenda-items/{id}`（`AgendaEdit` 的 nullable 字段允许显式 `null`，其余字段不传键）。
- [ ] 3. 来源徽标：`carry_from_open_question_id` 显示 `NTag` + “来自开放问题”（只读）；**不实现** #35 的 `copied_from_agenda_item_id` 徽标（规格 §15 已裁决延期，不要渲染或承诺该字段）。
- [ ] 4. 附件区块：`<section data-testid="agenda-attachments">` 内 `AttachmentPanel target-type="agenda_item" :target-id="item.id" :attachments="item.attachments ?? []" :can-contribute="canContribute"`；`@uploaded`/`@deleted` 更新本地 `item.attachments` 或触发 `changed`。
- [ ] 5. 详情操作区新增：迁移产出（`n-drawer` 选同会议其他议题）、转为开放问题（`n-popconfirm`）、复制到其他会议（`n-drawer` 选目标会议）。
- [ ] 6. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/agenda-workbench.test.ts src/tests/meeting-workspace.test.ts
npm --prefix frontend test
```

预期：全绿；既有 AI 编辑器槽（`agenda-notes-editor`）行为不变。

**完成标准：** 元信息、时长、carry 徽标、附件区块与三个命令均可用；载荷字段与后端 schema 一致。

**注意事项/已知风险：** `AgendaEdit` 仅 `proposer_user_id/presenter_user_id/estimated_minutes` 可为 `null`，其余字段不可为 `null`；不要发送空字符串（后端拒绝）。

- [ ] 提交：`git add frontend/src/components/AgendaDetail.vue frontend/src/domain/meetings.ts frontend/src/tests/agenda-workbench.test.ts frontend/src/tests/meeting-workspace.test.ts && git commit -m "feat: enrich agenda detail and commands"`

### Task P4-5：`AttachmentPanel` 改版（`n-upload` 样式壳 + `n-popconfirm`）

**目标：** 上传区使用 Naive 控件外观、文件图标用 `FileText`、删除用 `n-popconfirm` 替代 `window.confirm`。

**涉及文件：**
- 修改 `frontend/src/components/AttachmentPanel.vue`
- 修改 `frontend/src/tests/workflow-components.test.ts`（如包含附件断言）
- 修改 `frontend/src/tests/project-workspace.test.ts`（上传 `aria-label="上传附件"` 断言保留）

**实现步骤：**
- [ ] 1. 检查并更新相关断言：搜索 `上传附件`、`确定删除附件`、`file-glyph`、`DOC`；保留 `aria-label="上传附件"`；删除确认改为点击 `删除` 后出现 `n-popconfirm`，确认后断言 `DELETE /api/attachments/{target_type}/{target_id}/{id}`。
- [ ] 2. 重写 `AttachmentPanel.vue`：
  - 上传壳：`n-upload`（`:show-file-list="false"`、隐藏 input + `n-button` 触发）保留 20 MB 限制与 `FormData` 上传逻辑（**不改请求契约**）；
  - 卡片网格保留 `attachment-grid`/`attachment-card` 类（P7 统一清理）；
  - 文件占位 `DOC` 替换为 `NIcon` + `FileText`（图片仍用 `<img>`），`aria-hidden="true"`；
  - 删除按钮包 `n-popconfirm`（文案 `确定删除附件“{name}”吗？`），成功后 `emit('deleted', id)`；失败 `useMessage().error(errorMessage(...))`。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/workflow-components.test.ts src/tests/project-workspace.test.ts src/tests/meeting-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 无 `window.confirm`；无 `DOC` 字形；上传/下载契约不变。

**注意事项/已知风险：** `n-upload` 在 jsdom 下不触发真实文件选择；测试用 `fireEvent.change(input, { target: { files: [...] } })` 驱动隐藏 input，实现必须让该 input 可查询（`aria-label="上传附件"`）。

- [ ] 提交：`git add frontend/src/components/AttachmentPanel.vue frontend/src/tests/workflow-components.test.ts frontend/src/tests/project-workspace.test.ts && git commit -m "feat: restyle attachment panel"`

### Task P4-6：评论抽屉重构（删除 / 回复分页 / edited_at / mentions / 深链）

**目标：** 评论列表显示编辑与删除态、提及徽标；新增删除与回复分页；支持 `?comment=` 深链。

**涉及文件：**
- 修改 `frontend/src/components/MeetingCommentsPanel.vue`
- 修改 `frontend/src/components/MentionTextarea.vue`
- 修改 `frontend/src/domain/comments.ts`（补 `edited_at`、`mentions`、`parent_id`、`can_delete` 等可选字段）
- 修改 `frontend/src/views/MeetingWorkspaceView.vue`（读取 `route.query.comment` 打开抽屉）
- 修改 `frontend/src/tests/meeting-comments.test.ts`、`frontend/src/tests/comments-mentions.test.ts`

**实现步骤：**
- [ ] 1. 更新测试：
  - 带 `edited_at` 时显示“已编辑”；`body_markdown === null` 显示“评论已删除”且不显示编辑/回复按钮；
  - `can_delete: true` 时点击删除 → `n-popconfirm` 确认 → `DELETE /api/comments/c1` body `{ expected_version }`；
  - 回复分页：评论带 `reply_count > replies.length` 时显示“查看全部回复（N）”，点击后请求 `GET /api/comments/c1/replies?after=<lastId>&limit=20` 并追加渲染；
  - mentions：`mentions: [{ id, display_name }]` 时正文下方出现徽标文本；
  - 深链：mock `useRoute` 返回 `{ params: { id: 'm1' }, query: { comment: 'c9' } }`，渲染 `MeetingWorkspaceView`，断言评论抽屉自动打开且（评论已加载时）存在 `data-comment-id="c9"` 元素；未加载时显示“该评论在更早的讨论中”。
- [ ] 2. `MeetingCommentsPanel.vue`：列表请求 `GET /api/comments?target_type=meeting&target_id=&before=&limit=20&reply_limit=3`（“加载更多”按 `before` 游标）；编辑保留；删除新增（`can_delete` + `n-popconfirm` + `DELETE /api/comments/{id}` body `{ expected_version }`）；解决/重开保留（`can_resolve`）；回复区显示前 `reply_limit` 条，超出时按 `after` 游标拉取；根评论渲染 `:data-comment-id="comment.id"`；新增 props `{ focusCommentId?: string | null }`，内部 `watch` + `nextTick` 滚动，`prefers-reduced-motion` 下只滚动不高亮（用 `matchMedia('(prefers-reduced-motion: reduce)').matches` 判断）。
- [ ] 3. `MentionTextarea.vue`：内部 textarea 换 `n-input type="textarea"`（保留 `aria-label`、`v-model`、`v-model:mention-ids` 契约）；提及弹层保留现有键盘交互（↑/↓/Enter/Esc）；“输入 @ 可提及会议成员”提示文字保留（提示文字不算图标字形）。
- [ ] 4. `MeetingWorkspaceView.vue`：`onMounted`/`watch` 读取 `route.query.comment`，存在则 `commentsOpen = true` 并传 `focusCommentId`。
- [ ] 5. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/meeting-comments.test.ts src/tests/comments-mentions.test.ts src/tests/meeting-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 删除/回复分页/编辑态/提及/深链均按规格 §7.7 评论抽屉工作；`can_*` 门控严格。

**注意事项/已知风险：** 深链滚动在 jsdom 无布局，测试只断言抽屉打开与目标元素存在；`reply_limit` 固定为 3（请求 `reply_limit=3`，超出显示“查看全部回复（N）”后按 `after` 游标拉取）。

- [ ] 提交：`git add frontend/src/components/MeetingCommentsPanel.vue frontend/src/components/MentionTextarea.vue frontend/src/domain/comments.ts frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/meeting-comments.test.ts frontend/src/tests/comments-mentions.test.ts && git commit -m "feat: complete meeting comments panel"`

### Task P4-7：`CompletedMeetingChain` 改版 + `series_slot_at`/实际起止

**目标：** 完成链视觉改 `n-card`/`n-collapse`；会议页头与完成摘要补充 `series_slot_at`、`started_at/completed_at`。

**涉及文件：**
- 修改 `frontend/src/components/CompletedMeetingChain.vue`
- 修改 `frontend/src/views/MeetingWorkspaceView.vue`
- 修改 `frontend/src/tests/meeting-lifecycle.test.ts`
- 修改 `frontend/src/tests/meeting-workspace.test.ts`

**实现步骤：**
- [ ] 1. 测试新增/保留：保留 `completed-agenda-a1`/`completed-agenda-a2`/`completed-meeting-outcomes`/`completed-meeting-duration` 的 testid 与既有断言（读取快照语义不变）；新增：`series_slot_at` 有值时页头出现“系列槽位”本地时间；`snapshot_json.meeting.started_at/completed_at` 有值时完成摘要显示实际起止。
- [ ] 2. `MeetingWorkspaceView.vue` 元信息行：状态/进行时长（保留 `meeting-live-clock`）/主持/记录/系列槽位（`series_slot_at` 有值时“系列槽位 {formatDateTime}”，只读）；`completed` 显示 `started_at/completed_at`。
- [ ] 3. `CompletedMeetingChain.vue`：外层 `n-card`，折叠用 `n-collapse`（保留默认展开语义与既有 testid）；折叠箭头由 Naive 图标承担（P7 再核对无字形残留）。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/meeting-lifecycle.test.ts src/tests/meeting-workspace.test.ts src/tests/meeting-comments.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 完成链仍只读快照；新增时间信息为只读展示。

**注意事项/已知风险：** 不得在完成链里读取可变的 `meeting.agenda_items` 当前产出（规格 §7.7 快照语义）；`n-collapse` 默认展开行为要与既有 `<details open>` 一致，否则显式设置 `:default-expanded-names`。

- [ ] 提交：`git add frontend/src/components/CompletedMeetingChain.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/meeting-lifecycle.test.ts frontend/src/tests/meeting-workspace.test.ts && git commit -m "feat: restyle completed meeting chain"`

### Task P4-8：阶段门禁

**目标：** 确认 P4 会议工作区全部改动无回归，产出可合并的 P4 PR。

**涉及文件：** 无新增源码；验证 P4-1 至 P4-7 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. 运行规格 §9 P4 全部指定文件：

```bash
npm --prefix frontend test -- src/tests/meeting-workspace.test.ts src/tests/meeting-lifecycle.test.ts src/tests/agenda-workbench.test.ts src/tests/meeting-comments.test.ts src/tests/comments-mentions.test.ts src/tests/workflow-components.test.ts src/tests/outcome-composer.test.ts src/tests/use-meeting-workspace.test.ts
```

预期：全部通过；特别确认 `use-meeting-workspace.test.ts` 与 `outcome-composer.test.ts` 未因 UI 迁移回归。

- [ ] 2. `npm --prefix frontend test` → `Test Files 28 passed (28)`，无 failed。
- [ ] 3. `npm --prefix frontend run build` → 退出码 0。
- [ ] 4. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 5. 推送并创建 `feature/ui-overhaul-p4` PR（描述必须列出 `agenda-workbench.test.ts` 的有意断言更新）。等待用户合并后再开始 P5。

**完成标准：** 全量测试与构建双绿、后端零改动、P4 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；会议保存语义（`useMeetingWorkspace`）不得为通过测试而削弱。

---

# P5 项目页与产出工作流

> 阶段分支：`feature/ui-overhaul-p5`。核心是 `n-tabs`、编辑项目抽屉（成员/负责人）、系列管理、决策详情、行动项编辑、开放问题 Tab、动态台账。

### Task P5-1：`ProjectDetailView` `n-tabs` + 页头新建下拉 + 删除项目

**目标：** Tab 用 `n-tabs` 并映射 `?tab=` 深链；新建改 `n-dropdown`；新增删除项目（仅空项目）二次确认。

**涉及文件：**
- 修改 `frontend/src/views/ProjectDetailView.vue`
- 修改 `frontend/src/tests/project-workspace.test.ts`

**实现步骤：**
- [ ] 1. 更新测试：
  - Tab 查询 `getByRole('tab', { name: '动态' })` 保持可用（`n-tab` 渲染 `role="tab"`）；新增 `?tab=activity` 深链用例（mock `useRoute` 返回 `{ params: { id: 'p1' }, query: { tab: 'activity' } }`）断言动态 Tab 激活并请求台账；
  - 新建菜单：点击 `新建` 后 `await screen.findByRole('menuitem', { name: '行动项' })`（`NDropdown` Teleport）；点击后打开 `添加行动项` 抽屉；
  - 删除项目：`can_manage` 时出现 `删除项目`；点击后 `n-dialog` 要求输入项目名确认；确认后 `DELETE /api/projects/p1`；mock 409 `project_not_empty`/`project_has_attachments` 与 403 `project_delete_forbidden` 时展示 `error.message` 原文且不跳转；成功回 `/projects`。
- [ ] 2. `ProjectDetailView.vue`：`Tab` 类型增加 `'questions'`；`tabs` 数组：概览/会议/行动项/决策/开放问题/文件/动态；`n-tabs type="line"` + `n-tab-pane`；`watch` 路由 query 同步 `tab`（默认 `overview`），切换时 `router.replace({ query: { ...route.query, tab } })`；页头 `新建` 改 `n-dropdown`（菜单项：会议、系列会议、决策、行动项、进展、文件），保留 `canContribute` 门控；`删除项目` 按钮（`can_manage`）：`useDialog()` 的 `n-dialog` 内嵌 `n-input` 要求输入 `project.name` 才允许确认，**对话框正文必须说明“仅当项目下没有会议且没有项目附件时才能删除，删除不会级联清理”**；成功后 `router.push('/projects')`。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿（含只读 stakeholder 用例：删除按钮也不出现）。

**完成标准：** Tab 深链可用；删除项目约束与错误提示准确；不承诺级联删除。

**注意事项/已知风险：** `project-workspace.test.ts` 的 `useRoute` mock 当前只有 `params`，需补 `query` 与 `router.replace`；`NDropdown`/`n-dialog` Teleport，查询用全局 `screen`。

- [ ] 提交：`git add frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-workspace.test.ts && git commit -m "feat: rebuild project tabs and header actions"`

### Task P5-2：编辑项目抽屉（成员 / 负责人 / 冲突对话框）

**目标：** 编辑项目改右侧抽屉：名称/摘要/状态/健康度/目标日期/负责人/成员多选；409 走统一冲突对话框；成员管理受 `can_manage`。

**涉及文件：**
- 修改 `frontend/src/views/ProjectDetailView.vue`
- 修改 `frontend/src/tests/project-workspace.test.ts`

**实现步骤：**
- [ ] 1. 更新测试：
  - “编辑项目”打开抽屉（`await screen.findByText('编辑项目')` 或 `role=dialog`），包含 `名称/摘要/状态/健康度/目标日期/负责人/成员` 字段；成员下拉选项来自 `project.memberships[].user`；
  - 保存：修改名称与成员后提交 `PUT /api/projects/p1` body 含 `expected_version: 3`、`member_ids` 数组、`lead_user_id`；成功关闭抽屉并刷新；
  - 冲突：mock 抛 `ApiError(409,'version_conflict','内容已更新',{actual_version:4})`，断言出现 `内容已被其他成员更新` 对话框，点“用本地草稿覆盖”后以 `expected_version: 4` 重试；
  - 只读：`can_manage:false` 时不出现编辑按钮（既有用例保留）；
  - 抽屉内显示“移除成员会立即撤销其项目访问，但不会删除其历史记录。”与“干系人可查看不可编辑；当前没有成员角色指引入口。”。
- [ ] 2. 实现：`n-drawer` + `n-form`（`can_manage` 时可用）；成员 `n-select multiple`（提交 `member_ids` 全量数组，包含 lead）；负责人 `n-select clearable`（提交 `lead_user_id`）；成员角色只读展示（`n-tag`）；保存用 `useVersionedSave` + `VersionConflictDialog`（`localMarkdown` 放表单差异文本，`serverMarkdown` 放服务器最新摘要文本）。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 成员增删与负责人变更可用；409 统一冲突；stakeholder 只读。

**注意事项/已知风险：** `ProjectEdit.member_ids` 全量替换；不要尝试写 `memberships[].role`（后端无入口，规格 #25）。

- [ ] 提交：`git add frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-workspace.test.ts && git commit -m "feat: add project edit drawer with members"`

### Task P5-3：`ProjectCreatePanel` 拆分（会议 / 系列 / 决策 / 行动项抽屉）

**目标：** 项目页四类创建改为独立抽屉表单，复用 `NForm` 结构；会议创建复用 `MeetingCreateDrawer`。

**涉及文件：**
- 修改 `frontend/src/views/ProjectDetailView.vue`
- 修改 `frontend/src/components/ProjectCreatePanel.vue`
- 修改 `frontend/src/tests/project-create-panel.test.ts`

**实现步骤：**
- [ ] 1. 更新 `project-create-panel.test.ts`：按新契约测试（推荐直接渲染 `ProjectDetailView` 打开对应抽屉并断言请求体；若保留对 `ProjectCreatePanel` 的直接测试，则按新 props 重写）：
  - 决策抽屉提交 `POST /api/projects/p1/decisions` body `{ title, decision_markdown, rationale_markdown, reviewer_ids }`，`reviewer_ids` 由 `n-select multiple` 选择项目成员；
  - 行动项抽屉提交 `POST /api/projects/p1/actions` body `{ project_id, content, owner_user_id, due_date, priority }`；
  - 系列抽屉：本任务先保留现有字段由 `ProjectCreatePanel` 创建，P5-4 迁移到 `SeriesEditDrawer` 并复用；
  - 会议抽屉复用 `MeetingCreateDrawer`。
- [ ] 2. 实现：`ProjectCreatePanel.vue` 不再是一个大表单；推荐在 `ProjectDetailView` 内直接挂四个抽屉实例，`ProjectCreatePanel.vue` 缩为决策/行动项两个小表单（或删除并把表单内联到视图）；抽屉统一 `:width="'min(560px, 100vw)'"`、`label-placement="top"`、脚部取消 + 主按钮 loading。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/project-create-panel.test.ts src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 四类创建都有独立抽屉且请求契约与后端 schema 一致；系列周期字段逻辑保留并搬到 P5-4。

**注意事项/已知风险：** 决策 `decision_markdown` 后端要求非空，标题与内容的关系沿用现有实现（内容为空时用标题兜底，需在 UI 明确）。

- [ ] 提交：`git add frontend/src/views/ProjectDetailView.vue frontend/src/components/ProjectCreatePanel.vue frontend/src/tests/project-create-panel.test.ts && git commit -m "feat: split project create forms into drawers"`

### Task P5-4：`SeriesEditDrawer` 系列管理 + `series-manage.test.ts`

**目标：** 系列支持编辑/归档/常设议题/默认主持记录/参与者；创建复用同一抽屉。

**涉及文件：**
- 新建 `frontend/src/components/SeriesEditDrawer.vue`
- 修改 `frontend/src/domain/meetings.ts`（新增 `MeetingSeriesDetail`）
- 修改 `frontend/src/components/ProjectRecordTabs.vue`
- 新建 `frontend/src/tests/series-manage.test.ts`

**实现步骤：**
- [ ] 1. 新测试 `series-manage.test.ts`（规格 §10）：
  - 打开编辑：`GET /api/meeting-series/s1` 后抽屉显示 `title/purpose_markdown/recurrence*/default_duration_minutes/default_host/default_recorder/participants/standing_items`；
  - 关闭周期：把 `recurrence_frequency` 设为“不设固定周期”后保存，断言 `PUT /api/meeting-series/s1` body 中 `recurrence_frequency: null` **且** `recurrence_weekday/month_day/month/local_time/timezone/anchor_date` 全部显式 `null`（规格 §7.5 防残值）；
  - 常设议题增删行：新增一行提交字段 `title/agenda_type/default_owner_user_id/default_duration_minutes`；
  - 归档：`n-popconfirm` 后 `PUT /api/meeting-series/s1` body `{ expected_version, status: 'archived' }`；
  - 创建模式：`POST /api/projects/p1/meeting-series` 载荷含 `participants` 与 `standing_items`；
  - `can_contribute:false` 时行内不出现编辑/归档/临时添加按钮。
- [ ] 2. 实现 `SeriesEditDrawer.vue`：props `{ show, mode: 'create' | 'edit', projectId, seriesId?, members }`，emits `{ close, saved }`；字段按规格 §7.5；写入字段名严格为 `default_host_user_id`/`default_recorder_user_id`、常设议题 `default_owner_user_id`、参与者 `participants: [{ user_id, participation_role }]`；保存走 `POST`（create）或 `PUT`（edit，带 `expected_version`）。
- [ ] 3. `ProjectRecordTabs.vue` 会议 Tab：系列行新增 `编辑`（打开抽屉）与 `归档`（`n-popconfirm`）；保留 `/meetings?series_id=` 链接与“临时添加会议”（迁移为 `n-drawer`）。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/series-manage.test.ts src/tests/project-workspace.test.ts src/tests/meetings-view.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 系列编辑字段与后端 schema 完全一致；关闭周期不残留字段；归档可用。

**注意事项/已知风险：** `MeetingSeriesEdit` 允许 recurrence 组为 `null`，但 `recurrence_interval`/`default_duration_minutes` 不可为 `null`；未修改字段不发键，显式清空周期发全组 `null`。

- [ ] 提交：`git add frontend/src/components/SeriesEditDrawer.vue frontend/src/domain/meetings.ts frontend/src/components/ProjectRecordTabs.vue frontend/src/tests/series-manage.test.ts && git commit -m "feat: add series management drawer"`

### Task P5-5：`ActionEditDrawer` + 行动项 Tab 状态流转

**目标：** 项目行动项 Tab 行内支持状态流转与编辑抽屉；派生行动项无写操作。

**涉及文件：**
- 新建 `frontend/src/components/ActionEditDrawer.vue`
- 修改 `frontend/src/components/ProjectRecordTabs.vue`
- 修改 `frontend/src/tests/workflow-components.test.ts`

**实现步骤：**
- [ ] 1. 新测试（`workflow-components.test.ts` 追加）：点击行动项行的 `编辑` 打开 `ActionEditDrawer`；提交 `PUT /api/actions/a1` body `{ content, owner_user_id, due_date, priority, status, expected_version }`；状态快捷操作（`开始`/`完成`/`取消`）分别提交对应 `status`；`canceled` 走 `n-popconfirm` 确认；`is_derived: true` 的行不出现编辑与状态操作。
- [ ] 2. 实现 `ActionEditDrawer.vue`：props `{ show, action, members }`，emits `{ close, saved }`；字段 `content`（`n-input`）、`owner_user_id`（`n-select clearable`）、`due_date`（`n-date-picker type="date"`，提交 `YYYY-MM-DD`）、`priority`（`n-select`）、`status`（`n-select`）；保存 `PUT /api/actions/{id}`（含 `expected_version`）。
- [ ] 3. `ProjectRecordTabs.vue` 行动项 Tab：行改为 `n-list` 行 + 行内操作（`编辑` 抽屉、状态快捷按钮）；完成行显示 `completed_at`；均按 `canContribute && !is_derived` 门控。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/workflow-components.test.ts src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 行动项编辑与流转可用；派生项只读。

**注意事项/已知风险：** `ActionEdit` 的 `due_date` 可显式 `null`；流转到 `done` 时后端回填 `completed_at`，前端不做本地回填。

- [ ] 提交：`git add frontend/src/components/ActionEditDrawer.vue frontend/src/components/ProjectRecordTabs.vue frontend/src/tests/workflow-components.test.ts && git commit -m "feat: add action editing and transitions"`

### Task P5-6：`DecisionDetailDrawer` 决策全流程 + `decision-workflow.test.ts`

**目标：** 项目决策 Tab 点击行打开详情抽屉；评审/定稿/撤回/替代/编辑按状态与身份门控；P6 全局决策视图复用同一抽屉。

**涉及文件：**
- 新建 `frontend/src/components/DecisionDetailDrawer.vue`
- 修改 `frontend/src/domain/outcomes.ts`（补 `reviewers[]`、`decided_by`、`supersedes_decision_id`）
- 修改 `frontend/src/components/ProjectRecordTabs.vue`（决策 Tab 行点击）
- 新建 `frontend/src/tests/decision-workflow.test.ts`

**实现步骤：**
- [ ] 1. 新测试 `decision-workflow.test.ts`（规格 §10）：
  - 详情展示 `decision_markdown/rationale_markdown/created_by/decided_by/reviewers[]`（状态徽章 `pending/approved/changes_requested` 与 `responded_at/comment`）；`supersedes_decision_id` 存在时显示“已被替代”链；
  - `proposed` 且 `is_derived:false`：显示 `编辑`（`PUT /api/decisions/d1` 含 `reviewer_ids` 与 `expected_version`）、`定稿`（`POST /api/decisions/d1/finalize` body `{expected_version}`）、`撤回`（`POST /api/decisions/d1/withdraw`）；
  - 评审：当前用户是 `reviewers[]` 中 `pending` 的 `user_id` 时显示评审表单，提交 `POST /api/decisions/d1/review` body `{status:'approved', comment, expected_version}`；
  - 替代：`status:'final'` 且同项目存在其他 `final` 决策时显示 `替代`，选择新决策后提交 `POST /api/decisions/d1/supersede` body `{new_decision_id, expected_version, expected_new_version}`；
  - 派生决策（`is_derived:true`）不显示编辑/评审/定稿/撤回/替代；`can_contribute:false` 时全部写操作不渲染。
- [ ] 2. 实现 `DecisionDetailDrawer.vue`：props `{ show, decision, members, userNames: Record<string, string> }`，emits `{ close, saved }`；评审人姓名用 `userNames[reviewer.user_id] ?? '用户·' + id.slice(0, 8)`；替代表单的新决策列表组件内请求 `GET /api/decisions?project_id={decision.project_id}&status=final&limit=200` 并在选项中带 `version`；评审表单状态按钮 `approved`/`changes_requested` + `comment`。
- [ ] 3. `ProjectRecordTabs.vue` 决策 Tab：行改为可点击按钮，点击打开抽屉；保留 `StatusPill` 与会议来源链接；宿主传入 `userNames`（项目成员聚合）。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/decision-workflow.test.ts src/tests/workflow-components.test.ts src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 决策流转严格按状态/身份/能力；派生只读；替代仅 `final` 且同项目。

**注意事项/已知风险：** 项目 Tab 的决策项没有 `reviewers[].user`（只有 `user_id`），姓名由宿主聚合字典传入；P6 全局视图复用同一 props 契约（不要复制组件）。

- [ ] 提交：`git add frontend/src/components/DecisionDetailDrawer.vue frontend/src/domain/outcomes.ts frontend/src/components/ProjectRecordTabs.vue frontend/src/tests/decision-workflow.test.ts && git commit -m "feat: add decision detail workflow"`

### Task P5-7：`ProjectQuestionsTab` 开放问题生命周期 + `project-questions.test.ts`

**目标：** 项目详情新增“开放问题”Tab；支持编辑/排期/解决与只读来源展示；不提供“放弃”操作。

**涉及文件：**
- 新建 `frontend/src/components/ProjectQuestionsTab.vue`
- 修改 `frontend/src/domain/outcomes.ts`（补 `scheduled_meeting_id`、`resolved_by_decision_id`、`converted_from_agenda_item_id`、`source_agenda_item_id`）
- 修改 `frontend/src/views/ProjectDetailView.vue`
- 新建 `frontend/src/tests/project-questions.test.ts`

**实现步骤：**
- [ ] 1. 新测试 `project-questions.test.ts`（规格 §10）：
  - 列表：`GET /api/projects/p1/open-questions?limit=200`，显示状态/负责人/来源会议；`dropped` 渲染标签“已放弃”但**没有**放弃操作入口；
  - 创建：抽屉提交 `POST /api/projects/p1/open-questions` body `{question_markdown, owner_user_id}`（`source_*` 不传）；
  - 编辑：`PUT /api/open-questions/q1` body `{question_markdown, owner_user_id, expected_version}`；`is_derived:true` 时不显示编辑；
  - 排期：仅 `status==='open'` 且 `scheduled_meeting_id` 为空时显示；抽屉选择未来同项目会议后提交 `POST /api/open-questions/q1/schedule` body `{meeting_id, expected_version, expected_meeting_version}`；
  - 解决：抽屉可选关联同项目 `final` 决策，提交 `POST /api/open-questions/q1/resolve` body `{decision_id: null | 'd1', expected_version}`；
  - 只读展示：`scheduled_meeting_id`（已排入会议）、`resolved_by_decision_id`（由决策解决）、`converted_from_agenda_item_id`/`source_agenda_item_id`（来源议程）。
- [ ] 2. 实现 `ProjectQuestionsTab.vue`：props `{ project, canContribute }`；列表用 `n-list`（行操作用按钮组或 `n-dropdown`）；排期会议列表 `GET /api/meetings?project_id={id}&limit=200`，客户端过滤 `scheduled_start > now` 且状态非 `canceled`；目标会议版本取行内 `version`（若全局列表项无 `version`，选中后 `GET /api/meetings/{id}` 读取）。
- [ ] 3. `ProjectDetailView.vue` 挂载新 Tab：`<ProjectQuestionsTab v-else-if="tab === 'questions'" :project="project" :can-contribute="canContribute" @reload="load" />`。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/project-questions.test.ts src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 生命周期三动作可用；`dropped` 只读兼容；派生只读。

**注意事项/已知风险：** `/schedule` 要求目标会议在未来且 `expected_meeting_version` 正确；实现必须处理 409 冲突并提示刷新。**不实施** #36 写入口。

- [ ] 提交：`git add frontend/src/components/ProjectQuestionsTab.vue frontend/src/domain/outcomes.ts frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-questions.test.ts && git commit -m "feat: add open questions lifecycle tab"`

### Task P5-8：项目动态台账 + 进展编辑（原样回传 `source`）

**目标：** 动态 Tab 改用活动台账 `n-timeline`；台账中 `project_update` 条目支持编辑并原样回传 `source`；保留“进展记录”子区与发布器。

**涉及文件：**
- 修改 `frontend/src/components/ProjectActivityTab.vue`
- 修改 `frontend/src/components/ProjectUpdateComposer.vue`（仅容器/样式适配，不改发布契约）
- 修改 `frontend/src/components/ProjectOverview.vue`（最近动态改用台账最后 5 条）
- 修改 `frontend/src/domain/projects.ts`（补活动条目类型）
- 新建 `frontend/src/tests/project-activity.test.ts`

**实现步骤：**
- [ ] 1. 新测试 `project-activity.test.ts`（规格 §10）：
  - 台账：`GET /api/projects/p1/activity?limit=50` 返回 `{items:[{id, actor, event_type, subject, payload, created_at, meeting_id}], next_cursor}`，渲染 `n-timeline` 条目且文案来自 `activityLabel`（如“创建了项目 MeetFlow”）；`next_cursor` 非空时点“加载更多”请求 `before=<cursor>` 并追加；
  - 进展记录子区：`GET /api/projects/p1/updates?limit=50&offset=0` 返回数组；返回条数 === limit 时显示“加载更多”；
  - 进展编辑：`subject.type === 'project_update'` 的条目显示 `编辑`；打开抽屉修改健康度/内容后提交 `PUT /api/project-updates/up1` body 含 `expected_version` 且 **`source` 原样等于原条目 `source`**（用 `source: 'ai_draft_applied'` fixture 断言不被改写）；
  - `can_contribute:false` 时不渲染发布器与编辑入口。
- [ ] 2. 实现 `ProjectActivityTab.vue`：`n-timeline` + 游标加载更多；`ProjectUpdateComposer` 保留在顶部（`canContribute`）；编辑抽屉内联实现（`n-drawer` + `n-form`：健康度 `n-select`、内容 `MarkdownEditor`/`PluginEditorSlot`），保存走 `useVersionedSave` + `VersionConflictDialog`。
- [ ] 3. `ProjectOverview.vue`：最近动态改为请求 `GET /api/projects/p1/activity?limit=5` 并渲染前 5 条（`activityLabel`）；保留其余六块内容。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/project-activity.test.ts src/tests/project-workspace.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 台账真实事件流渲染；`source` 原样回传；进展发布/编辑与只读门控正确。

**注意事项/已知风险：** 编辑进展必须回传原 `source`（`ProjectUpdateEdit.source` 默认 `human`，省略会改写 AI 来源标记）；`GET /api/projects/{id}/updates` 返回纯数组无 `total`，用“返回条数 === limit”判断还有下一批。

- [ ] 提交：`git add frontend/src/components/ProjectActivityTab.vue frontend/src/components/ProjectOverview.vue frontend/src/domain/projects.ts frontend/src/tests/project-activity.test.ts && git commit -m "feat: add project activity timeline and update editing"`

### Task P5-9：`ProjectsView` 创建项目抽屉

**目标：** 项目列表页创建改右侧 `n-drawer` 表单（名称/标识自动 slug/说明），筛选保持客户端并注明（规格 §7.4）。

**涉及文件：**
- 修改 `frontend/src/views/ProjectsView.vue`
- 修改 `frontend/src/tests/home-attention.test.ts`（项目创建相关用例）
- 修改 `frontend/src/styles.css`（如移除内联表单样式）

**实现步骤：**
- [ ] 1. 更新 `home-attention.test.ts` 的“normalizes a project identifier without showing format instructions”用例：仍点击 `新建项目` 打开抽屉，`getByLabelText('项目标识')` 输入 `Meet Flow_Test` 后断言自动变为 `meet-flow-test` 且 `pattern` 为空；新增提交用例：填名称与说明后断言 `POST /api/projects` body 含 `name/slug/summary/member_ids`（`member_ids` 含创建者）。
- [ ] 2. 修改 `ProjectsView.vue`：创建入口改为 `n-drawer`（`:width="'min(560px, 100vw)'"`）+ `n-form`：名称（必填）、标识（自动 slug，允许手动覆盖）、说明；提交 `n-button type="primary" :loading`；成功后关闭抽屉并刷新列表（refetch-on-success）。保留 `project-card` 网格、状态/健康度客户端筛选（`/api/projects` 无筛选参数，属富内容面例外，界面上注明“筛选作用于已加载项目”）。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/home-attention.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 项目创建为抽屉且 slug 归一化行为不变；列表筛选仍客户端并注明范围。

**注意事项/已知风险：** `member_ids` 需包含创建者（后端已有兜底，前端仍显式传）；不要新增后端筛选参数。

- [ ] 提交：`git add frontend/src/views/ProjectsView.vue frontend/src/tests/home-attention.test.ts frontend/src/styles.css && git commit -m "feat: add project creation drawer"`

### Task P5-10：阶段门禁

**目标：** 确认 P5 项目页与产出工作流全部改动无回归，产出可合并的 P5 PR。

**涉及文件：** 无新增源码；验证 P5-1 至 P5-9 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. 运行规格 §9 P5 指定文件：

```bash
npm --prefix frontend test -- src/tests/project-workspace.test.ts src/tests/project-create-panel.test.ts src/tests/workflow-components.test.ts src/tests/project-questions.test.ts src/tests/series-manage.test.ts src/tests/project-activity.test.ts src/tests/decision-workflow.test.ts src/tests/home-attention.test.ts
```

预期：全部通过。

- [ ] 2. `npm --prefix frontend test` → `Test Files 32 passed (32)`（28 + 4 个新文件），无 failed。
- [ ] 3. `npm --prefix frontend run build` → 退出码 0。
- [ ] 4. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 5. 推送并创建 `feature/ui-overhaul-p5` PR；等待用户合并后再开始 P6。

**完成标准：** 全量测试与构建双绿、后端零改动、P5 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；确认派生项只读与延期项（#35/#36）没有被误实现。

---

# P6 全局视图、收件箱、AI 任务与管理页

> 阶段分支：`feature/ui-overhaul-p6`。行动项/决策改 `n-data-table` remote 分页；收件箱增量与深链；AI 任务丢弃；管理员用户/插件页表格化与能力徽标。

### Task P6-1：`useUserNameMap` 姓名聚合字典 + `links.ts` 收件箱深链

**目标：** 全局列表用“从 `/api/projects` 成员聚合姓名映射”显示人名；`links.ts` 支持通知 `source_comment` 深链。

**涉及文件：**
- 新建 `frontend/src/composables/useUserNameMap.ts`
- 修改 `frontend/src/utils/links.ts`
- 修改 `frontend/src/tests/ui-foundation.test.ts`（追加纯函数断言）

**实现步骤：**
- [ ] 1. 实现 `useUserNameMap.ts`：模块级 reactive 单例，导出 `userNames: Ref<Record<string, string>>`、`loadUserNames(): Promise<void>`（请求 `GET /api/projects`，遍历 `memberships[].user` 写入 `id → display_name`，重复时后写覆盖但同 id 姓名一致）、`nameOf(userId: string | null | undefined): string`（缺名回退 `用户·{id.slice(0, 8)}`，空 id 返回“未指定”）。兼容 `memberships` 缺省为 `[]`。**不**新增后端端点。
- [ ] 2. `links.ts` 增加 `notificationHref(item: { subject: { type: string; id: string }; meeting: { id: string } | null; source_comment: { id: string } | null }): string`：`source_comment && meeting` → `` `/meetings/${meeting.id}?comment=${source_comment.id}` ``；否则复用现有 `subjectHref(subject.type, subject.id, meeting?.id)`。保留 `subjectHref`/`subjectLabel` 原签名。
- [ ] 3. 在 `ui-foundation.test.ts` 追加纯函数断言：`notificationHref` 的两条分支；`nameOf` 的回退前缀（`用户·`）。`useUserNameMap` 的网络行为在 P6-2 的 `global-workspace.test.ts` 里通过 ActionsView 覆盖。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/ui-foundation.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 姓名映射只来自项目成员聚合；深链优先 `source_comment`。

**注意事项/已知风险：** 被移出项目的用户会缺名，接受 `用户·ID 前缀` 回退（规格 §15 已裁决）；不要尝试调用不存在的用户目录端点。

- [ ] 提交：`git add frontend/src/composables/useUserNameMap.ts frontend/src/utils/links.ts frontend/src/tests/ui-foundation.test.ts && git commit -m "feat: add name map and notification deep links"`

### Task P6-2：`ActionsView` 改 `n-data-table` remote 分页 + 行操作 + highlight

**目标：** 行动项全局视图服务端筛选分页；负责人显示姓名；支持编辑/状态流转与 `?highlight=` 定位。

**涉及文件：**
- 修改 `frontend/src/views/ActionsView.vue`
- 修改 `frontend/src/tests/global-workspace.test.ts`

**实现步骤：**
- [ ] 1. 更新 `global-workspace.test.ts`（有意更新，规格 §11.2）：把现有精确调用断言改为包含式参数断言（断言调用路径包含 `status=open`、`owner_user_id=u1`、`project_id=p1`），并补充：
  - 首次请求包含 `limit=50&offset=0`；
  - 表格渲染断言（`document.querySelector('.n-data-table')` 非空、行动内容可见）；
  - 负责人列显示 `林宇`（由 `/api/projects` 的 memberships 聚合），未覆盖的 id 回退 `用户·` 前缀；
  - 切换到第 2 页（`@update:page` 或分页控件）后请求含 `offset=50`；
  - `?highlight=<id>`（mock `useRoute` 返回 `query: { highlight: 'a1' }`）时目标行存在 `data-row-key="a1"` 且带高亮类；`prefers-reduced-motion` 不影响查询（只测类/滚动不测视觉）。
  - `vue-router` mock 需补 `useRoute`（当前只 mock 了 `useRouter`/`RouterLink`）。
- [ ] 2. 重写 `ActionsView.vue`：
  - `n-data-table`（`:remote="true"`、`:pagination="{ page, pageSize: 50, itemCount: total }"`、`:row-key="row => row.id"`、`scroll-x` 时显式 `min-width`）；列：内容（主列，`ellipsis` + tooltip）、负责人（`nameOf`）、优先级（`NTag` + `priorityTone`）、状态（`StatusPill` + 操作）、截止日期（逾期红色）、来源会议（`RouterLink`）；已完成行显示 `completed_at`；
  - 筛选区：负责人（我/全部 → `owner_user_id`）、状态（`status`）、项目（`project_id`）、期限（逾期 → `due_before=今天`；今天及以后 → `due_after=今天`）；**移除优先级筛选**（后端无参数）；
  - 行操作：状态流转（`n-popconfirm` 确认取消）与 `编辑`（复用 `ActionEditDrawer`）；`is_derived === true` 不提供；`?highlight=` 定位用 `row-key` 查找 + 滚动 + 2s 行高亮，`prefers-reduced-motion: reduce` 时只滚动不高亮（用 `matchMedia('(prefers-reduced-motion: reduce)').matches` 判断）；
  - `loadUserNames()` 在挂载时调用一次。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/global-workspace.test.ts src/tests/workflow-components.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 服务端筛选分页、姓名显示、行操作与 highlight 定位可用；无跨页客户端过滤。

**注意事项/已知风险：** 行动项优先级筛选只做展示配色，不做筛选；`n-data-table` 不启用固定列/虚拟滚动（规格 §11.1）。

- [ ] 提交：`git add frontend/src/views/ActionsView.vue frontend/src/tests/global-workspace.test.ts && git commit -m "feat: rebuild actions view with remote table"`

### Task P6-3：`DecisionsView` 改 `n-data-table` remote 分页 + 详情抽屉 + highlight

**目标：** 决策全局视图服务端筛选分页；行点击复用 `DecisionDetailDrawer`；支持 `?highlight=`。

**涉及文件：**
- 修改 `frontend/src/views/DecisionsView.vue`
- 修改 `frontend/src/tests/global-workspace.test.ts`
- 修改 `frontend/src/tests/workflow-components.test.ts`（如需）

**实现步骤：**
- [ ] 1. 更新 `global-workspace.test.ts` 决策部分：把现有精确调用断言改为包含式参数断言（断言调用路径包含 `project_id=p1`、`status=proposed`，并包含 `limit=50&offset=0`）；新增 `reviewer_user_id` 下拉（选项来自姓名聚合）断言；移除日期区间客户端过滤断言；补充表格渲染断言；`highlight` 用例（`query: { highlight: 'd1' }`）断言行 `data-row-key="d1"`；点击行打开 `决策详情` 抽屉（`await screen.findByText('决策详情')`）。
- [ ] 2. 重写 `DecisionsView.vue`：`n-data-table` remote + 列（标题、项目、状态、评审人徽章组 pending/approved/changes_requested、更新时间、来源会议）；筛选：项目、状态、评审人（`reviewer_user_id`，选项来自 `userNames`）；行点击打开 `DecisionDetailDrawer`（传入 `userNames`）；`loadUserNames()` 挂载时调用。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/global-workspace.test.ts src/tests/decision-workflow.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 决策筛选全服务端；详情抽屉复用 P5-6 组件；无日期区间客户端过滤。

**注意事项/已知风险：** 词典未覆盖的外部评审人不可选，属已知局限（规格 §7.9）；行点击不应在点击来源会议链接时误触（用 `@click.stop`）。

- [ ] 提交：`git add frontend/src/views/DecisionsView.vue frontend/src/tests/global-workspace.test.ts frontend/src/tests/workflow-components.test.ts && git commit -m "feat: rebuild decisions view with remote table"`

### Task P6-4：`InboxView` `n-list` + 增量刷新 + `source_comment` 深链

**目标：** 收件箱行改 `n-list`（未读加背景/圆点 + 粗体）；挂载与回到前台拉增量；深链优先 `source_comment`；已读操作联动壳层徽标。

**涉及文件：**
- 修改 `frontend/src/views/InboxView.vue`
- 修改 `frontend/src/tests/inbox.test.ts`

**实现步骤：**
- [ ] 1. 更新 `inbox.test.ts`：
  - 保留 `before` 游标“加载更多”断言；新增条目深链断言：`source_comment` 非空时链接为 `/meetings/m1?comment=c1`，否则为 `subjectHref` 结果；
  - 增量：挂载后调用 `GET /api/inbox/changes?cursor=<首屏最后一条 id>&limit=50`；返回新通知按 id 前插且不重复；`has_more: true` 时出现“点击刷新查看全部”提示；`visibilitychange` 回到前台再次请求增量；
  - 已读联动：标记已读成功后调用 `refreshUnread()`（可 spy `useInboxUnread` 的导出或用壳层请求断言）；
  - 未读行有圆点/加粗标记（断言 `data-unread="true"` 或类名，二选一并固定）。
- [ ] 2. 重写 `InboxView.vue`：`n-list` + `n-list-item`；未读圆点 + 粗体；保留“全部已读”按钮（`n-button`）与错误 `n-alert`；条目链接用 `notificationHref`；页面**不做定时轮询**，仅在 `onMounted` 与 `visibilitychange` 拉增量。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/inbox.test.ts src/tests/inbox-unread.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 增量与深链按规格 §7.10 工作；页面无定时器；已读成功后壳层徽标刷新。

**注意事项/已知风险：** `cursor` 即最后一条通知 id，按 id 升序返回；新通知前插时去重（按 id 集合）。

- [ ] 提交：`git add frontend/src/views/InboxView.vue frontend/src/tests/inbox.test.ts && git commit -m "feat: rebuild inbox with incremental refresh"`

### Task P6-5：`AiTasksView` 丢弃按钮 + 元信息 + `include_history`

**目标：** 终态未应用/未丢弃任务可丢弃；展示新字段；历史过滤开关。

**涉及文件：**
- 修改 `frontend/src/views/AiTasksView.vue`
- 修改 `frontend/src/tests/ai-tasks.test.ts`
- 修改 `frontend/src/tests/ai-work-assistant-plugin.test.ts`（如涉及）

**实现步骤：**
- [ ] 1. 更新测试：
  - `succeeded/failed/interrupted/canceled` 且无 `applied_at/dismissed_at` 时显示 `丢弃`，`n-popconfirm` 确认后 `POST /api/plugin-jobs/j1/dismiss`；后端 409 `plugin_job_not_dismissible` 时展示 `error.message`；
  - `error_code` 显示在卡片元信息；`rerun_of_id` 显示“重跑自任务 #x”；`applied_by/dismissed_by` 显示执行人；`applied_at/dismissed_at` 显示时间；
  - `include_history` 开关（`n-radio-group`：进行中/全部）：默认“进行中”请求 `/api/plugin-jobs?include_history=false`，切换“全部”请求 `include_history=true`；
  - 卡片文案包含“在发起页面应用此结果”（说明全局无应用按钮）；
  - 既有轮询、取消、重跑用例保留。
- [ ] 2. 修改 `AiTasksView.vue`：任务卡改 `n-card`；状态徽章改用 `StatusPill`（`kind="job"`，保留 `ai-task-status` 类避免既有断言失败）；新增丢弃、元信息与过滤开关；保留现有 `task-error-detail` 技术详情折叠；不新增全局应用按钮。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/ai-tasks.test.ts src/tests/ai-work-assistant-plugin.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 丢弃与历史过滤可用；无全局应用按钮；轮询行为不变。

**注意事项/已知风险：** `/apply` 由编辑器槽调用，`AiTasksView` 不调用；不要在全局视图提供应用入口。

- [ ] 提交：`git add frontend/src/views/AiTasksView.vue frontend/src/tests/ai-tasks.test.ts frontend/src/tests/ai-work-assistant-plugin.test.ts && git commit -m "feat: add ai job dismissal and history filter"`

### Task P6-6：`AdminUsersView` 表格化 + 重置密码抽屉

**目标：** 成员/申请/归档用 `n-data-table`；重置密码改 `n-drawer`；状态变更统一确认；头像用 `AppAvatar`。

**涉及文件：**
- 修改 `frontend/src/views/AdminUsersView.vue`
- 修改 `frontend/src/tests/account-admin.test.ts`

**实现步骤：**
- [ ] 1. 更新 `account-admin.test.ts`：
  - 用户列表用表格渲染（`document.querySelector('.n-data-table')` 非空或按行角色断言）；
  - 重置密码：点击 `重置密码` 打开抽屉（不再 `window.prompt`），输入 <12 位被拦截，输入 12 位提交 `POST /api/admin/users/{id}/reset-password` body `{password}`；
  - 批准/拒绝/归档/恢复：`n-popconfirm`（归档用 `n-dialog` 确认）；归档确认后 `POST /api/admin/users/{id}/disable`；恢复 `POST .../restore`；
  - 头像断言 `n-avatar` 存在且使用后端 `avatar_color`（fixture 补 `avatar_color: '#123456'`）。
- [ ] 2. 修改 `AdminUsersView.vue`：三区用 `n-data-table`（服务端无分页，全量加载；申请/归档区可用 `n-tabs` 或分区表格）；`重置密码` 抽屉（`n-form` min 12）；`AppAvatar` 替换 `.avatar`；`window.prompt` 与 `window.confirm` 全部移除。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/account-admin.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 管理员用户页无原生 prompt/confirm；头像使用后端颜色。

**注意事项/已知风险：** 管理员 API 可能不返回 `avatar_color`，`AppAvatar` 回退浅绿底即可；创建固定账号表单保留（可改 `n-form`，但本任务以列表与重置为主，不要遗漏原有用例）。

- [ ] 提交：`git add frontend/src/views/AdminUsersView.vue frontend/src/tests/account-admin.test.ts && git commit -m "feat: rebuild admin users with tables"`

### Task P6-7：`AdminPluginsView` 卡片/能力徽标/开关/事件表

**目标：** 插件卡片化；展示 `context_scopes`/`external_network` 能力；配置表单与开关 Naive 化；事件表固定 `limit=50` + 状态筛选。

**涉及文件：**
- 修改 `frontend/src/views/AdminPluginsView.vue`
- 修改 `frontend/src/tests/admin-plugins.test.ts`

**实现步骤：**
- [ ] 1. 更新 `admin-plugins.test.ts`：新增能力徽标断言（`上下文范围` 文本与 scope 值；`external_network: true` 时出现“可访问外部网络”且为警示色类/标签）；配置表单字段仍可填可存（`PUT /api/admin/plugins/{id}/config`）；开关切换 `PUT /api/admin/plugins/{id}/enabled`；事件表请求 `GET /api/admin/plugins/events?status=failed&limit=50`，表尾文案“最多显示 50 条，可用状态筛选”；**无页码**。
- [ ] 2. 修改 `AdminPluginsView.vue`：卡片改 `n-card` + `n-grid`；插件图标 `⌁` 改 `NIcon` + `Puzzle`；能力徽标区用 `NTag`；配置表单改 `n-form`（`n-input`/`n-input-number`/`n-switch`，secret 用 `n-input type="password"`）；启用开关改 `n-switch` 并保留“重启后生效”提示；事件失败改 `n-data-table`（列：事件类型/尝试次数/最后错误/重试按钮）。
- [ ] 3. **测试/验证：**运行：

```bash
npm --prefix frontend test -- src/tests/admin-plugins.test.ts
npm --prefix frontend test
```

预期：全绿。

**完成标准：** 能力徽标可见；事件表不做分页并注明上限。

**注意事项/已知风险：** 插件配置保存契约与错误处理不变；`external_network` 缺失时按 `false`/不显示警示处理。

- [ ] 提交：`git add frontend/src/views/AdminPluginsView.vue frontend/src/tests/admin-plugins.test.ts && git commit -m "feat: enrich admin plugins view"`

### Task P6-8：阶段门禁

**目标：** 确认 P6 全局视图、收件箱、AI 任务与管理页无回归，产出可合并的 P6 PR。

**涉及文件：** 无新增源码；验证 P6-1 至 P6-7 涉及的全部文件。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. 运行规格 §9 P6 指定文件：

```bash
npm --prefix frontend test -- src/tests/global-workspace.test.ts src/tests/inbox.test.ts src/tests/ai-tasks.test.ts src/tests/ai-work-assistant-plugin.test.ts src/tests/admin-plugins.test.ts src/tests/account-admin.test.ts
```

预期：全部通过。

- [ ] 2. `npm --prefix frontend test` → `Test Files 32 passed (32)`，无 failed。
- [ ] 3. `npm --prefix frontend run build` → 退出码 0。
- [ ] 4. `git diff --check` 无输出；`git status --short backend/` 为空。
- [ ] 5. 推送并创建 `feature/ui-overhaul-p6` PR（描述列出 `global-workspace.test.ts`、`meetings-view.test.ts` 等有意更新点）。等待用户合并后再开始 P7。

**完成标准：** 全量测试与构建双绿、后端零改动、P6 PR 已创建。

**注意事项/已知风险：** 阶段内失败不得带入下一阶段；确认全局列表没有恢复跨页客户端过滤。

---

# P7 收尾与文档

> 阶段分支：`feature/ui-overhaul-p7`。图标全量清扫、`styles.css` 瘦身、响应式与减弱动效走查、文档更新、手动视觉验收。

### Task P7-1：图标字形全量清扫（规格 §4.3 映射清单逐项替换）

**目标：** 前端与插件前端不再有 Unicode/emoji 图标字形；所有图标为 Lucide SVG + `NIcon`；图标按钮有 `aria-label`。

**涉及文件：**
- 修改 `frontend/src/**` 中所有命中的视图/组件（预计至少 `frontend/src/views/MeetingsView.vue`、`frontend/src/views/RegisterView.vue`、`frontend/src/views/ProjectOverview.vue`、`frontend/src/views/ProjectsView.vue`、`frontend/src/views/AdminPluginsView.vue`、`frontend/src/components/AgendaQueue.vue`、`frontend/src/components/ProjectRecordTabs.vue`、`frontend/src/components/CompletedMeetingChain.vue`、`frontend/src/components/AttachmentPanel.vue`、`frontend/src/components/AttentionCard.vue`、`frontend/src/views/InboxView.vue`、`frontend/src/styles.css`）
- 修改 `plugins/ai-work-assistant/frontend/assistant-ui.js`（如仍有装饰字形）
- 修改 `frontend/src/tests/ui-foundation.test.ts`（如增加字形扫描断言）

**实现步骤：**
- [ ] 1. **测试/验证：**运行扫描定位残留（排除测试文件；`→` 等也可能出现在普通文案里）：

```bash
rg -n '⌕|•••|✓|○|→|⌁|⌄|×|✕|✦|◎|●' frontend/src plugins --glob '!**/tests/**' --glob '!**/node_modules/**'
```

预期：输出全部命中点清单（P0-P6 已替换一部分）。
- [ ] 2. 按规格 §4.3 映射逐项替换：`⌕→Search`；`•••→MoreHorizontal`；`×→X`；`✓→Check`（成功图标 `✓` 圆形 → `CheckCircle2`）；`○→Circle`；`→`/`arrow-link` → `ChevronRight` 或 `ArrowUpRight`（链接可访问名不得包含箭头字符，箭头加 `aria-hidden="true"`）；`⌁→Puzzle`；`⌄→ChevronDown`（若来自 CSS `content`，改为模板内 Lucide 图标）；文件占位 `DOC→FileText`；字母头像全部走 `AppAvatar`。品牌 “M” 字标保留（不是功能图标）。
- [ ] 3. 每个图标按钮补 `aria-label`；小尺寸按钮加 `title` 或 `n-tooltip`。
- [ ] 4. 复扫并运行全量：

```bash
rg -n '⌕|•••|✓|○|→|⌁|⌄|×|✕|✦' frontend/src plugins --glob '!**/tests/**' --glob '!**/node_modules/**'
npm --prefix frontend test
```

预期：扫描无输出（或仅剩合理文案，逐条在 PR 说明）；全量无 failed。

**完成标准：** 功能图标全为 SVG；无字形图标残留；`aria-label` 完整。

**注意事项/已知风险：** 测试文件中若有断言旧字形的用例（如 `plugin-editor-slot.test.ts` 断言 `not.toHaveTextContent('✦')`）保持不动；它们正是防回归断言。`@` 提示文字“输入 @ 可提及成员”保留（是提示文字不是图标）。

- [ ] 提交：`git add frontend/src plugins/ai-work-assistant/frontend/assistant-ui.js frontend/src/tests/ui-foundation.test.ts && git commit -m "refactor: replace remaining glyph icons with svg"`

### Task P7-2：`styles.css` 瘦身（删除被替代类，保留布局与品牌 token）

**目标：** 删除被 Naive 组件取代的自定义样式，保留布局类、品牌 token、编辑器与会议进行中动效。

**涉及文件：**
- 修改 `frontend/src/styles.css`
- 删除 `frontend/src/components/ContextDrawer.vue`（仅当确认全仓无引用时；同时删除其相关样式）
- 可能修改仍引用旧类的视图/组件（若删除后发现引用保留，则回退该类并记录）

**实现步骤：**
- [ ] 1. 逐类确认不再被引用（示例命令，按候选类名执行）：
  - `.notice`/`.notice-error`/`.notice-warning`（被 `n-alert`/`n-message` 取代）
  - `.empty-state`/`.empty-inline`（被 `n-empty` 取代）
  - `.avatar`/`.avatar-small`（被 `AppAvatar` 取代）
  - `.dialog-backdrop`/`.conflict-dialog`（被 `NModal` 取代）
  - `.context-drawer`/`.context-drawer-backdrop`（被 `n-drawer` 取代）
  - `.search-box`、`.workspace-tabs`、`.project-new-menu`、`.table-list`、`.user-row`、`.switch`、`.upload-box`、`.file-glyph`、`.action-check`、`.arrow-link`、`.agenda-menu*`（按实际迁移情况）
  - `.status-pill[data-status]` 已 P0 删除，确认无残留
- [ ] 2. **测试/验证：**运行引用检查：

```bash
rg -n 'class="[^"]*(notice|empty-state|empty-inline|avatar|dialog-backdrop|conflict-dialog|context-drawer|table-list|user-row|switch|upload-box|file-glyph|action-check|arrow-link|agenda-menu)' frontend/src --glob '*.vue'
```

预期：无输出（或仅剩必须保留的类，逐条说明）。
- [ ] 3. 删除上述规则，保留：`:root` 品牌 token、`.app-shell`/`.page`/`.workspace-page`/`.workspace-sidebar`/`.workspace-topbar`、`.workspace-section`/`.attention-layout`/`.project-*` 布局类、`.markdown*`、`.agenda-*` 布局与状态类（测试依赖 `.agenda-status-*`/`.selected`）、`.meeting-live*` 脉冲与 `@media (prefers-reduced-motion)`、响应式媒体查询。文件顶部保留 §6.1 约定注释。
- [ ] 4. 运行全量测试与构建，并记录 `styles.css` 行数（目标显著低于 336 行）：

```bash
wc -l frontend/src/styles.css
npm --prefix frontend test
npm --prefix frontend run build
```

预期：测试/构建双绿；无因删样式导致的断言失败。

**完成标准：** 旧类删除且无引用；品牌 token 与布局完好。

**注意事项/已知风险：** 删除任何被测试 `toHaveClass` 断言依赖的类会破坏测试——先跑全量测试再提交；不确定的类保留并在 PR 标注。

- [ ] 提交：`git add frontend/src/styles.css && git commit -m "refactor: slim shared styles after naive migration"`

### Task P7-3：响应式断点走查（≤950 / ≤800 / ≤640）

**目标：** 断点行为符合规格 §4.7：两栏折叠、侧边栏变顶栏、表单单列、抽屉全宽、表格横向滚动。

**涉及文件：**
- 修改 `frontend/src/styles.css`（断点规则）
- 修改使用 `n-drawer` 的组件（宽度已用 `min(560px, 100vw)`，核对）

**实现步骤：**
- [ ] 1. 启动本地前后端（`./scripts/start.sh local`）并用真实浏览器（或测试浏览器工具）逐条核对：
  - `≤950px`：首页 `attention-layout` 单列、项目概览双列折叠、筛选区折行；
  - `≤800px`：侧边栏变顶栏网格（`.app-shell` 单列、导航横向）；
  - `≤640px`：表单单列、`n-drawer` 全宽、会议列表行单列、表格出现横向滚动（`scroll-x` 且显式 `min-width`）。
- [ ] 2. 修正断裂处：补充/调整 `@media` 规则，确保 `n-data-table` 在窄屏可滚动、`n-drawer` 宽度为 `min(560px, 100vw)`；不引入固定列（jsdom 约束）。
- [ ] 3. **测试/验证：**运行构建与测试：

```bash
npm --prefix frontend run build
npm --prefix frontend test
```

预期：双绿。

**完成标准：** 三个断点无横向溢出、无被遮挡操作；抽屉在 375px 视口可用。

**注意事项/已知风险：** 这是手动走查任务，结果与截图记录到 PR；若发现仅视觉问题，允许在本阶段微调样式，不新增组件逻辑。

- [ ] 提交：`git add frontend/src/styles.css frontend/src/components frontend/src/views && git commit -m "fix: polish responsive breakpoints"`

### Task P7-4：动效与 `prefers-reduced-motion` 走查

**目标：** 过渡 160-180ms；移除按钮 hover `translateY`；减弱动效媒体查询覆盖自有动画。

**涉及文件：**
- 修改 `frontend/src/styles.css`

**实现步骤：**
- [ ] 1. 删除 `.button:not(:disabled):hover { transform: translateY(-1px); }` 的位移效果（保留颜色/阴影过渡，交给 Naive 交互态）；确保不叠加重叠阴影。
- [ ] 2. 核对自有动画全部受 `@media (prefers-reduced-motion: reduce)` 约束：`.meeting-live .status-pill[data-status="in_progress"]`、`.agenda-queue-row.selected.agenda-status-in_progress`、`.agenda-detail-enter/leave`、`.completed-outcome-*` 的 `⌄` 旋转。Naive 自带 reduced-motion 支持，无需自定义。
- [ ] 3. 浏览器 DevTools 切换 `prefers-reduced-motion: reduce`，确认：无脉冲、无滚动斜纹、无位移动画；抽屉/对话框仍可正常开关。
- [ ] 4. **测试/验证：**运行：

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

预期：双绿。

**完成标准：** hover 无位移；减弱动效下无动画但仍可用。

**注意事项/已知风险：** 保留会议进行中的脉冲动效，但必须受媒体查询约束（规格 §4.6）。

- [ ] 提交：`git add frontend/src/styles.css && git commit -m "fix: align motion with reduced-motion preference"`

### Task P7-5：文档更新（规格 §13）

**目标：** `docs/development.md` 反映新的前端 UI 栈与测试底座；不新增验证命令；README/AGENTS 不动。

**涉及文件：**
- 修改 `docs/development.md`

**实现步骤：**
- [ ] 1. 在“架构概览”增加前端 UI 栈描述：Vue 3 + Naive UI（浅色主题；`src/theme/naive.ts` 维护 `themeOverrides` 与状态色映射；品牌值仍以 `styles.css` 的 `:root` 为准）+ `@lucide/vue` 图标 + Milkdown Crepe 编辑器；不引入 Pinia（reactive 单例模式）；`n-drawer`/`n-popconfirm`/`n-message` 的交互约定。
- [ ] 2. 在“测试与构建”补一句：Naive 组件测试依赖 `frontend/src/tests/setup.ts` 的 jsdom 补丁（`ResizeObserver`、`matchMedia`、`scrollTo`），弹出层用全局 `screen` 查询；命令保持 `npm --prefix frontend test` 与 `npm --prefix frontend run build` 不变。
- [ ] 3. 检查根 `README.md`、`AGENTS.md` 是否需要同步：按规格 §13 预期无需改动；如发现 UI 描述与事实不符，只做最小同步并在 PR 说明。
- [ ] 4. **测试/验证：** 检查 Markdown 链接与空白：

```bash
git diff --check docs/development.md
rg -n 'development.md|README.md' docs/README.md AGENTS.md
```

预期：`git diff --check` 无输出；链接目标存在。

**完成标准：** 文档描述与实现一致；命令不变；无长说明三处复制。

**注意事项/已知风险：** `docs/superpowers/specs|plans/` 是历史记录，不维护；最终以 `docs/development.md` 为准。

- [ ] 提交：`git add docs/development.md && git commit -m "docs: describe frontend ui stack"`

### Task P7-6：手动视觉验收清单（规格 §11.4）

**目标：** 在隔离实例上完成真实浏览器验收，覆盖自动化测试无法覆盖的交互。

**涉及文件：** 无计划内源码改动（若发现缺陷，修复落到对应阶段文件并重跑该阶段门禁）；验收记录写入 P7 PR 描述。

**实现步骤：**

**测试/验证：** 步骤 1 启动的容器必须通过 `docker ps` 可见且健康；步骤 2 清单逐项给出结论；步骤 3 的清理命令输出符合预期；另运行 `npm --prefix frontend test && npm --prefix frontend run build` 保持双绿。

- [ ] 1. 构建并使用一次性数据目录启动隔离实例（不改动现有 8000 服务）：

```bash
test_dir=$(mktemp -d /tmp/meetflow-ui-overhaul.XXXXXX)
mkdir -p "$test_dir/data"
docker build --tag meetflow:ui-overhaul-check .
docker run --detach --rm --name meetflow-ui-overhaul-check \
  --publish 127.0.0.1:18031:8000 \
  --volume "$test_dir/data:/app/data" \
  --env ADMIN_USERNAME=ui-check \
  --env ADMIN_PASSWORD=ui-check-admin-password \
  --env APP_SECRET_KEY=ui-check-app-secret-key-20260915-0123456789 \
  meetflow:ui-overhaul-check
```

- [ ] 2. 按清单逐项验收并记录结果（通过/异常+截图）：
  - 抽屉/对话框：焦点进入与 Esc 关闭；提交中不可点遮罩关闭；`n-popconfirm` 确认后正确提交。
  - `n-data-table`：行动项/决策/用户/插件事件的分页、筛选、空态观感；窄屏横向滚动。
  - 未读徽标：壳层 60s 轮询（可临时缩短验证或观察一次刷新）、收件箱已读后徽标即时减少；路由切换与回到前台刷新。
  - 冲突对话框：双栏对比可滚动；“载入服务器版本/用本地草稿覆盖”行为正确。
  - `≤640px`：表单单列、抽屉全宽、无横向溢出。
  - 面包屑：项目详情页头项目名回 `/projects`；会议工作区项目名回项目详情。
  - `prefers-reduced-motion: reduce`：无脉冲与位移动画。
  - 附件：真实上传/下载/删除（含 20 MB 上限拦截）。
  - SSE 工作简报：流式生成与取消。
  - Milkdown：在 `n-drawer` 内的滚动与工具栏可用；显式保存按钮仍工作且冲突提示正确。
- [ ] 3. 清理隔离资源并确认原服务不受影响：

```bash
docker stop meetflow-ui-overhaul-check
docker image rm meetflow:ui-overhaul-check
rm -rf "$test_dir"
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
```

预期：临时容器/镜像/数据目录均不存在；原有服务仍在。

**完成标准：** 清单逐项有结论；发现的问题要么修复（回到对应任务所属文件）要么记录为已知限制。

**注意事项/已知风险：** 不要使用真实 AI/插件密钥；验收实例使用一次性数据目录；任何修复都要重跑对应阶段门禁。

### Task P7-7：最终门禁（全量前端 + 构建 + 后端回归确认 + PR）

**目标：** 确认全部 8 个阶段合并后前端测试/构建双绿、后端零改动且回归结果与基线一致，产出最终 PR。

**涉及文件：** 无新增源码；汇总验证整个计划涉及的文件与 `docs/development.md`。

**实现步骤：**

**测试/验证：** 以下命令必须全部通过：

- [ ] 1. 全量前端测试：

```bash
npm --prefix frontend test
```

预期：`Test Files 32 passed (32)`（25 基线 + P0 1 个 + P1 2 个 + P5 4 个），无 failed/skipped。
- [ ] 2. 生产构建与体积对比：

```bash
npm --prefix frontend run build
```

预期：退出码 0；记录主 chunk 体积并与 P0 基线对比，写入 PR（体积增长应来自 Naive 具名导入与 tree-shaking，禁止出现全量引入迹象）。
- [ ] 3. 后端零改动确认与后端回归：

```bash
git status --short backend/
.venv/bin/python -m pytest -q
```

预期：`git status --short backend/` 无输出；`.venv/bin/python -m pytest -q` 为 `219 passed, 1 failed`（同一已知环境性失败 `test_wheel_resources.py::test_wheel_contains_and_runs_migrations_outside_source_tree`）。
- [ ] 4. 差异边界检查：

```bash
git diff --check
git status --short
```

预期：无空白错误；改动仅限前端源码/测试与 `docs/development.md`。
- [ ] 5. 推送 `feature/ui-overhaul-p7` 并创建最终 PR，描述包含：阶段改动总览、手册链接（`docs/development.md`）、有意更新的测试断言汇总、体积对比、手动验收清单结果、已知延期项（#25 角色指派、#35 复制来源徽标、#36 放弃写入口）。等待用户合并。

**完成标准：** 两条强制命令双绿、后端零改动、PR 完整。

**注意事项/已知风险：** 若后端 diff 出现任何文件，立即回滚该文件并排查；不得以“顺手修复”名义改后端。

---

## 规格覆盖自检

| 规格要求 | 实施任务 |
| --- | --- |
| §4.1 Token 精炼与品牌映射 | P0-2、P0-5、P7-2 |
| §4.2 `themeOverrides` + `statusTone` | P0-2、P0-5 |
| §4.3 图标策略与映射清单 | P0-2（NIcon 基础）、P7-1（全量清扫） |
| §4.4 头像策略（`avatar_color`） | P0-4、P6-6 |
| §4.5 加载/空态/错误面 | P3-2、P2-3、P4-2、P5-2（`useMessage`/`useDialog`）、P7-2 |
| §4.6 动效与 reduced-motion | P1-5、P7-4 |
| §4.7 响应式断点 | P7-3 |
| §4.8 无障碍 | P1-2（aria-label）、P4-3（button 语义）、P7-1 |
| §5.1 Provider + locale | P0-4 |
| §5.2 侧边栏/顶栏 | P1-2、P1-3 |
| §5.3 未读徽标数据流 | P1-1、P1-3、P6-4 |
| §5.4 导航 IA 与深链参数 | P4-6（comment）、P5-1（tab）、P6-2/P6-3（highlight）、P3-4（series_id 范围） |
| §6.1 抽屉表单模式 | P1-5（约定）、P3-3/P3-4、P4-2、P5-2/P5-3/P5-4/P5-5/P5-6 |
| §6.2 版本冲突统一 | P1-4、P5-2、P5-8 |
| §6.3 服务端分页模式 | P3-4、P5-8、P6-1/P6-2/P6-3/P6-4/P6-7 |
| §6.4 权限驱动渲染 | P0-6、P4-1/P4-2、P5-1/P5-2/P5-5/P5-6/P5-7、P6-5 |
| §6.5 反馈与刷新策略 | 全局约束 9/10 + 各任务 |
| §6.6 深链与返回 | P4-6、P6-2/P6-3 |
| §7.1-7.2 登录/注册/账号 | P2-1、P2-2、P2-3 |
| §7.3 首页 | P3-1、P3-2 |
| §7.4 项目列表 | P5-9（创建抽屉，筛选保持客户端并注明）；P5-3（项目详情页创建拆分） |
| §7.5 项目详情全部 | P5-1 至 P5-8 |
| §7.6 会议列表 | P3-4 |
| §7.7 会议工作区全部 | P4-1 至 P4-7 |
| §7.8 行动项全局 | P6-2（+P5-5 抽屉、P6-1 姓名） |
| §7.9 决策全局 | P6-3（+P5-6 抽屉） |
| §7.10 收件箱 | P6-4（+P6-1 深链） |
| §7.11 AI 任务 | P6-5 |
| §7.12 用户管理 | P6-6 |
| §7.13 插件管理 | P6-7 |
| §8 对齐清单（实现项） | 见各 Task；#25 角色指派/#35/#36 延期不实施 |
| §9 P0-P7 分期 | 八个阶段逐一对应 |
| §11.1 jsdom 适配 | P0-3 + 全局约束 11 |
| §11.2 既有测试有意更新 | P0-5、P1-2、P3-1/P3-4、P4-3（点名 161-164）、P6-2/P6-3 |
| §11.3 类型与构建 | 每个阶段门禁 |
| §11.4 手动验证 | P7-6 |
| §13 文档 | P7-5 |

## 假设与本计划裁决（需用户知悉）

1. **Provider 位置**：`NConfigProvider`/`NMessageProvider`/`NDialogProvider` 放在 `App.vue`（规格 §5.1 结构），`frontend/src/main.ts` 预计不改；如实现发现必须挂载级 provider，会补充并在 PR 说明。
2. **新增测试文件超出规格 §10 三个**：`ui-foundation.test.ts`（P0）、`versioned-save.test.ts`、`inbox-unread.test.ts`（P1）。理由：主题/状态色、jsdom 补丁、未读轮询与冲突原语需要确定性单测；最终测试文件数预计 32 个（非 25）。
3. **新增两个共享组件超出规格 §10 新组件清单**：`MeetingParticipantEditor.vue`（P3）与 `MeetingCreateDrawer.vue`（P3），用于在会议列表与项目页复用参与人编辑与创建表单；不新增路由、不改后端。
4. **`useUserNameMap` 命名**：规格只规定“从 `/api/projects` 成员聚合姓名映射”的策略，本计划把实现放在 `frontend/src/composables/useUserNameMap.ts`。
5. **未知状态回退**：`statusTone` 对未知状态返回 `'muted'`（中性灰），不误报错误；`priorityTone` 未列出时同样回退 `'muted'`。
6. **准备抽屉成员数据源**：会议可能包含非项目成员参与人；项目详情 403 时退化为当前参与人列表并提示，不阻断准备信息。
7. **`n-date-picker` 在 jsdom 的可驱动性**：优先使用；若测试驱动成本过高，允许在创建/准备抽屉内降级为受控 `input type="datetime-local"`（仅容器 Naive），并在对应 PR 说明。
8. **`ContextDrawer.vue`**：迁移完成后不再使用；P7-2 若确认无引用则删除文件（属样式清理范围），如保留则不删除。
9. **规则 8 的会议准备字段**：`meeting.host/recorder` 与参与人行 `participation_role` 独立展示与提交，不互相覆盖。
10. **延期项不再触碰**：项目成员角色指派（#25 的角色部分）、议题复制来源徽标（#35）、开放问题放弃（#36）均不实现、不改后端；仅当数据显示 `dropped` 时渲染标签。
