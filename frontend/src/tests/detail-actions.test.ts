import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MeetingDetailView from '../views/MeetingDetailView.vue'
import OpenActionsView from '../views/OpenActionsView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'm1' } }),
  useRouter: () => ({ push: pushMock }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const meeting = {
  id: 'm1', title: '黑客松产品讨论', project: 'MeetFlow', meeting_type: '方案讨论',
  meeting_date: '2026-07-17T14:30:00Z', participants: ['陈曦'],
  raw_notes_markdown: '## 原始记录', conclusions_markdown: '- 完成 MVP',
  actions: [], attachments: [], updates: [], created_by: { display_name: 'Admin' }, updated_by: { display_name: 'Admin' },
  created_at: '2026-07-17T14:30:00Z', updated_at: '2026-07-17T14:30:00Z',
}

describe('meeting detail', () => {
  beforeEach(() => { apiMock.mockReset(); pushMock.mockReset() })

  it('loads the package and saves an edited notes draft', async () => {
    const coreMeeting = { ...meeting, raw_notes_markdown: '## 新记录' } as Record<string, unknown>
    delete coreMeeting.actions
    delete coreMeeting.attachments
    delete coreMeeting.updates
    apiMock.mockResolvedValueOnce(meeting).mockResolvedValueOnce(coreMeeting)
    render(MeetingDetailView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(await screen.findByText('黑客松产品讨论')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '会议记录' }))
    await fireEvent.update(screen.getByLabelText('原始会议记录'), '## 新记录')
    await fireEvent.click(screen.getByRole('button', { name: '保存会议' }))
    expect(apiMock).toHaveBeenLastCalledWith('/api/meetings/m1', expect.objectContaining({
      method: 'PUT', body: expect.stringContaining('## 新记录'),
    }))
    expect(screen.getByRole('button', { name: '附件 0' })).toBeInTheDocument()
  })

  it('requires destructive confirmation before deleting a meeting', async () => {
    apiMock.mockResolvedValueOnce(meeting).mockResolvedValueOnce(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(MeetingDetailView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await screen.findByText('黑客松产品讨论')
    await fireEvent.click(screen.getByRole('button', { name: '删除会议' }))
    expect(window.confirm).toHaveBeenCalledWith('删除后将同时移除行动项和附件，确定继续？')
    expect(apiMock).toHaveBeenLastCalledWith('/api/meetings/m1', { method: 'DELETE' })
    expect(pushMock).toHaveBeenCalledWith('/')
  })

  it('preserves unsaved meeting edits when a child resource refreshes', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/plugins/actions') return Promise.resolve([])
      if (path === '/api/meetings/m1/actions') return Promise.resolve({ id: 'a1' })
      if (path === '/api/meetings/m1') return Promise.resolve(meeting)
      return Promise.resolve(undefined)
    })
    render(MeetingDetailView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await screen.findByText('黑客松产品讨论')
    await fireEvent.click(screen.getByRole('button', { name: '会议记录' }))
    await fireEvent.update(screen.getByLabelText('会议标题'), '尚未保存的新标题')
    await fireEvent.click(screen.getByRole('button', { name: /^行动项/ }))
    await fireEvent.update(screen.getByLabelText('行动内容'), '新增动作')
    await fireEvent.click(screen.getByRole('button', { name: '添加行动项' }))
    await waitFor(() => expect(screen.getByLabelText('行动内容')).toHaveValue(''))
    await fireEvent.click(screen.getByRole('button', { name: '会议记录' }))
    expect(screen.getByLabelText('会议标题')).toHaveValue('尚未保存的新标题')
  })

  it('keeps a new action draft when its request fails', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/plugins/actions') return Promise.resolve([])
      if (path === '/api/meetings/m1/actions') throw new Error('保存行动项失败')
      return Promise.resolve(meeting)
    })
    render(MeetingDetailView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await screen.findByText('黑客松产品讨论')
    await fireEvent.click(screen.getByRole('button', { name: /^行动项/ }))
    await fireEvent.update(screen.getByLabelText('行动内容'), '不能丢失的输入')
    await fireEvent.click(screen.getByRole('button', { name: '添加行动项' }))
    expect(await screen.findByText('保存行动项失败')).toBeInTheDocument()
    expect(screen.getByLabelText('行动内容')).toHaveValue('不能丢失的输入')
  })
})

describe('open actions', () => {
  it('groups open actions and marks an item done', async () => {
    const item = { id: 'a1', meeting_id: 'm1', meeting_title: '黑客松产品讨论', content: '整理演示脚本', owner: '林宇', due_date: null, status: 'open', created_by: { display_name: 'Admin' }, created_at: '', updated_at: '' }
    apiMock.mockReset().mockResolvedValueOnce([item]).mockResolvedValueOnce({ ...item, status: 'done' }).mockResolvedValueOnce([])
    render(OpenActionsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(await screen.findByText('整理演示脚本')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '标记完成' }))
    expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/actions/a1', expect.objectContaining({ method: 'PUT' }))
    await waitFor(() => expect(screen.getByText('所有行动项都已完成')).toBeInTheDocument())
  })
})
