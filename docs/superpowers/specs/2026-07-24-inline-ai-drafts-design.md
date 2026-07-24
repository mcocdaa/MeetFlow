# Inline AI Drafts Design

## Goal

Move AI output from a task-centre-first workflow to contextual, editable drafts
where the work is happening. The AI task centre remains a recovery and history
surface, not the normal place to finish work.

## User flow

```text
Meeting or project work surface
  -> start AI task
  -> inline pending state
  -> inline editable draft
  -> explicit confirm, discard, or leave for later
  -> normal MeetFlow record is created or updated
```

No AI result mutates a meeting, project update, or action item before the user
confirms it.

## Contextual surfaces

### Meeting summary

The meeting workspace summary area is the destination. Starting **生成会议纪要**
creates an inline pending card. When the task succeeds, the card contains an
editable Markdown draft and these controls:

- **应用到会议纪要**: updates the meeting summary through the existing versioned
  meeting update path.
- **丢弃草稿**: hides the inline draft without deleting the task history.
- **在 AI 任务中打开**: recovery link for the full task record.

### Project progress

The project overview's progress section is the destination. Starting
**总结项目进展** creates an inline pending card. A succeeded task becomes an
editable project-progress draft with:

- **发布项目进展**: creates a normal `ai_draft_applied` project update.
- **丢弃草稿** and **在 AI 任务中打开**.

### Action suggestions

The meeting's action area is the destination. Starting **建议行动项** creates an
inline pending card. A succeeded task renders a compact list of draft action
rows instead of a large Markdown textarea plus a global checkbox matrix.

Each row has a selected checkbox, editable content, owner, due date, and
priority. Draft rows use a visually distinct `AI 建议 · 尚未创建` state and are
not returned by the normal action APIs. The primary control reads
**创建已选 N 项**. It creates only selected rows through the ordinary action
creation path. A row can be removed from the draft before confirmation.

The original Markdown explanation is collapsed under **查看 AI 依据** rather
than occupying the primary work surface.

## AI task centre

`/ai-tasks` keeps personal task history, errors, queued/running status, and
unresolved drafts. It links each item back to its source meeting or project.
When a user opens a source surface, its unresolved task is rendered inline.
The task centre must not be required for normal confirmation.

## Data and API contract

Existing persistent `PluginJob` records remain the source of truth. Inline UI
loads jobs by target (`meeting` or `project`) and active/completed state. The
job API gains target-scoped listing so a surface does not download unrelated
personal history.

The frontend keeps edits to inline suggestions locally until explicit confirm.
For action suggestions, the apply request sends selected, edited candidates
(content, optional owner, due date, priority), not only result indexes. The
server validates each selected candidate and routes it through the existing
`OutcomeService.create_action` workflow. A job is marked applied once; a later
retry creates a new job.

Discarding is an interface state only: the job remains in history and can be
reopened. It must not be mistaken for cancellation of an in-flight task.

## States and failure handling

- Queued/requesting: small inline progress card; the source remains editable.
- Succeeded/unapplied: editable inline draft.
- Failed/interrupted: concise error and a retry action inline.
- Canceled: show no editable draft; allow rerun.
- Applied: replace the draft with a compact confirmation link to the resulting
  record.

Poll every three seconds only for inline active tasks. Stop polling when the
component unmounts or the task enters a terminal state.

## Scope and non-goals

- No streaming tokens, agent loops, tool calls, or automatic writes.
- No deletion of task history when a draft is discarded.
- No separate AI editing data model; jobs plus ordinary domain APIs remain the
  boundary.
- The existing AI task centre stays available while the inline workflow becomes
  primary.

## Verification

Tests cover inline task submission, active-state polling cleanup, succeeded
draft rendering on meeting/project/action surfaces, explicit apply, draft
discard visibility, and selected edited action candidate submission. Existing
backend job tests continue to cover authorization, deduplication, recovery,
and explicit writes. Frontend suites remain below 100 tests.
