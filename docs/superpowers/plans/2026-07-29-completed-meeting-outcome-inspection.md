# Completed Meeting Outcome Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users expand completed-meeting agenda rows to read the frozen decisions, actions, and open questions, including meeting-level outcomes.

**Architecture:** Keep the completed meeting as a read-only snapshot viewer. `CompletedMeetingChain.vue` will normalize the snapshot JSON into agenda and meeting-level outcome groups, then render them through native `details` / `summary` accordions. No API, database, or lifecycle code changes are needed; styles and tests remain in the existing frontend locations.

**Tech Stack:** Vue 3 Composition API, TypeScript, native HTML disclosure elements, existing `MarkdownView`, Vitest, Vue Testing Library, CSS.

---

## File structure

- Modify: `frontend/src/components/CompletedMeetingChain.vue`
  - Normalize untyped `snapshot_json` / legacy `snapshot` input into read-only groups and render accessible, multi-expand outcome accordions.
- Modify: `frontend/src/styles.css`
  - Add compact completed-outcome accordion, row, metadata, content, and responsive styles consistent with the completed-meeting visual system.
- Modify: `frontend/src/tests/meeting-lifecycle.test.ts`
  - Drive and verify snapshot-only rendering, multiple expanded agenda groups, empty groups, and optional meeting-level outcomes.

### Task 1: Add snapshot-viewer regression coverage

**Files:**
- Modify: `frontend/src/tests/meeting-lifecycle.test.ts`

- [ ] **Step 1: Add a completed-snapshot fixture with frozen outcomes and deliberately different current data**

  Add a helper after `fixture` that starts from `fixture('completed')`, gives its live `agenda_items[0].decisions` a sentinel title such as `当前可变决策`, then replaces `current_snapshot.snapshot_json` with two agenda entries and one meeting-level outcome. Use snapshot values such as:

  ```ts
  snapshot_json: {
    meeting: { title: '迭代评审', summary_markdown: '本轮范围已经确认' },
    agenda_items: [
      {
        id: 'a1', title: '发布方案', status: 'completed',
        decisions: [{ id: 'd1', title: '采用灰度发布', decision_markdown: '先向 10% 用户发布。', rationale_markdown: '先验证核心指标。', status: 'final' }],
        actions: [{ id: 'ac1', content: '准备灰度发布清单', priority: 'high', due_date: '2026-07-30', status: 'open' }],
        open_questions: [{ id: 'q1', question_markdown: '回滚阈值是什么？', status: 'open' }],
      },
      { id: 'a2', title: '后续跟进', status: 'completed', decisions: [], actions: [], open_questions: [] },
    ],
    meeting_decisions: [{ id: 'md1', title: '每周复盘一次', decision_markdown: '每周一复盘发布效果。', rationale_markdown: '', status: 'final' }],
    meeting_actions: [],
    meeting_open_questions: [],
  }
  ```

  Keep the helper locally typed with `as any` only at the snapshot boundary, because the production `MeetingSnapshot` deliberately models the JSON as a generic record.

- [ ] **Step 2: Write the failing accordion behavior test**

  Import `within` from Vue Testing Library and add a test that loads the helper fixture. Assert all of the following:

  ```ts
  const first = await screen.findByTestId('completed-agenda-a1')
  const second = screen.getByTestId('completed-agenda-a2')
  expect(first).not.toHaveAttribute('open')
  expect(second).not.toHaveAttribute('open')
  expect(screen.queryByText('当前可变决策')).not.toBeInTheDocument()

  await fireEvent.click(within(first).getByText('发布方案'))
  expect(first).toHaveAttribute('open')
  expect(screen.getByText('采用灰度发布')).toBeVisible()
  expect(screen.getByText('先向 10% 用户发布。')).toBeVisible()
  expect(screen.getByText('准备灰度发布清单')).toBeVisible()
  expect(screen.getByText('2026-07-30')).toBeVisible()
  expect(screen.getByText('回滚阈值是什么？')).toBeVisible()

  await fireEvent.click(within(second).getByText('后续跟进'))
  expect(first).toHaveAttribute('open')
  expect(second).toHaveAttribute('open')
  expect(within(second).getByText('本议题未记录产出')).toBeVisible()

  const meetingLevel = screen.getByTestId('completed-meeting-outcomes')
  await fireEvent.click(within(meetingLevel).getByText('会议级产出'))
  expect(meetingLevel).toHaveAttribute('open')
  expect(screen.getByText('每周复盘一次')).toBeVisible()
  ```

  Add a second assertion to the existing bare completed fixture test, or a small dedicated test, that `queryByTestId('completed-meeting-outcomes')` is absent when the snapshot has no meeting-level lists.

