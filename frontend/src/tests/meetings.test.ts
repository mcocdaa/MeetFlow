import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MarkdownView from '../components/MarkdownView.vue'
import MeetingsView from '../views/MeetingsView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushMock }) }))

const meeting = {
  id: 'm1', title: 'GRPO 数据集方案讨论', project: 'LLM Post-training', meeting_type: '方案评审',
  meeting_date: '2026-07-17T13:30:00Z', participants: ['陈曦', '林宇'], conclusion_count: 2,
  action_count: 2, open_action_count: 1, attachment_count: 1,
  created_by: { display_name: 'Admin' }, updated_by: { display_name: 'Admin' },
}

describe('meeting timeline', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
  })

  it('renders and searches meetings by title or project', async () => {
    apiMock.mockResolvedValue([meeting])
    render(MeetingsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(await screen.findByText('GRPO 数据集方案讨论')).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('搜索会议'), 'GRPO')
    await fireEvent.submit(screen.getByRole('search'))
    expect(apiMock).toHaveBeenLastCalledWith('/api/meetings?q=GRPO')
  })

  it('does not render an undefined total when the API only returns open action count', async () => {
    const summary = { ...meeting } as Partial<typeof meeting>
    delete summary.action_count
    apiMock.mockResolvedValue([summary])
    render(MeetingsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await screen.findByText('GRPO 数据集方案讨论')
    expect(screen.getByText('1 项待办')).toBeInTheDocument()
  })

  it('creates a meeting and opens its detail page', async () => {
    apiMock.mockResolvedValueOnce([]).mockResolvedValueOnce({ id: 'm2' })
    render(MeetingsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings?q='))
    await fireEvent.click(screen.getByRole('button', { name: '新建会议' }))
    await fireEvent.update(screen.getByLabelText('会议标题'), '黑客松产品讨论')
    await fireEvent.update(screen.getByLabelText('会议时间'), '2026-07-17T14:30')
    await fireEvent.click(screen.getByRole('button', { name: '创建并继续' }))
    expect(apiMock).toHaveBeenLastCalledWith('/api/meetings', expect.objectContaining({ method: 'POST' }))
    expect(pushMock).toHaveBeenCalledWith('/meetings/m2')
  })
})

describe('MarkdownView', () => {
  it('renders Markdown and sanitizes dangerous HTML attributes', () => {
    const { container } = render(MarkdownView, { props: { source: '# 结论\n<img src=x onerror="alert(1)">' } })
    expect(screen.getByRole('heading', { name: '结论' })).toBeInTheDocument()
    expect(container.querySelector('img')).not.toHaveAttribute('onerror')
  })
})
