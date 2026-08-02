# 议题记录 AI 草稿设计

## 目标

在会议工作台的“议题记录”编辑器提供与会议纪要、决策内容和行动项内容一致的 AI 入口。AI 读取当前编辑器草稿和服务端保存的议题/会议上下文，返回完整 Markdown 草稿；用户可以继续编辑，并通过既有“保存议题”提交。

## 范围和不变量

- 不新增领域字段、数据库迁移或 API 写入接口。
- AI 插件没有直接保存议题、创建产出或调用工具的权限。
- AI 结果整体替换当前编辑器文本。当前文本作为 `current_markdown` 一并提交，因此信息不会在生成前丢失。
- 仅具有 `can_contribute` 的用户可发起任务；只读成员和受邀但非项目成员看不到入口。
- 生成失败、取消或返回无效结果时，编辑器保留原文。
- 用户点击“保存议题”后，现有标签解析和并发版本控制继续生效；AI 生成的 `@决策:`、`@行动:`、`@开放问题:` 仍须经过这条人工确认的保存路径。

## 后端设计

为插件 job 增加运行时支持的 `agenda_item` target，不改变数据库中 `PluginJob.target_type` 的字符串存储方式。

提交、查看、取消、重新执行和列表筛选都以议题 ID 作为 target：

1. 读取 `AgendaItem`，不存在时返回现有的 `agenda_item_not_found` 404。
2. 通过其 `meeting_id` 使用既有会议可见性检查，再要求所属项目的贡献权限。
3. 以 `action_id:agenda_item:agenda_id` 去重，因此同一会议中不同议题可以并行生成。
4. `PluginContextBuilder.agenda_item()` 从服务端读取所属会议的插件上下文，并以最高裁剪优先级增加 `current_agenda_item`（与 target ID 对应的序列化议题）。浏览器 metadata 不进入 AI 输入，也不决定上下文。

新增 `ai-work-assistant.agenda_notes` action，输入仍只接受受长度限制的 `current_markdown`，target 为 `agenda_item`。提示词要求只依据上下文整理当前议题记录，生成完整可编辑 Markdown；资料不足时只能改写和组织，不能编造；标签只在资料明确支持时保留或生成。

## 前端设计

`AgendaDetail.vue` 在可编辑状态下用现有 `PluginEditorSlot` 包裹“议题记录”的 `MarkdownEditor`：

- slot：`agenda-notes-editor`
- target：`agenda_item` / 当前 `item.id`
- 文案：`AI 协助议题`、`整理议题记录`、`正在整理议题记录…`

插件完成时，现有 `registerEditor` writer 将 Markdown 写回 `draft.notes_markdown`。这会使既有 dirty 判定生效，但不会自动调用议题 PUT；用户仍需点击“保存议题”。无贡献权限时保留只读 `MarkdownEditor`，不加载 AI chrome。

## 测试与文档

- 后端覆盖 action 发现、议题 target 的上下文、权限、去重、任务读取/筛选，以及 action 返回的 Markdown。
- 前端覆盖插件注册与 job payload（必须是 `agenda_item` target），并验证 AI 回填只改变编辑器本地草稿、点击保存后才调用议题 PUT。
- 更新核心插件契约、AI 工作助手说明和 manifest 描述，说明议题级任务得到服务端可信上下文且只能返回草稿。

## 非目标

- 不为 AI 提供议题附件正文、文件读写、工具调用或自动应用按钮。
- 不改变现有会议、项目、决策、行动项和开放问题 action 的 target 或输入契约。
- 不将 AI 任务结果持久化为议题更新；持久化只由用户确认后的正常保存完成。
