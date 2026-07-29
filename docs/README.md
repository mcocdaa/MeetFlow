# MeetFlow 开发与维护文档

本文档集面向开发者和 agent。它说明当前实现、部署维护和发布流程；普通使用者请从仓库根目录的[README](../README.md)开始。

## 按任务阅读

| 任务 | 先阅读 |
| --- | --- |
| 修改应用代码、本地调试、测试或数据库迁移 | [development.md](development.md) |
| 部署、备份、恢复、更新回滚或插件挂载 | [operations.md](operations.md) |
| 修改 CI、容器发布或创建版本 tag | [release.md](release.md) |
| 修改插件运行时契约 | [后端插件契约](../backend/app/plugins/README.md) |
| 修改 AI 工作助手插件 | [AI 工作助手说明](../plugins/ai-work-assistant/README.md) |

## 文档归属

- 根目录 `README.md` 是给使用者的入口：介绍产品、提供公开镜像的快速启动和基础账号使用说明。
- 本目录的页面是给开发者和 agent 的当前操作手册：实现、维护和发布行为变化时应更新对应页面。
- 根目录 `AGENTS.md` 是给 agent 的仓库规则和阅读入口；它链接到本目录，但不复制完整的运维或开发说明。
- `docs/superpowers/specs/` 和 `docs/superpowers/plans/` 是带日期的设计与实施记录。它们用于理解历史决策，不能替代本目录中的当前手册。

## 维护原则

先更新真正受影响的受众文档，再从其他文档链接过去；不要在 README、`docs/` 和 `AGENTS.md` 中复制同一段长流程。用户可直接执行的默认 Docker 命令是例外：它应保留在根 README，并由运维文档引用。
