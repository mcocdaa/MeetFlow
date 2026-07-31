import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectCreatePanel from '../components/ProjectCreatePanel.vue'
import { api } from '../api/client'

vi.mock('../api/client', () => ({ api: vi.fn() }))
vi.mock('../auth/session', () => ({
  session: { user: { id: 'u1', username: 'lin', display_name: '林宇' } },
}))

const apiMock = vi.mocked(api)
const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: { id: 'u1', username: 'lin', display_name: '林宇' }, target_date: null, version: 1,
  memberships: [], updates: [], next_meeting: null, recent_decisions: [], open_actions: [],
  meeting_count: 0, decision_count: 0, open_action_count: 0, series_summaries: [], attachments: [],
  created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, updated_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '', updated_at: '',
} as any

describe('project series form', () => {
  beforeEach(() => apiMock.mockReset())

  it('submits a weekly series with an explicit timezone and local start time', async () => {
    apiMock.mockResolvedValueOnce({ id: 's1' } as never)
    render(ProjectCreatePanel, { props: { kind: 'series', project } })

    await fireEvent.update(screen.getByLabelText('系列标题'), '产品周会')
    await fireEvent.update(screen.getByLabelText('重复频率'), 'weekly')
    await fireEvent.update(screen.getByLabelText('每周星期'), '0')
    await fireEvent.update(screen.getByLabelText('开始时间'), '10:00')
    await fireEvent.update(screen.getByLabelText('时区'), 'Asia/Shanghai')
    await fireEvent.click(screen.getByRole('button', { name: '添加系列' }))

    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/meeting-series', expect.objectContaining({ method: 'POST' }))
    expect(JSON.parse(String(apiMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      title: '产品周会',
      recurrence_frequency: 'weekly',
      recurrence_weekday: 0,
      recurrence_local_time: '10:00:00',
      recurrence_timezone: 'Asia/Shanghai',
      recurrence_anchor_date: expect.any(String),
    })
  })

  it('uses the browser local calendar date as the default recurrence anchor', () => {
    class LocalCalendarDate extends Date {
      constructor() {
        super('2026-07-31T16:30:00.000Z')
      }

      getFullYear() { return 2026 }
      getMonth() { return 7 }
      getDate() { return 1 }
    }

    vi.stubGlobal('Date', LocalCalendarDate)
    try {
      render(ProjectCreatePanel, { props: { kind: 'series', project } })

      expect(screen.getByLabelText('起始日期')).toHaveValue('2026-08-01')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