- [ ] **Step 3: Run the focused test to prove it fails before the UI exists**

  Run from `frontend/`:

  ```bash
  npm test -- --run src/tests/meeting-lifecycle.test.ts
  ```

  Expected: FAIL because `completed-agenda-a1` and `completed-meeting-outcomes` do not yet exist.

### Task 2: Render normalized snapshot outcome accordions

**Files:**
- Modify: `frontend/src/components/CompletedMeetingChain.vue`

- [ ] **Step 1: Define narrow read-only snapshot view types and normalization helpers**

  Replace the direct `Record<string, any>` list casts with local structural types for the only fields the view renders:

  ```ts
  type SnapshotDecision = { id: string; title: string; decision_markdown: string; rationale_markdown: string; status: string }
  type SnapshotAction = { id: string; content: string; priority: string; due_date: string | null; status: string }
  type SnapshotQuestion = { id: string; question_markdown: string; status: string }
  type SnapshotOutcomeGroup = {
    id: string; testId: string; title: string; status: string | null
    decisions: SnapshotDecision[]; actions: SnapshotAction[]; openQuestions: SnapshotQuestion[]
  }
  ```

  Add the local read-only helpers below. They accept only the stable fields the screen renders, so a malformed or older snapshot degrades to an empty group instead of throwing during completed-meeting loading:

  ```ts
  type SnapshotRecord = Record<string, unknown>

  function record(value: unknown): SnapshotRecord {
    return value && typeof value === 'object' && !Array.isArray(value) ? value as SnapshotRecord : {}
  }
  function text(value: unknown): string { return typeof value === 'string' ? value : '' }
  function nullableText(value: unknown): string | null { return typeof value === 'string' && value ? value : null }
  function records(value: unknown): SnapshotRecord[] {
    return Array.isArray(value) ? value.filter((item): item is SnapshotRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : []
  }
  function decision(value: SnapshotRecord): SnapshotDecision {
    return { id: text(value.id), title: text(value.title), decision_markdown: text(value.decision_markdown), rationale_markdown: text(value.rationale_markdown), status: text(value.status) }
  }
  function action(value: SnapshotRecord): SnapshotAction {
    return { id: text(value.id), content: text(value.content), priority: text(value.priority), due_date: nullableText(value.due_date), status: text(value.status) }
  }
  function question(value: SnapshotRecord): SnapshotQuestion {
    return { id: text(value.id), question_markdown: text(value.question_markdown), status: text(value.status) }
  }
  function group(source: SnapshotRecord, id: string, testId: string, title: string, status: string | null, decisionKey = 'decisions', actionKey = 'actions', questionKey = 'open_questions'): SnapshotOutcomeGroup {
    return { id, testId, title, status, decisions: records(source[decisionKey]).map(decision), actions: records(source[actionKey]).map(action), openQuestions: records(source[questionKey]).map(question) }
  }
  ```

  Preserve the current `snapshot_json ?? snapshot ?? {}` compatibility expression, but pass it through `record` before accessing nested values. Missing or malformed `decisions`, `actions`, `open_questions`, `meeting_decisions`, `meeting_actions`, and `meeting_open_questions` therefore normalize to empty arrays.

