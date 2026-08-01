# Collaboration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project membership the enforced multi-user workspace boundary and prevent concurrent project-progress edits from silently overwriting each other.

**Architecture:** A single `WorkspaceAccess` policy resolves project membership, leadership, admin override, and meeting participation into view/contribute/manage/comment capabilities. HTTP adapters call it before returning or mutating every project-scoped resource, while serialisers expose server-calculated capabilities for UI affordances. `ProjectUpdate` gains the same SQLAlchemy optimistic-versioning contract used by projects, meetings, agendas, outcomes, and comments.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic/SQLite, pytest, Vue 3, TypeScript, Vitest, Testing Library.

---

## File map

| File | Responsibility |
| --- | --- |
| `backend/app/projects/access.py` | Central workspace capability resolution, SQL predicates, and `403` guards. |
| `backend/app/projects/models.py` | `ProjectMember.user_id` index and `ProjectUpdate.version` mapper configuration. |
| `backend/app/projects/schemas.py` | Separate project-progress create and edit payloads. |
| `backend/app/projects/service.py` | Filtered project reads, creator membership, guarded project/progress writes, progress conflict handling and capability serialisation. |
| `backend/app/projects/router.py` | Pass the current actor to project reads and use the edit schema. |
| `backend/app/meetings/{service.py,queries.py,router.py}` | Authorise project/meeting reads and meeting/series/lifecycle writes; expose meeting capabilities. |
| `backend/app/{agendas,outcomes,collaboration}/service.py` | Require project contribution or permitted meeting comment access at command boundaries. |
| `backend/app/{agendas,outcomes,collaboration}/router.py` | Authorise each resource-ID route before serialising it. |
| `backend/app/attachments/router.py` | Map attachment target to project/meeting access before list, upload, download, preview, and delete. |
| `backend/app/workspace/router.py` | Filter global action, decision and meeting pages to visible workspaces. |
| `backend/app/plugins/{context.py,router.py}` | Apply the same guards before plugin context, actions, and exports reveal meeting/project data. |
| `backend/migrations/versions/0009_workspace_access_versions.py` | Add `project_updates.version` and an index for membership lookup. |
| `backend/tests/collaboration/test_workspace_access.py` | HTTP permission matrix and bypass regression tests. |
| `backend/tests/domain/test_projects.py` | Project-update optimistic-concurrency tests. |
| `frontend/src/domain/{projects.ts,meetings.ts}` | Capability and version response types. |
| `frontend/src/views/ProjectDetailView.vue` | Hide project-management and contribution controls using server capabilities. |
| `frontend/src/components/ProjectActivityTab.vue` | Render the progress composer only for contributors. |
| `frontend/src/views/MeetingWorkspaceView.vue` | Hide meeting structure controls or comment access according to meeting capabilities. |
| `frontend/src/tests/project-workspace.test.ts` | Prove controls are visible only for permitted capability combinations. |
| `docs/development.md` | Document the project access model and project-update conflict protocol for contributors. |

## Task 1: Define and prove the workspace access policy

**Files:**
- Create: `backend/app/projects/access.py`
- Create: `backend/tests/collaboration/test_workspace_access.py`
- Modify: `backend/app/projects/models.py`

- [ ] **Step 1: Write the failing policy matrix test.**

  Create reusable users in one project: admin, lead, `member`, `stakeholder`, outsider, and an outsider who is a participant of `meeting`. Assert the policy’s exact decisions instead of testing router implementation:

  ```python
  def test_workspace_access_distinguishes_roles(access_context):
      access, rows = access_context

      assert access.project_capabilities(rows.project, rows.admin).can_manage
      assert access.project_capabilities(rows.project, rows.lead).can_manage
      assert access.project_capabilities(rows.project, rows.member).can_contribute
      assert not access.project_capabilities(rows.project, rows.member).can_manage
      assert access.project_capabilities(rows.project, rows.stakeholder).can_view
      assert not access.project_capabilities(rows.project, rows.stakeholder).can_contribute
      assert not access.project_capabilities(rows.project, rows.outsider).can_view
      assert access.meeting_capabilities(rows.meeting, rows.invited).can_view
      assert access.meeting_capabilities(rows.meeting, rows.invited).can_comment
      assert not access.meeting_capabilities(rows.meeting, rows.invited).can_contribute
  ```

