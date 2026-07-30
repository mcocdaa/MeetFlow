# MeetFlow backend plugin boundary

MeetFlow plugins are trusted Python code installed by the server administrator. The web UI can configure and enable discovered plugins, but it cannot upload or install code. Plugin code is imported only during application startup; changing code or enabled state requires a restart.

Plugin actions execute in the single FastAPI process. `PLUGIN_TIMEOUT_SECONDS` limits cooperative async handlers, but it cannot interrupt blocking Python code. A plugin that requires hard isolation must run its workload in a separate process or service. Runtime failures are logged with plugin ID, action ID, and exception class only; configuration values and exception messages are deliberately omitted.

The `/app/plugins` directory should be mounted read-only. Plugin manifests declare configuration fields and secrets. Secrets are encrypted in SQLite and are passed only to the corresponding loaded plugin action.

For meeting-targeted actions, MeetFlow supplies a server-built, read-only context package. It may include the saved meeting summary, participants, agenda notes and statuses, estimated and actual agenda durations, manual and note-derived outcomes, plus the supported `@决策:` / `@行动:` / `@开放问题:` tag syntax. Treat this package as authoritative input for suggestions, not as permission to mutate domain records: action handlers return a proposed editor value and the normal authenticated save path remains the only write boundary.
