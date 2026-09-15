# 前端 UI 全面改版与后端能力对齐设计

**日期：** 2026-09-14
**状态：** 设计已确认（含第 15 节裁决），进入实施计划阶段
**范围：** 前端全部 14 条路由与既有组件；引入 Naive UI 设计系统；将每页逻辑与后端既有 API 能力完全对齐。后端契约零改动（除确认为不可能的前端能力外，不新增端点、不改响应结构）。

## 1. 背景与目标

MeetFlow 前端目前是纯手写 CSS（`styles.css` 336 行 + 少量 scoped 样式）加少量自定义组件的形态：没有 UI 库、没有表单校验体系、状态色与文案散落在 CSS 属性选择器里，图标混杂 Unicode 字符（`⌕ ••• × ✓ ○ → ⌁ ⌄`）与 Lucide SVG。与此同时，后端在协作加固（`capabilities` 权限模型、`expected_version` 乐观锁、活动台账、收件箱、插件任务生命周期）以及会议/产出领域（议题跳过与移动、决策评审流转、开放问题排期与解决、系列常设议题等）交付了大量能力，前端只消费了其中一小部分：会议取消无入口、行动项全局视图显示 owner 原始 UUID、决策评审完全不渲染、项目动态只显示进展而非真实活动流、收件箱未读数从未出现在壳层。

本次改版的目标：

1. 以 Naive UI（浅色主题）为底座建立统一设计系统，保留既有深绿品牌方向（`#0b6a58` 家族）并精炼 token，通过 `themeOverrides` 映射品牌色。
2. 全面清理图标体系：功能图标一律使用 `@lucide/vue` SVG，替换全部 Unicode/emoji 字形；字母头像使用后端提供的 `avatar_color`。
3. 每页逻辑与后端 API 完全对齐：缺失的会议取消、议题跳过/移动/迁移/转问题/复制、决策评审流转、行动项编辑与状态流转、开放问题生命周期、项目活动台账、收件箱增量与未读、评论删除与回复分页、插件任务丢弃等能力都获得可见、可操作的 UI。
4. 全局稠密列表（行动项、决策、管理员用户、插件事件）改为 `n-data-table` + 服务端筛选/分页；富内容面（首页、项目、会议工作区）保持卡片/行布局。
5. 创建/编辑统一为右侧 `n-drawer` 表单；破坏性/确认操作统一 `n-popconfirm`（不够用时 `n-dialog`）。
6. 开放问题生命周期落在项目详情新 Tab（复用既有端点），不新增全局问题页。
7. 保持 Milkdown Crepe 编辑器与 marked+DOMPurify 渲染；保持既有轻量 reactive 单例状态模式（不引入 Pinia）。
8. 后端 API 契约、错误码、消息、响应结构、行为一律不改。25 个前端测试文件（`frontend/src/tests/*.test.ts`，共 124 个用例；目录内另有 `setup.ts`）最终全绿，`npm --prefix frontend run build`（vue-tsc 严格）通过。

## 2. 非目标

- 不改任何后端代码、端点、错误码、序列化结构或数据库迁移；后端行为（含状态机、权限判定）保持不变。
- 不新增后端能力作为前提：所有 UI 能力都只消费已存在的端点；确属“前端不可能实现”的对齐项在本规格第 8 节明确标记为延期并给出原因。
- 不引入 Pinia、Tailwind、ESLint、暗色主题、国际化多语言（仅接入 Naive 的 zhCN locale）。
- 不改变公开镜像启动方式、部署契约或插件信任模型。
- 不做实时协作（WebSocket）、在线状态、消息推送。
- 不重写会议工作区的保存/乐观锁核心逻辑（`useMeetingWorkspace`、`AgendaDetail` 的 dirty/冲突处理保留既有语义），只迁移其表现层并补齐缺失动作。

## 3. 已确认决策与约束

以下为用户已确认的决策，本规格不再重新讨论：

1. **组件库**：Naive UI（`naive-ui`），仅浅色主题；保留深绿品牌方向（现 token `--green #0b6a58` 家族），通过 `themeOverrides` 映射。
2. **图标**：仅 SVG，继续使用 `@lucide/vue`；允许 Naive 内置 icon 插槽。替换全部 Unicode/emoji 图标字形（`⌕`、`•••`、`×`、`✓`、`○`、`→`、`⌁`、`⌄`、`@`、字母字形等）。字母头像允许，但必须使用后端提供的 `avatar_color`。
3. **范围**：前端为主的全量视觉改版 + 页面逻辑与后端能力完全对齐，分阶段交付；不为未决问题新增后端端点；仅当某对齐项不可能实现时允许极小后端改动（本规格发现两处候选：#35 复制来源投影、#36 开放问题放弃写入口，已在第 8 节标记延期并在第 15 节请求用户授权，未获授权不实施）。
4. **列表形态**：稠密全局列表（行动项、决策、管理员用户、插件事件）→ `n-data-table` + 服务端筛选/分页；富内容面（首页、会议、项目、工作区）保留卡片/行布局。
5. **表单与确认**：创建/编辑实体 → 右侧 `n-drawer` 表单；破坏性/确认 → `n-popconfirm`（不足以表达时用 `n-dialog`）。
6. **开放问题**：生命周期落在项目详情新 Tab，复用 `GET/POST /api/projects/{id}/open-questions`、`PUT /api/open-questions/{id}`、`/schedule`、`/resolve`；不建全局问题页。
7. **编辑器与状态**：保留 Milkdown Crepe 编辑器与 marked+DOMPurify 渲染；保留既有轻量 reactive 单例状态模式，不引入 Pinia（除非发现硬性技术理由，本规格未发现）。
8. **后端契约冻结**：不改变任何后端 API 契约、错误码、消息或响应结构，不改后端行为。前端-only。
9. **测试与构建基线**：`frontend/src/tests/` 的 25 个测试文件（jsdom + @testing-library/vue，124 个用例；另有 `setup.ts`）必须全绿；允许对固化旧 UI 遗漏的测试（如“不显示版本号”“没有独立跳过动作”）做有意更新。`npm --prefix frontend run build` 必须通过。
10. **权限渲染**：页面逻辑必须严格按服务端 `capabilities` 渲染操作入口，绝不从角色推导项目/会议能力；仅管理页路由守卫（`meta.admin`）可依据服务端会话中的 `role`。

**调研校正（已对照当前后端实现逐条核实，以下事实优先于早期摘要）：**

1. `PUT /api/meetings/{id}` 的 `MeetingEdit.participants` 会被实际应用（`backend/app/meetings/service.py::update_meeting` 在 `participants is not None` 时全量替换并去重），主持/记录字段同样可改；不存在“后端没有参与人编辑端点”的限制，参与人在会议可变状态下可编辑。
2. `PUT /api/projects/{id}` 的 `ProjectEdit.member_ids` 会全量替换项目成员（`backend/app/projects/service.py::update`），`lead_user_id` 可改；但成员角色只能保持默认 `member`，没有把成员指派为 `stakeholder` 的写入口。
3. `reopen` 仅允许从 `completed` 转换（`backend/app/meetings/service.py::reopen`，`allowed_from={completed}`）；`canceled` 不可重开。`cancel` 不跳过议题、不生成完成快照，只标记状态并清空 `completed_at`；跳过未结束议题与生成快照发生在 `finish`。
4. 全局 `GET /api/meetings`、`/api/actions`、`/api/decisions` 均已有服务端筛选与 `limit/offset/total`；`GET /api/inbox/changes` 的 `cursor` 即最后一条通知 id，响应含 `unread_count`、`has_more`。
5. 当前基线：`npm --prefix frontend test` 为 25 个测试文件 / 124 个用例全绿；`styles.css` 336 行；`@lucide/vue`、Milkdown、marked+DOMPurify 均在用，`naive-ui` 尚未安装。

仓库规则约束（来自 `AGENTS.md` / `docs/README.md`，必须遵守）：

- 前端-only 改动不涉及 Alembic 迁移；本规格不会触碰生产数据字段。
- 文档归属：本规格是带日期的设计记录，不替代当前手册；`docs/development.md` 中前端栈描述需在改版落地时同步（见第 13 节）。
- 验证命令保持 `npm --prefix frontend test` 与 `npm --prefix frontend run build`；不新增强制命令。

## 4. 设计系统

### 4.1 Token 精炼

保留现有 `:root` 变量作为品牌基准，收敛为两组：

**品牌/语义 token（继续维护在 `styles.css` 的 `:root`，作为品牌色的唯一权威值；Naive 的 `themeOverrides` 无法在运行期读取 CSS 变量，因此 `src/theme/naive.ts` 以同值字面量映射，并在注释中标注与 `:root` 的对应关系）：**

| Token | 现值 | 改版后 | 说明 |
| --- | --- | --- | --- |
| `--green` | `#0b6a58` | `#0b6a58` | 主色，映射 `primaryColor` |
| `--green-dark` | `#075044` | `#075044` | 按压/深色文字，映射 `primaryColorPressed` |
| `--green-hover` | 无 | `#0d7c67` | 悬停，映射 `primaryColorHover`/`primaryColorSuppl` |
| `--green-soft` | `#dcebe6` | `#dcebe6` | 浅绿底（标签、头像底、选中行） |
| `--ink` | `#17232d` | `#17232d` | 主文字 |
| `--muted` | `#66727f` | `#66727f` | 次要文字 |
| `--paper` | `#fbfcfd` | `#fbfcfd` | 卡片/面板底 |
| `--canvas` | `#f1f3f5` | `#f1f3f5` | 页面底 |
| `--line` | `#d7dde3` | `#d7dde3` | 边框/分割线 |
| `--amber` | `#e9a23b` | `#e9a23b` | 警示主色 |
| `--red` | `#ae3f36` | `#ae3f36` | 错误/破坏主色 |
| `--shadow` | `0 8px 22px rgba(31,43,55,.07)` | 不变 | 卡片投影 |

**排版/间距/圆角：** 正文 14px/行高 1.65（沿用）；标题层级改为 28/20/16/14（放弃现有 `clamp(2.2rem, 5vw, 4.7rem)` 巨型页头，`PageHeader` 收敛为中等字号）；间距刻度沿用 4/8/12/16/24/32；圆角统一 8px（控件）/12px（卡片）；控制高度 40px（默认）/34px（小）。状态徽章圆角 999px。

### 4.2 Naive themeOverrides 映射表

新文件 `frontend/src/theme/naive.ts` 导出 `naiveThemeOverrides`（`GlobalThemeOverrides`）与 `statusTone()`。核心映射：

