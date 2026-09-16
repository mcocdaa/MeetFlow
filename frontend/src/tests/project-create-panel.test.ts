import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectCreatePanel from '../components/ProjectCreatePanel.vue'
import { api } from '../api/client'
import { renderWithProviders } from './helpers'

vi.mock('../api/client', () => ({ api: vi.fn() }))

const apiMock = vi.mocked(api)
const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: { id: 'u1', username: 'lin', display_name: '林宇' }, target_date: null, version: 1,
  memberships: [
    { role: 'member', user: { id: 'u1', username: 'lin', display_name: '林宇' } },
    { role: 'stakeholder', user: { id: 'u2', username: 'qiao', display_name: '乔一' } },
  ],
  updates: [], next_meeting: null, recent_decisions: [], open_actions: [],
  meeting_count: 0, decision_count: 0, open_action_count: 0, series_summaries: [], attachments: [],
  created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, updated_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '', updated_at: '',
} as any

function requestBody(index = 0) {
  return JSON.parse(String(apiMock.mock.calls[index]?.[1]?.body))
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

describe('project create panel', () => {
  beforeEach(() => { apiMock.mockReset() })

  it('submits a decision with reviewers and falls back to the title as its content', async () => {
    apiMock.mockResolvedValueOnce({ id: 'd1' } as never)
    renderWithProviders(ProjectCreatePanel, { props: { show: true, kind: 'decision', project } })

    await fireEvent.update(screen.getByLabelText('决策标题'), '采用方案 A')
    expect(screen.getByText('内容为空时以标题作为决策内容。')).toBeInTheDocument()
    await selectOption('.project-decision-reviewer-select', '乔一')
    await fireEvent.click(screen.getByRole('button', { name: '添加决策' }))

    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/decisions', expect.objectContaining({ method: 'POST' }))
    expect(requestBody()).toEqual({
      title: '采用方案 A',
      decision_markdown: '采用方案 A',
      rationale_markdown: '',
      reviewer_ids: ['u2'],
    })
  })

  it('submits an action with owner, due date, and priority', async () => {
    apiMock.mockResolvedValueOnce({ id: 'a1' } as never)
    renderWithProviders(ProjectCreatePanel, { props: { show: true, kind: 'action', project } })

    await fireEvent.update(screen.getByLabelText('行动项内容'), '确认范围')
    await selectOption('.project-action-owner-select', '乔一')
    await fireEvent.update(screen.getByLabelText('截止日期'), '2026-08-01')
    await fireEvent.click(screen.getByRole('button', { name: '添加行动项' }))

    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/actions', expect.objectContaining({ method: 'POST' }))
    expect(requestBody()).toEqual({
      project_id: 'p1',
      content: '确认范围',
      owner_user_id: 'u2',
      due_date: '2026-08-01',
      priority: 'normal',
    })
  })
})
