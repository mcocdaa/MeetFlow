# Meeting Workbench and Editor AI Surface Design

**Status:** approved for implementation planning

## Goal

Make the active-meeting page read as three clear, ordinary document-flow
scopes, and make AI a quiet editor-local capability instead of a competing
page action.

The result must fix the frustrating lifecycle path: a user who has edited the
current agenda or meeting record can choose `准备完成`, `返回准备`, `开始会议`, or
`结束会议` without losing entered content. The application saves the pending
changes first and changes state only after those saves succeed.

## Scope

This iteration covers only the meeting workspace and reusable editor-hosted AI
controls:

1. The meeting workbench visual hierarchy.
2. Save-before-lifecycle transitions for editable draft and active meetings.
3. The presentation and review flow of existing AI editor actions.

It does not introduce a fixed-viewport application shell, a no-scroll policy,
an AI chat pane, new AI actions, new plugin protocols, or backend schema/API
endpoints.

## Meeting workspace hierarchy

The page remains a normal vertically scrolling document. It contains three
successive scopes:

```text
+--------------------------- Meeting workbench ---------------------------+
| Current topic                                      | Agenda queue        |
| title, type, duration, record, outcomes, flow      | add, order, select  |
+--------------------------------------------------------------------------+

+---------------------------- Meeting summary ----------------------------+

+-------------------------- Materials and collaboration ------------------+
```

### One shared meeting-workbench surface

`Current topic` and `Agenda queue` are two regions of one parent
`Meeting workbench` surface, not two independent cards placed beside each
other. They keep their existing data ownership, headings, controls, selected
state, ordering, and responsive behavior.

- Desktop: the current topic occupies the flexible left region; the agenda
  queue remains narrow on the right. A restrained vertical divider separates
  the regions inside the shared outer border.
- The right queue is not a separate sticky card. A long queue extends the
  shared meeting-workbench scope naturally.
- The selected agenda state remains visible inside the queue, but neither its
  height nor its own shadow suggests that it is a separate page section.
- The no-agenda state stays inside the same shared surface: the compact
  explanation belongs in the left region and the add-agenda queue remains in
  the right region.
- Narrow screens stack the two inner regions inside the same parent surface,
  using a horizontal divider. The normal page scroll behavior is unchanged.

The summary and meeting-tools cards follow the shared workbench exactly as
normal sibling sections. A long agenda therefore reads as a longer meeting
session, rather than visually delaying an unrelated section below a detached
right card.

### Component boundary

`AgendaWorkbench` becomes the owner of the shared outer surface. `AgendaDetail`
and `AgendaQueue` render as embedded regions: their current independent
surface border, background, shadow, padding, and sticky positioning are
removed only in this composition. Their agenda mutation behavior is not moved
into the meeting page.

## Save before a meeting lifecycle transition

### Pending local state

Two local surfaces can hold content not yet persisted:

- `AgendaDetail`: title, type, duration, and agenda record for the currently
  selected agenda item.
- `MeetingWorkspaceView`: meeting title, purpose, raw notes, summary, and
  scheduled times.

Each surface gets explicit dirty detection against the most recently accepted
server entity. A clean surface makes no save request.

### Transition sequence

All header lifecycle actions (`准备完成`, `返回准备`, `开始会议`, `结束会议`) use one
coordinator. It executes the following sequence:

1. Flush the selected agenda draft if it is dirty.
2. Fetch the current meeting once if an agenda flush occurred, so the parent
   holds the incremented meeting version.
3. Persist the dirty meeting draft, including the summary, and adopt the
   returned meeting and version.
4. Submit the requested lifecycle command with that latest version.
5. Adopt the meeting returned by the lifecycle endpoint directly; do not call
   page-level `load()` after a successful transition.

Agenda updates increment the parent meeting version, so step 2 is required to
avoid an optimistic-version conflict in steps 3 and 4. Existing meeting update
and lifecycle endpoints already return a serialized meeting; no API work is
needed.

While the sequence runs, all lifecycle controls are disabled and use a
specific status such as `正在保存并开始会议…`. The transition is never submitted
when a required save fails. Failed saves leave the relevant local draft mounted
and editable, show an inline error, and do not refresh the route.

This is deliberately a save-then-transition sequence, not a new server-side
transaction: an agenda save can already have succeeded if a later meeting save
fails. That is acceptable because entered content is retained and the meeting
state has not changed. Atomic all-or-nothing persistence would require a
separate backend command and is out of scope.

### Component contract