| Naive 键 | 值 |
| --- | --- |
| `common.primaryColor` / `primaryColorHover` / `primaryColorPressed` / `primaryColorSuppl` | `#0b6a58` / `#0d7c67` / `#075044` / `#0d7c67` |
| `common.successColor` | `#2f9e68`（健康度 on_track 用） |
| `common.warningColor` | `#e9a23b` |
| `common.errorColor` | `#ae3f36` |
| `common.infoColor` | `#0b6a58` |
| `common.borderRadius` | `8px` |
| `common.textColorBase` / `textColor1` / `textColor2` / `textColor3` | `#17232d` / `#17232d` / `#4a545e` / `#66727f` |
| `common.borderColor` / `dividerColor` | `#d7dde3` / `#e5e9ed` |
| `common.bodyColor` / `cardColor` / `modalColor` / `popoverColor` / `tableColor` | `#f1f3f5` / `#fbfcfd` / `#ffffff` / `#ffffff` / `#ffffff` |
| `common.fontFamily` | `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif` |
| `Button.heightMedium` / `heightSmall` / `borderRadiusMedium` / `fontWeight` | `40px` / `34px` / `8px` / `700` |
| `Tag.borderRadius` | `999px` |
| `Card.borderRadius` | `12px` |
| `DataTable.thColor` / `tdColor` / `borderColor` | `#f4f6f8` / `#ffffff` / `#e5e9ed` |
| `Drawer` / `Dialog` / `Form` / `Input` / `Select` | 采用 common 默认，仅微调 `Input.borderRadius` 等为 `8px` |

**状态色映射 `statusTone()`**（把 `styles.css` 的 `.status-pill[data-status=...]` 四组规则收敛为单一函数，供 `StatusPill`/`NTag` 使用）：

| 语义组 | 状态值 | NTag type / 自定义色 |
| --- | --- | --- |
| 进行中·绿色 | `active` `in_progress` `final` `done` `resolved` `applied` `approved` `on_track` `succeeded` | `success` |
| 待办·琥珀 | `pending` `draft` `ready` `planned` `open` `proposed` `scheduled` `queued` `requesting` `at_risk` `changes_requested` | `warning` |
| 完成类·浅绿 | `completed` `skipped` `interrupted` | `default` + `--green-soft` 前景 |
| 取消/异常·红灰 | `rejected` `disabled` `canceled` `withdrawn` `superseded` `dropped` `failed` `dismissed` `off_track` `archived` | `error`（`disabled`/`archived`/`dismissed` 用 `default` 灰） |
| 优先级 | `urgent`→红，`high`→琥珀，`normal`→灰，`low`→浅灰 | `NTag` 自定义 |

`StatusPill.vue` 重构为 `NTag` 薄封装：保留同名组件与 `status/kind/label` props，`data-status` 属性继续输出（兼容现有测试选择器），文案仍来自 `utils/labels.ts`。

### 4.3 图标策略

- 功能图标一律 `@lucide/vue` 组件，包一层 `<NIcon>` 以统一尺寸/颜色；禁止新写 Unicode/emoji 字形作为图标。
- 映射清单（P7 全量清扫时逐项落地）：`⌕`→`Search`；`•••`→`MoreHorizontal`（议题行）/`Ellipsis`；`×`→`X`；`✓`→`Check`；`○`→`Circle`；`→`/`arrow-link`→`ChevronRight` 或 `ArrowUpRight`；`⌁`（插件 icon）→`Puzzle`；`⌄`（折叠箭头）→`ChevronDown`；`@`（提及提示）→`AtSign` 加文字“输入 @ 可提及成员”（提示文字保留）；文件占位 `DOC` 字母字形→`FileText`；成功图标 `✓` 圆形→`CheckCircle2`。
- 图标按钮必须有 `aria-label`（沿用现有约定），小尺寸按钮加 `title`/`n-tooltip`。
- 品牌标识（侧边栏/登录页的衬线 “M” 字标）属于品牌 logo 而非功能图标，本规格默认保留；如需改为 SVG 标识见第 15 节未决问题。

### 4.4 头像策略

- 新组件 `frontend/src/components/AppAvatar.vue`：基于 `n-avatar`，字母取 `display_name` 首字符，背景色取后端 `avatar_color`（`UserRef.avatar_color`、`/api/auth/session` 返回的 `avatar_color`）；缺省回退 `--green-soft` 底 + `--green-dark` 字。
- 替换 `App.vue` 顶栏、`AdminUsersView`、`AttentionCard`/评论等所有 `.avatar` 使用点；`UserRef` 类型已含可选 `avatar_color`，会话 `SessionUser` 增加 `avatar_color` 字段（`/api/auth/me` 与 `/session` 均返回）。
- 侧边栏品牌 `M` 块保留（见 4.3）。

### 4.5 加载 / 空态 / 错误面

- **加载**：页面级首屏用 `n-skeleton`（列表用 3-5 行骨架，卡片面用骨架卡片）；局部刷新沿用 `n-spin`。
- **空态**：统一 `n-empty`（描述文案沿用现有“尚无…”“调整筛选条件…”等措辞），删除 `.empty-state`/`.empty-inline` 自定义样式。
- **错误面**：
  - 瞬时操作失败（保存/状态变更）→ `n-message.error`（`useMessage`），消息取自 `apiErrorMessage` 的 `error.message`。
  - 页面级加载失败 → 保留行内 `n-alert`（对应 `.notice-error`），文案 + 重试按钮。
  - 阻断性确认（删除项目、归档用户、放弃 AI 结果、议题删除带产出迁移提示）→ `n-dialog`/`n-popconfirm`。
  - 全局 `useMessage`/`useDialog` 由 `App.vue` 的 provider 提供，组件通过 `useMessage()` 获取；错误处理统一走 `utils/errors.ts` 的 `errorMessage()`（保持现有签名）。

### 4.6 动效

- 过渡 160-180ms ease；抽屉/对话框使用 Naive 默认动画；`prefers-reduced-motion: reduce` 时关闭（Naive 自带支持；自有 CSS 动画沿用现有 `@media (prefers-reduced-motion)` 处理，保留会议进行中的脉冲动效但受该媒体查询约束）。
- 按钮 hover 的 `translateY(-1px)` 效果移除（交给 Naive 交互态），避免与 Naive 状态叠加。

### 4.7 响应式断点

- 内容最大宽度 1180px（工作区页 1280px），沿用 `.page`/`.workspace-page` 布局壳。
- 断点：`≤950px`（两栏折叠，过滤器折行）、`≤800px`（侧边栏变顶栏网格，沿用现状）、`≤640px`（表单单列、抽屉全宽）。
- `n-drawer` 宽度 `min(560px, 100vw)`；表格在窄屏启用横向滚动（`scroll-x`）。

### 4.8 无障碍

- 图标按钮必须 `aria-label`；`n-drawer`/`n-dialog` 由 Naive 提供 focus trap 与 Esc 关闭；表头、标签关联沿用现有 `label`/`aria-label` 约定。
- 状态徽章加 `role="status"` 仅用于页面级动态提示（如“纪要已保存”），列表徽章不加。
- 键盘可达：所有行操作保留为真实 `<button>`，不依赖 hover 才能操作。

## 5. 应用壳层

### 5.1 Provider 嵌套与 locale

`App.vue` 结构调整为：

```text
NConfigProvider(:theme-overrides="naiveThemeOverrides" :locale="zhCN" :date-locale="dateZhCN")
└─ NMessageProvider
   └─ NDialogProvider
      ├─ (session.user) NLayout → 侧边栏 + 顶栏 + RouterView
      └─ (未登录) RouterView（登录/注册）
```

- `zhCN`、`dateZhCN` 从 `naive-ui` 导入；不引入 `vfonts`，字体统一走 `themeOverrides.common.fontFamily`（见 4.2）。
- 登录/注册页同样位于 provider 内，复用 message/dialog。

### 5.2 侧边栏与顶栏

- `AppSidebar.vue` 重构为 `n-layout-sider` + `n-menu`：工作区菜单项（为你/项目/会议/行动项/决策/收件箱/AI 任务），管理员分组（用户/插件/设置）仍以 `session.user?.role === 'admin'` 门控（该处允许用 role，对应后端 `admin_user` 依赖）。图标用 Lucide 经 `NIcon` 渲染；收件箱项右侧渲染 `n-badge`（未读数）。
- 品牌区保留 “M” 字标 + “MeetFlow / 团队会议工作区”。
- 顶栏右侧：当前用户 `n-dropdown`（触发器为 `AppAvatar` + display_name，菜单项：账号设置、退出登录）+ 收件箱铃铛入口（`n-badge` 包裹 `Bell` 图标按钮，点击进 `/inbox`）。移除现有纯文本“退出”按钮。

### 5.3 未读徽标数据流

- 新模块 `frontend/src/composables/useInboxUnread.ts`：reactive 单例（导出 `unreadCount` ref + `refreshUnread()`），符合决策 7 的状态模式。
- **数据源**：`GET /api/inbox/changes?cursor=0&limit=1`（响应含 `unread_count`，代价最小）；首次取值失败时回退 `GET /api/inbox` 的 `unread_count`。
- **轮询节奏**：登录后立即取一次；此后每 60s 轮询 + 路由切换（`router.afterEach`）+ `visibilitychange` 回到前台时刷新。页面打开期间不重复轮询（由壳层统一负责）。
- **刷新触发**：收件箱页标记已读/全部已读成功后调用 `refreshUnread()`；会话过期/登出清零。
- 首页顶部沿用 `/api/attention` 自带的 `unread_count` 展示“未读提醒”，与壳层徽标互不影响。
- 收件箱页不持有定时器：挂载与回到前台时各自调用一次 `/api/inbox/changes` 拉增量；60s 未读轮询只存在于壳层单例，避免双轮询。

### 5.4 导航 IA

- 14 条路由保持不变，不新增路由。新增查询参数契约：
  - `/actions?highlight=<id>`、`/decisions?highlight=<id>`：`utils/links.ts::subjectHref` 已会生成该参数，目标视图需读取并实现滚动到对应行 + 行背景短暂高亮 2s。
  - `/meetings?series_id=<id>`：既有参数保留；全局 `/api/meetings` 没有 `series_id` 筛选参数，按“已加载页内客户端过滤”处理并注明范围（见 7.6）。
  - `/meetings/:id?comment=<comment_id>`：打开评论抽屉并滚动到该评论（收件箱 `source_comment` 深链用）。
- 面包屑/返回：项目详情页头保留项目名链接回 `/projects`；会议工作区保留项目名链接回项目详情。

## 6. 跨页通用模式

### 6.1 抽屉表单模式（创建/编辑）

