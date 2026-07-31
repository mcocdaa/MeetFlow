# MeetFlow 平台演进与会议工作流设计

日期：2026-07-31
状态：已批准，待拆分实施计划

## 1. 目标与已批准决策

本设计针对当前 MeetFlow `v0.1.1` 之后的演进，覆盖后端架构、会议工作台 UI、插件能力和未来 CLI 边界。

已批准的整体路线是“双轨纵切”：后端边界治理与真实会议工作流同时推进，每完成一个业务切片，就交付一个用户可见的体验改进。

部署形态保持不变：FastAPI 模块化单体、同步 SQLAlchemy、SQLite WAL、单应用容器、持久化 `/app/data`、管理员只读挂载 `/app/plugins`。本设计不引入微服务、Redis、Celery、PostgreSQL 迁移、通用 Repository 框架或事件溯源。

MeetFlow CLI 不属于当前实施范围。未来 CLI 是 Docker 外独立发布的远程 API 客户端，不直接读取数据库、数据目录或插件目录。

## 2. 当前代码证据

- `backend/app/meetings/service.py` 的 `MeetingService` 同时负责会议系列、会议 CRUD、生命周期、快照、归档包、响应序列化和插件上下文，文件约 1335 行。
- `backend/app/outcomes/service.py` 的 `OutcomeService` 同时负责决策、行动项、开放问题、成果迁移、通知和序列化，文件约 1123 行。
- 多个领域 Service 方法自行调用 `session.commit()` 和 `session.rollback()`，跨会议、议题、成果、活动和通知的命令没有统一的事务入口。
- `AgendaService` 依赖 `MeetingService` 的展示辅助函数，`ProjectService` 依赖 `OutcomeService` 拼装响应，领域逻辑和投影职责发生反向耦合。
- `frontend/src/views/HomeView.vue` 以一个 `Promise.all` 同时加载核心关注事项、插件 Action 和 AI 工作简报，可选插件失败会影响整个首页加载态。
- `frontend/src/views/MeetingWorkspaceView.vue` 已有 `raw_notes_markdown` 草稿字段和保存请求，但模板没有原始笔记编辑器；草稿、议题 flush、会议保存和生命周期操作由多个前端请求串联。
- 当前前端把 `draft → ready → in_progress` 暴露为两步操作，但后端启动命令已经允许草稿或 ready 会议直接开始。
- 当前插件后端契约主要是 `MeetingAction`；前端契约主要是 editor assistant 与 task extension。插件加载仍是受信任代码、启动导入和重启生效。
- `pyproject.toml` 没有 CLI entry point；现有备份能力位于 `scripts/backup.py`，属于服务器运维路径，不应与未来远程 CLI 混合。

## 3. 范围与非目标

### 3.1 当前范围

1. 低风险可靠性修正：版本、readiness、首页插件隔离、原始笔记和保存反馈。
2. 会议生命周期纵切：命令、策略、Unit of Work、议题计时、自动跳过、会议快照和当前议题工作台。
3. 成果与插件基础：OutcomeService 拆分、SQLite outbox、Plugin API v2、首批导出和通知插件。

### 3.2 非目标

- 不改变单机自托管和 SQLite 默认部署形态。
- 不在网页或 CLI 中上传、安装或执行任意插件代码。
- 不在当前版本实现 `meetflow-cli` 包。
- 不把 capability 声明描述成安全沙箱；进程内插件仍是管理员信任边界。
- 不把会议系统改造成事件溯源系统。

## 4. 后端架构设计

### 4.1 会议领域边界

保留现有 `backend/app/meetings` 目录和 SQLAlchemy 模型，在内部按业务职责拆分：

```text
meetings/
├── commands/
│   ├── series.py
│   ├── editing.py
│   ├── lifecycle.py
│   └── amendments.py
├── policies.py
├── snapshots.py
├── queries.py
├── projectors.py
├── models.py
├── schemas.py
└── router.py
```

第一纵切只实现并验证 `StartMeeting` 与 `FinishMeeting`，再迁移系列和普通编辑命令。过渡期间可以保留 `MeetingService` facade，使现有 Router 和测试逐步迁移，而不是一次性修改所有调用方。

`outcomes` 在第二阶段采用同样模式，分别拆出 decision、action、question 命令和查询；成果迁移作为显式命令保留，不隐藏在删除或更新操作中。

### 4.2 命令数据流

