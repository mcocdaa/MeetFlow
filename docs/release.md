# MeetFlow 发布指南

本文面向维护 GitHub 仓库、发布公共镜像或修改 CI 的开发者和 agent。服务器更新和回滚请阅读[运维指南](operations.md)，普通使用者的启动方式在根目录[README](../README.md)。

## 持续集成

`.github/workflows/ci.yml` 在推送到 `main` 和所有 Pull Request 上运行。它包含：

- 后端完整测试与 Python 字节码编译检查；
- 前端依赖安装、测试与生产构建；
- 依赖前两项成功的容器构建，并以受限权限实际启动新镜像。

容器 job 使用 `scripts/ci-container-smoke.sh` 检查镜像默认路径、只读启动、健康接口和宿主机绑定的 SQLite 持久化。它不会推送镜像。

`ci.yml` 不支持手动派发。需要测试未发布提交时，推送 `main` 或创建 Pull Request；GitHub Actions 页面也可以重新运行已经存在的 CI 记录。

## 发布镜像

`.github/workflows/release.yml` 只在 `v*` tag 推送时启动。工作流首先校验 tag 是带 `v` 前缀的 SemVer（可带预发布后缀），然后运行后端测试、前端测试和前端生产构建。

通过测试后，工作流使用 QEMU 和 Buildx 将公开镜像发布到 `ghcr.io/mcocdaa/meetflow`，目标是 `linux/amd64` 和 `linux/arm64`。发布过程附带构建来源证明（provenance）与 SBOM。

稳定标签例如 `v1.4.2` 会创建：

```text
ghcr.io/mcocdaa/meetflow:v1.4.2
ghcr.io/mcocdaa/meetflow:1.4.2
ghcr.io/mcocdaa/meetflow:1.4
ghcr.io/mcocdaa/meetflow:latest
ghcr.io/mcocdaa/meetflow:sha-<short-commit>
```

预发布标签如 `v1.4.2-rc.1` 不会推进 `latest` 或 `1.4`，但仍会发布该 tag 和 SHA 标签。镜像为公开包，服务器拉取不需要 `docker login ghcr.io`。

创建发布 tag：

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

不要把无效 tag、真实密钥或 GHCR 凭据写入仓库。发布工作流使用 GitHub 提供的 `GITHUB_TOKEN` 进行 GHCR 登录。

## 发布前检查清单

1. 确认 `main` 已包含要发布的提交，并且该提交对应的 CI 成功。
2. 确认版本号符合带 `v` 前缀的 SemVer，稳定版本不带预发布后缀。
3. 确认用户 README 和相关 `docs/` 页面反映了这次可见的部署、配置或发布行为。
4. 推送 tag 后，在 GitHub Actions 中确认 `Publish container` job 成功。
5. 在目标架构的服务器上拉取精确 `vX.Y.Z` 镜像，并按[运维指南](operations.md)保留同一个 `./data/` 与 `APP_SECRET_KEY` 启动和检查健康接口。
