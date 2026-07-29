# MeetFlow 运维指南

本文面向部署或维护 MeetFlow 服务器的开发者和 agent。普通使用者应先阅读仓库根目录的[README](../README.md)，其中提供公开镜像的一条启动命令。

## 生产配置边界

默认部署使用公开镜像 `ghcr.io/mcocdaa/meetflow`，通过 Docker 命令行 `-e` 传入配置，并将当前部署目录的 `./data/` 映射到容器的 `/app/data`：

```text
-v "$PWD/data:/app/data"
```

数据库、上传附件和容器内备份都位于这个数据目录。保留该目录和同一个 `APP_SECRET_KEY` 是更新、回滚与灾难恢复的前提：更换应用密钥会使现有会话失效，也无法解密已经保存的插件密钥。

不要将 `.env`、`data/`、备份、密码或任何 GHCR 凭据提交到 Git。使用命令行 `-e` 时，值会进入 shell 历史并可被具有 Docker 管理权限的人检查；需要集中保管配置时使用下一节的高级方式。

## HTTPS 反向代理

生产容器默认绑定宿主机的 `127.0.0.1:8000`，必须由 Caddy 或 Nginx 终止 TLS。生产环境必须设置 HTTPS `TRUSTED_ORIGINS`，并保持 `SECURE_COOKIES=true`；应用会拒绝 HTTP 可信来源或关闭安全 Cookie 的生产配置。

最小 Caddy 配置：

```caddy
meetflow.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

如果反向代理限制请求体大小，它的限制不得小于 `MAX_UPLOAD_BYTES`。默认的单个附件上限是 20 MiB。只有受信任的局域网或开发环境才应把端口公开绑定到 `0.0.0.0` 并改用 HTTP 配置。

## 高级配置：使用 `.env`

根 README 中的内联 `-e` 启动方式始终是默认路径。需要集中保存更多配置、或不希望把值写入启动命令时，先将模板复制到服务器的部署目录：

```bash
cp .env.example .env
```

将 `.env` 改为生产设置，至少包括 `APP_ENV=production`、强管理员密码、长期保存的 `APP_SECRET_KEY`、`SECURE_COOKIES=true` 和 HTTPS `TRUSTED_ORIGINS`。随后以 `--env-file ./.env` 替换默认启动命令中的每个 `-e` 参数：

```bash
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  --env-file ./.env \
  ghcr.io/mcocdaa/meetflow:latest
```

`.env.example` 的默认值只适合本地开发；生产 `.env` 不是共享配置样例，也不能提交。

## 镜像更新与回滚

发布稳定版本 `v1.4.2` 后可使用的镜像标签包括：

```text
ghcr.io/mcocdaa/meetflow:v1.4.2
ghcr.io/mcocdaa/meetflow:1.4.2
ghcr.io/mcocdaa/meetflow:1.4
ghcr.io/mcocdaa/meetflow:latest
ghcr.io/mcocdaa/meetflow:sha-<short-commit>
```

预发布标签如 `v1.4.2-rc.1` 只发布精确版本和 SHA 相关标签；不会移动 `latest` 或 `1.4`。更新前先完成备份，再拉取目标镜像并替换容器。重新运行根 README 的同一条启动命令时，必须保留同一个 `./data/` 和 `APP_SECRET_KEY`：

```bash
docker pull ghcr.io/mcocdaa/meetflow:latest
docker stop meetflow
docker rm meetflow
```

回滚时拉取指定的 `vX.Y.Z`，然后使用完全相同的配置重新执行启动命令，仅替换镜像标签。不要使用 `latest` 作为回滚目标。替换后检查服务：

```bash
docker ps --filter name=meetflow
curl http://127.0.0.1:8000/api/health
```

## 备份与恢复

备份脚本通过 SQLite 在线备份 API 创建数据库副本，因此不会遗漏 WAL 数据。对于直接 Docker 部署，在运行中的应用容器内执行；结果写入宿主机的 `./data/backups/`：

```bash
docker exec meetflow python /app/scripts/backup.py \
  --database /app/data/meetflow.db \
  --uploads /app/data/uploads \
  --output /app/data/backups
```

为使数据库与附件保持同一业务时点，应在无人使用的时段执行，或先在反向代理处临时阻止访问。备份期间不要上传、删除附件或编辑会议。从源码以 Compose 运行时，使用 `./scripts/backup-container.sh`；不使用 Docker 的本地维护可运行 `python scripts/backup.py`。

备份目录 `data/backups/<UTC时间>/` 包含：

```text
meetflow.db
uploads/
manifest.json
```

恢复前保留当前数据，再从指定备份复制数据库与上传目录：

```bash
docker stop meetflow
mv data data.before-restore
mkdir -p data
cp data.before-restore/backups/20260717T180000Z/meetflow.db data/meetflow.db
cp -a data.before-restore/backups/20260717T180000Z/uploads data/uploads
docker start meetflow
```

恢复后登录并检查会议、行动项和至少一个附件。备份目录不包含 `.env`，因此灾难恢复时先恢复原始 `APP_SECRET_KEY`，再启动应用。

## 生产插件挂载

插件是由服务器管理员安装的可信 Python 代码；网页只能配置、启用或停用已发现的插件，不能上传或安装代码。直接 Docker 部署时，在根 README 的启动命令中额外加入只读挂载：

```text
-v "$PWD/plugins:/app/plugins:ro"
```

然后：

1. 将完整插件目录放入部署目录的 `./plugins/`。
2. 在 `plugins/plugins.yaml` 注册插件路径。
3. 在管理员插件页面填写配置和 API Key，并启用插件。
4. 执行 `docker restart meetflow`。

这个挂载会覆盖镜像内整个 `/app/plugins`，所以宿主机必须提供完整的 `plugins.yaml` 和所需代码。插件只在启动时导入；改变代码、挂载或启用状态后都需要重启。插件运行时边界见[后端插件契约](../backend/app/plugins/README.md)。
