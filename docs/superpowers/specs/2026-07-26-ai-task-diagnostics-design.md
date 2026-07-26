# AI Task Diagnostics Design

## Goal

Replace the opaque `AI 任务执行失败` state with safe, actionable diagnostics
without exposing API keys, request headers, prompts, or stack traces.

## Execution error contract

The worker stores three fields for every failed job:

- `error_code`: stable machine-readable category;
- `error_message`: short Chinese explanation and a user-facing next step;
- `error_detail`: an optional, sanitized technical detail suitable for an
  expandable area in the task centre.

The task centre shows `error_message` by default. Failed cards provide a
collapsed “查看技术详情” section only when `error_detail` exists.

## Classification

The worker classifies plugin exceptions at the boundary where it invokes the
action handler:

| Condition | Code | User message |
| --- | --- | --- |
| HTTP 401 or 403 | `provider_auth_failed` | 认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。 |
| HTTP 402 | `provider_insufficient_balance` | AI 服务额度不足；请充值或更换有可用额度的 API Key。 |
| HTTP 404 | `provider_not_found` | 找不到 AI 服务或模型；检查服务地址和模型名称。 |
| HTTP 408 or timeout | `provider_timeout` | AI 服务响应超时；请稍后重试或检查超时设置。 |
| HTTP 429 | `provider_rate_limited` | AI 服务限流或配额已用尽；请稍后重试并检查服务额度。 |
| Other HTTP error | `provider_http_error` | AI 服务返回 HTTP 状态错误。 |
| Network request error | `provider_network_error` | 无法连接 AI 服务；检查服务地址和网络。 |
| Plugin configuration/input/output error | existing typed category | Preserve a clear configuration or compatibility message. |
| Unknown exception | `plugin_failed` | AI 任务执行失败；请查看技术详情或联系管理员。 |

Technical details are restricted to the HTTP status/reason or exception class
and a capped provider message. A redaction helper removes bearer tokens,
common API key patterns, and `api_key` assignments before persistence.

## Current incident

The current production failures reproduce as `HTTP 402` with the provider
message `Insufficient Balance`. The new classifier reports that as
`provider_insufficient_balance`; no API-key change is implied by this result.

## Verification

Worker tests cover 401, 402, 429, timeout, network, and redaction behavior.
Frontend tests cover the collapsed detail display. A Docker rebuild verifies
the migration and the running API.
