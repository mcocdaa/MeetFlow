# Contextual Project and Meeting Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users create project work in context, work through an active meeting without losing the current agenda, and collaborate through real comments and participant-only mentions.

**Architecture:** Reuse existing project-scoped meeting, series, decision, action, attachment, comment, and mention APIs rather than adding duplicate resource endpoints. Add only comment resolution and meeting-participant mention authorization on the backend. The Vue layer gains a reusable right drawer, entity-scoped panels, and components that own local refreshes so parent page reloads are reserved for explicit navigation or meeting lifecycle transitions.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, SQLite, Vue 3 Composition API, TypeScript, Vitest, pytest.

---

## File and Responsibility Map

| File | Responsibility |
| --- | --- |
| `backend/app/collaboration/models.py` | Persist comment resolution state. |
| `backend/app/collaboration/schemas.py` | Validate resolve/reopen version commands and serialize comment state. |
| `backend/app/collaboration/service.py` | Enforce meeting-participant mentions and resolve/reopen transitions. |
| `backend/app/collaboration/router.py` | Expose comment resolve/reopen routes. |
| `backend/alembic/versions/<revision>_comment_resolution.py` | Add nullable resolution columns without rewriting comment history. |
| `backend/tests/collaboration/test_comments.py` | Cover participant-only mentions and resolve/reopen authorization. |
| `frontend/src/components/ContextDrawer.vue` | Accessible, reusable right-side drawer that preserves page scroll. |
| `frontend/src/components/ProjectCreatePanel.vue` | Project-scoped meeting/series/decision/action/file creation forms. |
| `frontend/src/components/MeetingCommentsPanel.vue` | Comment thread, reply/edit/resolve controls, and entity-scoped reload. |
| `frontend/src/components/MentionTextarea.vue` | Accessible participant-only `@` picker with fixed-height scrollable listbox. |
| `frontend/src/components/AttachmentPanel.vue` | Emit the created/deleted attachment so consumers update local arrays. |
| `frontend/src/components/OutcomeComposer.vue` | Use `MentionTextarea` for eligible action notes and keep outcome save local. |
| `frontend/src/views/ProjectDetailView.vue` | Contextual actions and project drawer coordination. |
| `frontend/src/views/MeetingWorkspaceView.vue` | Stable agenda-first layout and drawer coordination. |
| `frontend/src/domain/comments.ts` | Frontend comment and mention API response types. |
| `frontend/src/styles.css` | Drawer, stable workbench, comment, and mention-listbox styling. |
| `frontend/src/tests/project-workspace.test.ts` | Project contextual action and no-page-reload behavior. |
| `frontend/src/tests/meeting-workspace.test.ts` | Agenda-first structure and local material/comment updates. |
| `frontend/src/tests/comments-mentions.test.ts` | Thread UI and mention keyboard/listbox behavior. |

### Task 1: Add comment resolution and participant-only mention authorization

**Files:**
- Create: `backend/alembic/versions/<revision>_comment_resolution.py`
- Modify: `backend/app/collaboration/models.py`, `backend/app/collaboration/schemas.py`, `backend/app/collaboration/service.py`, `backend/app/collaboration/router.py`
- Test: `backend/tests/collaboration/test_comments.py`

- [ ] **Step 1: Write two failing backend tests.**

```python
def test_meeting_comment_mentions_only_meeting_participants(client, meeting_id):
    outsider = create_active_member(client, "outsider")
    comment = client.post("/api/comments", json={
        "target_type": "meeting", "target_id": meeting_id,
        "body_markdown": "@outsider", "mention_user_ids": [outsider["id"]],
    })
    assert comment.status_code == 422
    assert comment.json()["error"]["code"] == "comment_mention_not_participant"


def test_comment_author_can_resolve_and_reopen_thread(client, meeting_id):
    root = create_comment(client, target_type="meeting", target_id=meeting_id)
    resolved = client.post(f"/api/comments/{root['id']}/resolve", json={"expected_version": 1})
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None
    reopened = client.post(f"/api/comments/{root['id']}/reopen", json={"expected_version": 2})
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None
```

- [ ] **Step 2: Run the two tests and verify they fail because the route/state is absent.**