- 统一用 `n-drawer placement="right" :width="560"`（窄屏 `100vw`）+ `n-form`（`label-placement="top"`）+ `n-form-item`（`rule` 声明必填/长度校验）。
- 抽屉页脚：左“取消”（`n-button quaternary`），右主操作（`n-button type="primary" :loading="saving"`）；提交中禁用关闭以免丢失上下文（`:mask-closable="!saving"`）。
- 提交失败：`useMessage().error(apiErrorMessage(...))`；成功后 `emit('created'/'saved')` 由宿主关闭抽屉并刷新（见 6.5）。
- 现有 `ContextDrawer.vue` 不再扩展，改为直接使用 `n-drawer`；`ProjectCreatePanel.vue` 按四类实体拆成独立抽屉表单（会议/系列/决策/行动项），共享 `NForm` 结构。
- 时间字段统一 `n-date-picker type="datetime"`（本地时区语义与现有 `datetime-local` 一致，提交时转 ISO 带时区）；日期字段 `type="date"`。

### 6.2 版本冲突统一

- 共享组件 `VersionConflictDialog.vue` 重构为基于 `n-modal`（保留 `localMarkdown`/`serverMarkdown`/`actualVersion` props 与 `close/reload/overwrite` 事件，双栏对比 + “复制本地草稿 / 载入服务器版本 / 用本地草稿覆盖”）。
- 新 composable `frontend/src/composables/useVersionedSave.ts`：捕获 `ApiError`（`status===409 && code==='version_conflict'`），返回 `{ conflict, retryWith(actualVersion), reset }`。
- 接入对象：项目 `PUT /api/projects/{id}`、会议 `PUT /api/meetings/{id}`、议题 `PUT /api/agenda-items/{id}`（已有）、项目进展 `PUT /api/project-updates/{id}`、决策 `PUT /api/decisions/{id}`、行动项 `PUT /api/actions/{id}`、开放问题 `PUT /api/open-questions/{id}`、系列 `PUT /api/meeting-series/{id}`、评论 `PUT /api/comments/{id}` 与 `resolve/reopen`。
- 对纯文本行编辑（行动项/问题/决策）冲突对话框正文为字段对比（服务器最新值 vs 本地草稿值）；Markdown 长文（进展/决策内容）沿用双栏 pre。

### 6.3 服务端分页模式

- `n-data-table` 传 `:data`、`:pagination`（`{ page, pageSize, itemCount }`）、`:remote="true"`、`@update:page` 触发重新请求；请求带 `limit/offset`（或 `before` 游标）。
- 游标列表（收件箱、活动台账、评论回复）用“加载更多”`n-button`（`loading` 态），参数 `before/after` 语义照抄后端。
- 列表页 `Page<T>` 响应（`{items,total,limit,offset}`）类型已存在于 `api/contracts.ts`，直接使用。
- 前端不再对全局列表做跨页客户端过滤：凡后端支持的筛选参数全部上移（见第 8 节）；后端不支持的筛选（行动项优先级、决策日期区间、会议关键词与系列）从 UI 移除或降级为“当前页内”搜索并注明范围。
- 项目域子列表（`/api/projects/{id}/decisions|actions|open-questions` 与 `/updates`）返回纯数组，只有 `limit/offset`、没有 `total`：“加载更多”以“返回条数 === limit”判断是否还有下一批。
- 插件事件（`/api/admin/plugins/events`）只支持 `status` + `limit`（上限 200），无 offset/total：页面固定一档 `limit` 并只提供状态筛选，不做页码。

### 6.4 权限驱动渲染

- 统一原则：写入入口只由服务端 `capabilities` 控制（项目/会议详情均返回 `can_manage/can_contribute/can_comment`）；附件删除用逐项 `can_delete`；评论操作用逐项 `can_edit/can_resolve/can_delete`。
- 新增工具 `frontend/src/utils/capabilities.ts`：`can(project | meeting, 'contribute')` 等；禁止在视图内用 `session.user.role` 推导这些能力。`role === 'admin'` 仅允许用于：管理员路由守卫、管理员导航、管理员页内部文案。
- 只读场景（`stakeholder`、仅会议参与人）：表单/编辑器禁用，按钮不渲染（而非禁用），评论区仍可用（`can_comment`）。
- 逐项只读：议题备注自动派生的产出（响应中 `is_derived === true`，即 `source_agenda_item_id` 非空）不可编辑，后端返回 409 `derived_outcome_read_only`；行动项/决策/开放问题列表与抽屉一律不渲染编辑与状态流转入口。

### 6.5 反馈与刷新策略

- **默认 refetch-on-success**：创建/编辑/状态变更成功后，宿主重新拉取受影响列表或直接采用 API 响应对象（会议/议题沿用现有 `accept` 模式）。
- **乐观更新仅限本地 UI 态**：菜单开合、选中行、插件开关的瞬时 UI 反馈（失败即回滚）；所有服务端状态变化一律以响应为准。
- 全局一致性：`n-message` 只用于瞬时反馈；页面错误保持行内 `n-alert`；避免同一失败同时弹 message 又刷 alert。

### 6.6 深链与返回

- `highlight` 参数：目标视图加载完成后定位行（表格 `row-key` 查找、滚动、闪烁高亮 2s，`prefers-reduced-motion` 下只滚动不高亮）。
- `comment` 参数：会议工作区自动打开评论抽屉、滚动到评论、若该评论在未加载的分页内则打开抽屉但不定位（提示“该评论在更早的讨论中”）。
- 返回行为保持浏览器默认历史；不做自定义返回栈。

## 7. 逐页设计

### 7.1 登录 / 注册（`LoginView.vue` / `RegisterView.vue`）

- **现状问题**：自绘表单无校验反馈；错误用行内 notice。
- **目标**：`n-form`（rules：必填/长度）+ `n-input`（密码 `type="password" show-password-on="click"`）+ 提交 `n-button type="primary" block :loading`；错误用 `n-alert type="error"`。保留左品牌区与右卡片布局（`auth-layout`），品牌文案不变。
- **端点**：`POST /api/auth/login`（错误码 `invalid_credentials`、`account_pending/rejected/disabled` 原文展示）、`POST /api/auth/register`（`registration_closed`、`username_taken`）。
- **受影响测试**：`auth.test.ts`、`registration-error.test.ts`（断言按新控件更新，如 `getByLabelText`→表单 label 保持）。

### 7.2 账号设置（`AccountView.vue`）

- **现状问题**：无校验、成功后直接登出跳转无提示。
- **目标**：`n-card` + `n-form`（新密码至少 12 位、两次一致性可选项不加，后端无确认字段）+ 成功后 `n-message.success('密码已修改，请重新登录')` 再跳登录。
- **端点**：`POST /api/auth/change-password`（`wrong_password` 原文）。
- **受影响测试**：`account-admin.test.ts`（账号设置部分）。

### 7.3 首页（`HomeView.vue`）

- **现状问题**：attention 未读数/提及/通知未渲染到头部；工作简报无 `generated_at`；卡片样式手写。
- **目标布局**：保留三块（需要关注 / 近期会议 / AI 工作简报）+ `home.secondary-card` 插件槽。头部显示 `/api/attention` 的 `unread_count`（“N 条未读提醒”徽标）。工作简报头显示 `generated_at`（有值时 “上次生成于 {time}”）。
- **Naive 组件**：`n-card`、`n-empty`、`n-skeleton`、`n-badge`、`n-button`；`AttentionCard` 改用 `n-thing` 结构 + `AppAvatar` 或 `attention-kind` 徽标 + `ChevronRight`。
- **端点与字段**：`GET /api/attention`（`items/unread_count/truncated`）、`GET /api/work-brief`（`content_markdown/generated_at`）、`GET /api/plugins/actions`（工作简报能力探测）、`POST /api/plugins/stream`（SSE 生成，保留现有流式逻辑）。
- **能力门控**：无（attention 已按用户域过滤）。
- **受影响测试**：`home-attention.test.ts`（新增未读数/生成时间断言）。

### 7.4 项目列表（`ProjectsView.vue`）

- **现状问题**：卡片 OK，创建用内联表单；状态/健康度筛选客户端。
- **目标**：保持 `project-card` 网格；创建改为右侧 `n-drawer` 表单（名称/标识自动 slug/说明）；筛选保留客户端（`/api/projects` 无筛选参数，列表小，属“富内容面”例外，注明为客户端筛选）。
- **端点**：`GET /api/projects`、`POST /api/projects`（`member_ids` 含创建者）。
- **受影响测试**：`project-create-panel.test.ts`、`project-workspace.test.ts`（部分）。

### 7.5 项目详情（`ProjectDetailView.vue` + 各 Tab）

**容器**：页头收敛（`PageHeader` 中等字号 + `project-context` 元信息行：状态/健康度/负责人/成员数/目标日期）；“新建”改为 `n-dropdown`（菜单项：会议、系列会议、决策、行动项、进展、文件）；“编辑项目”改为 `n-drawer` 表单（名称/摘要/状态/健康度/目标日期/负责人/成员 + `expected_version`，409 走 6.2 统一冲突对话框）；新增“删除项目”按钮（`n-popconfirm` → `n-dialog` 二次确认输入项目名，`DELETE /api/projects/{id}`）。删除受后端约束：仅当项目下没有会议且没有项目附件时可删除，否则返回 409 `project_not_empty` / `project_has_attachments`（无权限返回 403 `project_delete_forbidden`）；对话框文案与错误提示必须说明该限制，不得承诺级联删除；成功后回 `/projects`。Tab 用 `n-tabs`（`type="line"`，值映射到路由 query `?tab=` 以便深链）。

**成员与负责人（编辑抽屉内，`can_manage`）**：成员多选下拉提交 `member_ids`（后端全量替换成员），负责人下拉提交 `lead_user_id`；成员 `memberships[].role` 只读展示。抽屉内注明“移除成员会立即撤销其项目访问，但不会删除其历史记录”。后端没有把成员设为 `stakeholder` 的写入口（见第 8 节 #25），因此角色指派不提供入口。

**Tab 清单**：概览 / 会议 / 行动项 / 决策 / 开放问题（新增）/ 文件 / 动态。

