# 多用户协同权限与进展并发控制设计

**日期：** 2026-08-01  
**状态：** 设计已确认，进入实施计划阶段  
**范围：** 项目工作区、会议及其附属资源的服务端访问控制；项目进展的乐观并发控制；相关前端能力提示。

## 1. 问题与目标

MeetFlow 已有登录、项目成员和会议参与人模型，但多数项目关联 API 只要求已登录。当前 `ProjectService.update()`、`MeetingService.update_meeting()`、项目动态、评论、附件以及议题/产出路由没有统一项目成员校验。结果是任意已启用账号可以读取或改变不属于自己的工作区资源。

`Project`、`Meeting`、议题和评论已采用版本号避免并发覆盖；`ProjectUpdate` 没有版本列，两个作者或管理员并发编辑同一条进展时，后提交者会静默覆盖先提交者。

本次交付目标是：

1. 让项目成为真正的工作区访问边界，而非仅用于组织列表。
2. 让项目负责人、成员、干系人和仅会议参与人具有明确且可测试的能力。
3. 将所有项目关联 HTTP 入口收敛到同一访问策略，避免只修复个别 `PUT` 后仍被附件、议题或产出接口绕过。
4. 为项目进展补齐与其他可编辑资源一致的 `expected_version`/`409 version_conflict` 协议。
5. 让前端只展示当前用户实际可执行的写入操作，并在冲突或拒绝时给出可理解的反馈。

本次不引入实时协同协议、WebSocket、在线状态、细粒度字段级 ACL 或新的组织/团队表。

## 2. 已核对的当前实现

- `backend/app/projects/service.py` 仅在 `create_update()` 中检查项目成员；项目读取和 `update()` 未检查成员关系。
- `backend/app/meetings/service.py` 的创建、编辑、生命周期命令和读侧查询只检查账号启用状态或资源存在性。
- `backend/app/agendas/`、`backend/app/outcomes/`、`backend/app/attachments/router.py` 与 `backend/app/collaboration/` 的项目关联入口同样没有工作区访问策略。
- `ProjectMember` 现有角色为 `member` 和 `stakeholder`，`lead_user_id` 独立存储；可直接作为权限依据，不新增角色或表。
- `ProjectUpdate` 没有 `version` 列；`ProjectUpdateWrite` 被创建和编辑共用，编辑请求没有并发前提条件。
- `ProjectDetailView.vue` 与 `ProjectActivityTab.vue` 无能力数据，始终渲染项目编辑、新建资源和进展发布入口。

## 3. 权限模型

### 3.1 身份到能力的映射

| 身份 | 查看项目及项目级资源 | 修改项目资料/成员、删除项目 | 创建或修改会议、系列、议题、产出、附件、进展 | 查看单场受邀会议 | 在受邀会议评论 |
| --- | --- | --- | --- | --- | --- |
| `admin` | 是 | 是 | 是 | 是 | 是 |
| 项目负责人 | 是 | 是 | 是 | 是 | 是 |
| `ProjectMember(role=member)` | 是 | 否 | 是 | 是 | 是 |
| `ProjectMember(role=stakeholder)` | 是 | 否 | 否 | 是 | 否 |
| 非项目成员但为该会议参与人 | 否 | 否 | 否 | 是，仅该会议及其材料/评论 | 是，仅该会议 |
| 其他已启用账号 | 否 | 否 | 否 | 否 | 否 |

所有判断都以当前数据库状态为准：用户被移出项目后立即失去项目级能力；若仍是某场会议参与人，只保留该场会议的只读和评论能力。管理员不受成员关系限制。

### 3.2 可见性规则

- `/api/projects` 仅返回当前用户可查看的项目；管理员返回全部项目。
- 项目详情、动态、项目级会议/系列列表、项目级行动项/决策/问题、项目附件和活动流必须先通过项目查看校验。
- 单场会议详情、快照、议题、该会议的评论和附件允许项目查看者或该场会议参与人访问。
- 列表中过滤不可见记录，而使用已知资源 ID 直接访问不可见资源返回 `403` 和稳定的访问错误代码；不返回业务内容。

### 3.3 写入规则

- 项目负责人和管理员可修改项目资料、成员列表、负责人和删除项目。
- `member` 可创建和修改会议、会议系列、议题、产出、附件、项目进展与会议评论，但不能改项目成员、负责人或删除项目。
- `stakeholder` 只读；仅会议参与人只能创建、查看、编辑自己拥有的会议评论，不能更改会议结构或上传材料。
- 创建项目仍向任何已启用用户开放；服务端始终将创建者加入项目成员，防止 API 调用遗漏 `member_ids` 形成无人可进入的项目。
- 现有“只能编辑自己发布的项目进展/附件/评论，管理员可例外”的作者约束保留，并在能力校验之后执行。

## 4. 后端架构

### 4.1 集中访问策略

新增项目访问策略模块（建议 `backend/app/projects/access.py`），只负责从 `Project`、`ProjectMember`、`MeetingParticipant` 和当前 `User` 推导能力，不处理路由序列化或资源写入。

策略提供以下稳定入口：