Run: `python -m pytest backend/tests/collaboration/test_comments.py -k 'participant or resolve' -v`

Expected: failures for a missing resolve route and missing participant validation.

- [ ] **Step 3: Add a non-destructive migration and model fields.**

```python
# models.py
resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

# migration upgrade()
op.add_column("comments", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("comments", sa.Column("resolved_by", sa.String(length=36), nullable=True))
op.create_foreign_key("fk_comments_resolved_by_users", "comments", "users", ["resolved_by"], ["id"])
```

The downgrade removes the foreign key and both nullable columns. Do not alter existing comment rows or mention rows.

- [ ] **Step 4: Implement validation and transitions in `CommentService`.**

```python
def _allowed_mention_ids(self, meeting_id: str | None) -> set[str] | None:
    if meeting_id is None:
        return None
    return set(self.session.scalars(
        select(MeetingParticipant.user_id).where(MeetingParticipant.meeting_id == meeting_id)
    ))

def resolve(self, comment_id: str, payload: CommentCommand, actor: User) -> Comment:
    root = self._get_loaded(comment_id)
    if root.parent_id is not None:
        raise AppError(422, "comment_root_required", "只能解决评论主题")
    require_version(payload.expected_version, root.version)
    root.resolved_at, root.resolved_by, root.version = utcnow(), actor.id, root.version + 1
    self._record(root, actor, "comment.resolved")
    self.session.commit()
    return self._get_loaded(root.id)
```

Permit resolving/reopening to the root author, an active project member with the existing project edit permission, or an admin; use one shared authorization helper for both transitions. Change `_mentions` to receive `meeting_id`; reject IDs outside `_allowed_mention_ids` with `comment_mention_not_participant`. Keep existing active-account checks and explicit mention notifications.

- [ ] **Step 5: Add routes and serialized resolution fields.**

```python
@comments_router.post("/{comment_id}/resolve")
def resolve_comment(comment_id: str, payload: CommentCommand, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    service = CommentService(session)
    return service.serialize(service.resolve(comment_id, payload, user), user)

@comments_router.post("/{comment_id}/reopen")
def reopen_comment(comment_id: str, payload: CommentCommand, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    service = CommentService(session)
    return service.serialize(service.reopen(comment_id, payload, user), user)
```

Make `serialize()` expose `resolved_at` and `resolved_by` as user refs or `null`.

- [ ] **Step 6: Run focused backend tests and commit.**

Run: `python -m pytest backend/tests/collaboration/test_comments.py -v`

Expected: all comment tests pass.

```bash
git add backend/app/collaboration backend/alembic/versions backend/tests/collaboration/test_comments.py
git commit -m "feat: add resolvable meeting comments"
```

### Task 2: Create reusable drawer and contextual project creation surfaces

**Files:**
- Create: `frontend/src/components/ContextDrawer.vue`, `frontend/src/components/ProjectCreatePanel.vue`
- Modify: `frontend/src/views/ProjectDetailView.vue`, `frontend/src/components/AttachmentPanel.vue`, `frontend/src/domain/projects.ts`
- Test: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Write failing project-workspace tests.**

```ts
it('opens a project-scoped meeting drawer from Next meeting without reloading the page', async () => {
  render(ProjectDetailView)
  await screen.findByText('下一次会议')
  await fireEvent.click(screen.getByRole('button', { name: '添加会议' }))
  expect(screen.getByRole('dialog', { name: '添加会议' })).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: '创建会议' }))
  expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/meetings', expect.objectContaining({ method: 'POST' }))
  expect(apiMock).not.toHaveBeenCalledWith('/api/projects/p1')
})
```

Add analogous assertions for the Meetings tab’s `添加会议`/`添加系列`, Decisions tab’s `添加决策`, Actions tab’s `添加行动项`, and Files tab’s `添加文件`.

- [ ] **Step 2: Run this test and verify the actions are absent.**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: failure that `添加会议` cannot be found.

- [ ] **Step 3: Implement `ContextDrawer.vue`.**

```vue
<Teleport to="body">
  <div v-if="open" class="context-drawer-backdrop" @click.self="$emit('close')">
    <aside class="context-drawer" role="dialog" :aria-label="title" aria-modal="true">
      <header><h2>{{ title }}</h2><button aria-label="关闭" @click="$emit('close')">×</button></header>
      <slot />
    </aside>
  </div>
</Teleport>
```

