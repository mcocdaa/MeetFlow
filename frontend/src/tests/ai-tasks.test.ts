import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import PluginActionPanel from '../components/PluginActionPanel.vue'

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
  expect(screen.getByText('任务已加入 AI 任务中心')).toBeInTheDocument()
})
