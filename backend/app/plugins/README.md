# MeetFlow backend plugin boundary

MeetFlow plugins are trusted Python code installed by the server administrator. The web UI can configure and enable discovered plugins, but it cannot upload or install code. Plugin code is imported only during application startup; changing code or enabled state requires a restart.

Plugin actions execute in the single FastAPI process. `PLUGIN_TIMEOUT_SECONDS` limits cooperative async handlers, but it cannot interrupt blocking Python code. A plugin that requires hard isolation must run its workload in a separate process or service. Runtime failures are logged with plugin ID, action ID, and exception class only; configuration values and exception messages are deliberately omitted.

Manifest `api_version: 1` remains supported. Version 2 manifests may declare
`capabilities.actions`, `exporters`, `event_subscriptions`, `ui_slots`,
`context_scopes`, and `external_network`; unknown capability keys are rejected
during discovery so an enabled plugin cannot silently request an unsupported
integration surface. Declaring a capability does not grant access by itself;
the corresponding server-side contract must still validate the action,
bounded context, target and output.

Completed meetings are recorded in the `plugin_events` outbox in the same
SQLite transaction as the snapshot. The single-process worker claims queued
events, retries failures with bounded backoff, and marks events as failed after
five attempts; a restart requeues only events that were being processed.

管理员插件页通过 `GET /api/admin/plugins` 查看 manifest 能力、API 版本和本次进程是否已加载；通过
`GET /api/admin/plugins/events?status=failed` 查看脱敏后的失败事件、重试次数和最后错误。该诊断接口只读，
不会返回插件配置或事件 payload。修复配置后，管理员可以对单条失败事件调用
`POST /api/admin/plugins/events/{event_id}/retry`，它只把原事件重新置为 `queued`，由 Worker 异步处理。

Exporter plugins receive only the bounded meeting context and return a
validated `PluginExport`. The core enforces a safe single-segment filename,
bytes-only content and an 8 MB limit before sending the download response;
exporters do not receive a SQLAlchemy session or data-directory path.
The first-party `meeting-export` plugin exposes Markdown and JSON buttons on
completed meeting pages; disabling or removing that plugin leaves the core
meeting workspace usable and turns an attempted export into an inline error.

The `/app/plugins` directory should be mounted read-only. Plugin manifests declare configuration fields and secrets. Secrets are encrypted in SQLite and are passed only to the corresponding loaded plugin action.

Plugin jobs may target a meeting, project, or `agenda_item`. An `agenda_item` target is loaded server-side from its ID, then checked through its owning meeting and project; submitting one requires meeting-view and project-contribution permission. Its bounded context contains the selected `current_agenda_item` as well as the authoritative meeting context. It may include the saved meeting summary, participants, agenda notes and statuses, `agenda_outcome_tags`, `estimated_minutes`, `actual_duration_seconds`, and manual or note-derived outcomes. Outcome rows expose `source_agenda_item_id`, `source_tag_key`, and `is_derived`; these field names are stable plugin-contract fields. The supported tag syntax is `@决策:` / `@行动:` / `@开放问题:`. Treat every context package as authoritative input for suggestions, not as permission to mutate domain records: action handlers return a proposed editor value and the normal authenticated save path remains the only write boundary.