`AgendaDetail` exposes a focused `flushIfDirty()` operation through
`AgendaWorkbench`; it reuses the existing agenda PUT validation and reports
failure to the lifecycle coordinator. `AgendaWorkbench` exposes that operation
to `MeetingWorkspaceView` without making the meeting page own the agenda form
fields. The normal `保存议题` button keeps the same behavior.

The meeting page refactors `saveMeeting()` into a reusable persistence helper
that can either be called by the preparation drawer or by the lifecycle
coordinator. Saving from the drawer preserves its current explicit save
interaction; a lifecycle action does not trigger a route reload or discard an
open local surface.

## Editor-local AI controls

### Design basis

Overleaf puts writing tools in its editor toolbar, opens broad document chat
from a low-priority sidebar icon, and makes error-specific AI contextual with a
review/apply path. MeetFlow adopts the first and third patterns, but not a
global chat surface in this iteration.

- [Writefull for Overleaf](https://docs.overleaf.com/integrations-and-add-ons/ai-features/writefull)
  documents editor-toolbar integration for writing tools.
- [Overleaf AI assistant](https://docs.overleaf.com/integrations-and-add-ons/ai-features/ai-assistant)
  reserves a sidebar icon and adjacent pane for broad document chat.
- [Overleaf Error Assist](https://docs.overleaf.com/integrations-and-add-ons/ai-features/error-assist)
  uses a contextual trigger and an explicit apply/reject-style suggestion flow
  that can be undone.

### Entry placement

There is no large `AI 建议决策`-style button in a page header, a title-field
row, or a full-width row above an editor. When an enabled plugin offers one or
more actions for an editor, that editor renders one compact `✦` tool in its own
thin chrome beside the field label. The tool does not add a section or change
the form's vertical rhythm.

Activating the tool opens a small local command menu with the full action names,
for example `生成会议纪要`, `建议决策`, or `梳理开放问题`. The menu, rather than the
idle page, carries the descriptive labels. The icon has an accessible name,
keyboard focus treatment, and a tooltip.

The generic plugin host continues to resolve registered editor assistants and
to provide the same target, metadata, busy, update, and notice contracts. The
visual move is implemented by giving the reusable Markdown editor a slim
editor-chrome/tool slot; the host no longer renders its own full-width toolbar
and divider above every editor. No global right-side AI panel is added.

### Review before write

Existing AI actions still create and poll the same plugin jobs. A successful
response becomes a local, editable AI draft rather than immediately replacing
the editor model.

- The original editor text stays unchanged while the result is reviewed.
- A compact draft area offers `应用草稿` and `放弃`.
- Applying writes the draft to the existing editor as one replace operation,
  preserving the current one-step undo behavior.
- Discarding removes the local AI draft without changing the editor or the
  underlying meeting/outcome record.
- Job failures leave both original text and the editor enabled, with a local
  short error notice.

The task centre remains execution history and diagnostics; it is not used to
complete ordinary editor work.

## Error handling and accessibility

- A failed agenda or meeting save blocks only the requested lifecycle action;
  it does not reset editor content or silently retry with a stale version.
- A version conflict leaves the user on the current surface and reuses the
  existing conflict recovery behavior where available.
- Busy state disables duplicate lifecycle commands and duplicate AI commands,
  but does not disable unrelated meeting navigation or non-target editors.
- The AI command control is reachable by keyboard and exposes its menu and
  busy state through standard button/menu and live-status semantics.

## Verification

Frontend tests cover:

1. A populated and an empty workbench render one outer meeting-workbench
   surface with embedded topic and queue regions.
2. The summary and tools remain following sibling scopes; desktop and narrow
   layouts retain the intended ordering.
3. A clean lifecycle transition sends only the lifecycle request and adopts its
   returned meeting without calling `load()`.
4. A dirty agenda plus a dirty meeting executes agenda save, meeting refresh,
   meeting save, then the lifecycle request using fresh versions.
5. Agenda-save and meeting-save failures do not send the lifecycle request and
   preserve all entered draft text.
6. The AI idle state renders one compact editor tool rather than a full-width
   assistant row. The action menu exposes descriptive plugin actions.
7. Generated AI output remains a local draft until Apply; Apply updates the
   editor once, while Discard and failure preserve the original content.

Existing agenda ordering, outcome composition, plugin-job polling, optimistic
version, and keyboard-editor tests remain green.

## Self-review

- The design keeps normal document scrolling; it does not reintroduce an
  unrequested fixed-viewport layout.
- The shared workbench changes visual composition only; agenda data ownership
  and API boundaries remain explicit.
- The save chain calls out version refresh after agenda mutation, avoiding a
  stale lifecycle request.
- AI scope is limited to existing editor actions and adds review before write;
  it does not imply a chat agent, automatic persistence, or new backend APIs.
