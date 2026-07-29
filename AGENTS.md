# MeetFlow Agent Instructions

本文件面向在此仓库中工作的 agent。使用者文档在根目录 `README.md`；开发与维护文档从[docs/README.md](docs/README.md)开始。

## Read first

1. 先阅读[开发与维护文档](docs/README.md)，再按本次任务选择 `development.md`、`operations.md`、`release.md` 或插件契约。
2. 修改已有行为前，阅读相关的当前实现、测试和最近提交；不要把带日期的设计/计划记录当作唯一事实来源。
3. 工作区存在未提交改动时，先确认目标文件没有与其他改动重叠。只暂存和提交本任务的文件。

## Repository rules

- MeetFlow 是 Vue 3/Vite 前端和 FastAPI/SQLAlchemy 后端组成的单个服务，SQLite、附件和容器内备份依赖持久化数据目录。
- 公开镜像的默认服务器启动方式是 Docker 命令行 `-e` 配置，并使用 `-v "$PWD/data:/app/data"` 持久化数据。`.env` 与 `--env-file` 只用于高级配置。
- 不要提交 `.env`、真实账号密码、`APP_SECRET_KEY`、插件 API Key、`data/`、备份或 GHCR 凭据。
- 对生产数据库字段或结构的变更必须包含 Alembic 迁移；不要用临时建表逻辑替代迁移。
- 外部 `/app/plugins` 挂载必须是受信任代码且只读。插件的网页配置不能被扩展成上传或运行任意代码的机制。
- GitHub `main` push 运行 CI；只有合法的 `v*` tag 才发布公共多架构镜像。修改这些契约前先阅读[发布指南](docs/release.md)。

## Verification

按改动范围运行验证，并在报告中给出实际命令和结果：

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python -m pytest -q backend/tests/test_release_workflow.py
```

改动 Dockerfile、容器启动脚本或发布工作流时，遵循[发布指南](docs/release.md)的容器 smoke 说明。修改 Markdown 时检查本地链接和目标文件的 `git diff --check`；不要将既有无关文档的格式问题混入本次改动。

## Documentation ownership

- 使用者可见的启动、首次使用和基础账号说明放在根 `README.md`。
- 开发、运维、发布和插件维护细节放在相应 `docs/` 页面。
- Agent 的工作边界、必读文档和验证入口只放在本文件。

修改部署、配置、发布自动化、开发工作流或 agent 规则时，必须同步更新对应受众的文档，并用链接代替在三处复制长说明。
