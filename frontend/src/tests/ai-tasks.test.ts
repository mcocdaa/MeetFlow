import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import PluginActionPanel from '../components/PluginActionPanel.vue'
import AiTasksView from '../views/AiTasksView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

beforeEach(() => apiMock.mockReset())

it('submits a meeting-summary job once instead of running a draft inline', async () => {
  apiMock.mockResolvedValueOnce([
    {
      action_id: 'ai-work-assistant.meeting_summary',
      label: '生成会议纪要',
      description: '生成草稿',
      input_schema: { type: 'object' },
      target_types: ['meeting'],
    },
  ]).mockResolvedValueOnce({ id: 'job-1', status: 'queued' })

  render(PluginActionPanel, { props: { targetType: 'meeting', targetId: 'meeting-1' } })
  await fireEvent.click(await screen.findByRole('button', { name: '生成会议纪要' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({
      action_id: 'ai-work-assistant.meeting_summary',
      target_type: 'meeting',
      target_id: 'meeting-1',
      input: {},
    }),
  }))
  expect(screen.getByText('AI 正在生成草稿；完成后会显示在当前页面。')).toBeInTheDocument()
})

it('keeps succeeded work as a recovery link back to its meeting context', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-1', action_id: 'ai-work-assistant.meeting_summary', target_type: 'meeting', target_id: 'meeting-1',
      status: 'succeeded', result: { markdown: '# AI 草稿', model: 'test-model' }, created_at: '2026-07-24T00:00:00Z',
      started_at: null, finished_at: '2026-07-24T00:01:00Z', error_message: null, applied_at: null,
    }],
  })

  render(AiTasksView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  const link = await screen.findByRole('link', { name: '回到会议处理草稿' })

  expect(link).toHaveAttribute('href', '/meetings/meeting-1')
  expect(screen.queryByRole('button', { name: '应用到会议纪要' })).not.toBeInTheDocument()
})
