# AI 工作助手

这是 MeetFlow 随镜像提供的固定插件。它仅调用管理员配置的 OpenAI 兼容
`/chat/completions` 接口，生成可编辑草稿；它没有工具调用能力，也不能直接写入会议、项目或行动项。

部署后以管理员身份打开“插件管理”，配置 `base_url`、`model`、`timeout_seconds` 和 API Key。
插件文件在容器启动时加载；更改启用状态后需要重启容器。生成结果会进入 AI 任务中心，必须由用户确认后才会应用到 MeetFlow。
