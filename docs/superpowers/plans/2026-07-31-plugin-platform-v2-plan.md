# MeetFlow Plugin Platform v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在会议命令边界稳定后，为受信任插件增加 capability manifest、可靠提交后事件、导出器和固定前端插槽，同时保持 AI Work Assistant v1 兼容。

**Architecture:** Plugin API v2 与 v1 并行加载；核心只向插件提供 bounded context。业务事务在 SQLite 中同时写业务数据和 outbox event，现有单进程 Worker 在提交后处理事件并负责重试/去重。前端只开放声明过的固定 slot，不支持任意路由或代码上传。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite、Pydantic、httpx、Vue 3、TypeScript、Vitest。

**Prerequisite:** `docs/superpowers/plans/2026-07-31-meeting-workflow-foundation-plan.md` 的生命周期命令和投影已合并；如果尚未合并，只能先完成 manifest/SDK 的纯兼容工作，不能接入业务事件。

---

## 文件边界

- Create: `backend/app/plugins/events.py` — event 类型、payload 版本和 outbox 写入。
- Create: `backend/app/plugins/exporters.py` — exporter 协议与结果验证。
- Create: `backend/migrations/versions/0008_plugin_events.py` — outbox 表和索引。
- Create: `backend/tests/plugins/test_manifest_v2.py` — v1/v2 manifest 兼容性。
- Create: `backend/tests/plugins/test_plugin_events.py` — outbox、去重和事务行为。
- Create: `backend/tests/plugins/test_event_worker.py` — 领取、成功、重试和死信。
- Create: `backend/tests/plugins/test_exporters.py` — bounded exporter 输出。
- Create: `plugins/meeting-export/plugin.yaml` — Markdown/JSON first-party exporter。
- Create: `plugins/meeting-export/backend.py` — read-only 会议包导出。
- Create: `plugins/webhook-notifier/plugin.yaml` — 签名 Webhook 配置。
- Create: `plugins/webhook-notifier/backend.py` — event subscriber 和 httpx 发送。
- Create: `frontend/src/components/PluginSlot.vue` — 固定 slot 的加载和错误隔离。
- Modify: `backend/app/plugins/contracts.py` — capabilities、exporter、subscriber 类型。
- Modify: `backend/app/plugins/models.py` — outbox ORM model。
- Modify: `backend/app/plugins/manager.py` — API v1/v2、能力注册和诊断。
- Modify: `backend/app/plugins/worker.py` — event worker loop 和 retry policy。
- Modify: `backend/app/plugins/router.py` — 管理诊断和 exporter endpoint。
- Modify: `backend/app/meetings/lifecycle.py` — 在提交事务中记录 `meeting.completed` event。
- Modify: `frontend/src/plugins/contracts.ts` — 固定 slot registration API。
- Modify: `frontend/src/plugins/registry.ts` — slot registry。
- Modify: `frontend/src/plugins/runtime.ts` — 能力过滤和加载错误。
- Modify: `frontend/src/views/AdminPluginsView.vue` — capabilities、兼容状态和失败事件。
- Modify: `frontend/src/views/HomeView.vue` — `home.secondary-card` slot。
- Modify: `frontend/src/views/MeetingWorkspaceView.vue` — `meeting.toolbar.action` / summary slot。
- Modify: `frontend/src/tests/admin-plugins.test.ts` — v2 诊断显示。
- Modify: `frontend/src/tests/app-shell.test.ts` — slot module failure isolation。
- Create: `frontend/src/tests/plugin-slots.test.ts` — slot registry and rendering。
- Modify: `backend/app/plugins/README.md` — v2 manifest 和受信任代码边界。
- Modify: `plugins/plugins.yaml` — first-party plugin registry entries。

### Task 1: 锁定 v1 兼容与 v2 manifest

**Files:**
- Test: `backend/tests/plugins/test_manifest_v2.py`
- Modify: `backend/app/plugins/contracts.py`
- Modify: `backend/app/plugins/manager.py`

- [ ] **Step 1: 写 manifest 红测试**

```python
def test_v1_manifest_still_loads_with_empty_capabilities(plugin_factory, plugin_client):
    plugin_factory("legacy-ai", manifest={"api_version": 1})
    descriptors = plugin_client.app.state.plugin_manager.discover()
    assert descriptors[0].manifest.api_version == 1

def test_v2_manifest_rejects_unknown_capability(plugin_factory, plugin_client):
    plugin_factory("bad-v2", manifest={"api_version": 2, "capabilities": {"unknown": ["x"]}})
    descriptors = plugin_client.app.state.plugin_manager.discover()
    assert any(error.plugin_id == "bad-v2" for error in plugin_client.app.state.plugin_manager.errors())
```

