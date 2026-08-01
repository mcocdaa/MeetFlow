# MeetFlow Meeting Workflow Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将会议生命周期和工作台改造成一次命令、明确保存状态、当前议题优先的可验证纵向切片，同时保持现有 API、SQLite 和插件兼容。

**Architecture:** 先做低风险 runtime/home 修正，再以 `StartMeeting`/`FinishMeeting` 为边界抽出会议命令、策略和轻量 Unit of Work；`MeetingService` 保留兼容 facade。前端通过会议 API 模块与 `useMeetingWorkspace` 管理草稿、版本和生命周期，议题/附件/评论组件继续复用。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite WAL、Vue 3、TypeScript、Vitest、Testing Library。

---

## 文件边界

- Create: `backend/app/runtime_info.py` — 包版本、health/readiness 结果。
- Create: `backend/app/domain/unit_of_work.py` — 命令事务执行器，不建立通用 Repository。
- Create: `backend/app/meetings/policies.py` — 生命周期状态迁移和完成规则。
- Create: `backend/app/meetings/lifecycle.py` — Start/Finish 命令实现。
- Create: `backend/app/meetings/projectors.py` — 会议和快照响应投影，逐步从 Service 移出。
- Create: `frontend/src/api/meetings.ts` — 会议读取、保存和生命周期 API 函数。
- Create: `frontend/src/composables/useMeetingWorkspace.ts` — 会议草稿、保存队列、版本和生命周期。
- Create: `frontend/src/components/meeting/SaveStateIndicator.vue` — 保存状态的可访问展示。
- Modify: `pyproject.toml` — 将包版本与当前 `v0.1.1` 基线统一。
- Modify: `backend/app/main.py` — 使用 runtime version、增加 readiness、连接生命周期命令。
- Modify: `backend/app/plugins/worker.py` — 提供只读运行状态供 readiness 使用。
- Modify: `backend/app/meetings/service.py` — 保留公共 facade，委托 lifecycle/queries/projectors。
- Modify: `backend/app/meetings/router.py` — 使用命令 facade，保持路径和错误 envelope。
- Modify: `frontend/src/views/HomeView.vue` — 核心关注事项与可选插件资源隔离。
- Modify: `frontend/src/views/MeetingWorkspaceView.vue` — 使用 composable、原始笔记和一步开始。
- Modify: `frontend/src/components/AgendaDetail.vue` — 保留显式议题保存，向工作台报告保存状态。
- Modify: `frontend/src/components/AgendaWorkbench.vue` — 暴露 flush 和当前议题状态。
- Modify: `frontend/src/styles.css` — 只添加工作台保存状态、原始笔记和移动布局样式。
- Modify: `backend/tests/test_health.py` — 版本和 readiness API。
- Create: `backend/tests/test_readiness.py` — 数据库、插件错误和 Worker 状态矩阵。
- Modify: `backend/tests/domain/test_meeting_lifecycle.py` — 命令 facade、原始笔记快照和事务回滚回归。
- Modify: `frontend/src/tests/home-attention.test.ts` — 可选插件失败降级。
- Modify: `frontend/src/tests/meeting-workspace.test.ts` — 一步开始、原始笔记、保存状态和离开保护。
- Create: `frontend/src/tests/use-meeting-workspace.test.ts` — composable debounce、flush 和冲突状态。
- Modify: `docs/development.md` — 更新当前命令/查询/事务边界和验证入口。

### Task 1: 锁定现有生命周期和 runtime 行为

**Files:**
- Test: `backend/tests/test_health.py`
- Test: `backend/tests/domain/test_meeting_lifecycle.py`
- Test: `frontend/src/tests/home-attention.test.ts`
- Test: `frontend/src/tests/meeting-workspace.test.ts`