- [ ] **Step 2: Run the focused test and verify it fails because the policy module does not exist.**

  Run from this worktree:

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration/test_workspace_access.py::test_workspace_access_distinguishes_roles
  ```

  Expected: import failure for `app.projects.access.WorkspaceAccess`.

- [ ] **Step 3: Implement the policy as the single source of truth.**

  Add immutable capability values and guard methods. `admin` and `lead_user_id` manage; `ProjectMemberRole.member` contributes; any member views; a `MeetingParticipant` only views/comments that meeting.

  ```python
  @dataclass(frozen=True)
  class WorkspaceCapabilities:
      can_view: bool = False
      can_manage: bool = False
      can_contribute: bool = False
      can_comment: bool = False

  class WorkspaceAccess:
      def __init__(self, session: Session):
          self.session = session

      def project_capabilities(self, project: Project, actor: User) -> WorkspaceCapabilities:
          if actor.role == UserRole.ADMIN or project.lead_user_id == actor.id:
              return WorkspaceCapabilities(True, True, True, True)
          membership = next((row for row in project.memberships if row.user_id == actor.id), None)
          if membership is None:
              return WorkspaceCapabilities()
          if membership.role == ProjectMemberRole.member:
              return WorkspaceCapabilities(True, False, True, True)
          return WorkspaceCapabilities(True, False, False, False)

      def meeting_capabilities(self, meeting: Meeting, actor: User) -> WorkspaceCapabilities:
          project = self._project_with_memberships(meeting.project_id)
          project_caps = self.project_capabilities(project, actor)
          if project_caps.can_view:
              return project_caps
          invited = self.session.scalar(select(MeetingParticipant.user_id).where(
              MeetingParticipant.meeting_id == meeting.id,
              MeetingParticipant.user_id == actor.id,
          ))
          return WorkspaceCapabilities(can_view=bool(invited), can_comment=bool(invited))

      def require_project_view(self, project_id: str, actor: User) -> Project:
          return self._require_project(project_id, actor, "can_view", "project_view_forbidden")

      def require_project_contribute(self, project_id: str, actor: User) -> Project:
          return self._require_project(project_id, actor, "can_contribute", "project_contribution_forbidden")

      def require_project_manage(self, project_id: str, actor: User) -> Project:
          return self._require_project(project_id, actor, "can_manage", "project_management_forbidden")

      def require_meeting_view(self, meeting_id: str, actor: User) -> Meeting:
          meeting = self._meeting(meeting_id)
          if not self.meeting_capabilities(meeting, actor).can_view:
              raise AppError(403, "project_view_forbidden", "无权查看此会议")
          return meeting

      def require_meeting_comment(self, meeting_id: str, actor: User) -> Meeting:
          meeting = self._meeting(meeting_id)
          if not self.meeting_capabilities(meeting, actor).can_comment:
              raise AppError(403, "meeting_comment_forbidden", "无权评论此会议")
          return meeting
  ```

  Each `require_*` loads the canonical resource and raises the designed `403` code (`project_view_forbidden`, `project_contribution_forbidden`, `project_management_forbidden`, or `meeting_comment_forbidden`). A missing resource still returns its current `404`. Implement `visible_project_ids(actor)` as a `select(ProjectMember.project_id)` subquery that includes lead projects; administrators bypass filtering.

  Add `index=True` to `ProjectMember.user_id` in the model so SQLAlchemy metadata matches the migration in Task 5.

- [ ] **Step 4: Run the focused policy tests and verify they pass.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration/test_workspace_access.py -k access
  ```

  Expected: policy matrix passes for all six actor types.

- [ ] **Step 5: Commit the isolated policy foundation.**

  ```bash
  git add backend/app/projects/access.py backend/app/projects/models.py backend/tests/collaboration/test_workspace_access.py
  git commit -m "feat: define workspace access policy"
  ```

## Task 2: Apply project visibility, management, and capability responses

