# Project Workspace Information Architecture

## Purpose

Make a project page answer three questions at a glance: what is the current
state, what needs attention now, and where should the user continue work.
The page is a project driving surface, not a vertically stacked collection of
all project editors.

## Scope

This redesign covers the project detail workspace and its six existing tabs:
Overview, Meetings, Actions, Decisions, Files, and Activity. It preserves the
current backend entities and routes. It does not add new project-management
objects, notifications, or AI capabilities.

## Information Architecture

### Persistent project header

The header contains identity and durable project state only:

- project name and one-line description;
- lifecycle status, health, owner, target date, and member count;
- a single primary `New` menu with Meeting, Meeting series, Decision, Action,
  Progress update, and File;
- a secondary `Edit project` action.

The `New` menu opens the existing creation drawers or attachment workflow. It
replaces scattered create buttons in the overview while keeping contextual
create buttons inside the dedicated tabs.

### Tabs

The stable tab order is:

1. Overview
2. Meetings
3. Actions
4. Decisions
5. Files
6. Activity

Each tab has one responsibility and owns its detailed list and creation flow.
The overview only links to those complete views; it does not duplicate their
forms or full lists.

## Overview: the project driving surface

The overview uses a two-column desktop grid with an intentional reading order.
On narrow screens it becomes one column.

### Row 1: current state and next meeting

- **Current state**: compact, human-maintained project summary plus health.
  It is read-only in the overview; editing remains in `Edit project`.
- **Next meeting**: title, scheduled time, meeting status, and a single
  `Open meeting` action. If absent, show a compact `Schedule meeting` action.

### Row 2: attention and open work

- **Needs attention**: only actionable exceptions, such as overdue actions,
  unassigned actions, blockers, and drafts awaiting confirmation. Each row
  states the reason and leads to its source.
- **Open actions**: up to five actions, ordered by overdue, due date, then
  priority. Show owner, due date, and status. A `View all actions` link leads
  to the Actions tab.

### Row 3: durable outcomes and recent context

- **Recent decisions**: up to three decisions with status and link to the
  Decisions tab.
- **Recent activity**: up to five chronological entries, mixing human project
  progress, material changes, and meeting completions. A `View all activity`
  link leads to the Activity tab.

Metric counts may sit in the header metadata or at the bottom of the overview,
but never displace the two decision-making rows above.

## Dedicated work tabs

### Meetings

Shows next meeting, series, and recent completed meetings. The tab header
contains `Add meeting` and `Add series`. Opening a meeting moves into the
meeting workspace; meeting preparation, agenda, materials, comments, and
outcomes never expand inside the project page.

### Actions

Shows project actions as the working queue with status, owner, due date,
priority, source meeting, and filters. The header has `Add action`. Creating or
editing actions remains in this tab or its drawer, not on the overview.

### Decisions

Shows project decisions with title, final/proposed state, source meeting, and
last update. The header has `Add decision`.

### Files

Shows project attachments and upload controls. The header has `Add file`.

### Activity

Owns chronological project progress. `Add progress update` opens a drawer or
composer in this tab; it is not permanently rendered on the overview. Each
entry shows author, time, health (when supplied), and Markdown content.

## AI placement and flow

AI is assistance to a destination, never a top-level project section.

- Meeting summary and action suggestions remain in the meeting workspace.
- Project progress generation is available in the Activity composer alongside
  the manual progress editor.
- A submitted job creates no second editor in the overview. When ready, its
  editable draft appears in the same Activity composer; the user can edit and
  publish it with the ordinary `Publish progress` action.
- The AI task center remains recovery/history only, linking users back to the
  destination page for edits and confirmation.

## Interaction rules

- Keep one primary action per section header; secondary navigation is textual.
- Do not show two controls that write the same entity on the same screen.
- Preserve scroll position after attachment, action, or AI-draft updates.
- Empty states state what is missing and offer one contextually correct create
  action.
- Opening an editor uses the existing drawer pattern where possible, so the
  project dashboard does not reflow into an editing surface.

## Migration from the current layout

- Remove the persistent `ProjectUpdateComposer` and project AI draft surface
  from Overview.
- Move progress composer and project progress drafts to Activity.
- Retain existing overview cards but cap their visible list lengths and add
  source links.
- Replace duplicated overview creation buttons with the header `New` menu;
  retain tab-local creation controls for direct work.
- Keep all existing backend endpoints and persistent data intact.

## Acceptance criteria

- A project overview contains no multiline text editor, AI draft editor, or
  large plugin panel.
- A user can create every existing project child entity from the header `New`
  menu and from its owning tab.
- The first viewport communicates health, next meeting, and actionable work
  without scrolling through a history composer.
- AI-generated project progress is editable and published only inside Activity.
- Meeting, Action, Decision, File, and Activity tabs each have a clear owner
  and do not duplicate unrelated editors.