- [ ] **Step 2: 增加 capability 类型**

```python
class PluginCapabilities(BaseModel):
    actions: list[str] = Field(default_factory=list)
    exporters: list[str] = Field(default_factory=list)
    event_subscriptions: list[str] = Field(default_factory=list)
    ui_slots: list[str] = Field(default_factory=list)
    context_scopes: list[str] = Field(default_factory=list)
    external_network: bool = False
```

把 `PluginManifest.capabilities` 设为该类型，保留缺省空值使 v1 manifest 不变；`PluginManager.supported_api_versions = {1, 2}`，仍拒绝其他版本。

- [ ] **Step 3: 验证 manifest 与启用状态**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/plugins/test_manifest_v2.py backend/tests/plugins/test_config.py`

Expected: PASS；v1 AI 插件和已有 secret/config 测试不变。

- [ ] **Step 4: Commit manifest contract**

```bash
git add backend/app/plugins/contracts.py backend/app/plugins/manager.py backend/tests/plugins/test_manifest_v2.py
git commit -m "feat: add plugin v2 capability manifest"
```

### Task 2: 建立 outbox 数据模型与迁移

**Files:**
- Test: `backend/tests/plugins/test_plugin_events.py`
- Create: `backend/migrations/versions/0008_plugin_events.py`
- Create: `backend/app/plugins/events.py`
- Modify: `backend/app/plugins/models.py`

- [ ] **Step 1: 写 outbox 红测试**

```python
def test_record_event_is_unique_and_queued(plugin_client, meeting_id):
    database = plugin_client.app.state.database
    event_id = f"meeting.completed:meeting:{meeting_id}:1"
    with database.session() as session:
        first = record_plugin_event(
            session,
            event_type="meeting.completed",
            target_type="meeting",
            target_id=meeting_id,
            payload={"version": 1},
            event_id=event_id,
        )
        second = record_plugin_event(
            session,
            event_type="meeting.completed",
            target_type="meeting",
            target_id=meeting_id,
            payload={"version": 1},
            event_id=event_id,
        )
        session.commit()
        assert first.event_id == second.event_id
        assert first.status == PluginEventStatus.queued
```

- [ ] **Step 2: 定义 ORM model**

新增 `PluginEvent` 字段：`event_id` 主键、`event_type`、`payload_version`、`target_type`、`target_id`、`payload_json`、`status`、`attempts`、`next_attempt_at`、`claimed_at`、`finished_at`、`last_error`、`created_at`。`event_id` 唯一，`status/next_attempt_at` 建索引。

- [ ] **Step 3: 编写 Alembic 0008**

迁移只创建 `plugin_events` 表和索引；downgrade 删除索引后删除表。不要修改既有 plugin_jobs 表。

- [ ] **Step 4: 实现 record_plugin_event**

`record_plugin_event(session, event_type, target_type, target_id, payload, event_id=None)` 对显式 event id 幂等；payload 必须是 JSON mapping，并拒绝 secret/config 内容。

- [ ] **Step 5: 验证 fresh upgrade 和幂等**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/plugins/test_plugin_events.py backend/tests/migrations/test_fresh_baseline.py backend/tests/migrations/test_startup_migrations.py`

Expected: PASS；新鲜数据库迁移到 head，旧数据库升级后保留 plugin_jobs 和 plugin_configs。

- [ ] **Step 6: Commit outbox storage**

```bash
git add backend/app/plugins/events.py backend/app/plugins/models.py backend/migrations/versions/0008_plugin_events.py backend/tests/plugins/test_plugin_events.py
git commit -m "feat: add plugin event outbox"
```

### Task 3: 接入会议完成事件并实现 Worker 可靠处理

**Files:**
- Test: `backend/tests/plugins/test_event_worker.py`
- Modify: `backend/app/meetings/lifecycle.py`
- Modify: `backend/app/plugins/manager.py`
- Modify: `backend/app/plugins/worker.py`
- Modify: `backend/app/plugins/events.py`

- [ ] **Step 1: 写领取、成功和失败测试**

测试覆盖：queued event 被领取一次；handler 成功后为 succeeded；异常递增 attempts 并设置 `next_attempt_at`；超过 5 次进入 failed/dead-letter；重启 recover 不重复处理已 succeeded event。

- [ ] **Step 2: 在 FinishMeeting 事务中记录事件**

在第二阶段启用 outbox 后，`FinishMeeting` 在创建 snapshot、activity 和 notification 的同一个 Unit of Work 中调用：