**Files:**
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/tests/collaboration/test_workspace_access.py`

- [ ] **Step 1: Write failing project-route tests.**

  Verify that the outsider sees no row from `GET /api/projects`, receives `403 project_view_forbidden` from `GET /api/projects/{id}`, and cannot `PUT` the project. Verify a `member` receives `403 project_management_forbidden` for `PUT`, while the lead succeeds. Verify a project created with `member_ids=[]` is still visible to its creator.

  ```python
  def test_project_routes_filter_visibility_and_require_management(two_client_context):
      admin, member, outsider, project = two_client_context
      assert outsider.get("/api/projects").json() == []
      assert outsider.get(f"/api/projects/{project['id']}").status_code == 403
      assert member.put(f"/api/projects/{project['id']}", json={"expected_version": 1, "summary": "x"}).status_code == 403
      assert admin.put(f"/api/projects/{project['id']}", json={"expected_version": 1, "summary": "x"}).status_code == 200
  ```

- [ ] **Step 2: Run the test and verify the current API leaks or permits the access.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration/test_workspace_access.py -k project_routes
  ```

  Expected: failure because the outsider currently receives a project and the member can update it.

- [ ] **Step 3: Implement guarded project operations and serialised capabilities.**

  Change `ProjectService.list(actor)` to filter with `WorkspaceAccess.visible_project_ids(actor)`. Change `detail(project_id, actor)` and `update(project_id, payload, actor)` to call the policy; update requires `require_project_manage`. In `create`, append the actor ID to `member_ids` before validation/deduplication. Add a small `serialize_capabilities()` helper and include:

  ```python
  "capabilities": {
      "can_manage": caps.can_manage,
      "can_contribute": caps.can_contribute,
      "can_comment": caps.can_comment,
  }
  ```

  in actor-aware detail responses. Pass `user` from each project router handler, not `_user`. Keep list payloads lightweight; they do not require capability objects.

- [ ] **Step 4: Run focused tests and verify the API contract.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/domain/test_projects.py backend/tests/collaboration/test_workspace_access.py -k "project or access"
  ```

  Expected: all project domain tests and the new visibility/management tests pass.

- [ ] **Step 5: Commit project-boundary enforcement.**

  ```bash
  git add backend/app/projects/service.py backend/app/projects/router.py backend/tests/collaboration/test_workspace_access.py
  git commit -m "feat: enforce project workspace access"
  ```

## Task 3: Guard meeting, series, global workspace, and plugin data paths

**Files:**
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/meetings/queries.py`
- Modify: `backend/app/meetings/router.py`
- Modify: `backend/app/workspace/router.py`
- Modify: `backend/app/plugins/context.py`
- Modify: `backend/app/plugins/router.py`
- Modify: `backend/tests/collaboration/test_workspace_access.py`

- [ ] **Step 1: Write failing meeting and global-list access tests.**

  Test an outsider against `GET /api/meetings/{id}`, `PUT /api/meetings/{id}`, `POST /api/meetings/{id}/start`, `GET /api/meetings`, and a plugin export endpoint. Test an invited non-member can read only their meeting and post a meeting comment later, but cannot update or start it. Assert global meetings/actions/decisions pages exclude the outsider’s inaccessible project.

  ```python
  def test_invited_user_can_view_but_not_mutate_meeting(two_client_context):
      invited, outsider, meeting = two_client_context.invited, two_client_context.outsider, two_client_context.meeting
      assert invited.get(f"/api/meetings/{meeting['id']}").status_code == 200
      assert invited.put(f"/api/meetings/{meeting['id']}", json={"expected_version": 1, "title": "No"}).status_code == 403
      assert outsider.get(f"/api/meetings/{meeting['id']}").status_code == 403
  ```