- [ ] **Step 2: Derive agenda and meeting-level groups exclusively from the snapshot**

  Build the computed values from the normalized snapshot with the helpers defined in the preceding step:

  ```ts
  const snapshot = computed(() => record(props.meeting.current_snapshot?.snapshot_json ?? props.meeting.current_snapshot?.snapshot ?? {}))
  const snapshotMeeting = computed(() => record(snapshot.value.meeting))
  const snapshotAgenda = computed<SnapshotOutcomeGroup[]>(() => records(snapshot.value.agenda_items).map((item) =>
    group(item, text(item.id), `completed-agenda-${text(item.id)}`, text(item.title), nullableText(item.status)),
  ))
  const meetingOutcomes = computed<SnapshotOutcomeGroup | null>(() => {
    const value = group(snapshot.value, 'meeting-outcomes', 'completed-meeting-outcomes', '会议级产出', null, 'meeting_decisions', 'meeting_actions', 'meeting_open_questions')
    return value.decisions.length || value.actions.length || value.openQuestions.length ? value : null
  })
  const outcomeGroups = computed(() => meetingOutcomes.value ? [...snapshotAgenda.value, meetingOutcomes.value] : snapshotAgenda.value)
  ```

  Use `id: 'meeting-outcomes'`, `title: '会议级产出'`, and `status: null` for the latter. Do not read the similarly named mutable fields on `Meeting` for either result.

- [ ] **Step 3: Replace count-only cards with semantic multi-expand accordions**

  Replace the current `article v-for` inside `.completed-agenda-list` with a `details` element per `outcomeGroups` group:

  ```vue
  <details :data-testid="item.testId" class="completed-outcome-accordion">
    <summary class="completed-outcome-summary">
      <div>
        <span v-if="item.status" class="status-pill">{{ item.status }}</span>
        <strong>{{ item.title }}</strong>
      </div>
      <dl aria-label="产出数量">
        <div><dt>决策</dt><dd>{{ item.decisions.length }}</dd></div>
        <div><dt>行动</dt><dd>{{ item.actions.length }}</dd></div>
        <div><dt>开放问题</dt><dd>{{ item.openQuestions.length }}</dd></div>
      </dl>
    </summary>
    <div class="completed-outcome-body">
      <section v-if="item.decisions.length" class="completed-outcome-group">
        <h3>决策 <span>{{ item.decisions.length }}</span></h3>
        <article v-for="decision in item.decisions" :key="decision.id" class="completed-outcome-row">
          <header><strong>{{ decision.title }}</strong><span class="status-pill">{{ decision.status }}</span></header>
          <MarkdownView :source="decision.decision_markdown" empty-text="未记录决策正文" />
          <div v-if="decision.rationale_markdown" class="completed-outcome-rationale"><span>依据</span><MarkdownView :source="decision.rationale_markdown" /></div>
        </article>
      </section>
      <section v-if="item.actions.length" class="completed-outcome-group">
        <h3>行动项 <span>{{ item.actions.length }}</span></h3>
        <article v-for="action in item.actions" :key="action.id" class="completed-outcome-row">
          <header><strong>{{ action.content }}</strong><span class="status-pill">{{ action.status }}</span></header>
          <p class="completed-outcome-meta">优先级：{{ action.priority || '未设置' }}<template v-if="action.due_date"> · 截止：{{ action.due_date }}</template></p>
        </article>
      </section>
      <section v-if="item.openQuestions.length" class="completed-outcome-group">
        <h3>开放问题 <span>{{ item.openQuestions.length }}</span></h3>
        <article v-for="question in item.openQuestions" :key="question.id" class="completed-outcome-row">
          <header><span>问题</span><span class="status-pill">{{ question.status }}</span></header>
          <MarkdownView :source="question.question_markdown" empty-text="未记录问题正文" />
        </article>
      </section>
      <p v-if="!item.decisions.length && !item.actions.length && !item.openQuestions.length" class="empty-inline">本议题未记录产出</p>
    </div>
  </details>
  ```

  Render the three group sections in fixed order only when non-empty. Reuse `MarkdownView` for `decision_markdown`, non-empty `rationale_markdown`, and `question_markdown`; render action `content` as text. Use the existing `status-pill` for statuses and simple metadata text for action priority and due date. If all three group lists are empty, show `本议题未记录产出` inside the body.

  The `outcomeGroups` order keeps `meetingOutcomes` after all agenda groups. Its `status: null` means the existing `v-if="item.status"` omits the agenda status pill, and its `testId` is `completed-meeting-outcomes`; it is absent when `meetingOutcomes` is null.