Capture the element that opened the drawer and restore focus when it closes. Lock background scrolling by adding/removing a body class without changing `window.scrollY`; do not use route changes.

- [ ] **Step 4: Implement `ProjectCreatePanel.vue` and local update events.**

Use a discriminated prop `kind: 'meeting' | 'series' | 'decision' | 'action' | 'file'`, a required `project`, and emits `created` with `{ kind, entity }`. Call existing endpoints:

```ts
const paths = {
  meeting: `/api/projects/${project.id}/meetings`,
  series: `/api/projects/${project.id}/meeting-series`,
  decision: `/api/projects/${project.id}/decisions`,
  action: `/api/projects/${project.id}/actions`,
}
```

For `file`, render `AttachmentPanel target-type="project"`; change `AttachmentPanel` to emit `uploaded(attachment)` and `deleted(id)` using the POST/DELETE response rather than only `changed`.

- [ ] **Step 5: Wire `ProjectDetailView` actions and local project patches.**

Store `drawerKind` and a small `applyCreated` switch. Append a new series to `project.series_summaries`, a decision to `project.recent_decisions`, an attachment to `project.attachments`, and increment the corresponding count. For meetings, set `project.next_meeting` only if it is earlier than the current upcoming meeting. Do not call `load()` from any drawer completion handler.

- [ ] **Step 6: Run focused tests and commit.**

Run: `npm test -- --run src/tests/project-workspace.test.ts`

Expected: project contextual-action tests pass.

```bash
git add frontend/src/components/ContextDrawer.vue frontend/src/components/ProjectCreatePanel.vue frontend/src/components/AttachmentPanel.vue frontend/src/domain/projects.ts frontend/src/views/ProjectDetailView.vue frontend/src/tests/project-workspace.test.ts
git commit -m "feat: add contextual project creation"
```

### Task 3: Build meeting comments and accessible participant mentions

**Files:**
- Create: `frontend/src/components/MentionTextarea.vue`, `frontend/src/components/MeetingCommentsPanel.vue`, `frontend/src/domain/comments.ts`, `frontend/src/tests/comments-mentions.test.ts`
- Modify: `frontend/src/components/OutcomeComposer.vue`, `frontend/src/views/MeetingWorkspaceView.vue`, `frontend/src/styles.css`

- [ ] **Step 1: Write failing frontend tests for thread rendering and mention selection.**

```ts
it('filters the fixed-height participant list after @ and inserts the selected mention', async () => {
  render(MentionTextarea, { props: { participants } })
  const editor = screen.getByRole('textbox', { name: '评论内容' })
  await fireEvent.update(editor, '@王')
  expect(screen.getByRole('listbox', { name: '会议参与者' })).toBeInTheDocument()
  expect(screen.getByRole('option', { name: '王敏 @wangmin' })).toBeInTheDocument()
  await fireEvent.keyDown(editor, { key: 'ArrowDown' })
  await fireEvent.keyDown(editor, { key: 'Enter' })
  expect(editor).toHaveValue('@王敏 ')
})

it('posts a reply and refreshes only the comment thread', async () => {
  render(MeetingCommentsPanel, { props: { meeting } })
  await fireEvent.click(screen.getByRole('button', { name: '回复' }))
  await fireEvent.click(screen.getByRole('button', { name: '发送评论' }))
  expect(apiMock).toHaveBeenCalledWith('/api/comments', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 2: Run the test and verify missing component failures.**

Run: `npm test -- --run src/tests/comments-mentions.test.ts`

Expected: module-not-found or missing-listbox failures.

- [ ] **Step 3: Implement `MentionTextarea.vue` with the WAI-ARIA combobox/listbox contract.**

Keep a normal `<textarea>` as the focused editable control. Compute the active `@query` from the text before the caret. Render only while there is an active mention token:

```vue
<textarea ref="input" role="combobox" aria-autocomplete="list"
  :aria-expanded="Boolean(matches.length)" aria-controls="mention-listbox"
  :aria-activedescendant="activeOptionId" @keydown="onKeydown" />