- [ ] **Step 1: 先运行当前基线测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/test_health.py backend/tests/domain/test_meeting_lifecycle.py`

Expected: 当前测试通过；记录测试数量，后续不得降低。

- [ ] **Step 2: 写入缺失的回归断言**

在 `test_meeting_lifecycle.py` 增加只验证既有契约的测试：完成快照包含 `raw_notes_markdown`，且 `start` 从 `draft` 进入 `in_progress`；不要重复已有自动 skipped、5 分钟默认值和 marker-derived outcome 测试。

```python
def test_snapshot_keeps_raw_notes_and_start_accepts_draft(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        draft = session.get(Meeting, meeting_id)
        started = MeetingService(session).start(
            meeting_id, LifecycleCommand(expected_version=draft.version), actor
        )
        completed = MeetingService(session).finish(
            meeting_id, LifecycleCommand(expected_version=started.version), actor
        )
        assert completed.status == MeetingStatus.completed
        assert completed.current_snapshot.snapshot_json["meeting"]["raw_notes_markdown"] == "raw notes"
```

- [ ] **Step 3: 写 HomeView 的插件降级失败测试**

在 `home-attention.test.ts` 让 `/api/plugins/actions` reject，同时让 `/api/attention` 返回一条待办；断言待办仍显示，AI 区域出现局部错误。

- [ ] **Step 4: 写工作台原始笔记和一步开始测试**

在 `meeting-workspace.test.ts` 断言 `raw_notes_markdown` 有可访问编辑器；对 `draft` fixture 只点击一次 `开始会议`，断言不会请求 `/api/meetings/:id/ready`。

- [ ] **Step 5: 运行新增的红测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/test_health.py backend/tests/domain/test_meeting_lifecycle.py`; `npm --prefix frontend test -- --run src/tests/home-attention.test.ts src/tests/meeting-workspace.test.ts`

Expected: 新增 UI 断言失败，后端基线仍通过；不要在此步修改实现。

- [ ] **Step 6: Commit tests only**

```bash
git add backend/tests/test_health.py backend/tests/domain/test_meeting_lifecycle.py frontend/src/tests/home-attention.test.ts frontend/src/tests/meeting-workspace.test.ts
git commit -m "test: define meeting workflow foundation contracts"
```

### Task 2: 统一版本与 readiness

**Files:**
- Create: `backend/app/runtime_info.py`
- Create: `backend/tests/test_readiness.py`
- Modify: `pyproject.toml`
- Modify: `backend/app/main.py`
- Modify: `backend/app/plugins/worker.py`
- Modify: `backend/tests/test_health.py`

- [ ] **Step 1: 写 runtime info 的失败测试**

```python
def test_runtime_info_reports_package_version_and_readiness(client):
    assert client.get("/api/meta").json()["version"] == "0.1.1"
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "plugins": "ok", "worker": "stopped-in-test"}
```

- [ ] **Step 2: 执行测试确认 endpoint 不存在**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/test_readiness.py`

Expected: FAIL with 404 or missing response fields。

- [ ] **Step 3: 增加版本和 readiness 实现**

`runtime_info.py` 暴露纯函数，避免从 `main.py` 读取全局应用：

```python
from importlib.metadata import PackageNotFoundError, version

def package_version() -> str:
    try:
        return version("meetflow")
    except PackageNotFoundError:
        return "0.1.1"
```

`main.py` 使用 `FastAPI(version=package_version())`，增加 `/api/meta` 和 `/api/health/ready`。readiness 只返回状态字符串、迁移可用性、插件错误数量和 Worker 运行态；测试环境 Worker 明确返回 `stopped-in-test`。`PluginJobWorker` 增加只读 `running` 属性，不改变其循环逻辑。

- [ ] **Step 4: 统一包版本**

把 `pyproject.toml` 的 `project.version` 从 `0.1.0` 改为 `0.1.1`，并保持 release workflow 的 tag 校验不变。

- [ ] **Step 5: 刷新 editable 安装元数据**

Run: `.venv/bin/python -m pip install -e .`

Expected: `importlib.metadata.version("meetflow")` 返回 `0.1.1`，使本地 readiness 和 FastAPI metadata 测试读取到新版本。

- [ ] **Step 6: 运行 runtime 测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/test_health.py backend/tests/test_readiness.py`

Expected: PASS，旧 `/api/health` 仍返回 `{"status":"ok"}`。

- [ ] **Step 7: Commit runtime slice**

```bash
git add pyproject.toml backend/app/runtime_info.py backend/app/main.py backend/app/plugins/worker.py backend/tests/test_health.py backend/tests/test_readiness.py
git commit -m "feat: expose MeetFlow runtime readiness"
```

### Task 3: 隔离首页核心资源与可选插件

**Files:**
- Modify: `frontend/src/views/HomeView.vue`
- Modify: `frontend/src/tests/home-attention.test.ts`

- [ ] **Step 1: 保留红测试并明确资源状态**

测试 fixture 让 `attention` 成功、`actions` 失败、`work-brief` 成功；断言 priority queue 可见，且只有 AI 区域显示错误。

- [ ] **Step 2: 拆出三个加载函数**

```ts
async function loadAttention() {
  response.value = await api<AttentionResponse>('/api/attention')
}

async function loadWorkBriefCapability() {
  try {
    const actions = await api<PluginAction[]>('/api/plugins/actions')
    workBriefEnabled.value = actions.some((item) => item.action_id === 'ai-work-assistant.user_work_brief')
  } catch (reason) {
    workBriefError.value = reason instanceof Error ? reason.message : 'AI 插件状态读取失败'
    workBriefEnabled.value = false
  }
}
```

`load()` 先等待核心 `attention`，然后调用已捕获自身异常的 `loadWorkBriefCapability()`；不能让可选请求设置全局 `error`。

- [ ] **Step 3: 运行前端聚焦测试**

Run: `npm --prefix frontend test -- --run src/tests/home-attention.test.ts`

Expected: PASS，包含插件失败和已有工作简报持久化用例。

- [ ] **Step 4: Commit HomeView**

```bash
git add frontend/src/views/HomeView.vue frontend/src/tests/home-attention.test.ts
git commit -m "fix: isolate optional plugin failures on home"
```

### Task 4: 提取会议 API 和草稿 composable

**Files:**
- Create: `frontend/src/api/meetings.ts`
- Create: `frontend/src/composables/useMeetingWorkspace.ts`
- Create: `frontend/src/tests/use-meeting-workspace.test.ts`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`

- [ ] **Step 1: 写 composable 的 debounce 和 flush 红测试**

```ts
it('debounces meeting draft saves and flushes before lifecycle', async () => {
  const apiMock = vi.fn().mockResolvedValue({ ...meeting, version: 2 })
  const workspace = useMeetingWorkspace({ initial: meeting, request: apiMock, debounceMs: 800 })
  workspace.draft.value.raw_notes_markdown = 'new notes'
  await vi.advanceTimersByTimeAsync(799)
  expect(apiMock).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  expect(apiMock).toHaveBeenCalledWith(expect.objectContaining({ method: 'PUT' }))
})
```

- [ ] **Step 2: 定义 API 模块函数**

```ts
export function getMeeting(id: string) { return api<Meeting>(`/api/meetings/${id}`) }
export function updateMeeting(id: string, body: MeetingUpdate) {
  return api<Meeting>(`/api/meetings/${id}`, { method: 'PUT', body: JSON.stringify(body) })
}
export function runMeetingLifecycle(id: string, action: LifecycleAction, expectedVersion: number) {
  return api<Meeting>(`/api/meetings/${id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) })
}
```

- [ ] **Step 3: 实现 composable 状态机**

先在 `frontend/src/domain/meetings.ts` 复用已有 `Meeting` 类型，并在 `frontend/src/api/meetings.ts` 明确定义：

```ts
export type LifecycleAction = 'start' | 'finish'
export type MeetingUpdate = Pick<Meeting, 'title' | 'purpose_markdown' | 'raw_notes_markdown'> & {
  expected_version: number
}
```

`useMeetingWorkspace` 必须持有 `meeting`、`draft`、`acceptedDraft`、`saving`、`saveState`、`conflict` 和 `lifecycleAction`；每次成功更新都替换服务器 version，409 时保留 draft 并暴露冲突状态。只对会议级字段 debounce；议题仍由 `AgendaDetail` 显式保存，避免两个组件同时写同一 AgendaItem。

- [ ] **Step 4: 接入 MeetingWorkspaceView**

删除 view 中重复的会议保存、版本和生命周期 API 拼接，改由 composable 提供 `persistIfDirty()`、`flushBeforeLifecycle()` 和 `runLifecycle()`；现有 `AgendaWorkbench.flushCurrentDraft()` 继续作为前置步骤。

- [ ] **Step 5: 运行 composable 和工作台测试**

Run: `npm --prefix frontend test -- --run src/tests/use-meeting-workspace.test.ts src/tests/meeting-workspace.test.ts`

Expected: 新旧保存、冲突和生命周期顺序测试全部 PASS。

- [ ] **Step 6: Commit API/composable slice**

```bash
git add frontend/src/api/meetings.ts frontend/src/composables/useMeetingWorkspace.ts frontend/src/tests/use-meeting-workspace.test.ts frontend/src/views/MeetingWorkspaceView.vue
git commit -m "refactor: centralize meeting workspace draft state"
```

### Task 5: 加入原始笔记、一步开始和保存状态 UI

**Files:**
- Create: `frontend/src/components/meeting/SaveStateIndicator.vue`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/components/AgendaWorkbench.vue`
- Modify: `frontend/src/components/AgendaDetail.vue`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/tests/meeting-workspace.test.ts`

- [ ] **Step 1: 先补 UI 红测试**

新增断言：`raw_notes_markdown` 有编辑器；草稿状态只显示 `开始会议`；保存状态包含可读文本和 `aria-live="polite"`；输入后导航尝试会保留草稿。

- [ ] **Step 2: 实现保存状态组件**

```vue
<template>
  <span class="save-state" role="status" aria-live="polite">{{ label }}</span>
</template>
```

组件只接收 `state: 'idle' | 'saving' | 'saved' | 'error' | 'conflict'`，不包含 API 逻辑。

- [ ] **Step 3: 加入原始笔记编辑器**

在会议纪要前新增整场会议原始笔记区域，绑定 `draft.raw_notes_markdown`，复用 `MarkdownEditor` 和 `registerEditor` flush；保存 payload 保持现有 `MeetingEdit` schema。

- [ ] **Step 4: 合并开始按钮**

把 `draft` 和 `ready` 的 template 分支改成同一 `lifecycle('start')` 按钮；保留后端 `/ready`、`/draft` API 给旧客户端和管理员流程，但不再从当前工作台触发。

- [ ] **Step 5: 加入导航保护和移动布局**

使用 `onBeforeRouteLeave` 和 `beforeunload` 仅在 `dirty || saveState === 'error'` 时提示；移动端将 `.agenda-queue` 放入现有 `ContextDrawer`，不重写抽屉组件。

- [ ] **Step 6: 运行前端回归**

Run: `npm --prefix frontend test -- --run src/tests/meeting-workspace.test.ts src/tests/agenda-workbench.test.ts src/tests/markdown-editor.test.ts`；`npm --prefix frontend run build`

Expected: PASS，构建产物无 TypeScript 错误。

- [ ] **Step 7: Commit workspace UI**

```bash
git add frontend/src/components/meeting/SaveStateIndicator.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/components/AgendaWorkbench.vue frontend/src/components/AgendaDetail.vue frontend/src/styles.css frontend/src/tests/meeting-workspace.test.ts
git commit -m "feat: focus meeting workspace on current topic"
```

### Task 6: 抽出生命周期 Policy、Unit of Work 和命令 facade

**Files:**
- Create: `backend/app/domain/unit_of_work.py`
- Create: `backend/app/meetings/policies.py`
- Create: `backend/app/meetings/lifecycle.py`
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/meetings/router.py`
- Modify: `backend/tests/domain/test_meeting_lifecycle.py`

- [ ] **Step 1: 写 Policy 单元测试**

```python
def test_lifecycle_policy_accepts_draft_and_ready_for_start():
    assert LifecyclePolicy.can_start(MeetingStatus.draft)
    assert LifecyclePolicy.can_start(MeetingStatus.ready)
    assert not LifecyclePolicy.can_start(MeetingStatus.completed)
```

- [ ] **Step 2: 实现最小 Unit of Work**

```python
class UnitOfWork:
    def __init__(self, session: Session):
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def execute(self, command):
        try:
            result = command(self.session)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise
```

不在 Unit of Work 中创建 Repository、隐藏查询或改变 Session 生命周期；请求依赖仍负责关闭 Session。

- [ ] **Step 3: 将 start/finish 的状态判断移动到 Policy**

`LifecyclePolicy` 只接受状态和是否存在未完成议题等纯输入，返回允许/拒绝；错误继续使用现有 `AppError` code。`finish` 已有的自动 skipped、耗时、snapshot 和 source-chain 校验逻辑保持行为不变。

- [ ] **Step 4: 把生命周期方法迁移到命令类**

`MeetingLifecycleCommands.start()` 和 `.finish()` 接收 `UnitOfWork`、meeting id、payload、actor；旧 `MeetingService.start/finish` 只作为 facade 调用命令类。迁移时保留 scheduled occurrence 会先完成旧 occurrence 的现有规则和所有 snapshot relationship loading。

- [ ] **Step 5: 保证一次提交和失败回滚**

新增测试在 snapshot 构建或 activity 写入抛错时检查 meeting、agenda、snapshot 都没有部分提交；保留已有并发 race 测试，确保 409 语义不变。

- [ ] **Step 6: 运行后端生命周期测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/domain/test_meeting_lifecycle.py backend/tests/domain/test_meeting_series.py backend/tests/domain/test_agendas.py`

Expected: PASS，现有生命周期、重复 finish、并发 start/finish、series isolation 全部保留。

- [ ] **Step 7: Commit lifecycle architecture**

```bash
git add backend/app/domain/unit_of_work.py backend/app/meetings/policies.py backend/app/meetings/lifecycle.py backend/app/meetings/service.py backend/app/meetings/router.py backend/tests/domain/test_meeting_lifecycle.py
git commit -m "refactor: isolate meeting lifecycle commands"
```

### Task 7: 移出会议查询与投影，并保持 API 响应兼容

**Files:**
- Create: `backend/app/meetings/queries.py`
- Create: `backend/app/meetings/projectors.py`
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/plugins/context.py`
- Create: `backend/tests/api/test_meeting_api.py` — meeting detail、series、snapshot 和 plugin-context response contract。

- [ ] **Step 1: 记录当前响应快照**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/api backend/tests/domain/test_meeting_lifecycle.py`

保存当前 meeting detail、series detail、snapshot 和 plugin context 的 JSON 字段集合，作为迁移后的契约断言。

- [ ] **Step 2: 移动纯 serializer 函数**

先移动 `serialize_snapshot`、`serialize_amendment`、`serialize_series`、`serialize_meeting`、`serialize_attachment` 和 `serialize_action`；这些函数不能调用 `session.commit()`、认证依赖或插件 handler。

- [ ] **Step 3: 移动查询方法**

将 `list_series`、`list_meetings`、`series_detail`、`meeting_detail`、`package` 和 `plugin_context` 的读取部分移入 `MeetingQueries`；插件 context 继续通过 `PluginContextBuilder` 做字符预算。

- [ ] **Step 4: 保留 facade 与 API 字段**

旧 `MeetingService` 方法委托 `MeetingQueries`，Router 路径和 response model 不变。跨领域展示引用改为 `projectors.user_ref` 等纯函数，删除 Agenda/Project 对 Meeting/Outcome Service serializer 的导入。

- [ ] **Step 5: 运行 API 契约测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/api backend/tests/domain/test_meeting_lifecycle.py backend/tests/plugins`

Expected: PASS，现有响应字段、snapshot source metadata 和 bounded plugin context 不变。

- [ ] **Step 6: Commit query/projection split**

```bash
git add backend/app/meetings/queries.py backend/app/meetings/projectors.py backend/app/meetings/service.py backend/app/plugins/context.py backend/tests/api
git commit -m "refactor: separate meeting queries and projectors"
```

### Task 8: 更新开发文档并执行完整验证

**Files:**
- Modify: `docs/development.md`

- [ ] **Step 1: 更新架构说明**

在 `docs/development.md` 说明会议命令、Unit of Work、查询投影、前端 composable 和 readiness；明确 CLI 仍是延期的独立远程包，服务器运维继续使用 `scripts/backup.py` 和 `docs/operations.md`。

- [ ] **Step 2: 检查 Markdown**

Run: `git diff --check`；确认文档中的 `backend/`、`frontend/` 和 `docs/operations.md` 链接存在。

- [ ] **Step 3: 运行完整验证**

Run:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: 后端和前端测试通过，生产构建成功；若 Docker 文件没有变化，本计划不额外重建容器。

- [ ] **Step 4: Commit docs and final verification**

```bash
git add docs/development.md docs/README.md
git commit -m "docs: describe meeting workflow architecture"
git status --short --branch
```

Expected: 只有本计划涉及的提交存在，工作区无未提交应用改动。
