import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import SeriesEditDrawer from '../components/SeriesEditDrawer.vue'
import { session } from '../auth/session'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const lin = { id: 'u1', username: 'lin', display_name: '林宇' }
const qiao = { id: 'u2', username: 'qiao', display_name: '乔一' }
const members = [lin, qiao]

const seriesDetail = {
  id: 's1',
  project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' },
  title: '产品周会',
  purpose_markdown: '同步产品进展',
  recurrence_description: '每周一 10:00（Asia/Shanghai）',
  recurrence: {
    frequency: 'weekly',
    interval: 1,
    weekday: 0,
    month_day: null,
    month: null,
    local_time: '10:00:00',
    timezone: 'Asia/Shanghai',
    anchor_date: '2026-08-01',
  },
  default_duration_minutes: 60,
  default_host: lin,
  default_recorder: qiao,
  status: 'active',
  version: 3,
  participants: [
    { user: lin, participation_role: 'host', position: 0 },
    { user: qiao, participation_role: 'attendee', position: 1 },
  ],
  standing_items: [],
  created_by: lin,
  updated_by: lin,
  created_at: '',
  updated_at: '',
}

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: lin, target_date: null, version: 3,
  memberships: [
    { role: 'member', user: lin },
    { role: 'stakeholder', user: qiao },
  ],
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
  updates: [], next_meeting: null, recent_decisions: [], meeting_count: 0, decision_count: 0, open_action_count: 0,
  series_summaries: [{ id: 's1', title: '产品周会', status: 'active', recurrence_description: '每周一 10:00' }],
  attachments: [], created_by: lin, updated_by: lin, created_at: '', updated_at: '',
} as any

async function selectOption(selectSelector: string, label: string, scope: ParentNode = document) {
  const select = scope.querySelector(`${selectSelector} .n-base-selection`)
  if (!select) throw new Error(`select ${selectSelector} is missing`)
  await fireEvent.click(select)
  const option = await waitFor(() => {
    // Naive teleports every select menu to document.body, so options are never inside the row.
    const candidate = [...document.querySelectorAll('.n-base-select-option__content')]
      .find((item) => item.textContent === label)
    if (!candidate) throw new Error(`option ${label} is not open yet`)
    return candidate
  })
  await fireEvent.click(option)
}

function jsonBody(call: unknown[]) {
  return JSON.parse(String((call[1] as RequestInit).body))
}

function calledWithPath(path: string, method: string) {
  return apiMock.mock.calls.find(([calledPath, init]) => (
    calledPath === path && (init as RequestInit | undefined)?.method === method
  ))
}

async function openSeriesDrawer() {
  renderWithProviders(ProjectRecordTabs, { props: { project, tab: 'meetings', canContribute: true } })
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings?project_id=p1'))
  await fireEvent.click(await screen.findByRole('button', { name: '编辑系列“产品周会”' }))
  return screen.findByRole('heading', { name: '编辑系列' })
}