- `require_project_view(project_id, actor)`
- `require_project_contribute(project_id, actor)`
- `require_project_manage(project_id, actor)`
- `require_meeting_view(meeting_id, actor)`
- `require_meeting_comment(meeting_id, actor)`
- `project_capabilities(project, actor)` 与 `meeting_capabilities(meeting, actor)`

访问策略统一执行账号启用检查、管理员短路、负责人判断、成员角色判断和会议参与人判断。它返回已加载的资源，避免路由先 `get()`、服务层再查询而产生不同的判定路径。

`ProjectService`、`MeetingService`、`AgendaService`、`OutcomeService`、`CommentService` 和附件路由在其公开服务入口或路由适配层调用该策略。内部调度器和同一事务内的纯领域辅助方法不接受 HTTP actor，不执行访问判断；它们只由已经通过命令边界的服务调用。

`ProjectMember.user_id` 增加索引，以支持按当前用户过滤项目列表和快速成员校验。

### 4.2 API 与序列化契约

项目详情和会议详情加入服务端计算的能力对象，避免前端自行猜测成员关系：

```json
{
  "capabilities": {
    "can_manage": false,
    "can_contribute": true,
    "can_comment": true
  }
}
```

项目能力表示项目级能力；会议能力表示单场会议能力。现有字段和 URL 不改名。拒绝写入保持 `403`，使用领域明确的错误码，例如 `project_view_forbidden`、`project_contribution_forbidden`、`project_management_forbidden` 和 `meeting_comment_forbidden`。客户端继续使用既有 `api()` 错误处理，不将权限判断仅放在 UI。

### 4.3 项目进展的乐观并发

`ProjectUpdate` 新增 `version` 整数列，初始值为 1，并配置 SQLAlchemy 的 `version_id_col`。创建返回 `version: 1`。

创建与编辑请求拆分：

- `ProjectUpdateWrite` 保持创建用字段：`health`、`content_markdown`、`source`。
- 新建 `ProjectUpdateEdit`，在同一字段基础上增加必填 `expected_version >= 1`。

编辑时服务先校验作者/管理员和贡献能力，再校验 `expected_version`，写入后递增版本。并发提交触发 `StaleDataError` 时回滚、读取实际版本，并返回既有格式的 `409 version_conflict`：

```json
{
  "error": {
    "code": "version_conflict",
    "details": {"expected_version": 1, "actual_version": 2}
  }
}
```

新 Alembic 迁移为已有 `project_updates` 行回填 1，再设置为非空；升级和降级都使用 SQLite 兼容的批处理模式。迁移同时创建 `project_members.user_id` 索引。

## 5. 前端行为

- `ProjectDetailView` 仅当 `project.capabilities.can_manage` 时显示“编辑项目”；仅当 `can_contribute` 时显示“新建”菜单及可创建的项目级操作。
- `ProjectActivityTab` 仅当 `can_contribute` 时显示 `ProjectUpdateComposer`；所有可查看者仍可阅读进展历史。
- `MeetingWorkspaceView` 根据会议能力显示编辑、生命周期、材料上传和评论入口：仅评论能力只保留评论；贡献能力才显示结构性写入操作。
- 项目、会议和进展领域 TypeScript 类型加入能力和进展版本字段。前端从服务端返回的新版本更新本地状态。
- 现有统一错误提示保留；收到 `409 version_conflict` 时，进展编辑器提示刷新后重试。当前界面没有项目进展编辑入口，因此本次不新增编辑 UI，只完成 API/类型契约，避免无测试的编辑表单扩张范围。

## 6. 测试策略

测试先行，并覆盖真实服务边界和 HTTP 路由：

1. 为管理员、负责人、`member`、`stakeholder`、非成员和仅会议参与人建立同一项目与会议夹具。
2. 验证项目列表过滤、项目详情拒绝、项目管理拒绝和成员贡献允许。
3. 验证非成员不能通过会议、议题、产出、附件、活动或评论入口绕过项目边界；仅会议参与人可读/评论自己的会议，但不能更改会议或项目资源。
4. 使用两个 SQLAlchemy 会话读取同一 `ProjectUpdate`：第一个编辑提交后，第二个以旧版本编辑得到 `version_conflict`，持久化内容保留第一个编辑。
5. 验证项目进展 API 返回版本、编辑请求缺少 `expected_version` 得到 422、过期版本得到 409、作者和管理员约束仍有效。
6. 前端组件测试验证能力不足时不渲染项目编辑、新建和进展发布按钮；贡献者仍可看到原有入口。
7. 运行相关后端测试、全量后端测试、前端测试、生产构建和 Alembic 升级检查。

## 7. 交付边界与非目标

本次不改变登录、用户审批、插件信任模型、会议状态机、数据导出格式或 Docker 部署方式。外部插件仍被视为受信任的服务器端代码；本次 ACL 保护 HTTP 请求和内建服务命令，不把插件配置扩展成任意权限委派。

本次也不增加项目进展的删除功能、历史版本列表、自动合并 Markdown 或实时光标。发生版本冲突时的唯一行为是拒绝过期写入并要求客户端刷新。