```text
FastAPI Router
  → Command Handler
  → domain policy / authorization
  → SQLAlchemy models and explicit queries
  → activity + notification records（第二阶段启用 outbox 后追加外部事件记录）
  → one Unit of Work commit
  → query projector
  → existing API response envelope
```

Router 只负责认证、请求参数和响应状态码。状态迁移、来源链、活动记录和并发规则不能继续散落在 Router 或展示函数中。

### 4.3 Unit of Work 与事务

- 每个用户命令创建一个 Unit of Work。
- Command Handler 可以修改多个聚合和附属记录，但不自行 `commit()`。
- 成功路径只提交一次；异常路径统一 rollback。
- 会议数据、活动事件和站内通知在同一事务中写入。
- 外部插件和 Webhook 不在用户命令事务内同步调用。
- 查询函数不提交事务，响应由 `queries.py` 和 `projectors.py` 负责。

第一阶段不建立通用 Repository 层；直接使用可读的 SQLAlchemy `select()` 和显式加载策略。

### 4.4 生命周期、并发与错误

`StartMeeting`：

1. 校验用户状态、会议存在和 `expected_version`。
2. 允许 `draft` 或 `ready` 进入 `in_progress`。
3. 写入开始时间和活动记录。
4. 一次提交并返回完整会议投影。

`FinishMeeting`：

1. flush 当前议题草稿并校验会议版本。
2. 校验或处理剩余议题。
3. 将未完成议题自动标记为 `skipped`，记录实际耗时。
4. 解析 `@决策:`、`@行动:`、`@开放问题:` 标记为可确认的结构化建议。
5. 创建不可变 `MeetingSnapshot`。
6. 写活动和站内通知；第二阶段启用 outbox 后，再写可由插件消费的外部事件。
7. 一次提交并返回会后投影。

保留现有 `expected_version` 乐观并发语义。`StaleDataError`、版本冲突和可预期完整性冲突统一映射为稳定的 409 `AppError`，包含 expected/actual version；未知异常继续交给统一错误处理，不被宽泛捕获。

### 4.5 查询与投影

展示辅助函数从领域 Service 移到 `projectors.py`。跨领域引用不再通过导入其他 Service 的 serializer 实现。

- `queries.py` 声明列表、详情、会议包和插件上下文的读取关系。
- 插件上下文继续使用有字符预算的 bounded context。
- API 响应继续使用当前错误 envelope 和资源结构，降低前端迁移风险。

### 4.6 运维可观测性

- 应用版本由包元数据或构建变量统一提供，消除代码版本与 Git tag 漂移。
- `/api/health` 保留轻量存活检查。
- 新增 readiness 检查数据库连接、迁移 revision、Plugin Worker 和插件加载错误。
- readiness 不返回密钥、配置值或完整外部异常。

## 5. 会议工作台 UI 设计

### 5.1 信息层级

桌面端采用主工作区加右侧议程栏：

```text
会议标题 / 状态 / 保存状态 / 生命周期操作

┌ 当前议题 ──────────────────────┐  ┌ 议程队列 ┐
│ 标题、负责人、预计和实际时间    │  │ 已完成    │
│ 当前议题笔记                    │  │ 当前议题  │
│ 完成并进入下一议题              │  │ 待处理    │
└───────────────────────────────┘  └──────────┘

┌ 整场会议原始笔记 ──────────────┐  ┌ 材料/评论 ┐
└───────────────────────────────┘  └──────────┘

┌ 决策 / 行动项 / 开放问题 ──────┐
└───────────────────────────────┘
```

当前议题始终位于主区域顶部。空议程也保持顶部对齐，避免编辑区域随空状态垂直跳动。

### 5.2 生命周期交互

- `draft` 和 `ready` 统一显示一个“开始会议”按钮。
- 开始前自动 flush 必要草稿，再执行一次启动命令。
- 会议进行中显示当前议题、预计 `5min`、实际计时和保存状态。
- 结束按钮不因剩余议题被静默禁用；结束命令负责自动标记未完成议题为 `skipped`。
- 结束后进入冻结快照和会后成果视图。
- 不提供日常独立“跳过”按钮，减少状态操作。

### 5.3 草稿与保存

会议原始笔记、当前议题笔记和会议纪要分开保存。文本停止输入约 800ms 后自动保存；切换议题、开始或结束会议前立即 flush。