describe('series management', () => {
  beforeEach(() => {
    apiMock.mockReset()
    session.user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member', status: 'active' }
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/meeting-series/s1') return Promise.resolve(seriesDetail)
      if (path.startsWith('/api/meetings?')) return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 })
      return Promise.resolve({})
    })
  })

  it('loads the series detail into the edit drawer', async () => {
    await openSeriesDrawer()

    expect(apiMock).toHaveBeenCalledWith('/api/meeting-series/s1')
    expect(screen.getByLabelText('系列标题')).toHaveValue('产品周会')
    expect(screen.getByLabelText('系列说明')).toHaveValue('同步产品进展')
    expect(document.querySelector('.series-recurrence-frequency')?.textContent).toContain('每周')
    expect(document.querySelector('.series-recurrence-weekday')?.textContent).toContain('周一')
    expect(screen.getByLabelText('开始时间')).toHaveValue('10:00')
    expect(screen.getByLabelText('时区')).toHaveValue('Asia/Shanghai')
    expect(screen.getByLabelText('起始日期')).toHaveValue('2026-08-01')
    expect(screen.getByLabelText('默认会议时长')).toHaveValue('60')
    expect(document.querySelector('.series-default-host')?.textContent).toContain('林宇')
    expect(document.querySelector('.series-default-recorder')?.textContent).toContain('乔一')
    expect(document.querySelectorAll('.participant-editor-row')).toHaveLength(2)
    expect(screen.getByRole('heading', { name: '常设议题' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '添加常设议题' })).toBeInTheDocument()
  })

  it('clears the whole recurrence group when the frequency is removed', async () => {
    await openSeriesDrawer()

    await selectOption('.series-recurrence-frequency', '不设固定周期')
    await fireEvent.click(screen.getByRole('button', { name: '保存系列' }))

    await waitFor(() => expect(calledWithPath('/api/meeting-series/s1', 'PUT')).toBeTruthy())
    const payload = jsonBody(calledWithPath('/api/meeting-series/s1', 'PUT')!)
    expect(payload).toMatchObject({
      expected_version: 3,
      recurrence_frequency: null,
      recurrence_weekday: null,
      recurrence_month_day: null,
      recurrence_month: null,
      recurrence_local_time: null,
      recurrence_timezone: null,
      recurrence_anchor_date: null,
    })
    for (const key of ['recurrence_frequency', 'recurrence_weekday', 'recurrence_month_day', 'recurrence_month', 'recurrence_local_time', 'recurrence_timezone', 'recurrence_anchor_date']) {
      expect(payload).toHaveProperty(key, null)
    }
  })

  it('submits added standing items with the backend field names', async () => {
    await openSeriesDrawer()

    await fireEvent.click(screen.getByRole('button', { name: '添加常设议题' }))
    const row = document.querySelector('.standing-item-row') as HTMLElement
    await fireEvent.update(within(row).getByLabelText('常设议题标题'), '指标回顾')
    await selectOption('.standing-agenda-type', '信息同步', row)
    await selectOption('.standing-agenda-owner', '乔一', row)
    await fireEvent.update(within(row).getByLabelText('默认时长'), '30')
    await fireEvent.click(screen.getByRole('button', { name: '保存系列' }))

    await waitFor(() => expect(calledWithPath('/api/meeting-series/s1', 'PUT')).toBeTruthy())
    const payload = jsonBody(calledWithPath('/api/meeting-series/s1', 'PUT')!)
    expect(payload.standing_items).toEqual([
      {
        title: '指标回顾',
        agenda_type: 'information',
        default_owner_user_id: 'u2',
        default_duration_minutes: 30,
      },
    ])
  })

  it('archives a series after confirming', async () => {
    renderWithProviders(ProjectRecordTabs, { props: { project, tab: 'meetings', canContribute: true } })
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings?project_id=p1'))

    await fireEvent.click(await screen.findByRole('button', { name: '归档系列“产品周会”' }))
    expect(await screen.findByText('确定归档系列“产品周会”吗？')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => expect(calledWithPath('/api/meeting-series/s1', 'PUT')).toBeTruthy())
    expect(jsonBody(calledWithPath('/api/meeting-series/s1', 'PUT')!)).toEqual({
      expected_version: 3,
      status: 'archived',
    })
  })

  it('creates a series with participants and standing items in the same drawer', async () => {
    apiMock.mockResolvedValue({ id: 's2' } as never)
    renderWithProviders(SeriesEditDrawer, {
      props: { show: true, mode: 'create', projectId: 'p1', members },
    })

    await fireEvent.update(screen.getByLabelText('系列标题'), '产品周会')
    await fireEvent.click(screen.getByRole('button', { name: '添加常设议题' }))
    const row = document.querySelector('.standing-item-row') as HTMLElement
    await fireEvent.update(within(row).getByLabelText('常设议题标题'), '指标回顾')
    await selectOption('.standing-agenda-type', '信息同步', row)
    await selectOption('.standing-agenda-owner', '乔一', row)
    await fireEvent.update(within(row).getByLabelText('默认时长'), '15')
    await fireEvent.click(screen.getByRole('button', { name: '保存系列' }))

    await waitFor(() => expect(calledWithPath('/api/projects/p1/meeting-series', 'POST')).toBeTruthy())
    expect(jsonBody(calledWithPath('/api/projects/p1/meeting-series', 'POST')!)).toMatchObject({
      title: '产品周会',
      participants: [{ user_id: 'u1', participation_role: 'host' }],
      standing_items: [
        {
          title: '指标回顾',
          agenda_type: 'information',
          default_owner_user_id: 'u2',
          default_duration_minutes: 15,
        },
      ],
    })
  })

  it('hides every series write entry from read-only members', async () => {
    renderWithProviders(ProjectRecordTabs, { props: { project, tab: 'meetings', canContribute: false } })
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings?project_id=p1'))

    expect(screen.queryByRole('button', { name: '编辑系列“产品周会”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '归档系列“产品周会”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '临时添加会议“产品周会”' })).not.toBeInTheDocument()
  })
})
