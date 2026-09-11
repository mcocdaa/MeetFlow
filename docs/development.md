# MeetFlow 开发指南

本文面向修改 MeetFlow 源码的开发者和 agent。部署或维护服务器请阅读[运维指南](operations.md)，发布镜像请阅读[发布指南](release.md)。

## 架构概览

- 后端是 Python 3.12 上的 FastAPI 和 SQLAlchemy 服务；路由、领域服务与数据模型都位于 `backend/app/`。
- 前端是 Vue 3、TypeScript 与 Vite，源码位于 `frontend/src/`；生产构建由同一个 FastAPI 服务提供。
- SQLite 保存结构化数据，附件和备份保存在数据目录。容器运行时的持久化目录是 `/app/data`，部署时对应宿主机的 `./data/`。
- 生产镜像只有一个应用容器。Vue 资源在构建阶段生成，运行阶段启动 Uvicorn 和内置的插件任务 worker。
- 会议系列的固定周期实例由应用进程内的低频 worker 创建；读取系列、会议列表和开始固定实例也会补算，因而不依赖外部 Cron。
- 生命周期转换（`start`、`finish`、`cancel`、`reopen`）统一由 `MeetingService` 在单会话事务中提交：简单转换走表驱动的 `_transition`，`start`/`finish` 走 `_run_meeting_command`，失败时回滚并按 `expected_version` 报告 409，共享的乐观锁诊断位于 `domain/versioning.py::resolve_stale`；`LifecyclePolicy` 负责纯状态迁移判断和会议可变状态白名单（`MUTABLE_MEETING_STATUSES`，保留 `ready` 以兼容旧数据）。会议列表由 `meetings/queries.py::query_meetings` 纯函数提供唯一的查询与序列化实现（项目内列表与工作区全局 `/api/meetings` 共用），`meetings/projectors.py` 承担快照、附件与引用投影，`outcomes/projectors.py` 承担成果序列化；读取路径不再反向依赖 service。
- 外部插件目录固定为 `/app/plugins`。生产部署可将宿主机目录以只读方式挂载到这里；插件代码仅应来自可信的服务器管理员。

## 本地开发

需要 Python 3.12、Node.js 22 和 npm。首次准备环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
npm --prefix frontend ci
./scripts/start.sh local
```

该脚本会在 `http://127.0.0.1:8000` 启动带自动重载的后端，并在 `http://localhost:5173` 启动 Vite；Vite 会将 `/api` 代理到后端。健康检查是 `http://127.0.0.1:8000/api/health`。

本地开发默认读取项目根目录的配置和数据目录。需要修改配置时，以[仓库根目录 `.env.example`](../.env.example)为参考；不要把真实密码、密钥或本地 `.env` 提交到 Git。

## 测试与构建

后端测试、前端测试和生产构建分别运行：

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

也可以从 `frontend/` 目录运行 `npm test` 和 `npm run build`。不要在仓库根目录直接运行 npm 命令，因为根目录没有前端 `package.json`。

需要对运行中的实例做端到端 API 冒烟时，运行 `scripts/smoke_api.py`。它会写入真实数据，只应指向一次性或专用测试实例：

```bash
.venv/bin/python scripts/smoke_api.py --base-url http://127.0.0.1:8000 --admin-password "$ADMIN_PASSWORD"
```

改动发布或容器相关文件时，还应阅读[发布指南](release.md)中的 CI 与镜像验证说明。

## 从源码使用 Docker Compose

Compose 是从源码构建、调试或修改 `MEETFLOW_PORT`、`MEETFLOW_BIND` 时使用的高级路径，不是普通服务器使用公开镜像的默认方式。先准备本地配置，再构建并后台启动：

```bash
cp .env.example .env
./scripts/start.sh docker-detached
docker compose ps
```

停止该 Compose 服务：

```bash
docker compose down
```

`compose.yaml` 将 `./data` 映射为 `/app/data`，并将 `./plugins` 以只读方式映射为 `/app/plugins`。它会读取 `.env`，因此不要把 `.env`、`data/` 或备份文件加入提交。

## 数据库迁移

运行中的非测试环境会在启动时执行 Alembic 的 `head` 迁移；迁移配置在 `backend/alembic.ini`，版本文件位于 `backend/migrations/versions/`。任何会改变已持久化表结构的改动都必须包含经过审查的 Alembic 迁移，并在真实数据上升级前完成备份。

测试环境使用独立的 schema 创建路径以保持测试隔离。不要把这种测试便利性当作生产数据库升级策略。

## 多用户工作区访问

项目是工作区访问边界。完整的角色和 API 契约见[协同加固设计](superpowers/specs/2026-08-01-collaboration-hardening-design.md)：`admin` 与项目负责人（lead）可管理工作区，`member` 可贡献会议、议题、产出、附件和项目进展，`stakeholder` 只能查看。非项目成员若被邀请为某场会议参与人，仅能查看该场会议及其材料，并可在该会议评论；这不授予项目级访问或写入权。

项目和会议详情的 `capabilities` 由服务端计算，前端只能据此渲染操作入口，不能从登录角色或成员列表自行推导权限。附件响应另有逐项 `can_delete`，它同时反映贡献能力及作者/管理员约束。个人 attention 与 inbox 共用同一工作区通知范围：权限撤销后，既有私有项目通知不得出现在列表、增量、未读数或已读命令中。编辑项目进展必须提交 `expected_version`；过期写入返回 `409 version_conflict`，客户端应刷新后重试。该版本字段和 `project_members.user_id` 索引由 Alembic 迁移 `0009` 交付，不能用测试建表逻辑替代生产迁移。

## 会议系列与完成快照

`MeetingSeries` 的周期规则使用 IANA 时区和结构化频率字段，而不是展示用文字。`Meeting.occurrence_kind` 区分固定周期与临时实例，`series_slot_at` 唯一标识固定周期槽位；临时实例不得占用该槽位。修改这些字段或 `AgendaItem.actual_duration_seconds`、自动产出来源字段时，必须提供 Alembic 迁移。

开始固定周期实例会收尾同一系列上一个未结束的固定实例。结束会议会在同一事务内跳过未结束议题、保存会议及议题实际时长并创建快照。会后 UI 必须读取快照中的纪要、议题记录、状态、时长和产出，而不是读取可重新打开后改变的当前记录；全部 API 响应都会把 SQLite 读回的无偏移时间规范为带 `Z` 的 UTC，前端统一经 `src/utils/time.ts` 的解析与本地时区格式化，不能按浏览器本地时区直接解释无后缀时间。

工作台的会议级草稿集中在 `useMeetingWorkspace`：它维护服务器版本、dirty 状态、保存状态和 409 冲突，并在生命周期命令前 flush 会议纪要、目的和原始笔记。当前页面仍保留显式保存按钮以兼容既有用户流程；离开有未保存草稿的页面会触发路由和浏览器 unload 保护。议题编辑继续由 `AgendaWorkbench` 显式保存，避免与会议级 PUT 并发写同一条记录。
