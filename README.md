# MeetFlow

MeetFlow 是一个轻量级多人共享会议档案工具。一次会议可以保存 Markdown 原始记录、关键结论、结构化行动项、后续补充、图片与小文件。管理员负责账号审批和插件配置，所有成员使用同一个共享工作区。

## 技术结构

- FastAPI、SQLAlchemy 和 SQLite 后端
- Vue 3 前端
- SQLite 保存结构化数据，附件保存在同一持久化目录
- 单个生产容器：构建阶段编译 Vue，运行阶段只启动一个 Uvicorn 进程
- 管理员安装的可信 Python 插件，可通过通用会议操作接口追加 AI 等能力

## 本地开发

要求 Python 3.12、Node.js 22 和 npm。

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
npm --prefix frontend ci
./scripts/start.sh local
```

前端地址为 `http://localhost:5173`，Vite 会把 `/api` 转发到 `http://127.0.0.1:8000`。后端健康检查位于 `http://127.0.0.1:8000/api/health`。

运行测试：

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

## Docker 启动

复制环境模板，然后至少替换管理员密码和应用密钥：

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

把输出写入 `.env` 的 `APP_SECRET_KEY`，再启动：

```bash
./scripts/start.sh docker-detached
docker compose ps
curl http://127.0.0.1:8000/api/health
```

默认映射到宿主机 `8000` 端口。可在 `.env` 中修改 `MEETFLOW_PORT`。数据库和附件位于宿主机 `data/`，插件目录以只读方式挂载到容器 `/app/plugins`。

停止服务：

```bash
docker compose down
```

## 生产环境

远程部署必须修改 `.env`：

```env
APP_ENV=production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=替换为至少12位的强密码
APP_SECRET_KEY=替换为独立生成的随机密钥
ALLOW_REGISTRATION=false
SECURE_COOKIES=true
TRUSTED_ORIGINS=https://meetflow.example.com
```

应用生产校验会拒绝开发默认值、文档占位密码、非 HTTPS 可信来源以及关闭的安全 Cookie。

`APP_SECRET_KEY` 必须随 `data/` 一起长期保存。直接更换会使现有登录会话失效，并导致已经加密保存的插件密钥无法解密。当前版本没有自动密钥轮换流程。

### HTTPS 反向代理

推荐让 Caddy 或 Nginx 终止 TLS，只把容器端口绑定到可信网络。最小 Caddy 配置：

```caddy
meetflow.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

如果反向代理限制请求体大小，其限制必须不低于 `MAX_UPLOAD_BYTES`。默认单个附件上限为 20 MiB。

### 使用 GHCR 镜像

发布 `v*` Git 标签后，GitHub Actions 会生成以下镜像标签：

```text
ghcr.io/mcocdaa/meetflow:latest
ghcr.io/mcocdaa/meetflow:0.1.0
ghcr.io/mcocdaa/meetflow:sha-xxxxxxx
```

服务器可设置镜像后更新：

```bash
export MEETFLOW_IMAGE=ghcr.io/mcocdaa/meetflow:latest
docker compose pull meetflow
docker compose up -d --no-build meetflow
```

私有镜像需要先执行 `docker login ghcr.io`。生产更新先备份，再拉取新镜像；不要把 `.env` 或 GHCR 凭据提交到 Git。

## 账号管理

首次启动会从 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 幂等创建管理员，但不会在后续启动覆盖已经存在的管理员密码。

- `ALLOW_REGISTRATION=true`：用户可以申请账号，必须经管理员批准后才能登录。
- `ALLOW_REGISTRATION=false`：关闭自助申请，由管理员直接创建固定体验账号。

管理员可以批准、拒绝或禁用账号，也可以重置成员密码。

## 备份与恢复

备份脚本使用 SQLite 在线备份 API，因此不会产生只复制主数据库文件而漏掉 WAL 的问题。为了保证数据库与附件处于同一个业务时点，推荐在无人写入时执行，最稳妥的方式是短暂停止容器：

```bash
docker compose stop meetflow
python scripts/backup.py
docker compose start meetflow
```

备份默认写入 `backups/<UTC时间>/`，包含：

```text
meetflow.db
uploads/
manifest.json
```

恢复前先保留当前数据，然后从指定备份恢复：

```bash
docker compose down
mv data data.before-restore
mkdir -p data
cp backups/20260717T180000Z/meetflow.db data/meetflow.db
cp -a backups/20260717T180000Z/uploads data/uploads
docker compose up -d
```

恢复后应登录并检查会议、行动项和至少一个附件。`backups/` 和 `data/` 都已加入 `.gitignore`。

## 插件

插件是由服务器管理员安装的可信 Python 代码，网页只能配置、启用或停用已发现的插件，不能上传执行代码。

1. 将插件目录放入宿主机 `plugins/`。
2. 在 `plugins/plugins.yaml` 注册插件路径。
3. 在管理员插件页面填写配置和 API Key，并启用插件。
4. 重启服务：`docker compose restart meetflow`。

插件代码仅在启动时导入。插件目录以只读方式挂载；插件失败不会自动写入会议内容。更完整的插件边界见 `backend/app/plugins/README.md`。

## GitHub Actions

- `.github/workflows/ci.yml`：在主分支推送和 Pull Request 中运行后端测试、前端测试/构建以及完整容器构建。
- `.github/workflows/release.yml`：推送 `v*` 标签时构建并发布 `ghcr.io/mcocdaa/meetflow`。

创建首个发布版本：

```bash
git tag v0.1.0
git push origin v0.1.0
```

## 当前数据库升级约束

当前 MVP 在启动时通过 SQLAlchemy `create_all()` 幂等创建表，适合首次部署，但不会迁移已经存在的表结构。开始保存长期真实数据后，在修改数据库字段之前应先引入 Alembic 迁移。