顶部显示 `保存中`、`已保存`、`保存失败` 和 `有冲突`。失败保留本地内容；409 继续复用冲突对话框；只有未保存或失败状态才触发离开页面保护。

### 5.4 前端模块

```text
frontend/src/
├── api/meetings.ts
├── composables/useAsyncResource.ts
├── composables/useMeetingWorkspace.ts
└── components/meeting/
    ├── CurrentTopicPanel.vue
    ├── MeetingAgendaRail.vue
    ├── MeetingNotesPanel.vue
    ├── MeetingPreparationDrawer.vue
    └── SaveStateIndicator.vue
```

不立即引入 Pinia。`useMeetingWorkspace` 统一管理服务器版本、本地草稿、保存队列和生命周期命令；现有 Markdown、插件、附件和评论组件继续复用。

### 5.5 首页插件降级

关注事项、近期会议和 AI 工作简报使用独立资源状态。AI 插件不可用或生成失败时只降级简报区域，不让核心首页进入全局错误态。

移动端优先显示当前议题，议程队列进入抽屉；保存状态通过文字和 `aria-live` 表达；推进议题后焦点进入新议题编辑器。

## 6. 插件生态设计

### 6.1 Plugin API v2

保持 v1 AI 插件兼容，同时增加：

| 能力 | 说明 |
| --- | --- |
| Action | 现有同步、流式、Job 和人工 Apply |
| Exporter | Markdown、JSON、ICS 等导出 |
| Event Subscriber | 订阅提交后的领域事件 |
| UI Slot | 首页卡片、会议工具栏、项目面板等固定位置 |

manifest 增加 capabilities、bounded context 和外部网络声明。声明用于兼容检查、管理展示和测试生成，不被描述为安全沙箱。

### 6.2 Outbox

业务命令在同一事务写入业务数据和 outbox event；内置 Worker 在提交后领取、执行、重试或进入失败诊断。事件包含 `event_id`、`event_type`、`payload_version`、目标资源和重试次数；订阅方按 event id 去重。

### 6.3 固定前端插槽

新增 `home.secondary-card`、`project.overview.panel`、`meeting.toolbar.action` 和 `meeting.summary.panel`，保留现有 editor assistant 与 task extension。插件加载或渲染失败只影响对应插槽。

### 6.4 首批插件

按顺序实现 Webhook Notifier、Markdown/JSON Meeting Export、ICS Calendar；AI Work Assistant 逐步迁移到 v2，但生成结果仍必须由用户确认。

继续禁止网页上传、任意路由注入、插件直接依赖核心 SQLAlchemy 模型和插件自有数据库迁移。

## 7. 独立 meetflow-cli（延期）

CLI 不进入当前实施计划。未来作为 Docker 外独立分发包，通过 HTTPS、Bearer PAT 和 JSON API 访问 MeetFlow。

CLI 不直接访问 SQLite、`data/`、`/app/plugins`，不控制 Docker，不安装服务器插件，不复用浏览器 Cookie。

启动 CLI 项目前，后端需要稳定 `/api/v1`、PAT scope/过期/撤销、分页、幂等写入、OpenAPI operation id 和兼容矩阵。CLI 的语言、仓库、配置存储和发布方式另写独立规格。

## 8. 分阶段交付

### 阶段 0：低风险修正

版本/readiness、首页插件隔离、原始笔记、一步开始、保存状态和离开保护。

### 阶段 1：会议纵切

StartMeeting、FinishMeeting、Unit of Work、议题计时、自动 skipped、标记解析、快照、当前议题工作台。

### 阶段 2：成果与插件基础

OutcomeService 拆分、outbox、Plugin API v2、Webhook、导出器和 ICS。

### 阶段 3：独立 CLI

在单独项目中设计和发布，依赖稳定 API 和 PAT，不倒灌当前阶段范围。

## 9. 验证标准

- Policy 单元测试覆盖状态迁移和完成时自动跳过。
- Command 集成测试证明一次命令只提交一次，失败不产生部分数据。
- 并发测试证明版本冲突稳定返回 409。
- 前端测试覆盖原始笔记保存、草稿保留、一步开始、结束快照和插件降级。
- Plugin 测试覆盖 manifest 兼容性、事件重试、去重、错误隔离和密钥脱敏。
- 现有 API 路径、错误 envelope、Alembic 迁移和 Docker 部署契约保持兼容。