- **概览（`ProjectOverview.vue`）**：卡片改 `n-card`；内容与现有六块一致；“需要处理”数据源改 `/api/attention` 结果按 project 过滤（现状已如此）；“最近动态”条目改为活动台账最后 5 条（见动态 Tab 数据源），不再用 `project.updates`。
- **会议 Tab（`ProjectRecordTabs` 会议部分）**：会议行改 `n-list` + 状态徽章；系列区新增“编辑/归档”操作（`n-popconfirm` 归档），编辑开 `n-drawer`（见下“系列管理”）；保留“临时添加会议”抽屉（改 `n-drawer`）。
  - **系列管理（新组件 `SeriesEditDrawer.vue`）**：读 `GET /api/meeting-series/{id}`（返回 `title/purpose_markdown/recurrence*/default_duration_minutes/default_host/default_recorder/status/version/participants/standing_items/created_by/updated_by`）。编辑：`PUT /api/meeting-series/{id}`（`expected_version` + 上述可空字段；写入字段名为 `default_host_user_id`/`default_recorder_user_id`；`recurrence_frequency=null` 表示不再固定周期，关闭周期时同时把同组其余字段（`recurrence_weekday/month_day/month/local_time/timezone/anchor_date`）传 `null`，避免留下与 `frequency=null` 不一致的残值）。归档：`status: 'archived'`。常设议题（`standing_items`）以可增删行列表编辑（标题/类型/默认负责人/默认时长，注意 `StandingAgendaWrite` 字段名为 `default_owner_user_id`）。参与者与默认主持/记录从项目成员列表选择。创建系列时同样使用该抽屉（`POST /api/projects/{id}/meeting-series` 载荷含 `participants`、`standing_items`）。
- **行动项 Tab**：`n-list` 行（内容/负责人/截止/优先级/状态）+ 行内操作（状态流转快捷操作 + “编辑”开 `n-drawer`）。编辑抽屉（新 `ActionEditDrawer.vue`）：`PUT /api/actions/{id}`（`content/owner_user_id/due_date/priority/status/expected_version`）。状态流转：待开始→进行中→已完成、已取消（`n-popconfirm` 取消）；`completed_at` 由后端回填并显示在已完成行。负责人下拉数据源为项目 `memberships`（见第 8 节用户名字典）。
- **决策 Tab**：`n-list`（标题/状态/评审人徽章）→ 点击行开决策详情抽屉（新 `DecisionDetailDrawer.vue`）：
  - 展示：`decision_markdown`、`rationale_markdown`、`created_by`、`decided_by`、`reviewers[]`（`user_id/status/responded_at/comment`；来自会议详情的嵌入决策还带 `user`）、`supersedes_decision_id`（替换链：若本决策被替代，在列表/抽屉显示“已被替代”链）。
  - 操作（严格按状态、身份与 `can_contribute` 渲染）：
    - 编辑（`PUT /api/decisions/{id}`，`expected_version`）：仅 `proposed` 且非派生（`is_derived === false`）时显示；可同时替换 `reviewer_ids`。
    - 评审（本人是 `reviewers[]` 中的当前评审人时）：`POST /api/decisions/{id}/review`（`status: approved|changes_requested` + `comment` + `expected_version`），抽屉内评审表单；后端要求 `can_contribute`，非评审人提交返回 403。
    - 定稿 `POST /api/decisions/{id}/finalize`（`expected_version`，`n-popconfirm`）：仅 `proposed`；定稿人写入 `decided_by`。
    - 撤回 `POST /api/decisions/{id}/withdraw`：仅 `proposed`。
    - 替代 `POST /api/decisions/{id}/supersede`（选择新决策 + 双方版本，`n-drawer` 二级表单，`new_decision_id` 从同项目 `final` 决策列表选择；后端要求双方均为 `final`、同项目且新决策尚未建立替代关系）。
  - 创建决策抽屉支持 `reviewer_ids`（多选项目成员）。
  - 评审人姓名：项目 Tab 与全局表都只有 `reviewers[].user_id`，姓名取自项目 `memberships` 聚合字典（见第 8 节 #14）。
- **开放问题 Tab（新 `ProjectQuestionsTab.vue`）**：`GET /api/projects/{id}/open-questions`（`limit=200`）列表（状态/负责人/来源会议）；行操作：编辑（`PUT /api/open-questions/{id}`，`question_markdown/owner_user_id/expected_version`，仅非派生）、排期（`POST /api/open-questions/{id}/schedule`，仅 `open` 且未排期时提供；目标会议须同项目且在未来 + `expected_meeting_version` + `expected_version`，`n-drawer`）、解决（`POST /api/open-questions/{id}/resolve`，可选关联同项目 `final` 决策 + `expected_version`，`n-drawer`）。创建沿用 `n-drawer`（`POST /api/projects/{id}/open-questions`）。只读展示 `scheduled_meeting_id`（已排入会议）、`resolved_by_decision_id`（由决策解决）、`converted_from_agenda_item_id`/`source_agenda_item_id`（来源议程）。**不提供“放弃（dropped）”操作**：`QuestionEdit` 不含 `status`，现有端点无法写入 `dropped`；仅在数据显示该状态时渲染标签（处理方式同 `ready`，见第 8 节 #36 与第 15 节）。
- **文件 Tab**：`AttachmentPanel`（改版后 `n-upload` 样式壳 + 卡片网格 + `n-popconfirm` 删除），沿用 `target_type=project`。
- **动态 Tab（`ProjectActivityTab.vue` 重构）**：
  - 真实台账：`GET /api/projects/{id}/activity?limit=50&before=<cursor>`（`items[]: {id, actor, event_type, subject, payload, created_at, meeting_id}` + `next_cursor`），`n-timeline` 渲染；事件文案函数 `activityLabel(event_type, payload)`（新 `utils/activity.ts`，覆盖 `project.created/updated`、`project_update.*`、`meeting.*`、`agenda_item.*`、`attachment.*`、`decision.*`、`action.*`、`open_question.*`、`comment.*` 等事件类型，未知类型回退英文原值）。
  - 进展发布：`ProjectUpdateComposer` 保留在 Tab 顶部（`can_contribute`）。
  - 进展编辑：台账中 `subject.type === 'project_update'` 的条目提供“编辑”入口 → `PUT /api/project-updates/{id}`（`expected_version` + `health/content_markdown` + **原样回传既有 `source`**，作者或管理员，409 冲突对话框）。回传 `source` 是必要细节：`ProjectUpdateEdit` 的 `source` 默认 `human`，若省略会把 `ai_draft_applied` 的来源标记改写为 `human`。进度历史单独用 `GET /api/projects/{id}/updates?limit=50&offset=`（返回纯数组，无 `total`）的“加载更多”作为“进展记录”子区块（避免台账翻页深时看不到完整进展史）。
- **能力门控**：`can_manage`（编辑项目、删除项目、成员多选与负责人下拉）；`can_contribute`（新建菜单、各 Tab 创建/编辑、系列管理与归档、评审与定稿按身份）；`stakeholder` 只读（“干系人可查看不可编辑”在成员列表旁加说明文案，并注明角色没有可写入口，见第 8 节 #25）。
- **端点汇总**：`GET/PUT/DELETE /api/projects/{id}`、`GET/POST /api/projects/{id}/{meetings,meeting-series,actions,decisions,open-questions,updates}`、`GET /api/meeting-series/{id}`、`PUT /api/meeting-series/{id}`、`POST /api/meeting-series/{id}/occurrences`、`GET /api/projects/{id}/activity`、`PUT /api/project-updates/{id}`、`PUT /api/{decisions,actions,open-questions}/{id}` 及子动作、附件端点。
- **受影响测试**：`project-workspace.test.ts`、`project-create-panel.test.ts`、`workflow-components.test.ts`；新增 `project-questions.test.ts`、`series-manage.test.ts`、`project-activity.test.ts`、`decision-workflow.test.ts`。

### 7.6 会议列表（`MeetingsView.vue`）

- **现状问题**：一次性拉 50 条客户端分组；创建为内联表单；搜索/筛选客户端。
- **目标**：保留按状态分组的行布局（富内容面），数据改服务端分页：`GET /api/meetings?limit=50&offset=&status=&project_id=&participant_user_id=&start_after=&start_before=`；“加载更多”按钮翻页，组由已加载数据派生（分组只覆盖已加载页，文案注明）。高级筛选映射服务器参数：项目→`project_id`、状态→`status`、参与者→`participant_user_id`（下拉自项目成员）、时间窗→`start_after/start_before`；关键词搜索与既有 `series_id` 参数保留为“当前已加载页内”客户端过滤并注明范围（全局列表无 `series_id` 参数，后端不支持跨页系列筛选；从项目系列进入时若目标会议未出现在已加载页，提示继续加载）。创建会议改右侧 `n-drawer`（`POST /api/projects/{id}/meetings`，含参与人角色选择器，见 7.7 参与人模型）。
- **端点与字段**：`GET /api/meetings`（分页参数 + `items/total/limit/offset`）、`GET /api/projects`。
- **受影响测试**：`meetings-view.test.ts`（筛选与分组断言调整）、`global-workspace.test.ts`（会议创建流程保持；全局视图分页断言补充 `limit/offset`）。

### 7.7 会议工作区（`MeetingWorkspaceView.vue` + 子组件 + 抽屉）

**页头操作（按 `capabilities.can_contribute`）**：

| 状态 | 操作 |
| --- | --- |
| `draft` / `ready` | 准备信息（抽屉）、开始会议（主按钮）、取消会议（`n-popconfirm`，`POST /api/meetings/{id}/cancel`，`expected_version`） |
| `in_progress` | 结束会议（主按钮；后端会跳过未结束议题并生成完成快照）、取消会议（`n-popconfirm`，确认文案只说明“会议将标记为已取消且不可重开”，不承诺跳过议题或快照） |
| `completed` | 重新打开（`n-popconfirm`，`POST /api/meetings/{id}/reopen`；后端仅允许 `completed → in_progress`）、导出 Markdown/JSON（保留插件导出按钮） |
| `canceled` | 无状态操作（后端不允许重开已取消会议）：仅查看与导出 |

**`ready` 状态处理（明确决策）**：后端状态机不再产生 `ready`（`LifecyclePolicy` 仅为旧数据保留该状态；`start` 同时接受 `draft` 与 `ready`）。前端：`StatusPill` 仍渲染 `ready` 为“待开始”（兼容旧数据）；所有操作判定将 `ready` 与 `draft` 同等对待；列表中归入“即将开始”组。不新增任何到 `ready` 的转换 UI。

**元信息行**：状态/进行时长（保留 live 计时）/主持/记录/系列槽位。新增 `series_slot_at` 展示（有值时显示“系列槽位 {本地时间}”，只读）；`started_at`/`completed_at`（已完成会议显示实际起止）。

**会议准备抽屉**（由 `ContextDrawer` 改为 `n-drawer`）：标题/开始/结束（`n-date-picker datetime`，时间窗成对提交）/会议目的（Milkdown 编辑器，保留 `PluginEditorSlot` 包裹）/主持与记录（`host_user_id`、`recorder_user_id`，下拉自项目成员，可清空）。**参与人可编辑**：列表行 = 成员下拉 + 角色下拉（host 主持、recorder 记录、presenter 主讲、attendee 参与），保存时提交完整 `participants` 数组（后端 `MeetingEdit.participants` 全量替换并去重）；`can_contribute` 时可用，`completed`/`canceled` 会议锁定（后端 409 `meeting_locked`）。注意 `meeting.host/recorder` 与参与人行上的 `participation_role` 是两组独立字段，展示不得混用。创建会议抽屉复用同一参与人编辑器（`MeetingWrite.participants`）。