<ul v-if="matches.length" id="mention-listbox" role="listbox" aria-label="会议参与者">
  <li v-for="(participant, index) in matches" :id="optionId(index)" role="option"
      :aria-selected="index === activeIndex" @mousedown.prevent="insert(participant)">
    {{ participant.user.display_name }} @{{ participant.user.username }}
  </li>
</ul>
```

Give the list `max-height: 12rem; overflow-y: auto`; Arrow Up/Down changes `activeIndex`, Enter replaces the active `@query` with `@display_name ` and emits unique participant IDs, Escape closes it. Do not intercept ordinary editing, Home, End, Backspace, or Delete.

- [ ] **Step 4: Implement `MeetingCommentsPanel.vue`.**

Load `GET /api/comments?target_type=meeting&target_id=<meeting.id>` locally on mount. Render roots in ascending chronological order and replies indented beneath their root. Send `CommentWrite` with `mention_user_ids` from `MentionTextarea`; edit with `expected_version`; resolve/reopen with current `version`. Refetch only the comment endpoint after success and emit an updated count to its parent.

- [ ] **Step 5: Integrate the components.**

Replace `comments-reserved` in `MeetingWorkspaceView` with a drawer trigger `评论 (count)` and `MeetingCommentsPanel` inside `ContextDrawer`. In `OutcomeComposer`, replace the collaboration note field with `MentionTextarea` only for action content where a meeting is available; submit the emitted IDs only if the corresponding backend schema supports them, otherwise keep the field visually scoped to comments until that endpoint is extended in a separate migration. This prevents silently dropping mentions.

- [ ] **Step 6: Add styles, run tests, and commit.**

Run: `npm test -- --run src/tests/comments-mentions.test.ts src/tests/meeting-workspace.test.ts`

Expected: comment, mention, and workspace tests pass; the popup is scroll-constrained.

```bash
git add frontend/src/components/MentionTextarea.vue frontend/src/components/MeetingCommentsPanel.vue frontend/src/domain/comments.ts frontend/src/components/OutcomeComposer.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/styles.css frontend/src/tests/comments-mentions.test.ts frontend/src/tests/meeting-workspace.test.ts
git commit -m "feat: add meeting comments and participant mentions"
```

### Task 4: Make the meeting workbench agenda-first and mutations scroll-stable

**Files:**
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`, `frontend/src/components/AgendaWorkbench.vue`, `frontend/src/components/AgendaDetail.vue`, `frontend/src/components/AttachmentPanel.vue`, `frontend/src/styles.css`
- Test: `frontend/src/tests/meeting-workspace.test.ts`, `frontend/src/tests/agenda-workbench.test.ts`

- [ ] **Step 1: Write failing layout/stability tests.**

```ts
it('keeps current topic before preparation fields for a ready meeting', async () => {
  render(MeetingWorkspaceView)
  const currentTopic = await screen.findByText('当前议题')
  const preparation = screen.getByRole('button', { name: '准备信息' })
  expect(currentTopic.compareDocumentPosition(preparation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('does not call the page meeting loader after an attachment changes', async () => {
  render(MeetingWorkspaceView)
  await fireEvent.click(screen.getByRole('button', { name: /材料/ }))
  await fireEvent.click(screen.getByRole('button', { name: '上传' }))
  expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1')
})
```

- [ ] **Step 2: Run the tests and verify the current vertical Preparation panel fails the hierarchy assertion.**

Run: `npm test -- --run src/tests/meeting-workspace.test.ts src/tests/agenda-workbench.test.ts`

Expected: a missing `准备信息` trigger and/or loader call failure.

- [ ] **Step 3: Refactor `MeetingWorkspaceView` state boundaries.**

Keep `meeting` as the page’s lifecycle state. Add `preparationOpen`, `materialsOpen`, `commentsOpen`, and `materialItems` refs. Render `AgendaWorkbench` immediately after the header. Move the existing Preparation form into `ContextDrawer` and save it without replacing the workbench component; after a successful metadata PUT, patch only title/purpose/timestamps/version on `meeting.value`.

- [ ] **Step 4: Patch local attachment and outcome consumers.**

