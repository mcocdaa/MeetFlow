# MeetFlow 开发指南

本文面向修改 MeetFlow 源码的开发者和 agent。部署或维护服务器请阅读[运维指南](operations.md)，发布镜像请阅读[发布指南](release.md)。

## 架构概览

- 后端是 Python 3.12 上的 FastAPI 和 SQLAlchemy 服务；路由、领域服务与数据模型都位于 `backend/app/`。
- 前端是 Vue 3、TypeScript 与 Vite，源码位于 `frontend/src/`；生产构建由同一个 FastAPI 服务提供。
- SQLite 保存结构化数据，附件和备份保存在数据目录。容器运行时的持久化目录是 `/app/data`，部署时对应宿主机的 `./data/`。
- 生产镜像只有一个应用容器。Vue 资源在构建阶段生成，运行阶段启动 Uvicorn 和内置的插件任务 worker。
- 会议系列的固定周期实例由应用进程内的低频 worker 创建；读取系列、会议列表和开始固定实例也会补算，因而不依赖外部 Cron。
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

## 会议系列与完成快照

`MeetingSeries` 的周期规则使用 IANA 时区和结构化频率字段，而不是展示用文字。`Meeting.occurrence_kind` 区分固定周期与临时实例，`series_slot_at` 唯一标识固定周期槽位；临时实例不得占用该槽位。修改这些字段或 `AgendaItem.actual_duration_seconds`、自动产出来源字段时，必须提供 Alembic 迁移。

开始固定周期实例会收尾同一系列上一个未结束的固定实例。结束会议会在同一事务内跳过未结束议题、保存会议及议题实际时长并创建快照。会后 UI 必须读取快照中的纪要、议题记录、状态、时长和产出，而不是读取可重新打开后改变的当前记录；会议 API 会将 SQLite 读回的无偏移时间规范为带 `Z` 的 UTC，前端仍需将历史快照中的无后缀时间按 UTC 兼容解析，不能按浏览器本地时区解释。