**会议纪要 / 原始笔记**：编辑器与保存逻辑不变（`useMeetingWorkspace`、`SaveStateIndicator` 保留；显式保存按钮保留以兼容既有流程），仅容器改 `n-card`、按钮改 `n-button`、冲突提示沿用。

**议题工作台（`AgendaWorkbench.vue` / `AgendaDetail.vue` / `AgendaQueue.vue`）**：

- 队列行：`n-dropdown` 替代 `•••` 菜单，菜单项扩展为：编辑详情（进入详情）、**跳过**（`POST /api/agenda-items/{id}/skip`，`expected_version`，`n-popconfirm`）、**完成并进入下一项**（详情主按钮）、取消议题、**移动议题**（`POST /api/agenda-items/{id}/move`，`n-drawer` 选目标会议，载荷严格按 `AgendaMove`：`target_meeting_id`、`position?`、`expected_version`、`expected_source_meeting_version`、`expected_target_meeting_version`）、删除（保留带产出的守卫提示 → 迁移或改取消）。不新增独立“开始此议题”按钮：会议 `in_progress` 时首项由后端 `start` 自动开始，`complete-and-advance` 自动开始下一项，沿用现有选择语义。
- 详情新增：
  - 元信息：`proposer`（提案人）、`presenter`（主讲人）展示 + 编辑（`AgendaWrite/AgendaEdit` 的 `proposer_user_id/presenter_user_id`，下拉数据源为会议参与人 + 项目成员）；`estimated_minutes`；完成后显示 `started_at/completed_at/actual_duration_seconds`（“实际用时 X 分 Y 秒”，会议进行中显示“已进行 hh:mm:ss”）。
  - 来源标记：`carry_from_open_question_id` 显示“来自开放问题”徽标（只读；会议详情的议题投影已返回该字段）。`copied_from_agenda_item_id` 不在会议详情的议题投影中（仅单议题响应与会议快照含该字段，且没有单议题 GET 端点），因此“复制自其他议题”徽标延期；若用户授权对会议详情投影做极小补充，见第 15 节未决问题 3。
  - **议题附件**：详情底部新增附件区块（`AttachmentPanel target-type="agenda_item"`，读 `AgendaItem.attachments`，上传/删除按 `can_delete`）。
  - 议题菜单扩展：**迁移产出**（`POST /api/agenda-items/{id}/migrate-outcomes`，`n-drawer` 选目标议题，携带四方版本；守卫删除提示的落地动作）、**转为开放问题**（`POST /api/agenda-items/{id}/convert-to-question`，`n-popconfirm`，携带 `expected_source_version/expected_source_meeting_version`）、**复制到其他会议**（`POST /api/agenda-items/{id}/copy-to-meeting`，`n-drawer` 选目标会议，`target_meeting_id` + 三方版本）。
  - AI 议题记录入口（`PluginEditorSlot slot="agenda-notes-editor"`）保留。
- 实时时长：详情进行中用会议 `started_at` 计算（保留现有 `meeting-live-clock`）；议题自身 `started_at` 由后端在 start/complete 时写入，用于展示单项用时。

**材料抽屉**：`n-drawer` + 改版 `AttachmentPanel`（`n-upload` 样式壳、文件类型图标 `FileText/Image`、删除 `n-popconfirm`）。

**评论抽屉**：`MeetingCommentsPanel` 重构：
- 列表：`GET /api/comments?target_type=meeting&target_id=&before=&limit=20&reply_limit=`（翻页“加载更多”）；评论显示 `created_at`、`edited_at`（“已编辑”）、删除态（`body_markdown===null` 显示“评论已删除”）；提及（`mentions`）显示在正文下方徽标。
- 操作：编辑（`can_edit`）、删除（新增 `can_delete` → `n-popconfirm` → `DELETE /api/comments/{id}` 带 `expected_version`）、解决/重开（`can_resolve`）；回复分页：`GET /api/comments/{id}/replies?after=&limit=`，超过 `reply_limit` 的回复显示“查看全部回复（N）”。
- 输入：`MentionTextarea` 改 `n-input type="textarea"` + 自定义提及弹层（保留现有键盘交互与 `mention_user_ids` 提交）。
- 深链：`?comment=<id>` 打开抽屉并定位。

**完成链（`CompletedMeetingChain.vue`）**：视觉改 `n-card`/`n-collapse`；补充 `series_slot_at`、实际起止时间；快照读取语义不变（按 development.md：读取快照而非当前记录）。

**端点汇总（新增消费）**：`POST /api/meetings/{id}/cancel|reopen`、`POST /api/agenda-items/{id}/skip|move`、`/migrate-outcomes`、`/convert-to-question`、`/copy-to-meeting`、`GET/POST/DELETE /api/attachments/agenda_item/{id}[...]`、`DELETE /api/comments/{id}`、`GET /api/comments/{id}/replies`。

**受影响测试**：`meeting-workspace.test.ts`、`meeting-lifecycle.test.ts`、`agenda-workbench.test.ts`（161 行“不暴露版本号/独立跳过动作”断言有意更新为新行为：版本冲突语义保留、跳过动作存在）、`meeting-comments.test.ts`、`comments-mentions.test.ts`、`workflow-components.test.ts`、`outcome-composer.test.ts`、`use-meeting-workspace.test.ts`。

### 7.8 行动项全局视图（`ActionsView.vue`）

- **现状问题**：action 全局视图已有 owner/status/project/due 服务端筛选，但优先级、关键词等本地过滤不足以覆盖全量，且忽略 `limit/offset/total`（只拉默认一页）；owner 显示原始 UUID；无编辑/状态流转；`due_after`/`completed_at` 未用。
- **目标**：`n-data-table`（`remote` 分页 + 服务端筛选）。列：内容（主列，超长省略 + tooltip）、负责人、优先级（tag）、状态（可操作）、截止日期（逾期红色标注）、来源会议（链接）。筛选区：负责人（我/全部，映射 `owner_user_id`）、状态（`status`）、项目（`project_id`）、期限（逾期→`due_before=今天`；今天及以后→`due_after=今天`）。移除优先级筛选（后端无该参数，且服务端分页下只筛当前页会误导）。
- 行操作：状态流转下拉（`n-popconfirm` 确认取消）与“编辑”抽屉（`PUT /api/actions/{id}`：`content/owner_user_id/due_date/priority/status/expected_version`）；已完成行显示 `completed_at`。派生行动项（`is_derived === true`）不提供编辑与状态流转入口。
- **用户名字典（明确决策）**：无用户目录端点，全局列表用“姓名聚合”策略：加载 `/api/projects` 时从各项目 `memberships[].user`（含 `display_name`）聚合 `userId → name` 映射；缺名回退 `用户·{id 前 8 位}`（比裸 UUID 可读）。同一策略用于决策评审人/行动负责人展示。已知局限：被移出项目的用户可能缺名，接受回退文案（第 15 节未决问题 2 供确认）。
- **端点与字段**：`GET /api/actions`（`limit/offset/total` + `status/owner_user_id/project_id/due_before/due_after`）、`PUT /api/actions/{id}`、`GET /api/projects`。
- **受影响测试**：`global-workspace.test.ts`（行动项部分；改为断言服务端参数与表格渲染）。

### 7.9 决策全局视图（`DecisionsView.vue`）

- **现状问题**：只读；评审、定稿、撤回、替代、编辑、`decided_by`、`reviewers[]` 均未渲染；日期区间为客户端过滤。
- **目标**：`n-data-table`（`remote` 分页 + 服务端筛选）。列：标题、项目、状态、评审人（徽章组：pending/approved/changes_requested）、更新时间、来源会议。筛选：项目、状态、评审人（下拉自用户名字典，映射 `reviewer_user_id`；移除日期区间——后端无参数；词典未覆盖的外部评审人不可选，属已知局限）。行点击 → 决策详情抽屉（同 7.5 决策 Tab 的 `DecisionDetailDrawer`，评审/定稿/撤回/替代/编辑全流程在此完成，状态与身份门控与 7.5 一致；派生决策不提供写操作；替代仅对同项目 `final` 决策开放）。
- **端点与字段**：`GET /api/decisions`（`project_id/status/reviewer_user_id/limit/offset`，items 含 `reviewers[]`）、`PUT /api/decisions/{id}`、`/review`、`/finalize`、`/withdraw`、`/supersede`。
- **受影响测试**：`global-workspace.test.ts`（决策部分）、`workflow-components.test.ts`；新增 `decision-workflow.test.ts`。

### 7.10 收件箱（`InboxView.vue`）

- **现状问题**：壳层没有未读入口；`/inbox/changes` 未用；`source_comment` 深链未用。
- **目标**：行改 `n-list`（未读加背景/圆点 + 粗体），保留 `before` 游标“加载更多”；条目链接：优先 `source_comment`（`/meetings/:id?comment=<id>`），否则 `subject` 深链（沿用 `subjectHref`，`agenda_item` 时带 `meeting.id`）；标记已读/全部已读逻辑保留并在成功后调 `refreshUnread()`（壳层徽标联动）。增量：页面挂载与 `visibilitychange` 回到前台时调用 `GET /api/inbox/changes?cursor=<last_id>&limit=50`（`cursor` 即最后一条通知 id，按 id 升序返回；`next_cursor` 推进，`has_more` 时提示“点击刷新查看全部”），新通知按 id 前插；页面自身不做定时轮询（60s 未读轮询只在壳层单例）。
- **端点与字段**：`GET /api/inbox`（`items/next_cursor/unread_count`）、`GET /api/inbox/changes`（`notifications/next_cursor/has_more/unread_count`）、`POST /api/inbox/{id}/read`、`POST /api/inbox/read-all`。
- **受影响测试**：`inbox.test.ts`（新增深链与增量刷新断言）。

### 7.11 AI 任务（`AiTasksView.vue`）

- **现状问题**：不显示 `dismiss`/`apply` 入口；`error_code/rerun_of_id/applied_by/dismissed_by` 未展示；历史过滤无 UI。
- **目标**：任务卡改 `n-card`；状态徽章沿用 `statusTone`。新增：
  - 失败任务显示 `error_code`（若有）与技术详情折叠（保留）。
  - `rerun_of_id` 显示“重跑自任务 #x”；`applied_by/dismissed_by` 显示执行人；`applied_at/dismissed_at` 显示时间。
  - **丢弃结果**：终态且未应用、未丢弃的任务（`succeeded/failed/interrupted/canceled`）提供“丢弃”按钮（`n-popconfirm` → `POST /api/plugin-jobs/{id}/dismiss`；后端对不可丢弃任务返回 409 `plugin_job_not_dismissible`）。**应用**：需要写入编辑器上下文的 action（如会议纪要/议题记录/进展），由发起处的 `PluginEditorSlot` 承担应用，`AiTasksView` 不提供全局应用按钮（避免无上下文写入）；该决策在卡片文案注明“在发起页面应用此结果”。
  - 历史过滤开关：`n-radio-group`（进行中/全部，映射 `include_history`）。