```python
record_plugin_event(
    uow.session,
    event_type="meeting.completed",
    target_type="meeting",
    target_id=meeting.id,
    payload={"meeting_id": meeting.id, "snapshot_id": snapshot.id, "version": meeting.version},
)
```

事件只在核心事务成功后才可能被 Worker 领取。

- [ ] **Step 3: 实现原子领取**

单容器 Worker 仍可使用 polling，但领取必须先将 queued 行更新为 processing，并检查更新行数；只处理 `next_attempt_at <= now` 的事件。

- [ ] **Step 4: 实现重试策略**

重试间隔为 `min(2 ** attempts * 5, 300)` 秒；错误详情经过现有 `_redact_detail`；达到 5 次后保留可读 `last_error` 并停止自动重试。

- [ ] **Step 5: 运行 Worker 测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/plugins/test_event_worker.py backend/tests/plugins/test_jobs.py backend/tests/domain/test_meeting_lifecycle.py`

Expected: PASS；既有 AI job worker 的 queued/requesting/recover 行为不受影响。

- [ ] **Step 6: Commit event processing**

```bash
git add backend/app/meetings/lifecycle.py backend/app/plugins/events.py backend/app/plugins/manager.py backend/app/plugins/worker.py backend/tests/plugins/test_event_worker.py
git commit -m "feat: dispatch committed plugin events"
```

### Task 4: 增加 Exporter 协议和 Meeting Export 插件

**Files:**
- Test: `backend/tests/plugins/test_exporters.py`
- Create: `backend/app/plugins/exporters.py`
- Create: `plugins/meeting-export/plugin.yaml`
- Create: `plugins/meeting-export/backend.py`
- Modify: `backend/app/plugins/contracts.py`
- Modify: `backend/app/plugins/manager.py`
- Modify: `backend/app/plugins/router.py`
- Modify: `plugins/plugins.yaml`

- [ ] **Step 1: 写 exporter 输出测试**

```python
def test_meeting_exporter_returns_bounded_markdown(ai_plugin_client, meeting_id):
    response = ai_plugin_client.post(
        f"/api/meetings/{meeting_id}/plugin-exports/meeting-export.markdown"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Current topic" not in response.text
```

测试还要断言 exporter 不能读取超出 bounded context 的项目或用户数据。

- [ ] **Step 2: 定义 Exporter 协议**

```python
@dataclass(frozen=True)
class PluginExport:
    media_type: str
    filename: str
    content: bytes

ExporterHandler = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Awaitable[PluginExport]]
```

Exporter 只能接收 Core 构造的 context，不接收 SQLAlchemy Session 或数据目录路径。

- [ ] **Step 3: 注册并校验 exporter**

v2 plugin registry 新增 `register_exporter()`；manager 校验 manifest capability 中声明的 exporter id；未知 id、空文件名、超过 8MB 的结果返回 `plugin_output_invalid`。

- [ ] **Step 4: 实现 Markdown/JSON Meeting Export**

插件只读取会议 package context，输出稳定标题、议程、成果和快照元数据；不自动写入会议、不修改附件、不调用外部网络。

- [ ] **Step 5: 运行 exporter 与插件兼容测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/plugins/test_exporters.py backend/tests/plugins/test_actions.py backend/tests/plugins/test_config.py`

Expected: PASS；AI Work Assistant v1 actions 继续加载。

- [ ] **Step 6: Commit first exporter**

```bash
git add backend/app/plugins/exporters.py backend/app/plugins/contracts.py backend/app/plugins/manager.py backend/app/plugins/router.py backend/tests/plugins/test_exporters.py plugins/meeting-export plugins/plugins.yaml
git commit -m "feat: add meeting export plugin contract"
```

### Task 5: 增加固定前端插件插槽与错误隔离

