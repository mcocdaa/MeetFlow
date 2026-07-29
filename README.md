# MeetFlow

MeetFlow 是一个轻量级多人共享会议档案工具。一次会议可以保存 Markdown 原始记录、关键结论、结构化行动项、后续补充、图片与小文件。所有成员使用同一个共享工作区；管理员负责账号审批和插件配置。

## 快速启动

MeetFlow 的公开镜像是 `ghcr.io/mcocdaa/meetflow`。服务器拉取和启动时不需要执行 `docker login ghcr.io`。

在服务器的空部署目录中，先生成一个应用密钥并保存到密码管理器：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

将下列示例值替换为真实值，然后从这个部署目录执行一条命令：

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

`$PWD/data` 是当前部署目录中的 `./data/`，其中保存数据库、附件和备份；容器内固定映射为 `/app/data`。第一次运行时 Docker 会创建该目录。

`APP_SECRET_KEY` 必须与 `./data/` 一起长期保存。直接更换会使现有登录会话失效，也会导致已经加密保存的插件密钥无法解密。命令行 `-e` 是默认配置方式；需要集中保存配置时，请阅读[运维指南](docs/operations.md)中的高级 `.env` 方式。

生产容器默认只监听宿主机 `127.0.0.1:8000`。在对外提供服务前，请按[运维指南](docs/operations.md)配置 HTTPS 反向代理、可信来源和上传限制。

## 首次登录与账号

首次启动会使用 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 创建管理员。后续启动不会用新的环境变量密码覆盖已有账号。

- `ALLOW_REGISTRATION=true`：用户可以申请账号，管理员批准后才能登录。
- `ALLOW_REGISTRATION=false`：关闭自助申请，由管理员创建固定体验账号。

管理员可以批准、拒绝或禁用账号，也可以重置成员密码。登录后，所有成员都在同一个共享工作区中维护会议、结论、行动项和附件。

## 检查服务

```bash
docker ps --filter name=meetflow
curl http://127.0.0.1:8000/api/health
```

健康接口返回 `{"status":"ok"}` 后，再通过配置好的 HTTPS 域名访问 MeetFlow。

## 进一步文档

- [运维指南](docs/operations.md)：HTTPS、高级配置、更新回滚、备份恢复与生产插件挂载。
- [发布指南](docs/release.md)：GitHub Actions、GHCR 镜像和版本标签，供仓库维护者使用。
- [开发与维护文档](docs/README.md)：架构、本地开发、测试与 agent 工作入口。