- **端点与字段**：`GET /api/plugin-jobs?include_history=`、`POST /api/plugin-jobs/{id}/{cancel,rerun,dismiss}`；`/apply` 由编辑器槽调用。
- **受影响测试**：`ai-tasks.test.ts`、`ai-work-assistant-plugin.test.ts`。

### 7.12 用户管理（`AdminUsersView.vue`）

- **现状问题**：手写行列表；重置密码用 `window.prompt`。
- **目标**：`n-data-table`（成员/申请/归档三区或单表 + 状态筛选；服务端无分页，全量加载，仍用表格呈现）。重置密码改为 `n-drawer`（新密码输入，min 12）。批准/拒绝/归档/恢复用 `n-popconfirm`（归档走 `n-dialog` 确认）。头像用 `AppAvatar`（`avatar_color`）。
- **端点**：`GET /api/admin/users`、`POST /api/admin/users`、`POST /api/admin/users/{id}/{approve,reject,disable,restore,reset-password}`。
- **受影响测试**：`account-admin.test.ts`。

### 7.13 插件管理（`AdminPluginsView.vue`）

- **现状问题**：`⌁` 字形图标；`context_scopes`/`external_network` 能力不展示；事件失败用内联段落；开关为手写 switch。
- **目标**：卡片改 `n-card` + `n-grid`；插件图标 `Puzzle`；能力徽标区新增 `context_scopes`（上下文范围）与 `external_network`（外部网络）徽标（“可访问外部网络”警示色）；配置表单改 `n-form`（`n-input/n-input-number/n-switch`，secret 用 `n-input type="password"`）；启用开关 `n-switch` + 保留“重启后生效”提示；事件失败改 `n-data-table`（列：事件类型/尝试次数/最后错误/重试按钮）。事件表不做分页：后端只支持 `status` + `limit`（上限 200），固定 `limit=50` 并在表尾注明“最多显示 50 条，可用状态筛选”。
- **端点**：`GET /api/admin/plugins`、`PUT /api/admin/plugins/{id}/{config,enabled}`、`GET /api/admin/plugins/events?status=failed`、`POST /api/admin/plugins/events/{id}/retry`。
- **受影响测试**：`admin-plugins.test.ts`（新增能力徽标断言）。

## 8. 后端逻辑对齐清单

下表把当前缺口映射到具体 UI 落点。标记“延期”的行说明前端无既有端点支撑、按决策 3 明确不实现（除非用户后续授权后端改动）。

| # | 后端能力缺口 | UI 落点 | 使用的端点与字段 | 决策 |
| --- | --- | --- | --- | --- |
| 1 | 会议取消无 UI | 会议工作区页头 `n-popconfirm` | `POST /api/meetings/{id}/cancel`（`expected_version`） | 实现 |
| 2 | `ready` 状态永远不产生但被渲染 | 列表与详情按 `draft` 同等处理，`StatusPill` 继续渲染“待开始” | 无新端点 | 实现（保留渲染，不新增转换 UI） |
| 3 | 议题附件从未渲染 | 议题详情附件区块 | `GET/POST/DELETE /api/attachments/agenda_item/{id}` | 实现 |
| 4 | 议题 proposer/presenter 未展示 | 议题详情元信息 + 编辑 | `AgendaWrite/AgendaEdit` 的 `proposer_user_id/presenter_user_id` | 实现 |
| 5 | 议题 started_at/completed_at/actual_duration_seconds 未展示 | 议题详情“实际用时”、队列行 | 序列化已返回 | 实现（只读） |
| 6 | 议题 carry 来源未展示 | 议题详情“来自开放问题”徽标 | `carry_from_open_question_id`（会议详情的议题投影已返回） | 实现（只读） |
| 7 | move/complete/skip/migrate-outcomes/convert-to-question/copy-to-meeting 未用 | 议题 `n-dropdown` 菜单 + `n-drawer` | 对应 `POST /api/agenda-items/{id}/…` 端点 | 实现 |
| 8 | `series_slot_at` 未展示 | 会议页头元信息 | `series_slot_at` | 实现（只读） |
| 9 | 参与人角色展示不当/创建后无法编辑 | 创建抽屉与准备抽屉的角色选择 + 详情角色徽章 | `MeetingWrite.participants`、`MeetingEdit.participants`（后端全量替换）、`host_user_id/recorder_user_id` | 实现（`can_contribute` 且会议未锁定时可编辑） |
| 10 | `avatar_color` 未用 | `AppAvatar` 全局替换 | `UserRef.avatar_color`、`/api/auth/session` | 实现 |
| 11 | 系列只有创建与列表 | 系列编辑/归档抽屉、常设议题/默认主持记录/参与者编辑 | `GET/PUT /api/meeting-series/{id}`（`standing_items/default_host/default_recorder/status`） | 实现 |
| 12 | 决策评审/定稿/撤回/替代/编辑/decided_by/reviewers 未渲染 | 项目决策 Tab + 全局决策表 + 决策详情抽屉 | `PUT /api/decisions/{id}`、`/review`、`/finalize`、`/withdraw`、`/supersede`；`decided_by`、`reviewers[]`、`supersedes_decision_id` | 实现 |
| 13 | 行动项编辑/状态流转/负责人/截止/优先级未用 | 全局表格 + 项目 Tab + 编辑抽屉 | `PUT /api/actions/{id}`（`content/owner_user_id/due_date/priority/status/expected_version`） | 实现 |
| 14 | 行动项 owner 显示裸 UUID | 用户名字典（从 `/api/projects` 成员聚合） | `memberships[].user.display_name` | 实现（有回退文案） |
| 15 | `due_after` 过滤未用 | 行动项筛选“今天及以后到期” | `GET /api/actions?due_after=` | 实现 |
| 16 | `completed_at` 未用 | 行动项已完成行显示完成时间 | `completed_at` | 实现 |
| 17 | 开放问题生命周期未用 | 项目“开放问题”Tab（更新/排期/解决；来源与排期/解决状态只读展示） | `GET/POST /api/projects/{id}/open-questions`、`PUT /api/open-questions/{id}`、`/schedule`、`/resolve`；只读展示 `scheduled_meeting_id/resolved_by_decision_id/converted_from_agenda_item_id/source_agenda_item_id` | 实现（“放弃为 dropped”无写入口，见 #36） |
| 18 | 活动台账未用 | 项目动态 Tab `n-timeline` | `GET /api/projects/{id}/activity`（`before` 游标） | 实现 |
| 19 | 进展分页/编辑未用 | 动态 Tab“进展记录”子区 + 编辑抽屉 | `GET /api/projects/{id}/updates`、`PUT /api/project-updates/{id}`；编辑时原样回传 `source`，避免 `ai_draft_applied` 被改写为 `human` | 实现 |
| 20 | 收件箱未读数不在壳层 | 侧边栏徽标 + 顶栏铃铛 + 60s 轮询 | `GET /api/inbox/changes`（`unread_count`） | 实现 |
| 21 | `/inbox/changes` 增量未用 | 收件箱页面挂载/回到前台时增量刷新 | `GET /api/inbox/changes?cursor=` | 实现 |
| 22 | 通知 `source_comment` 深链未用 | 收件箱条目链接 `?comment=` | `source_comment`、`data` | 实现 |
| 23 | 评论删除/回复分页/edited_at/mentions 未显示 | 评论抽屉 | `DELETE /api/comments/{id}`、`GET /api/comments/{id}/replies`、`can_delete`、`edited_at`、`mentions` | 实现（`deleted_at` 以 `body_markdown===null` 呈现） |
| 24 | 项目删除无 UI | 项目详情 `n-dialog` 二次确认（仅空项目；409 `project_not_empty`/`project_has_attachments`、403 `project_delete_forbidden` 原样提示） | `DELETE /api/projects/{id}` | 实现 |
| 25 | 项目成员/负责人/角色管理无 UI | 编辑项目抽屉的成员多选与负责人下拉；成员角色只读展示 | `ProjectEdit.member_ids`（全量替换）、`lead_user_id` | 实现（新增/移除成员与换负责人）；成员角色 `stakeholder` 没有指派入口，延期 |
| 26 | 插件 `context_scopes`/`external_network` 不显示 | 插件管理能力徽标 | `capabilities.context_scopes`、`capabilities.external_network` | 实现 |
| 27 | 插件任务 dismiss/apply 不在核心 AiTasksView | 丢弃按钮；应用留在编辑器槽 | `POST /api/plugin-jobs/{id}/dismiss`；`/apply`（编辑器上下文） | 实现（全局应用按钮不做） |
| 28 | `error_code/rerun_of_id/applied_by/dismissed_by` 未展示 | AiTasksView 卡片元信息 | 序列化字段 | 实现 |
| 29 | applied/dismissed 任务被隐藏 | AiTasksView `include_history` 过滤开关 | `GET /api/plugin-jobs?include_history=` | 实现 |
| 30 | 全局视图客户端过滤/忽略分页 | 行动项/决策 `n-data-table` remote 分页；会议列表服务端参数 + 加载更多 | 各 `limit/offset/total` | 实现 |
| 31 | 简报 `generated_at` 未用 | 首页工作简报头 | `generated_at` | 实现 |
| 32 | 首页未展示未读数/提及/通知 | 首页头部未读徽标 + 关注卡 reasons | `/api/attention` 的 `unread_count` | 实现 |
| 33 | 项目编辑冲突缺统一 UX | `useVersionedSave` + 统一冲突对话框 | `409 version_conflict`（`expected_version/actual_version`） | 实现 |
| 34 | 派生产出不可编辑未在 UI 体现 | 行动项/决策/开放问题列表与抽屉对 `is_derived=true` 隐藏编辑与状态流转 | 后端 409 `derived_outcome_read_only`；响应含 `source_agenda_item_id`/`is_derived` | 实现（只读） |
| 35 | 议题 copy 来源未展示 | 议题详情“复制自其他议题”徽标 | 会议详情的议题投影缺 `copied_from_agenda_item_id`（仅单议题响应与快照含该字段） | 延期：需极小后端投影补充，见第 15 节未决问题 3 |
| 36 | 开放问题“放弃（dropped）”无写入口 | 不提供放弃操作；仅在数据显示 `dropped` 时渲染标签 | `QuestionEdit` 不含 `status`，`PUT` 无法置为 `dropped`；`dropped` 仅兼容既有数据 | 延期：无端点，见第 15 节未决问题 4 |
| 37 | 插件事件列表无分页 | 插件管理事件表固定 `limit=50` + 状态筛选 | `GET /api/admin/plugins/events?status=&limit=`（无 offset/total） | 实现（不做页码，注明数据上限） |

