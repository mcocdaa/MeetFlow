# Contextual Project and Meeting Workspace Design

**Status:** Approved for planning

## Goal

Make a project the primary operational workspace and make an active meeting a stable discussion workspace. Users create and update work where the relevant context is visible; local changes never reset the page scroll position or editor focus.

## Product Rules

1. A project is the entry point for project-scoped work. The user must not need to leave the project page merely to create a meeting, series, decision, action item, or file.
2. A meeting is an agenda-led work session. The current agenda item and its queue are the primary surface while a meeting is in progress.
3. Outcomes retain their context. Decisions, actions, and open questions created during a meeting remain linked to the agenda item that produced them.
4. Comments are working collaboration, not a placeholder. A user can add a top-level comment, reply in a thread, edit their own comment, and resolve or reopen a thread.
5. Mentions are constrained to the participants of the current meeting. They create explicit mention records and do not parse arbitrary usernames as implicit mentions.
6. Saving a local surface updates that surface only. It must not invoke the page-level loading state, remount the primary editor, replace the active meeting object wholesale, scroll the document, or steal focus.

## Project Workspace

### Contextual actions

Project actions appear in the header of the content block they affect. No global “new” menu is added.

| Location | Visible action | Result |
| --- | --- | --- |
| Overview: Next meeting | `添加会议` | Opens project-scoped meeting drawer; saved meeting updates the card. |
| Overview: Recent decisions | `添加决策` | Opens project-scoped decision drawer; saved decision appears in the list. |
| Meetings tab | `添加会议`, `添加系列` | Opens the corresponding project-scoped drawer. |
| Decisions tab | `添加决策` | Opens a project-scoped decision drawer. |
| Actions tab | `添加行动项` | Opens a project-scoped action drawer. |
| Files tab | `添加文件` | Opens a project-scoped upload drawer/panel. |

The meeting, series, decision, action, and file forms share one right-side drawer shell. Closing it preserves the page state. On successful submit it emits a typed result to the currently displayed project block; it does not call `ProjectDetailView.load()`.

### Project-scope outcomes

Project decisions and actions are valid without a meeting agenda item. The UI asks for the minimum existing fields: title/content, owner for actions, and due date where supported. Project scope is prefilled and cannot be changed in the drawer.

## Meeting Workspace

### Stable hierarchy

For draft and ready meetings, meeting metadata is collapsed by default in a header action labelled `准备信息`. The editable Preparation form opens in a side drawer or inline disclosure and is never placed above the main agenda workspace by default.

For active meetings, the first working viewport contains:

1. Meeting header and lifecycle action.
2. Left primary pane: current agenda item, notes, outcomes, and flow controls.
3. Right narrow pane: agenda queue and add-agenda action.

The content order is the same in draft, ready, and in-progress states. Metadata may be edited while draft or ready; the active meeting workspace does not move when metadata is opened or saved.

### Contextual meeting actions

* `添加决策`, `添加行动项`, and `添加开放问题` remain adjacent to the current agenda item’s outcomes.
* `跳过` and `完成并下一项` remain a separate flow-control group at the lower edge of the agenda detail. They are visually and semantically separate from outcome creation.
* `材料 (N)` and `评论 (N)` open independent right-side drawers. The primary agenda pane stays mounted.
* Adding a material or comment updates the drawer list in place. Creating an outcome updates the current agenda item’s outcome list in place. A full meeting fetch is reserved for lifecycle transitions or an explicit refresh.

## Comments and Mentions

### Comments

Replace the reserved comments panel with a meeting-comment drawer:

* Top-level comments are ordered newest last within a chronological thread list.
* Replies belong to one root comment and are visually indented.
* Authors may edit their own content; users with the appropriate existing project permission may resolve or reopen a root thread.
* Resolved threads are collapsed by default but remain available, preserving the meeting record.
* Comment create, reply, edit, resolve, and reopen events are recorded in the existing activity mechanism where it is already used for collaboration changes.

### Mention selector

Every free-text composer that supports an assignee or collaboration note shows a short affordance such as `输入 @ 可提及会议成员`; no format explanation is shown before the user is in an eligible composer.

Typing `@` followed by zero or more characters opens a filtered participant picker anchored to the caret/composer. The popup:

* contains only current meeting participants;
* has a fixed maximum height and scrolls internally;
* filters by display name and username;
* is keyboard accessible: Arrow Up/Down changes the active option, Enter inserts a mention, Escape closes it, and ordinary text editing keeps browser behavior;
* uses an accessible combobox/listbox relationship with `aria-expanded`, `aria-controls`, `aria-activedescendant`, and `aria-autocomplete="list"`;
* inserts a stable textual token such as `@林宇` into Markdown/content, while the API separately receives the mentioned participant IDs.

Mention candidate state is client-only. The persisted source of truth is the comment/action/etc. content plus explicit mention rows created by the API in the same transaction.

## API and Data Boundaries

Existing project, meeting, agenda, attachment, action, decision, and collaboration endpoints remain authoritative. New endpoints are limited to capabilities the current API lacks:

* create project-scoped decisions and actions from the project drawer;
* list/create/edit/resolve/reopen meeting comment threads;
* create/list explicit mention records for meeting collaboration surfaces;
* return enough participant identity data for the mention picker.

Responses are entity-scoped. Components own their refresh methods: an attachment drawer refreshes attachments, a comments drawer refreshes its thread list, and an outcome composer refreshes only the selected agenda item. Page-level `load()` is not used as a generic mutation callback.

## Error, Conflict, and Focus Behaviour

* Mutations keep their form open and show an inline error on failure.
* Version conflicts use the existing conflict pattern where an entity already supports optimistic versions; no mutation silently overwrites server data.
* On success, a drawer closes only when the user chose a submit-and-close action. Inline composers remain focused and retain their surrounding scroll position.
* Failed uploads or comments leave the entered text/file selection available for retry where browser capabilities permit.

## Testing and Acceptance Criteria

1. Project overview and all relevant tabs expose their contextual creation action.
2. A successful contextual mutation updates its own block without calling the page-level project/meeting reload method.
3. An active meeting renders current topic and agenda queue before any expanded preparation form.
4. Materials and comments can be added while the meeting remains open.
5. Comments support a persisted root/reply thread and resolved state.
6. Typing `@` filters only meeting participants; keyboard selection inserts the chosen mention; the list scrolls rather than growing the editor.
7. Existing attachment, outcome, lifecycle, agenda ordering, authorization, and optimistic-version protections remain covered.
8. Backend and frontend test suites remain below 100 tests each unless a user-approved test budget change is made.

## Out of Scope

* AI-generated minutes, agent tool calls, and plugin behavior.
* Cross-project mentions and workspace-wide people search.
* Real-time collaborative cursors or WebSocket presence.
* A global command palette or a project-wide “new” menu.