- [ ] **Step 2: Run the test and verify the current endpoints are unguarded.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration/test_workspace_access.py -k "meeting or global"
  ```

  Expected: failure because an outsider can currently read or mutate the meeting.

- [ ] **Step 3: Add meeting-aware adapters without weakening scheduler behavior.**

  At HTTP boundaries, use `WorkspaceAccess.require_project_view()` for project-scoped meeting/series lists, `require_meeting_view()` for meeting detail/snapshots, and `require_project_contribute()` before all meeting, series, occurrence, lifecycle, amendment, and plugin-action/export writes. Keep `materialize_due_occurrences()` actor-free because it is an internal scheduler command.

  Make `MeetingQueries` accept an actor only for public read methods, or guard in routers before invoking the existing actor-free query implementation. Add `capabilities` to `GET /api/meetings/{id}` only, using `meeting_capabilities()` after the view guard.

  In `workspace/router.py`, add the visible project predicate to global actions and decisions. For global meetings include projects visible to the user plus meetings where the user is a participant, using `distinct()` when the participant filter is joined. In `plugins/context.py` and plugin action/export routes, require the corresponding project/meeting capability before constructing a context.

- [ ] **Step 4: Run meeting and plugin regression tests.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/domain/test_meeting_series.py backend/tests/domain/test_meeting_lifecycle.py backend/tests/plugins backend/tests/collaboration/test_workspace_access.py -k "not retry"
  ```

  Expected: existing lifecycle/plugin behavior remains green; new forbidden and invited-user cases pass.

- [ ] **Step 5: Commit protected meeting entry points.**

  ```bash
  git add backend/app/meetings backend/app/workspace/router.py backend/app/plugins/context.py backend/app/plugins/router.py backend/tests/collaboration/test_workspace_access.py
  git commit -m "feat: protect meeting workspace access"
  ```

## Task 4: Close project-resource bypasses

**Files:**
- Modify: `backend/app/agendas/service.py`
- Modify: `backend/app/agendas/router.py`
- Modify: `backend/app/outcomes/service.py`
- Modify: `backend/app/outcomes/router.py`
- Modify: `backend/app/collaboration/service.py`
- Modify: `backend/app/collaboration/router.py`
- Modify: `backend/app/attachments/router.py`
- Modify: `backend/tests/collaboration/test_workspace_access.py`

- [ ] **Step 1: Write failing bypass tests before adding guards.**

  Cover each resource family through a representative route: outsider creating an agenda item, decision, attachment, or comment receives `403`; stakeholder can list but cannot create; project member can create; invited non-member can list/create comments only on their own meeting and cannot upload a meeting attachment.

  ```python
  def test_non_member_cannot_bypass_project_boundary_with_comments_or_attachments(two_client_context):
      outsider, meeting = two_client_context.outsider, two_client_context.meeting
      assert outsider.post("/api/comments", json={"target_type": "meeting", "target_id": meeting["id"], "body_markdown": "intrude", "mention_user_ids": []}).status_code == 403
      assert outsider.post(f"/api/attachments/meeting/{meeting['id']}", files={"file": ("x.txt", b"x", "text/plain")}).status_code == 403
  ```

- [ ] **Step 2: Run bypass tests and verify they fail for the intended missing guards.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration/test_workspace_access.py -k "bypass or stakeholder or invited"
  ```

- [ ] **Step 3: Add guards at each resource’s canonical source chain.**

  In `AgendaService`, load the item/meeting then call `require_project_contribute(meeting.project_id, actor)` before every create, update, delete, move, reorder, and lifecycle command; call `require_meeting_view` before detail/list output. In `OutcomeService`, guard `project_id` creators and load each existing decision/action/question/agenda source before update/review/finalise/convert/copy commands. In `CommentService`, use `_target_context()` to choose project contribution for project targets and `require_meeting_comment()` for meeting or agenda targets; apply the same view decision to comment lists and replies. In the attachment router, derive project and optional meeting from `require_target()` and require view for list/download/preview, contribution for upload, and contribution plus existing author/admin rule for deletion.

  Do not duplicate role checks in routers; route handlers only supply the current actor and let service/attachment helpers call `WorkspaceAccess`.

- [ ] **Step 4: Run the affected domain and collaboration suites.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/collaboration backend/tests/domain/test_outcomes.py backend/tests/meetings/test_attachments.py backend/tests/domain/test_meeting_lifecycle.py
  ```

  Expected: bypass tests pass, all existing ownership/version/state-machine tests remain green.