标记延期的项：#25 的成员角色指派（无 `stakeholder` 写入口，成员增删与换负责人已实现）、#35（会议详情议题投影缺 copy 来源字段）、#36（开放问题没有放弃写入口）。#35 与 #36 若要消除，需要用户授权的极小后端改动（见第 15 节未决问题 3、4）；未获授权时保持前端-only 基线，UI 不提供对应入口。

## 9. 分期实施

每阶段独立可交付、可合并，且 `npm --prefix frontend test` 与 `npm --prefix frontend run build` 保持全绿。阶段内测试未绿不进入下一阶段。

### P0 基础设施（依赖、主题、测试底座）

- **内容**：`package.json` 增加 `naive-ui`（`^2.x`）；新建 `frontend/src/theme/naive.ts`（`naiveThemeOverrides` + `statusTone` + 状态色表）；`main.ts`/`App.vue` 接入 `NConfigProvider`（zhCN/dateZhCN）+ `NMessageProvider` + `NDialogProvider`；`tests/setup.ts` 增加 jsdom 补丁：`ResizeObserver` stub、`window.matchMedia` stub、`HTMLElement.prototype.scrollTo` noop（Naive 依赖）；`StatusPill.vue` 重构为 `NTag` 封装（保留 props 与 `data-status`）；新建 `AppAvatar.vue`、`utils/capabilities.ts`、`utils/activity.ts`（事件文案，先覆盖已知事件类型）。
- **改动文件**：`frontend/package.json`、`package-lock.json`、`src/main.ts`、`src/App.vue`、`src/theme/naive.ts`（新）、`src/components/StatusPill.vue`、`src/components/AppAvatar.vue`（新）、`src/utils/capabilities.ts`（新）、`src/utils/activity.ts`（新）、`src/tests/setup.ts`。
- **验证**：`npm --prefix frontend test`（重点 `app-shell`、`api-client`、`auth`）；`npm --prefix frontend run build`。

### P1 壳层与通用原语

- **内容**：`AppSidebar.vue` → `n-menu` + 收件箱 `n-badge`；`App.vue` 顶栏 `n-dropdown` + 铃铛；`useInboxUnread.ts`（轮询 60s + 路由/前台刷新）；`VersionConflictDialog.vue` → `n-modal` 重构 + `useVersionedSave.ts`；`PageHeader.vue` 字号收敛；确定抽屉表单与确认模式模板。
- **改动文件**：`src/App.vue`、`src/components/AppSidebar.vue`、`src/composables/useInboxUnread.ts`（新）、`src/composables/useVersionedSave.ts`（新）、`src/components/VersionConflictDialog.vue`、`src/components/PageHeader.vue`。
- **验证**：`npm --prefix frontend test -- src/tests/app-shell.test.ts src/tests/home-attention.test.ts`；构建。

### P2 认证与账号

- **内容**：登录/注册/账号设置三页迁 `n-form` + `n-input`。
- **改动文件**：`src/views/LoginView.vue`、`src/views/RegisterView.vue`、`src/views/AccountView.vue`。
- **验证**：`npm --prefix frontend test -- src/tests/auth.test.ts src/tests/registration-error.test.ts src/tests/account-admin.test.ts`；构建。

### P3 首页与会议列表

- **内容**：`HomeView` 卡片化 + 未读徽标 + `generated_at`；`MeetingsView` 服务端参数筛选 + 加载更多 + 创建抽屉（含参与人角色选择）。
- **改动文件**：`src/views/HomeView.vue`、`src/views/MeetingsView.vue`、`src/components/AttentionCard.vue`。
- **验证**：`npm --prefix frontend test -- src/tests/home-attention.test.ts src/tests/meetings-view.test.ts src/tests/global-workspace.test.ts`；构建。

### P4 会议工作区

- **内容**：7.7 全部（页头取消/重开、准备抽屉可编辑参与人/主持/记录、议题菜单与元信息/附件/时长、材料与评论抽屉、完成链补充）。
- **改动文件**：`src/views/MeetingWorkspaceView.vue`、`src/components/AgendaWorkbench.vue`、`AgendaDetail.vue`、`AgendaQueue.vue`、`AttachmentPanel.vue`、`MeetingCommentsPanel.vue`、`CompletedMeetingChain.vue`、`MentionTextarea.vue`、`OutcomeComposer.vue`（抽屉化可选，P4 保持内联）。
- **验证**：`npm --prefix frontend test -- src/tests/meeting-workspace.test.ts src/tests/meeting-lifecycle.test.ts src/tests/agenda-workbench.test.ts src/tests/meeting-comments.test.ts src/tests/comments-mentions.test.ts src/tests/workflow-components.test.ts src/tests/outcome-composer.test.ts src/tests/use-meeting-workspace.test.ts`；构建。

### P5 项目页与产出工作流

- **内容**：7.5 全部（`n-tabs`、删除项目与空项目约束、编辑抽屉含成员/负责人、系列管理抽屉、决策详情抽屉与状态约束、行动项编辑抽屉、开放问题 Tab（放弃项延期说明）、动态台账）。
- **改动文件**：`src/views/ProjectDetailView.vue`、`src/components/ProjectOverview.vue`、`ProjectRecordTabs.vue`、`ProjectActivityTab.vue`、`ProjectCreatePanel.vue`（拆分）、`ProjectUpdateComposer.vue`、新组件 `SeriesEditDrawer.vue`、`DecisionDetailDrawer.vue`、`ActionEditDrawer.vue`、`ProjectQuestionsTab.vue`。
- **验证**：`npm --prefix frontend test -- src/tests/project-workspace.test.ts src/tests/project-create-panel.test.ts src/tests/workflow-components.test.ts` + 新增 `project-questions.test.ts`、`series-manage.test.ts`、`project-activity.test.ts`、`decision-workflow.test.ts`；构建。

### P6 全局视图、收件箱、AI 任务与管理页

- **内容**：`ActionsView`/`DecisionsView` `n-data-table` remote 分页 + 抽屉；`InboxView` 增量 + 深链；`AiTasksView` 丢弃/元信息/历史开关；`AdminUsersView`/`AdminPluginsView` 表格化与能力徽标（插件事件固定 `limit`、无页码）。
- **改动文件**：`src/views/ActionsView.vue`、`DecisionsView.vue`、`InboxView.vue`、`AiTasksView.vue`、`AdminUsersView.vue`、`AdminPluginsView.vue`、`src/utils/links.ts`（`source_comment` 深链）。
- **验证**：`npm --prefix frontend test -- src/tests/global-workspace.test.ts src/tests/inbox.test.ts src/tests/ai-tasks.test.ts src/tests/ai-work-assistant-plugin.test.ts src/tests/admin-plugins.test.ts src/tests/account-admin.test.ts`；构建。

### P7 收尾与文档

- **内容**：图标字形全量清扫（4.3 映射清单逐项替换）；`.notice`/`.empty-state`/`.avatar` 等旧类清理与 `styles.css` 瘦身（保留布局类与品牌 token）；动效/`prefers-reduced-motion` 走查；`≤640px` 响应式走查；文档更新（第 13 节）；全量测试 + 构建 + 手动视觉验收。
- **改动文件**：`src/styles.css`、各残余视图/组件、`docs/development.md`。
- **验证**：`npm --prefix frontend test`、`npm --prefix frontend run build`、手动清单（第 11 节）。

## 10. 文件清单（新增与修改）

**新增：**

- `frontend/src/theme/naive.ts` — 主题覆盖 + 状态色映射
- `frontend/src/components/AppAvatar.vue` — 头像（`avatar_color`）
- `frontend/src/composables/useInboxUnread.ts` — 壳层未读状态单例
- `frontend/src/composables/useVersionedSave.ts` — 409 冲突处理
- `frontend/src/utils/capabilities.ts` — 能力判定辅助
- `frontend/src/utils/activity.ts` — 活动事件文案映射
- `frontend/src/components/SeriesEditDrawer.vue`
- `frontend/src/components/DecisionDetailDrawer.vue`
- `frontend/src/components/ActionEditDrawer.vue`
- `frontend/src/components/ProjectQuestionsTab.vue`
- 测试新增：`frontend/src/tests/project-questions.test.ts`、`series-manage.test.ts`、`project-activity.test.ts`、`decision-workflow.test.ts`

**修改（按阶段）：** P0：`package.json`、`package-lock.json`、`src/main.ts`、`src/App.vue`、`src/components/StatusPill.vue`、`src/tests/setup.ts`；P1：`src/App.vue`、`AppSidebar.vue`、`VersionConflictDialog.vue`、`PageHeader.vue`；P2：`LoginView.vue`、`RegisterView.vue`、`AccountView.vue`；P3：`HomeView.vue`、`MeetingsView.vue`、`AttentionCard.vue`；P4：`MeetingWorkspaceView.vue`、`AgendaWorkbench.vue`、`AgendaDetail.vue`、`AgendaQueue.vue`、`AttachmentPanel.vue`、`MeetingCommentsPanel.vue`、`CompletedMeetingChain.vue`、`MentionTextarea.vue`、`OutcomeComposer.vue`；P5：`ProjectDetailView.vue`、`ProjectOverview.vue`、`ProjectRecordTabs.vue`、`ProjectActivityTab.vue`、`ProjectCreatePanel.vue`、`ProjectUpdateComposer.vue`；P6：`ActionsView.vue`、`DecisionsView.vue`、`InboxView.vue`、`AiTasksView.vue`、`AdminUsersView.vue`、`AdminPluginsView.vue`、`src/utils/links.ts`；P7：`src/styles.css`、`docs/development.md`。

**不改动**：`backend/**`（全部）；`src/api/client.ts`；`src/plugins/**` 契约；`useMeetingWorkspace.ts` 的持久化语义（仅如 P4 需要可加类型字段）。

**类型与封装修正**：`src/api/meetings.ts`（补 `cancel`/`reopen` 生命周期封装，`LifecycleAction` 从 `start|finish` 扩展到四种命令）、`src/domain/meetings.ts`（补议题 `carry_from_open_question_id`、`actual_duration_seconds` 等展示字段与参与人写入类型）、`src/domain/outcomes.ts`（补 `reviewers[]`、`decided_by`、`completed_at` 等展示字段）。

## 11. 测试策略

### 11.1 Naive UI 与 jsdom 适配

