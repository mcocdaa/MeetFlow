import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import { session } from '../auth/session'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const lin = { id: 'u1', username: 'lin', display_name: '林宇' }
const qiao = { id: 'u2', username: 'qiao', display_name: '乔一' }

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: lin, target_date: null, version: 3,
  memberships: [
    { role: 'member', user: lin },
    { role: 'stakeholder', user: qiao },
  ],
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
  updates: [], next_meeting: null, recent_decisions: [], meeting_count: 0, decision_count: 0, open_action_count: 0,
  series_summaries: [], attachments: [], created_by: lin, updated_by: lin, created_at: '', updated_at: '',
} as any

const decisions = [
  {
    id: 'd1', project_id: 'p1', meeting_id: 'm1', agenda_item_id: null,
    title: '采用方案 A', decision_markdown: '采用方案 A 落地', rationale_markdown: '成本更低',
    status: 'proposed', is_derived: false, created_by: 'u1', decided_by_user_id: null,
    reviewers: [
      { user_id: 'u2', status: 'pending', responded_at: null, comment: '' },
    ],
    version: 3, created_at: '', updated_at: '',
  },
  {
    id: 'd2', project_id: 'p1', meeting_id: null, agenda_item_id: null,
    title: '迁移到新架构', decision_markdown: '全面迁移', rationale_markdown: '',
    status: 'final', is_derived: false, created_by: 'u1', decided_by_user_id: 'u2',
    reviewers: [{ user_id: 'u1', status: 'approved', responded_at: '2026-07-02T02:00:00Z', comment: '可以' }],
    supersedes_decision_id: 'd0', version: 2, created_at: '', updated_at: '',
  },
  {
    id: 'd3', project_id: 'p1', meeting_id: null, agenda_item_id: null,
    title: '采用方案 B', decision_markdown: '备选', rationale_markdown: '',
    status: 'final', is_derived: false, created_by: 'u1', decided_by_user_id: null,
    reviewers: [], version: 1, created_at: '', updated_at: '',
  },
  {
    id: 'd4', project_id: 'p1', meeting_id: 'm1', agenda_item_id: null,
    title: '议题生成的决策', decision_markdown: '自动', rationale_markdown: '',
    status: 'proposed', is_derived: true, created_by: 'u1', decided_by_user_id: null,
    reviewers: [{ user_id: 'u2', status: 'pending', responded_at: null, comment: '' }],
    version: 1, created_at: '', updated_at: '',
  },
  {
    id: 'd5', project_id: 'p1', meeting_id: null, agenda_item_id: null,
    title: '被替代的决策', decision_markdown: '旧方案', rationale_markdown: '',
    status: 'superseded', is_derived: false, created_by: 'u1', decided_by_user_id: 'u1',
    reviewers: [], supersedes_decision_id: null, version: 4, created_at: '', updated_at: '',
  },
]

function mockDecisions(items: unknown[]) {
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    if (path.startsWith('/api/decisions/') && (init?.method === 'POST' || init?.method === 'PUT')) {
      return Promise.resolve({ id: path.split('/')[3] })
    }
    if (path.startsWith('/api/decisions?')) {
      const url = new URL(`http://localhost${path}`)
      const status = url.searchParams.get('status')
      const filtered = status ? items.filter((item: any) => item.status === status) : items
      return Promise.resolve({ items: filtered, total: filtered.length, limit: 200, offset: 0 })
    }
    return Promise.resolve({})
  })
}

function renderDecisions(items: unknown[], canContribute = true) {
  mockDecisions(items)
  return renderWithProviders(ProjectRecordTabs, { props: { project, tab: 'decisions', canContribute } })
}

async function openDecision(title: string) {
  await fireEvent.click(await screen.findByRole('button', { name: `查看决策“${title}”` }))
  return screen.findByRole('heading', { name: '决策详情' })
}

function decisionCall(id: string, suffix = '', method = 'POST') {
  return apiMock.mock.calls.find(([path, init]) => (
    path === `/api/decisions/${id}${suffix}` && (init as RequestInit | undefined)?.method === method
  ))
}

async function selectOption(selectSelector: string, label: string) {
  await fireEvent.click(document.querySelector(`${selectSelector} .n-base-selection`)!)
  const option = await waitFor(() => {
    const candidate = [...document.querySelectorAll('.n-base-select-option__content')]
      .find((item) => item.textContent === label)
    if (!candidate) throw new Error(`option ${label} is not open yet`)
    return candidate
  })
  await fireEvent.click(option)
}