- [ ] **Step 5: Commit the closed bypass paths.**

  ```bash
  git add backend/app/agendas backend/app/outcomes backend/app/collaboration backend/app/attachments backend/tests/collaboration/test_workspace_access.py
  git commit -m "feat: guard project resources by workspace access"
  ```

## Task 5: Add optimistic concurrency to project progress

**Files:**
- Create: `backend/migrations/versions/0009_workspace_access_versions.py`
- Modify: `backend/app/projects/models.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/tests/domain/test_projects.py`
- Modify: `backend/tests/collaboration/test_workspace_access.py`

- [ ] **Step 1: Write the failing two-session and API contract tests.**

  Use two sessions to fetch the same `ProjectUpdate`, commit one `ProjectUpdateEdit(expected_version=1, content_markdown="Winner")`, then attempt a stale second edit. Also assert the API serialises `version: 1`, rejects a PUT with no `expected_version` as `422`, and returns the standard `409` details for stale writes.

  ```python
  with pytest.raises(AppError) as conflict:
      ProjectService(second_session).edit_update(
          update_id,
          ProjectUpdateEdit(expected_version=1, content_markdown="Stale"),
          author,
      )
  assert conflict.value.code == "version_conflict"
  assert conflict.value.details == {"expected_version": 1, "actual_version": 2}
  ```