**Files:**
- Test: `frontend/src/tests/plugin-slots.test.ts`
- Create: `frontend/src/components/PluginSlot.vue`
- Modify: `frontend/src/plugins/contracts.ts`
- Modify: `frontend/src/plugins/registry.ts`
- Modify: `frontend/src/plugins/runtime.ts`
- Modify: `frontend/src/views/HomeView.vue`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/tests/app-shell.test.ts`

- [ ] **Step 1: 写 slot registry 红测试**

```ts
it('registers only fixed slots and isolates a broken plugin component', async () => {
  registerPluginSlot('home.secondary-card', BrokenCard)
  expect(slotsFor('home.secondary-card')).toHaveLength(1)
  expect(() => registerPluginSlot('arbitrary-route', BrokenCard)).toThrow('unsupported_plugin_slot')
})
```

- [ ] **Step 2: 扩展前端注册 API**

新增 `registerPluginSlot(slot, component)`；允许集合固定为 `home.secondary-card`、`project.overview.panel`、`meeting.toolbar.action`、`meeting.summary.panel`。继续保留 `registerEditorAssistant` 和 `registerTaskExtension`。

- [ ] **Step 3: 实现 PluginSlot 错误边界**

`PluginSlot.vue` 使用 `onErrorCaptured` 将错误写入局部 notice 并隐藏当前 component；不能向上抛出导致页面卸载。slot 容器输出 `role="region"` 和可读标题。

- [ ] **Step 4: 接入首页和会议工作台**

在 HomeView 的 AI 简报下方挂 `home.secondary-card`；在会议 header actions 和 summary 区域挂 `meeting.toolbar.action`/`meeting.summary.panel`。插件为空时不渲染空框。

- [ ] **Step 5: 运行前端插件测试**

Run: `npm --prefix frontend test -- --run src/tests/plugin-slots.test.ts src/tests/app-shell.test.ts src/tests/admin-plugins.test.ts`

Expected: PASS；模块加载失败只产生局部 notice，核心登录和工作台仍可渲染。

- [ ] **Step 6: Commit fixed plugin slots**

```bash
git add frontend/src/components/PluginSlot.vue frontend/src/plugins frontend/src/views/HomeView.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/plugin-slots.test.ts frontend/src/tests/app-shell.test.ts
git commit -m "feat: add isolated plugin UI slots"
```

### Task 6: 增加 Webhook Notifier 与管理诊断

**Files:**
- Test: `backend/tests/plugins/test_webhook_notifier.py`
- Create: `plugins/webhook-notifier/plugin.yaml`
- Create: `plugins/webhook-notifier/backend.py`
- Modify: `frontend/src/views/AdminPluginsView.vue`
- Modify: `frontend/src/tests/admin-plugins.test.ts`
- Modify: `backend/app/plugins/router.py`
- Modify: `backend/app/plugins/README.md`

- [ ] **Step 1: 写 Webhook 测试**

使用 `httpx.MockTransport` 验证：事件 payload 不含 secret、请求带 HMAC signature、2xx 标记成功、5xx 触发 retry、401 返回可读诊断。

- [ ] **Step 2: 实现最小 manifest 和 handler**

配置字段只有 `endpoint_url`、`signing_secret` 和 `timeout_seconds`；secret 通过现有加密配置读取，不出现在日志、管理响应或事件 payload。

- [ ] **Step 3: 扩展管理响应**

`GET /api/admin/plugins` 增加 capabilities、api compatibility、pending event count、failed event count 和 `reload_required`；不返回明文配置。

- [ ] **Step 4: 更新 AdminPluginsView**

显示能力清单、版本兼容状态、最近失败类型和“修改后需要重启”提示；保存/启用流程保留现有管理员权限。

- [ ] **Step 5: 运行插件和管理测试**

Run: `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/plugins/test_webhook_notifier.py backend/tests/plugins/test_config.py backend/tests/plugins/test_event_worker.py`; `npm --prefix frontend test -- --run src/tests/admin-plugins.test.ts`

Expected: PASS；secret redaction、retry、管理员权限和错误 envelope 均保持。

- [ ] **Step 6: Commit Webhook and diagnostics**

```bash
git add plugins/webhook-notifier backend/app/plugins/router.py frontend/src/views/AdminPluginsView.vue frontend/src/tests/admin-plugins.test.ts backend/tests/plugins/test_webhook_notifier.py backend/app/plugins/README.md
git commit -m "feat: add webhook plugin diagnostics"
```

### Task 7: 完成插件文档、迁移和全套验证

**Files:**
- Modify: `backend/app/plugins/README.md`
- Modify: `docs/development.md`

- [ ] **Step 1: 更新插件契约文档**

写清 v1/v2 兼容、capability manifest、bounded context、outbox retry、固定 UI slots、只读挂载和重启要求；明确 capability 不是 sandbox。

- [ ] **Step 2: 检查迁移资源和链接**

Run: `git diff --check`; `PYTHONPATH=backend:. .venv/bin/python -m pytest -q backend/tests/migrations/test_fresh_baseline.py backend/tests/migrations/test_startup_migrations.py backend/tests/migrations/test_wheel_resources.py`

Expected: `0008_plugin_events.py` 被 wheel 包含，fresh 和 upgrade schema 都到 head。

- [ ] **Step 3: 运行完整验证**

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: 后端、前端和生产构建全部通过；插件错误不改变核心 health 响应。

- [ ] **Step 4: Commit docs and verification**

```bash
git add backend/app/plugins/README.md docs/development.md plugins/plugins.yaml
git commit -m "docs: describe MeetFlow plugin platform v2"
git status --short --branch
```
