import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, expect, it, vi } from 'vitest'
import { h, nextTick, ref } from 'vue'

// @ts-expect-error Plugin ESM lives outside the TypeScript app source tree.
import { register } from '../../../plugins/ai-work-assistant/frontend/entry.js'

type RegisteredAssistant = ReturnType<typeof registerAssistant>

function registerAssistant() {
  const assistants = new Map<string, unknown>()
  const taskExtensions = new Map<string, unknown>()
  const apiMock = vi.fn()
  register({
    registerEditorAssistant: (slot: string, component: unknown) => assistants.set(slot, component),
    registerTaskExtension: (pluginId: string, component: unknown) => taskExtensions.set(pluginId, component),
    api: apiMock,
    vue: { h, ref, nextTick },
  })
  return { assistants, taskExtensions, apiMock }
}

function renderAssistant(registered: RegisteredAssistant, slot: string, modelValue = '原有内容') {
  const component = registered.assistants.get(slot)
  if (!component) throw new Error(`assistant was not registered for ${slot}`)
  return render(component as any, {
    props: {
      modelValue,
      context: { targetType: slot === 'project-update-editor' ? 'project' : 'meeting', targetId: 'target-1' },
    },
  })
}

afterEach(() => vi.useRealTimers())

it('registers assistants for all editor slots and its task extension', () => {
  const registered = registerAssistant()

  expect([...registered.assistants.keys()]).toEqual([
    'meeting-summary-editor',
    'project-update-editor',
    'action-composer',
  ])
  expect([...registered.taskExtensions.keys()]).toEqual(['ai-work-assistant'])
})

it('applies the terminal job markdown exactly once after active polling', async () => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: 'job-1', status: 'queued' })
    .mockResolvedValueOnce({ id: 'job-1', status: 'succeeded', result: { markdown: '# 真实 AI 结果' } })
  const { emitted } = renderAssistant(registered, 'meeting-summary-editor')

  await fireEvent.click(screen.getByRole('button', { name: 'AI 生成会议纪要' }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(registered.apiMock).toHaveBeenNthCalledWith(1, '/api/plugin-jobs', {
    method: 'POST',
    body: JSON.stringify({
      action_id: 'ai-work-assistant.meeting_summary',
      target_type: 'meeting',
      target_id: 'target-1',
      input: { current_markdown: '原有内容' },
    }),
  })
  expect(registered.apiMock).toHaveBeenNthCalledWith(2, '/api/plugin-jobs/job-1')
  expect(emitted()['update:modelValue']).toEqual([['# 真实 AI 结果']])
  expect(emitted()['update:busy']).toEqual([
    [{ active: true, label: '正在生成会议纪要…' }],
    [{ active: false, label: '' }],
  ])
})

it('writes an action suggestion into the existing editable action field', async () => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: 'job-action', status: 'queued' })
    .mockResolvedValueOnce({
      id: 'job-action',
      status: 'succeeded',
      result: { markdown: '- 明确负责人并补充截止日期' },
    })
  const { emitted } = renderAssistant(registered, 'action-composer', '原有行动内容')

  await fireEvent.click(screen.getByRole('button', { name: 'AI 建议行动项' }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(emitted()['update:modelValue']).toEqual([['- 明确负责人并补充截止日期']])
  expect(screen.queryByRole('button', { name: /创建所选行动项/ })).not.toBeInTheDocument()
})

it('does not mutate editor content when a job fails', async () => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: 'job-2', status: 'queued' })
    .mockResolvedValueOnce({ id: 'job-2', status: 'failed', error_message: '模型不可用' })
  const { emitted } = renderAssistant(registered, 'action-composer', '保留的行动内容')

  await fireEvent.click(screen.getByRole('button', { name: 'AI 建议行动项' }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(emitted()['update:modelValue']).toBeUndefined()
  expect(emitted().notice).toEqual([['模型不可用']])
})
