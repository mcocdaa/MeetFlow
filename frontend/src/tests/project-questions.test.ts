import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectQuestionsTab from '../components/ProjectQuestionsTab.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  api: apiMock,
}))
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

const future = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
const past = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString()

const questions = [
  {
    id: 'q1', project_id: 'p1', meeting_id: 'm1', agenda_item_id: null,
    question_markdown: '是否需要多语言', owner_user_id: 'u1', status: 'open', is_derived: false,
    scheduled_meeting_id: null, resolved_by_decision_id: null,
    converted_from_agenda_item_id: null, source_agenda_item_id: null,
    version: 2, created_at: '', updated_at: '',
  },
  {
    id: 'q2', project_id: 'p1', meeting_id: null, agenda_item_id: null,
    question_markdown: '已放弃的问题', owner_user_id: null, status: 'dropped', is_derived: false,
    scheduled_meeting_id: null, resolved_by_decision_id: null,
    converted_from_agenda_item_id: null, source_agenda_item_id: null,
    version: 1, created_at: '', updated_at: '',
  },
  {
    id: 'q3', project_id: 'p1', meeting_id: 'm2', agenda_item_id: null,
    question_markdown: '已排期的问题', owner_user_id: 'u2', status: 'scheduled', is_derived: false,
    scheduled_meeting_id: 'm2', resolved_by_decision_id: null,
    converted_from_agenda_item_id: null, source_agenda_item_id: null,
    version: 3, created_at: '', updated_at: '',
  },
  {
    id: 'q4', project_id: 'p1', meeting_id: null, agenda_item_id: null,
    question_markdown: '已解决的问题', owner_user_id: null, status: 'resolved', is_derived: false,
    scheduled_meeting_id: null, resolved_by_decision_id: 'd1',
    converted_from_agenda_item_id: 'ag2', source_agenda_item_id: null,
    version: 4, created_at: '', updated_at: '',
  },
  {
    id: 'q5', project_id: 'p1', meeting_id: 'm1', agenda_item_id: null,
    question_markdown: '派生问题', owner_user_id: null, status: 'open', is_derived: true,
    scheduled_meeting_id: null, resolved_by_decision_id: null,
    converted_from_agenda_item_id: null, source_agenda_item_id: 'ag1',
    version: 1, created_at: '', updated_at: '',
  },
]

function mockQuestions(items: unknown[], extras: (path: string) => unknown = () => undefined) {
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    const extra = extras(path)
    if (extra !== undefined) return Promise.resolve(extra)
    if (path === '/api/projects/p1/open-questions?limit=200') {
      return Promise.resolve(items)
    }
    if (path.startsWith('/api/open-questions/') && init?.method === 'POST') {
      return Promise.resolve({ id: path.split('/')[3] })
    }
    if (path.startsWith('/api/open-questions/') && init?.method === 'PUT') {
      return Promise.resolve({ id: path.split('/')[3] })
    }
    return Promise.resolve({})
  })
}

function renderQuestions(items: unknown[], canContribute = true, extras?: (path: string) => unknown) {
  mockQuestions(items, extras)
  return renderWithProviders(ProjectQuestionsTab, { props: { project, canContribute } })
}

function questionCall(id: string, suffix = '', method = 'POST') {
  return apiMock.mock.calls.find(([path, init]) => (
    path === `/api/open-questions/${id}${suffix}` && (init as RequestInit | undefined)?.method === method
  ))
}

async function selectOption(selectSelector: string, label: string, match: 'exact' | 'prefix' = 'exact') {
  await fireEvent.click(document.querySelector(`${selectSelector} .n-base-selection`)!)
  const option = await waitFor(() => {
    const candidate = [...document.querySelectorAll('.n-base-select-option__content')]
      .find((item) => (match === 'exact'
        ? item.textContent === label
        : item.textContent?.startsWith(label)))
    if (!candidate) throw new Error(`option ${label} is not open yet`)
    return candidate
  })
  await fireEvent.click(option)
}

