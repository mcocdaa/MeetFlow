# Workbench Layout and AI Work Assistant Design

**Status:** approved design, pending implementation plan  
**Scope:** Fix meeting-workspace visual hierarchy and add one trusted, fixed AI text plugin with three draft-producing actions.

## 1. Goals

1. Make an empty meeting agenda look deliberate rather than like a broken full-height editor.
2. Ensure every Markdown editor begins on a consistent top text baseline.
3. Add practical AI assistance without turning MeetFlow into an agent platform or allowing automatic writes to official meeting/project records.

## 2. Non-goals

- Change the established populated-agenda workbench layout.
- Add plugin upload, web installation, hot reload, tool calls, web research, or autonomous agents.
- Let AI mutate meetings, projects, decisions, actions, or comments directly.
- Parse attachment contents in the first AI plugin.

## 3. Meeting workspace layout

### 3.1 Prepared meeting drawer

The right-side **准备信息** drawer uses a single-column form hierarchy:

1. Meeting title occupies its own full-width row.
2. Start and end time appear as a balanced two-column row below it.
3. Purpose editor and participant chips follow.
4. The primary **保存会议信息** action remains visible at the drawer bottom; it must not compress title or date fields.

This removes the narrow title field visible in the current three-column grid.

### 3.2 Agenda workbench with agenda items

Keep the existing workbench: agenda detail on the left and a fixed-width `310px` agenda queue on the right, top-aligned. The queue remains sticky on desktop and returns above the detail on narrow screens.

### 3.3 Agenda workbench with no agenda items

The empty state is not an editor. It is a compact left-side status card alongside the same narrow queue.

- The empty detail card has no viewport-like `min-height`.
- It uses an explicit compact minimum height aligned to the queue card (rather than filling available vertical space).
- Its heading, explanation, and a local **添加议题** action are vertically grouped with normal card padding.
- The existing queue-side **+ 议题** remains available, so users can act from either side without visually duplicating a large form.

The two cards must share a top edge and feel like one coherent two-column state.

### 3.4 Markdown editor baseline

All reusable Markdown editors share the same editing baseline:

- The first editable paragraph begins at the editor content top padding.
- The first paragraph has no extra top margin.
- Placeholder text uses that same first-paragraph position; it must not be vertically centered.
- Only editing surfaces which need writing room retain an explicit `min-height`; that height does not introduce vertical centering.
- The meeting agenda record editor, preparation purpose, raw notes, summary, comments, and outcome text reuse the rule.

## 4. AI Work Assistant plugin

### 4.1 Installation and configuration

Ship one administrator-installed trusted Python plugin: `ai-work-assistant`.

It uses the existing fixed-on-disk plugin discovery and its own administrator-only OpenAI-compatible configuration:

- Base URL
- API key (secret, never returned after save)
- Model
- Timeout

It appears as one expandable row in plugin management. The three actions are declared in its manifest, and start/stop remains restart-aware as defined by the existing plugin system.

### 4.2 Actions

| Action | Input | Editable draft | Explicit apply target |
| --- | --- | --- | --- |
| `meeting_summary` | meeting purpose, agenda records, outcomes, raw notes, existing summary | Markdown meeting minutes | `summary_markdown` on the meeting |
| `project_progress` | project summary, latest updates, recent meetings, open actions, recent decisions | Markdown project update | ordinary project update endpoint |
| `action_suggestions` | meeting agenda records, conclusions, open questions, existing actions | Markdown proposal plus structured candidate rows | create selected ordinary action items |

The plugin receives only serialised first-party text and structured entity metadata. Attachment names and types may be included as context labels; binary or text attachment contents are not read.

### 4.3 Job lifecycle

All actions use the existing persistent plugin-job mechanism:

1. User launches an available action from the meeting or project context.
2. Server creates (or returns) an active deduplicated job keyed by action and source entity.
3. The worker invokes the configured OpenAI-compatible text endpoint.
4. The task centre polls the job until it reaches success or failure.
5. Successful output is stored as an editable draft.
6. A user explicitly applies the draft through a normal domain endpoint; the plugin has no direct-write capability.

Retries follow the existing job contract. A failed job surfaces its safe error message in the task centre and never overwrites user-entered records.

### 4.4 Presentation

- Meeting page exposes **生成会议纪要** and **建议行动项** in the local tools area when the plugin is runtime-enabled.
- Project page exposes **总结项目进展** near the project update workflow.
- AI task centre distinguishes the three action names, source links, queued/running/success/failed state, and apply controls.
- Generated content is clearly labeled **AI 草稿** until applied.

## 5. Testing and acceptance

### Layout

- Empty workbench renders detail and queue as compact, top-aligned sibling cards.
- Populated workbench retains detail-left / queue-right ordering.
- The first placeholder and typed line in each representative Markdown editor is top-aligned.
- Preparation drawer shows a full-width title and two-column time row at desktop widths.

### Plugin

- Registry discovers all three actions from one fixed manifest.
- Secret configuration is not returned or logged.
- Active duplicate submissions return the same job.
- Each action receives only permitted serialised context.
- AI output remains a draft until an explicit apply request succeeds.
- A disabled or failed plugin never breaks core meeting/project pages.

## 6. Self-review

- No automatic AI writes or attachment parsing are implied.
- The plugin uses the existing trusted fixed-code/job architecture rather than introducing another plugin runtime.
- Empty and populated agenda states have distinct, unambiguous layout rules.
- Markdown alignment is defined as a reusable editor invariant, not a one-screen patch.
