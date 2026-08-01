# 插件失败事件安全重试设计

日期：2026-07-31

状态：已确认，待实现

## 目标

为管理员提供一个安全的失败事件恢复入口。当插件事件已经达到自动重试上限并进入 `failed` 状态后，管理员可以在修复插件配置或外部依赖后重新投递该事件。重试继续使用现有单进程 Worker，不把插件执行放进管理员 HTTP 请求。

## 范围

本次只处理已经存在的 `plugin_events` 记录：

- 后端提供管理员专用的重试命令。
- 前端插件管理页展示每条失败事件的重试按钮和进行中状态。
- 重试复用原始 `event_id` 和 payload，保持订阅方幂等语义。
- 增加领域函数和前端/后端测试。

本次不做：新建事件、手动执行插件、修改事件 payload、批量重试、权限模型扩展、数据库迁移、CLI 或 Docker 部署变更。

## 方案

### 后端命令

在插件事件服务中增加 `retry_plugin_event(session, event_id)`：

1. 查询事件；不存在时抛出 `KeyError`。
2. 只有 `status == failed` 允许重试；其他状态抛出 `ValueError`。
3. 保留 `event_id`、`event_type`、目标和 payload，只重置投递状态：
   - `status = queued`
   - `attempts = 0`
   - `next_attempt_at = utcnow()`
   - `claimed_at = None`
   - `finished_at = None`
   - `last_error = None`
4. 在同一 session 中提交并刷新记录，返回脱敏后的事件对象。

新增 `POST /api/admin/plugins/events/{event_id}/retry`，使用现有 `admin_user` 依赖。路由把 `KeyError` 映射为 404，把非 `failed` 状态映射为 409。成功响应沿用事件诊断序列化格式，不返回 `payload_json`。

### 前端交互

插件管理页的失败事件区域为每个事件增加“重试”按钮：

- 单个事件只能同时发起一次重试。
- 请求期间按钮显示“重试中…”并禁用。
- 成功后重新加载插件与失败事件列表；事件从失败列表消失时给出短暂成功状态。
- 请求失败时保留事件列表，并在页面顶部显示后端错误。

### 数据流

```text
AdminPluginsView
  │ POST /api/admin/plugins/events/{id}/retry
  ▼
retry_plugin_event
  │ status failed → queued, attempts 0, next_attempt_at now
  ▼
PluginJobWorker.run_event_once
  │ claim queued event
  ▼
PluginManager.invoke_event
  ├─ success → succeeded
  └─ failure → bounded retry / failed
```

重试不会直接调用插件，因此不会绕过现有超时、错误隔离、敏感信息脱敏和 Worker 领取逻辑。

## 并发与错误处理

- 事件状态检查和字段重置在同一个数据库 session 中完成。
- 重复点击在前端被禁用；后端仍以状态检查作为最终保护。
- 已经是 `queued`、`processing` 或 `succeeded` 的事件不能被管理员重复重置。
- 重试接口不接受 payload、attempts 或状态字段，避免管理员接口成为任意事件注入入口。

## 验证

后端测试覆盖：

- failed 事件能够重置为 queued，并清理运行时字段。
- 不存在事件返回 404。
- 非 failed 事件返回 409。
- 原始 event_id 和 payload 保持不变。

前端测试覆盖：

- 失败事件显示重试按钮。
- 点击后调用正确 endpoint 并显示进行中状态。
- 成功刷新后移除已恢复事件。
- 请求失败时保留失败事件并显示错误。

## 兼容性与回滚

只增加管理员路由和 UI 行为，不改变已有事件表结构、Worker 协议或普通成员接口。回滚代码即可恢复现有“只读失败诊断”行为，不需要数据库回滚。