- [ ] **Step 2: Run the focused test and verify the stale write currently succeeds or the edit payload cannot be imported.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/domain/test_projects.py -k project_update
  ```

- [ ] **Step 3: Add schema, model, service, router, and migration support.**

  Configure the model exactly like the existing versioned models:

  ```python
  version: Mapped[int] = mapped_column(Integer, default=1)
  __mapper_args__ = {"version_id_col": version, "version_id_generator": False}
  ```

  Define `ProjectUpdateEdit(ProjectUpdateWrite)` with `expected_version: int = Field(ge=1)`. Make `create_update()` set `version=1`; make `edit_update()` require `ProjectUpdateEdit`, validate author/admin after contribution access, call `require_version`, increment the version, and convert `StaleDataError` to the same `version_conflict` payload used by `Project.update`. Return `version` from `serialize_update()` and accept the edit schema only on `PUT /api/project-updates/{update_id}`.

  The migration must use revision `0009`, depend on `0008`, add a non-null `project_updates.version` with temporary `server_default="1"`, remove the server default after existing rows are populated, and create `ix_project_members_user_id`. Its downgrade drops that index and version column using `batch_alter_table` so SQLite is supported.

- [ ] **Step 4: Run model, migration, and focused tests.**

  ```bash
  ../../.venv/bin/python -m pytest -q backend/tests/domain/test_projects.py backend/tests/collaboration/test_workspace_access.py -k "update or progress"
  ../../.venv/bin/alembic -c backend/alembic.ini upgrade head
  ../../.venv/bin/alembic -c backend/alembic.ini downgrade 0008
  ../../.venv/bin/alembic -c backend/alembic.ini upgrade head
  ```

  Expected: one winner persists, stale writers receive `409`, and the migration upgrades/downgrades cleanly.

- [ ] **Step 5: Commit versioned progress writes.**

  ```bash
  git add backend/migrations/versions/0009_workspace_access_versions.py backend/app/projects/models.py backend/app/projects/schemas.py backend/app/projects/service.py backend/app/projects/router.py backend/tests/domain/test_projects.py backend/tests/collaboration/test_workspace_access.py
  git commit -m "feat: add versioned project updates"
  ```

## Task 6: Reflect server capabilities in the Vue workspace

**Files:**
- Modify: `frontend/src/domain/projects.ts`
- Modify: `frontend/src/domain/meetings.ts`
- Modify: `frontend/src/views/ProjectDetailView.vue`
- Modify: `frontend/src/components/ProjectActivityTab.vue`
- Modify: `frontend/src/views/MeetingWorkspaceView.vue`
- Modify: `frontend/src/tests/project-workspace.test.ts`

- [ ] **Step 1: Add failing UI capability tests.**

  Extend the existing project fixture with a `capabilities` field. Render the view with all flags false and assert that “编辑项目”, “新建”, and “发布进展” are absent. Render again with `can_manage: true, can_contribute: true, can_comment: true` and assert the existing controls remain present.

  ```ts
  it('does not expose project mutation controls to a read-only stakeholder', async () => {
    apiMock.mockImplementation((path: string) => Promise.resolve(
      path === '/api/projects/p1' ? { ...project, capabilities: { can_manage: false, can_contribute: false, can_comment: false } } : { items: [] },
    ))
    render(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    expect(screen.queryByRole('button', { name: '编辑项目' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建' })).not.toBeInTheDocument()
  })
  ```

- [ ] **Step 2: Run the UI test and verify it fails because controls are unconditional.**

  ```bash
  npm --prefix frontend test -- --run src/tests/project-workspace.test.ts
  ```

  Expected: the read-only fixture still finds project mutation controls.

- [ ] **Step 3: Implement capability-driven rendering without client-side ACL logic.**

  Add a shared `WorkspaceCapabilities` TypeScript type and require `capabilities` on `ProjectDetail` and `Meeting`. Gate project management with `project.capabilities.can_manage`; gate `ProjectCreatePanel` and `ProjectUpdateComposer` with `can_contribute`; gate meeting structural controls with `meeting.capabilities.can_contribute`; keep comments visible only when `can_comment`. Do not derive permissions from `session.user` or membership arrays.

- [ ] **Step 4: Run focused frontend tests and build.**

  ```bash
  npm --prefix frontend test -- --run src/tests/project-workspace.test.ts src/tests/meeting-lifecycle.test.ts src/tests/meeting-comments.test.ts
  npm --prefix frontend run build
  ```

  Expected: controls match server capabilities and the production bundle builds.

- [ ] **Step 5: Commit the capability UI.**

  ```bash
  git add frontend/src/domain/projects.ts frontend/src/domain/meetings.ts frontend/src/views/ProjectDetailView.vue frontend/src/components/ProjectActivityTab.vue frontend/src/views/MeetingWorkspaceView.vue frontend/src/tests/project-workspace.test.ts
  git commit -m "feat: reflect workspace capabilities in UI"
  ```

## Task 7: Document the contract and run the full verification gate

**Files:**
- Modify: `docs/development.md`
- Modify: `docs/superpowers/plans/2026-08-01-collaboration-hardening.md`

- [ ] **Step 1: Document the supported access and conflict contracts.**

  Add a concise “多用户工作区访问” subsection in `docs/development.md` that links to the approved design, names the four project roles (admin, lead, member, stakeholder), explains meeting-participant read/comment scope, and requires `expected_version` for project-progress edits. Document that schema changes are delivered by migration `0009`, not test-only table creation.

- [ ] **Step 2: Mark the executed plan steps complete as their commits land.**

  Replace only the checkboxes corresponding to completed plan steps; do not edit design intent or squash the implementation commits into the documentation commit.

- [ ] **Step 3: Run all mandated verification from the implementation worktree.**

  ```bash
  ../../.venv/bin/python -m pytest -q
  npm --prefix frontend test
  npm --prefix frontend run build
  ../../.venv/bin/python -m pytest -q backend/tests/test_release_workflow.py
  git diff --check
  git status --short --branch
  ```

  Expected: all tests/build commands exit 0, `git diff --check` is silent, and only intended documentation changes remain unstaged before the final commit.

- [ ] **Step 4: Commit documentation and checked plan status.**

  ```bash
  git add docs/development.md docs/superpowers/plans/2026-08-01-collaboration-hardening.md
  git commit -m "docs: document workspace access controls"
  ```

## Plan self-review

- Spec coverage: Tasks 1–4 implement every role, visibility, contribution, comment, attachment, global-list, and plugin boundary in the approved design. Task 5 covers model/schema/router/migration/atomic conflict behavior. Task 6 covers capability-driven UI. Task 7 covers the required developer documentation and complete verification.
- Type consistency: `WorkspaceCapabilities`, `WorkspaceAccess`, `ProjectUpdateEdit`, `can_manage`, `can_contribute`, and `can_comment` are used with the same names throughout.
- Scope: no task introduces real-time collaboration, field-level ACLs, progress deletion/history, automatic Markdown merges, user-management changes, or Docker/release behavior changes.
