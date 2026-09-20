# MeetFlow

> 轻量级多人共享会议档案、结构化行动项追踪与团队知识沉淀系统。

[![Family: *Flow](https://img.shields.io/badge/family-*Flow-8A2BE2.svg)](https://github.com/mcocdaa)
[![CI](https://github.com/mcocdaa/MeetFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/mcocdaa/MeetFlow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/mcocdaa/MeetFlow?display_name=tag&sort=semver)](https://github.com/mcocdaa/MeetFlow/releases)
[![Container image](https://img.shields.io/badge/image-ghcr.io%2Fmcocdaa%2Fmeetflow-0b6a58)](https://github.com/mcocdaa/MeetFlow/pkgs/container/meetflow)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](compose.yaml)

MeetFlow 是一个轻量级多人共享会议档案工具。一次会议可以保存 Markdown 原始记录、关键结论、结构化行动项、后续补充、图片与小文件。所有成员使用同一个共享工作区；管理员负责账号审批和插件配置。

## 快速启动

MeetFlow 的公开镜像是 `ghcr.io/mcocdaa/meetflow`，支持 `linux/amd64` 和 `linux/arm64`，服务器拉取不需要 `docker login ghcr.io`。

在服务器的空部署目录中复制配置模板并编辑：

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # 生成 APP_SECRET_KEY
vim .env
```

至少替换 `.env` 中的三项：`ADMIN_PASSWORD`（至少 12 位的强密码）、`APP_SECRET_KEY`（上一步生成并长期保存的随机值）和 `TRUSTED_ORIGINS`（你的 HTTPS 域名）。`.env` 包含密钥，不要提交到 Git。

然后从这个部署目录启动：

```bash
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  --env-file .env \
  ghcr.io/mcocdaa/meetflow:latest
```

`$PWD/data` 是当前部署目录中的 `./data/`，保存数据库、附件和备份；容器内固定映射为 `/app/data`，第一次运行时 Docker 会创建该目录。`APP_SECRET_KEY` 必须与 `./data/` 一起长期保存：更换它会使现有登录会话失效，也会导致已经加密保存的插件密钥无法解密。

生产容器默认只监听宿主机 `127.0.0.1:8000`。对外提供服务前，请按[运维指南](docs/operations.md)配置 HTTPS 反向代理；`APP_ENV=production` 会拒绝不安全的 Cookie 或 HTTP 可信来源配置。更新回滚、备份恢复和生产插件挂载也见运维指南。

## 首次登录与账号

首次启动会使用 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 创建管理员。后续启动不会用新的环境变量密码覆盖已有账号。

- `ALLOW_REGISTRATION=true`：用户可以申请账号，管理员批准后才能登录。
- `ALLOW_REGISTRATION=false`：关闭自助申请，由管理员创建固定体验账号。

管理员可以批准、拒绝或禁用账号，也可以重置成员密码。登录后，所有成员都在同一个共享工作区中维护会议、结论、行动项和附件。

## 会议系列与纪要

项目可以创建独立的会议系列，并设置每天、每周、每月或每年的本地开始时间、时区和默认时长。每个系列也可以临时添加会议；临时会议仍归属于该系列，但不会替代下一次固定周期会议。固定周期实例到期时会创建为“待开始”；开始新周期实例时，同一系列上一个尚未结束的固定实例会自动结束。

会议操作只有“待开始 → 会议进行中 → 已结束”三个状态。结束会议时，未完成议题会统一记为已跳过；每个议题记录预计时长（新增默认为 5 分钟）及实际耗时。

会议纪要和议题记录均需要显式保存。议题记录中可使用 `@决策:`、`@行动:`、`@开放问题:` 生成随记录同步的产出；在下方手动添加的产出不受记录修改影响。会议结束后，完成档案会只读展示已保存纪要、会议总实际时长、每条议题记录及其耗时、状态和产出。

## 检查服务

```bash
docker ps --filter name=meetflow
curl http://127.0.0.1:8000/api/health
```

健康接口返回 `{"status":"ok"}` 后，再通过配置好的 HTTPS 域名访问 MeetFlow。

## 进一步文档

- [运维指南](docs/operations.md)：HTTPS、临时覆盖配置、更新回滚、备份恢复与生产插件挂载。
- [发布指南](docs/release.md)：GitHub Actions、GHCR 镜像和版本标签，供仓库维护者使用。
- [开发与维护文档](docs/README.md)：架构、本地开发、测试与 agent 工作入口。