describe('project open questions', () => {
  beforeEach(() => {
    apiMock.mockReset()
  })

  it('lists open questions with status, owner, and provenance', async () => {
    renderQuestions(questions)

    expect(await screen.findByText('是否需要多语言')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/open-questions?limit=200')
    expect(screen.getAllByText('待解答').length).toBeGreaterThan(0)
    expect(screen.getByText(/林宇/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '来源会议' })[0]).toHaveAttribute('href', '/meetings/m1')
    expect(screen.getByText('已放弃')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '放弃' })).not.toBeInTheDocument()
    expect(screen.getByText(/已排入会议/)).toHaveTextContent('m2')
    expect(screen.getByText(/由决策解决/)).toHaveTextContent('d1')
    expect(screen.getByText(/来源议程 ag2/)).toBeInTheDocument()
  })

  it('creates a question from the drawer without source fields', async () => {
    renderQuestions([])
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/open-questions?limit=200'))

    await fireEvent.click(screen.getByRole('button', { name: '添加开放问题' }))
    expect(await screen.findByRole('heading', { name: '添加开放问题' })).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('问题内容'), '是否需要多语言')
    await selectOption('.question-owner-select', '乔一')
    await fireEvent.click(screen.getByRole('button', { name: '提交' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/open-questions', expect.objectContaining({ method: 'POST' })))
    const call = apiMock.mock.calls.find(([path, init]) => (
      path === '/api/projects/p1/open-questions' && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      question_markdown: '是否需要多语言',
      owner_user_id: 'u2',
    })
  })

  it('edits a question with its expected version', async () => {
    renderQuestions(questions)
    await fireEvent.click(await screen.findByRole('button', { name: '编辑开放问题“是否需要多语言”' }))
    expect(await screen.findByRole('heading', { name: '编辑开放问题' })).toBeInTheDocument()

    await fireEvent.update(screen.getByLabelText('问题内容'), '是否需要多语言支持')
    await selectOption('.question-owner-select', '乔一')
    await fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

    await waitFor(() => expect(questionCall('q1', '', 'PUT')).toBeTruthy())
    expect(JSON.parse(String((questionCall('q1', '', 'PUT')![1] as RequestInit).body))).toEqual({
      question_markdown: '是否需要多语言支持',
      owner_user_id: 'u2',
      expected_version: 2,
    })
  })

  it('hides editing for derived questions', async () => {
    renderQuestions([questions[4]])
    expect(await screen.findByText('派生问题')).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: '编辑开放问题“派生问题”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '排期开放问题“派生问题”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '解决开放问题“派生问题”' })).not.toBeInTheDocument()
  })

  it('schedules an open question into a future meeting of the same project', async () => {
    renderQuestions(questions, true, (path) => {
      if (path === '/api/meetings?project_id=p1&limit=200') {
        return {
          items: [
            { id: 'm2', title: '迭代评审', scheduled_start: future, status: 'ready', version: 5 },
            { id: 'm3', title: '已取消的会议', scheduled_start: future, status: 'canceled', version: 1 },
            { id: 'm4', title: '过去的会议', scheduled_start: past, status: 'ready', version: 1 },
          ],
          total: 3, limit: 200, offset: 0,
        }
      }
      return undefined
    })

    await fireEvent.click(await screen.findByRole('button', { name: '排期开放问题“是否需要多语言”' }))
    expect(await screen.findByRole('heading', { name: '排期开放问题' })).toBeInTheDocument()
    await selectOption('.question-schedule-meeting', '迭代评审', 'prefix')
    await fireEvent.click(screen.getByRole('button', { name: '确认排期' }))

    await waitFor(() => expect(questionCall('q1', '/schedule')).toBeTruthy())
    expect(JSON.parse(String((questionCall('q1', '/schedule')![1] as RequestInit).body))).toEqual({
      meeting_id: 'm2',
      expected_version: 2,
      expected_meeting_version: 5,
    })

    expect(screen.queryByRole('button', { name: '排期开放问题“已排期的问题”' })).not.toBeInTheDocument()
  })

  it('resolves a question with and without a final decision', async () => {
    renderQuestions(questions, true, (path) => {
      if (path === '/api/decisions?project_id=p1&status=final&limit=200') {
        return {
          items: [{
            id: 'd1', project_id: 'p1', title: '采用方案 A', decision_markdown: '采用', rationale_markdown: '',
            status: 'final', is_derived: false, created_by: 'u1', reviewers: [], version: 4,
            created_at: '', updated_at: '',
          }],
          total: 1, limit: 200, offset: 0,
        }
      }
      return undefined
    })

    await fireEvent.click(await screen.findByRole('button', { name: '解决开放问题“是否需要多语言”' }))
    expect(await screen.findByRole('heading', { name: '解决开放问题' })).toBeInTheDocument()
    await selectOption('.question-resolve-decision', '采用方案 A')
    await fireEvent.click(screen.getByRole('button', { name: '确认解决' }))
    await waitFor(() => expect(questionCall('q1', '/resolve')).toBeTruthy())
    expect(JSON.parse(String((questionCall('q1', '/resolve')![1] as RequestInit).body))).toEqual({
      decision_id: 'd1',
      expected_version: 2,
    })

    await fireEvent.click(screen.getByRole('button', { name: '解决开放问题“是否需要多语言”' }))
    await screen.findByRole('heading', { name: '解决开放问题' })
    await fireEvent.click(screen.getByRole('button', { name: '确认解决' }))
    await waitFor(() => expect(
      apiMock.mock.calls.filter(([path, init]) => (
        path === '/api/open-questions/q1/resolve'
        && (init as RequestInit | undefined)?.method === 'POST'
        && JSON.parse(String((init as RequestInit).body)).decision_id === null
      )).length,
    ).toBe(1))
  })

  it('hides every write entry from read-only members', async () => {
    renderQuestions(questions, false)
    expect(await screen.findByText('是否需要多语言')).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: '添加开放问题' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑开放问题“是否需要多语言”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '排期开放问题“是否需要多语言”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '解决开放问题“是否需要多语言”' })).not.toBeInTheDocument()
  })
})
