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

## Docker 服务端启动（推荐）

MeetFlow 镜像公开发布在 `ghcr.io/mcocdaa/meetflow`，服务器拉取和启动时不需要执行 `docker login ghcr.io`。在服务器的空部署目录中，先生成并存入密码管理器一个应用密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

然后将下面的示例值替换为真实值，并从该部署目录执行这一条启动命令：

```bash
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  -e APP_ENV=production \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='替换为至少12位的强密码' \
  -e APP_SECRET_KEY='替换为至少32字符且长期保存的随机密钥' \
  -e ALLOW_REGISTRATION=false \
  -e SECURE_COOKIES=true \
  -e TRUSTED_ORIGINS=https://meetflow.example.com \
  ghcr.io/mcocdaa/meetflow:latest
```

`$PWD/data` 是当前部署目录中的 `./data/`，其中保存 SQLite 数据库和附件；容器内固定映射为 `/app/data`。第一次运行时 Docker 会创建该目录。命令行 `-e` 是默认配置方式，但值会保留在 shell 历史记录中，并可被拥有 Docker 管理权限的人通过容器检查看到；需要集中保存配置时使用下方高级方式。

`APP_SECRET_KEY` 必须与 `./data/` 一起长期保存。直接更换会使现有登录会话失效，并导致已经加密保存的插件密钥无法解密。首次启动会创建 `ADMIN_USERNAME` 指定的管理员；后续启动不会用新的环境变量密码覆盖该账号。

### HTTPS 反向代理

生产容器默认只绑定宿主机 `127.0.0.1:8000`，必须由 Caddy 或 Nginx 终止 TLS。生产校验会拒绝 HTTP 可信来源和关闭的安全 Cookie。最小 Caddy 配置：

```caddy
meetflow.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

如果反向代理限制请求体大小，其限制必须不低于 `MAX_UPLOAD_BYTES`。默认单个附件上限为 20 MiB。只有受信任的局域网或开发环境才应把端口公开绑定到 `0.0.0.0` 并改用 HTTP 配置。

### 高级配置：使用 `.env`

默认启动不依赖 env 文件。需要集中保存更多配置、或不希望把值写入启动命令时，先从本仓库将已有模板复制到部署目录：

```bash
cp .env.example .env
```

将 `.env` 改为生产设置，包括 `APP_ENV=production`、强管理员密码、持久应用密钥、`SECURE_COOKIES=true` 和 HTTPS `TRUSTED_ORIGINS`，然后把上方的每个 `-e` 选项替换为：

```bash
--env-file ./.env
```

例如，高级启动命令的其他 Docker 参数与默认命令相同：

```bash
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  --env-file ./.env \
  ghcr.io/mcocdaa/meetflow:latest
```

不要提交 `.env`、`data/`、备份或任何 GHCR 凭据。

### 镜像标签、更新和回滚

推送经过验证的 `v*` Git 标签后，稳定版例如 `v1.4.2` 会发布：

```text
ghcr.io/mcocdaa/meetflow:v1.4.2
ghcr.io/mcocdaa/meetflow:1.4.2
ghcr.io/mcocdaa/meetflow:1.4
ghcr.io/mcocdaa/meetflow:latest
ghcr.io/mcocdaa/meetflow:sha-<short-commit>
```

`v1.4.2-rc.1` 只发布精确版本和 SHA 标签，不会移动 `latest` 或 `1.4`。更新前先备份，再拉取镜像；替换容器时重复同一条启动命令，保留同一 `./data/` 目录和同一个 `APP_SECRET_KEY`：

```bash
docker pull ghcr.io/mcocdaa/meetflow:latest
docker stop meetflow
docker rm meetflow
```

回滚时先拉取指定的 `vX.Y.Z` 标签，然后用完全相同的配置重新执行启动命令，只把镜像标签替换为该版本。不要以 `latest` 作为回滚目标。

检查服务：

```bash
docker ps --filter name=meetflow
curl http://127.0.0.1:8000/api/health
```

### 从源码使用 Docker Compose

从源码检出运行、需要修改 `MEETFLOW_PORT` 或 `MEETFLOW_BIND` 时，仍可使用 Compose：

```bash
cp .env.example .env
./scripts/start.sh docker-detached
docker compose ps
```

停止该 Compose 服务：

```bash
docker compose down
```

## 账号管理

首次启动会从 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 幂等创建管理员，但不会在后续启动覆盖已经存在的管理员密码。

- `ALLOW_REGISTRATION=true`：用户可以申请账号，必须经管理员批准后才能登录。
- `ALLOW_REGISTRATION=false`：关闭自助申请，由管理员直接创建固定体验账号。

管理员可以批准、拒绝或禁用账号，也可以重置成员密码。

## 备份与恢复

备份脚本使用 SQLite 在线备份 API，因此不会产生只复制主数据库文件而漏掉 WAL 的问题。对上面的直接部署方式，在运行中的应用容器内执行备份；结果会写入宿主机当前部署目录的 `./data/backups/`：

```bash
docker exec meetflow python /app/scripts/backup.py \
  --database /app/data/meetflow.db \
  --uploads /app/data/uploads \
  --output /app/data/backups
