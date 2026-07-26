import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import InlineAiDrafts from '../components/InlineAiDrafts.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

beforeEach(() => apiMock.mockReset())

it('applies a meeting summary only after the inline draft is confirmed', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{ id: 'job-1', action_id: 'ai-work-assistant.meeting_summary', status: 'succeeded', result: { markdown: '# AI 草稿' }, applied_at: null }],
  }).mockResolvedValueOnce({ id: 'meeting-1', version: 3 }).mockResolvedValueOnce({ summary_markdown: '# 已确认纪要' })

  render(InlineAiDrafts, { props: { targetType: 'meeting', targetId: 'meeting-1', mode: 'summary' } })
  await fireEvent.update(await screen.findByLabelText('AI 会议纪要草稿'), '# 已确认纪要')
  await fireEvent.click(screen.getByRole('button', { name: '应用到会议纪要' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-1/apply', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ edited_markdown: '# 已确认纪要', expected_version: 3 }),
  }))
})

it('creates only checked edited action candidates from the inline draft', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-2', action_id: 'ai-work-assistant.action_suggestions', status: 'succeeded', applied_at: null,
      result: { markdown: '- 整理方案\n- 发送纪要', candidates: [{ content: '整理方案' }, { content: '发送纪要' }] },
    }],
  }).mockResolvedValueOnce({ created_count: 1 })

  render(InlineAiDrafts, { props: { targetType: 'meeting', targetId: 'meeting-1', mode: 'actions', participants: [] } })
  await fireEvent.click(await screen.findByRole('checkbox', { name: '发送纪要' }))
  await fireEvent.update(screen.getByLabelText('行动项：发送纪要'), '发送最终纪要')
  await fireEvent.click(screen.getByRole('button', { name: '创建已选 1 项' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-2/apply', expect.objectContaining({
    method: 'POST', body: expect.stringContaining('发送最终纪要'),
  }))
})

it('persists a discarded draft before removing it from the inline panel', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{ id: 'job-3', action_id: 'ai-work-assistant.meeting_summary', status: 'succeeded', result: { markdown: '# AI 草稿' }, applied_at: null }],
  }).mockResolvedValueOnce({ id: 'job-3', dismissed_at: '2026-07-26T10:00:00Z' })

  render(InlineAiDrafts, { props: { targetType: 'meeting', targetId: 'meeting-1', mode: 'summary' } })
  await fireEvent.click(await screen.findByRole('button', { name: '丢弃草稿' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-3/dismiss', { method: 'POST' })
  expect(screen.queryByLabelText('AI 会议纪要草稿')).not.toBeInTheDocument()
})