describe('decision workflow', () => {
  beforeEach(() => {
    apiMock.mockReset()
    session.user = { id: 'u2', username: 'qiao', display_name: '乔一', role: 'member', status: 'active' }
    session.loaded = true
  })

  it('shows the decision detail with reviewers and the supersession chain', async () => {
    renderDecisions(decisions)
    await openDecision('采用方案 A')

    expect(await screen.findByText('采用方案 A 落地')).toBeInTheDocument()
    expect(screen.getByText('成本更低')).toBeInTheDocument()
    expect(screen.getByText(/创建人/)).toHaveTextContent('林宇')
    expect(screen.getByText('待评审')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    await openDecision('迁移到新架构')
    expect(await screen.findByText('全面迁移')).toBeInTheDocument()
    expect(screen.getByText(/定稿人/)).toHaveTextContent('乔一')
    expect(screen.getByText('已同意')).toBeInTheDocument()
    expect(screen.getByText('可以')).toBeInTheDocument()
    expect(screen.getByText(/替代了决策/)).toHaveTextContent('d0')
  })

  it('renders a superseded decision as replaced', async () => {
    renderDecisions([decisions[4]])
    await openDecision('被替代的决策')

    expect(await screen.findByText('已被替代')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
  })

  it('edits, finalizes, and withdraws a proposed decision', async () => {
    renderDecisions(decisions)
    await openDecision('采用方案 A')

    await fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    await fireEvent.update(await screen.findByLabelText('决策标题'), '采用方案 A（修订）')
    await selectOption('.decision-edit-reviewers', '林宇')
    await fireEvent.click(screen.getByRole('button', { name: '保存修改' }))
    await waitFor(() => expect(decisionCall('d1', '', 'PUT')).toBeTruthy())
    expect(JSON.parse(String((decisionCall('d1', '', 'PUT')![1] as RequestInit).body))).toMatchObject({
      title: '采用方案 A（修订）',
      decision_markdown: '采用方案 A 落地',
      rationale_markdown: '成本更低',
      reviewer_ids: ['u2', 'u1'],
      expected_version: 3,
    })

    await fireEvent.click(screen.getByRole('button', { name: '定稿' }))
    await fireEvent.click(await screen.findByRole('button', { name: '确认' }))
    await waitFor(() => expect(decisionCall('d1', '/finalize')).toBeTruthy())
    expect(JSON.parse(String((decisionCall('d1', '/finalize')![1] as RequestInit).body))).toEqual({ expected_version: 3 })

    await fireEvent.click(screen.getByRole('button', { name: '撤回' }))
    await waitFor(() => expect(decisionCall('d1', '/withdraw')).toBeTruthy())
    expect(JSON.parse(String((decisionCall('d1', '/withdraw')![1] as RequestInit).body))).toEqual({ expected_version: 3 })
  })

  it('accepts a review from the assigned pending reviewer', async () => {
    renderDecisions([decisions[0]])
    await openDecision('采用方案 A')

    expect(await screen.findByRole('heading', { name: '提交评审' })).toBeInTheDocument()
    await selectOption('.decision-review-status', '同意')
    await fireEvent.update(screen.getByLabelText('评审意见'), '同意推进')
    await fireEvent.click(screen.getByRole('button', { name: '提交评审' }))

    await waitFor(() => expect(decisionCall('d1', '/review')).toBeTruthy())
    expect(JSON.parse(String((decisionCall('d1', '/review')![1] as RequestInit).body))).toEqual({
      status: 'approved',
      comment: '同意推进',
      expected_version: 3,
    })
  })

  it('supersedes a final decision with another final decision of the same project', async () => {
    renderDecisions(decisions)
    await openDecision('迁移到新架构')

    expect(await screen.findByRole('heading', { name: '替代决策' })).toBeInTheDocument()
    await selectOption('.decision-supersede-select', '采用方案 B')
    await fireEvent.click(screen.getByRole('button', { name: '确认替代' }))

    await waitFor(() => expect(decisionCall('d2', '/supersede')).toBeTruthy())
    expect(JSON.parse(String((decisionCall('d2', '/supersede')![1] as RequestInit).body))).toEqual({
      new_decision_id: 'd3',
      expected_version: 2,
      expected_new_version: 1,
    })
  })

  it('keeps derived decisions read-only', async () => {
    renderDecisions([decisions[3]])
    await openDecision('议题生成的决策')

    expect(await screen.findByText('自动')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '定稿' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '提交评审' })).not.toBeInTheDocument()
  })

  it('renders no write entries for read-only members', async () => {
    renderDecisions(decisions, false)
    await openDecision('采用方案 A')

    expect(await screen.findByText('采用方案 A 落地')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '定稿' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '撤回' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '提交评审' })).not.toBeInTheDocument()
  })
})