```

为了保证数据库与附件处于同一个业务时点，应选择无人使用的时段，或先在反向代理处临时阻止用户访问。备份期间不要上传、删除附件或编辑会议。备份完成后即可恢复反向代理访问。从源码以 Compose 部署时可使用 `./scripts/backup-container.sh`；不使用 Docker 的本地部署可运行 `python scripts/backup.py`。

直接部署的备份写入 `data/backups/<UTC时间>/`，包含：

```text
meetflow.db
uploads/
manifest.json
```

恢复前先保留当前数据，然后从指定备份恢复：

```bash
docker stop meetflow
mv data data.before-restore
mkdir -p data
cp data.before-restore/backups/20260717T180000Z/meetflow.db data/meetflow.db
cp -a data.before-restore/backups/20260717T180000Z/uploads data/uploads
docker start meetflow
```

恢复后应登录并检查会议、行动项和至少一个附件。`backups/` 和 `data/` 都已加入 `.gitignore`。

备份目录不包含 `.env`。必须把生产环境配置单独保存在受控的密码管理器或加密离线备份中，尤其是原始 `APP_SECRET_KEY`。灾难恢复时应先恢复同一个 `APP_SECRET_KEY` 再启动应用，否则现有会话会失效，数据库中的插件 API Key 也无法解密。不要把 `.env` 放入普通共享备份或提交到 Git。

## 插件

插件是由服务器管理员安装的可信 Python 代码，网页只能配置、启用或停用已发现的插件，不能上传执行代码。

直接 Docker 部署需要在启动命令中额外加入只读挂载 `-v "$PWD/plugins:/app/plugins:ro"`，然后：

1. 将插件目录放入当前部署目录的 `./plugins/`。
2. 在 `plugins/plugins.yaml` 注册插件路径。
3. 在管理员插件页面填写配置和 API Key，并启用插件。
4. 重启服务：`docker restart meetflow`。

插件代码仅在启动时导入。该挂载会覆盖镜像内的整个 `/app/plugins` 目录，因此必须在宿主机提供完整的 `plugins.yaml` 与所需插件代码；插件目录以只读方式挂载，插件失败不会自动写入会议内容。从源码以 Compose 部署时对应使用 `docker compose restart meetflow`。更完整的插件边界见 `backend/app/plugins/README.md`。

## GitHub Actions

- `.github/workflows/ci.yml`：在主分支推送和 Pull Request 中运行后端测试、前端测试/构建，并实际以受限权限启动新构建的镜像后检查健康接口和持久化目录。
- `.github/workflows/release.yml`：推送通过 SemVer 校验的 `v*` 标签时，测试后发布公开的 `ghcr.io/mcocdaa/meetflow` 多架构镜像清单（`linux/amd64`、`linux/arm64`），附带构建来源证明和 SBOM。

创建首个发布版本：

```bash
git tag v0.1.0
git push origin v0.1.0
```

## 当前数据库升级约束

当前 MVP 在启动时通过 SQLAlchemy `create_all()` 幂等创建表，适合首次部署，但不会迁移已经存在的表结构。开始保存长期真实数据后，在修改数据库字段之前应先引入 Alembic 迁移。