Pass `materialItems` to `AttachmentPanel`; append/remove using its new events. Change `AgendaDetail` to emit the created outcome entity or the selected agenda ID, then refetch only `GET /api/meetings/<id>` when an outcome response cannot supply a fully hydrated agenda item. Preserve `selectedId` in `AgendaWorkbench` before that refresh and restore it after, rather than remounting the full route.

- [ ] **Step 5: Apply stable layout CSS.**

```css
.meeting-workbench-shell { display:grid; grid-template-columns:minmax(0, 1fr) 19rem; align-items:start; }
.agenda-detail { min-height:calc(100vh - var(--workspace-header-height)); }
.agenda-queue-narrow { position:sticky; top:1rem; max-height:calc(100vh - 2rem); overflow:auto; }
```

Use the existing responsive breakpoint to return to a single column below tablet width. Do not use fixed heights on the notes editor; only queue/list drawers are independently scrollable.

- [ ] **Step 6: Run focused frontend tests and commit.**

Run: `npm test -- --run src/tests/meeting-workspace.test.ts src/tests/agenda-workbench.test.ts`

Expected: agenda is the first work surface and local mutations do not invoke page-level reload.

```bash
git add frontend/src/views/MeetingWorkspaceView.vue frontend/src/components/AgendaWorkbench.vue frontend/src/components/AgendaDetail.vue frontend/src/components/AttachmentPanel.vue frontend/src/styles.css frontend/src/tests/meeting-workspace.test.ts frontend/src/tests/agenda-workbench.test.ts
git commit -m "feat: prioritize active meeting workbench"
```

### Task 5: Run release verification and deploy the single-container update

**Files:**
- Modify only if required by test discoveries: files named in Tasks 1–4
- Test: all existing backend and frontend suites

- [ ] **Step 1: Verify migrations and backend suites in bounded groups.**

Run:

```bash
python -m pytest -q backend/tests/auth backend/tests/api backend/tests/collaboration
python -m pytest -q backend/tests/domain/test_agendas.py backend/tests/domain/test_meeting_lifecycle.py backend/tests/domain/test_meeting_series.py
python -m pytest -q backend/tests/domain/test_outcomes.py backend/tests/domain/test_projects.py backend/tests/inbox
python -m pytest -q backend/tests/meetings backend/tests/migrations backend/tests/plugins
python -m pytest -q backend/tests/test_backup.py backend/tests/test_frontend_integration.py backend/tests/test_health.py backend/tests/test_settings.py
```

Expected: every group passes and the total test count remains below 100.

- [ ] **Step 2: Verify the complete frontend suite and production build.**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Expected: every test passes; Vite’s existing large lazy meeting-editor chunk warning may remain, but TypeScript compilation and the build exit successfully.

- [ ] **Step 3: Rebuild and restart Docker.**

Run: `docker compose up -d --build --force-recreate`

Expected: a healthy `meetflow-meetflow-1` container using the newly created image.

- [ ] **Step 4: Run live HTTP smoke tests.**

Run:

```bash
curl --max-time 10 -sS -i http://127.0.0.1:8000/api/health
curl --max-time 10 -sS -i http://127.0.0.1:8000/api/auth/session
```

Expected: 200 with `{"status":"ok"}` and 200 with anonymous `{"user":null}` before login. Then manually verify one contextual project creation and one meeting comment/mention through the served SPA.

- [ ] **Step 5: Commit verification-only fixes, if any, and record the deployment evidence.**

```bash
git status --short
git log --oneline -5
```

Do not commit generated `frontend/dist/`, SQLite data, runtime attachment files, `.superpowers/brainstorm/`, or unrelated user changes.

## Plan Self-Review

* **Spec coverage:** Task 2 covers contextual project actions and local updates; Task 4 covers agenda-first meeting layout and scroll stability; Task 1 and Task 3 cover real comments, resolution, mentions, and accessibility; Task 5 covers regression and Docker verification.
* **No placeholders:** Migration revision is intentionally generated by Alembic at execution time; its required schema operations are stated in Task 1. All behavioral choices and commands are explicit.
* **Type consistency:** Backend comments use `CommentWrite`, `CommentEdit`, and `CommentCommand`; frontend receives comment responses in `domain/comments.ts`; the mention picker emits participant IDs and uses existing `MeetingParticipant` user references.