- [ ] **Step 4: Run the focused test and confirm the read-only snapshot behavior passes**

  Run from `frontend/`:

  ```bash
  npm test -- --run src/tests/meeting-lifecycle.test.ts
  ```

  Expected: PASS, including the new closed-by-default, multi-expand, empty-state, meeting-level, and snapshot-source assertions.

### Task 3: Add restrained accordion styling and verify the frontend

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/tests/meeting-lifecycle.test.ts`

- [ ] **Step 1: Add completed-outcome accordion styles next to the existing completed meeting rules**

  Replace the old `.completed-agenda-list article` rules with focused styles for:

  ```css
  .completed-outcome-accordion { border: 1px solid #e4e7eb; border-radius: 10px; background: #fff; overflow: hidden; }
  .completed-outcome-summary { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 13px; cursor: pointer; list-style: none; }
  .completed-outcome-summary::-webkit-details-marker { display: none; }
  .completed-outcome-summary::after { content: '⌄'; color: #7d8792; transition: transform .15s ease; }
  .completed-outcome-accordion[open] .completed-outcome-summary::after { transform: rotate(180deg); }
  .completed-outcome-body { padding: 0 13px 13px; border-top: 1px solid #edf0f3; background: #fafbfc; }
  ```

  Add compact grid styles for the count `dl`, outcome group headings, and outcome rows. Preserve the existing `.status-pill` colors and use no new animation except the short chevron rotation. Add the 900px rule that stacks `.completed-outcome-summary` content and keeps the count grid legible.

- [ ] **Step 2: Run focused frontend tests and production build**

  Run from `frontend/`:

  ```bash
  npm test -- --run src/tests/meeting-lifecycle.test.ts
  npm run build
  ```

  Expected: all focused lifecycle tests pass and Vite completes successfully. Treat only the known bundle-size advisory, if emitted, as non-blocking.

- [ ] **Step 3: Run the complete frontend suite and whitespace validation**

  Run from `frontend/`, then repository root:

  ```bash
  npm test -- --run
  git diff --check
  ```

  Expected: all frontend test files pass and `git diff --check` produces no output.

- [ ] **Step 4: Visually validate the completed meeting in an isolated browser session**

  Use the `testing-isolated-web-ui` skill so existing Docker data remains untouched. Seed or use an isolated completed meeting that has one agenda outcome of each type, one empty agenda, and one meeting-level decision. Confirm:

  1. closed cards show title, status, and three counts;
  2. two agenda cards can remain open together;
  3. all detailed fields render read-only from the snapshot;
  4. meeting-level outcomes appear only when present;
  5. the narrow viewport retains readable counts and expanded content.

- [ ] **Step 5: Commit the completed feature**

  From repository root, stage only the three task files and commit:

  ```bash
  git add frontend/src/components/CompletedMeetingChain.vue frontend/src/styles.css frontend/src/tests/meeting-lifecycle.test.ts
  git commit -m "feat: expand completed meeting outcomes"
  ```

  Do not stage unrelated worktree changes, including `backend/tests/migrations/test_fresh_baseline.py`, `backend/tests/plugins/test_jobs.py`, `frontend/src/tests/home-attention.test.ts`, or untracked planning documents.