- 基线：当前 `npm --prefix frontend test` 为 25 个测试文件 / 124 个用例全绿；每个阶段结束都必须保持全绿，并在阶段报告中给出实际命令与结果。
- `tests/setup.ts` 增加全局补丁（P0）：`ResizeObserver`（空实现类）、`window.matchMedia`（返回 `{matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}}`）、`Element.prototype.scrollTo` noop。
- 抽屉/对话框/`n-popconfirm`/`n-dropdown` 内容 Teleport 到 `document.body`：测试一律用 `screen.findByRole('dialog')`、`findByText` 等全局查询（不依赖 `container`）；`cleanup()` 已存在于 setup。
- `n-data-table` 在 jsdom 下宽度为 0：不启用固定列与虚拟滚动；需要 `scroll-x` 时给表格显式 `min-width`；分页断言检查请求参数（`limit/offset`）与 `itemCount` 渲染，不测滚动行为。
- 弹出层异步渲染：操作后 `await screen.findBy...`；断言消息用 `findByText` 匹配 `n-message` 文案。

### 11.2 既有测试更新策略

- 保留既有约定：角色查询优先（`getByRole`）、标签（`getByLabelText`）、关键 `data-testid`（`meeting-workbench`、`agenda-detail`、`agenda-queue`、`flow-actions`、各编辑器 testid、`agenda-row-*`）尽量沿用，减少无谓改写。
- **有意更新**固化旧遗漏的断言：`agenda-workbench.test.ts:161-164`“不暴露议题记录版本号或独立跳过动作”→ 改为“不暴露版本号，但提供独立跳过动作并通过 `/skip` 端点提交”；`meetings-view.test.ts` 保留“高级筛选”交互语义，但“当前显示 N 场会议”这类客户端统计改为服务端分页/筛选断言（`series_id` 仍为已加载页内客户端过滤）；`global-workspace.test.ts` 现有 `project_id/status/owner_user_id` 服务端参数断言保留，补充 `limit/offset` 与表格渲染断言；`meeting-workspace.test.ts` 的 `ready` 用例保留（行为不劣化）。
- 新增测试覆盖本次新能力：会议取消/重开（含 canceled 无重开入口）、参与人角色编辑提交、议题跳过/移动（五个版本字段）/迁移/转问题/复制、议题附件、系列编辑/归档/常设议题、决策评审流转（pending/approved/changes_requested、定稿、撤回、替代约束）、行动项编辑抽屉与状态流转、项目成员增删与换负责人、开放问题排期/解决与 `dropped` 只读兼容、活动台账渲染与游标、收件箱增量与 `source_comment` 深链、壳层未读徽标、插件任务丢弃与 `include_history`、`context_scopes/external_network` 徽标、空项目删除约束与 409 提示、派生产出无编辑入口。
- 能力门控测试：`can_contribute=false` 时不渲染各写入入口（沿用 `project-workspace`/`meeting-workspace` 既有模式，扩展至新 Tab/抽屉）。

### 11.3 类型与构建

- 每阶段末 `npm --prefix frontend run build`（`vue-tsc -b` 严格）通过；新组件 props 全量类型化；`naive-ui` 组件类型以具名导入使用。

### 11.4 保留手动验证

- 视觉验收（P7 清单）：抽屉/对话框焦点与 Esc、`n-data-table` 分页/排序感观、徽标更新节奏、冲突对话框双栏对比、`≤640px` 布局、`prefers-reduced-motion`、真实浏览器下的附件上传与下载、SSE 工作简报流式、Milkdown 编辑器在 `n-drawer` 内的滚动与工具栏。
- 手动 API 冒烟沿用 `scripts/smoke_api.py`（不需要因为本次改动而变）。

## 12. 风险与缓解

1. **25 个测试文件（124 用例）大规模翻新的回归风险**：改动覆盖全部视图，测试可能成批失败。
   - 缓解：严格按 P0-P7 分阶段，每阶段全量 `npm --prefix frontend test` 绿才合并；保留 role/label/testid 约定；只对明确固化旧遗漏的断言做有意更新（记录在 commit/PR 说明）。
2. **Naive UI 在 jsdom 环境的兼容风险**（ResizeObserver、matchMedia、Teleport 时序、表格零宽）。
   - 缓解：P0 先落地 setup 补丁与一个最小冒烟测试；避免虚拟滚动/固定列；弹出层断言用全局查询 + `findBy*`。
3. **包体积与首屏性能**（naive-ui 体积可观）。
   - 缓解：ESM 具名导入由 Vite tree-shaking；不引入 `unplugin-auto-import` 等隐式全量插件；路由懒加载保持；构建产物体积在 P0/P7 各对比一次。
4. **视觉一致性/品牌退化**：过度使用 Naive 默认外观冲淡深绿品牌与现有卡片质感。
   - 缓解：以 4.2 的 `themeOverrides` 与状态色表作为 Naive 侧的单一事实来源（品牌值对齐 `styles.css` 的 `:root`）；`StatusPill` 保留独立组件；P7 做全局视觉走查。
5. **能力门控回归**（误从 `session.user.role` 推导项目/会议能力）。
   - 缓解：`utils/capabilities.ts` 唯一入口 + 测试覆盖无 `can_contribute` 时无写入入口；code review 检查 `session.user.role` 出现点只允许在管理员路由/导航。
6. **范围膨胀到后端**：对齐过程中可能发现“前端做不到”的条目，产生改后端的冲动。
   - 缓解：第 8 节清单把此类条目显式标记延期（#25 角色指派、#35 复制来源投影、#36 放弃写入口）；后端文件零改动基线；#35/#36 需用户在第 15 节明确授权极小改动后才可实施。
7. **会议工作区保存语义回归**（dirty/409/离开保护是最复杂的既有逻辑）。
   - 缓解：`useMeetingWorkspace`、`AgendaDetail` 的持久化与冲突逻辑不改语义，仅换 UI 层；相关测试文件（`use-meeting-workspace`、`meeting-workspace`、`agenda-workbench`）在 P4 全量跑。
8. **早期调研结论与实现不一致**：本规格已按后端代码校正参与人可编辑、成员可管理、canceled 不可重开、开放问题无法放弃等事实（第 3 节“调研校正”）。实现阶段若再遇到出入，一律以后端当前代码为准，并在规格或 PR 中标注延期，不凭摘要实现。

## 13. 文档更新清单

- `docs/development.md`：
  - “架构概览”增加前端 UI 栈描述：Vue 3 + Naive UI（浅色主题，`src/theme/naive.ts` 维护 `themeOverrides` 与状态色映射）+ `@lucide/vue` 图标 + Milkdown 编辑器；不引入 Pinia（reactive 单例模式）。
  - “测试与构建”不变（命令未变）；补一句：Naive 组件测试依赖 `tests/setup.ts` 的 jsdom 补丁。
- 根 `README.md`：本次不改变任何用户可见行为与启动方式，README 无截图需替换；仅在文案与 UI 描述不一致处做最小同步（预计无）。
- `AGENTS.md`：无需改动——没有新增规则、命令或后端契约变化；前端验证命令保持现有两条。
- 本规格自身（历史决策记录）不做后续维护，改版细节最终以 `docs/development.md` 为准。

## 14. 决策摘要

- 引入 `naive-ui`（浅色），品牌深绿 `#0b6a58` 通过 `themeOverrides` 映射；新建 `src/theme/naive.ts` 承载 Naive 主题映射与状态色（品牌值与 `styles.css` 的 `:root` 保持一致）。
- 图标全 SVG（`@lucide/vue`），替换全部 Unicode/emoji 字形；图标按钮必带 `aria-label`；字母头像统一 `AppAvatar` 并使用后端 `avatar_color`；品牌 “M” 字标默认保留。
- 稠密全局列表（行动项/决策/用户/插件事件）→ `n-data-table` + 服务端筛选分页；富内容面保持卡片/行布局。
- 创建/编辑 → 右侧 `n-drawer`；确认/破坏性 → `n-popconfirm`/`n-dialog`；提示 → `n-message`/`n-alert`。
- 会议参与人（角色、主持/记录）在创建与准备抽屉中可编辑（`PUT /api/meetings/{id}` 会应用 `participants`）；项目成员增删与换负责人在编辑项目抽屉中管理（`member_ids` 全量替换；成员角色指派无入口）。
- 生命周期操作：cancel 可用于 `draft/ready/in_progress`；reopen 仅 `completed`；`canceled` 不可重开，且 cancel 不跳过议题、不生成快照。
- 开放问题生命周期落项目详情新 Tab（更新/排期/解决）；“放弃（dropped）”无写入口、延期；系列管理落在项目详情会议 Tab 抽屉；不新增路由与全局问题页。
- 版本冲突统一为共享 `VersionConflictDialog`（`n-modal`）+ `useVersionedSave`，覆盖全部 `expected_version` 实体。
- 壳层未读徽标：`/api/inbox/changes?cursor=0&limit=1` 的 `unread_count`，60s 轮询 + 路由/前台/已读操作触发刷新。
- `ready` 状态：仅渲染兼容旧数据，操作上视同 `draft`，不新增转换 UI。
- 全局列表用户名：从 `/api/projects` 成员聚合姓名映射，缺名回退“用户·ID 前缀”。
- 权限渲染只依据服务端 `capabilities`（与逐项 `can_delete/can_edit/can_resolve`）；`role` 仅用于管理员路由/导航。
- 反馈策略：refetch-on-success 为主，乐观更新仅限本地 UI 态。
- 后端契约零改动；延期对齐项：成员角色（stakeholder）指派、复制来源徽标（第 8 节 #35）、开放问题放弃（第 8 节 #36）；其中 #35/#36 是否通过用户授权的极小后端改动消除，见第 15 节。
- 状态管理与编辑器栈不变（reactive 单例、Milkdown Crepe、marked+DOMPurify、无 Pinia）。
- 分八阶段交付（P0-P7），每阶段测试全绿 + 构建通过才推进。

## 15. 未决问题（2026-09-15 已确认）

1. **品牌 “M” 字标**：保留侧边栏/登录页的衬线 “M” 字标作为品牌 logo，不改为 SVG 标识。
2. **全局列表用户名来源**：接受“从 `/api/projects` 成员聚合姓名映射、缺名回退 ID 前缀”方案（第 7.8/8 节），不新增后端用户目录端点。
3. **复制议题的来源徽标（第 8 节 #35）**：延期，保持前端-only；“复制自其他议题”徽标不做，不修改后端投影。
4. **开放问题“放弃（dropped）”（第 8 节 #36）**：延期，仅兼容展示；本次不提供放弃操作，不修改后端。
5. **会议工作区显式保存按钮**：保留显式保存，本次只迁移表现层，不改为自动保存。
