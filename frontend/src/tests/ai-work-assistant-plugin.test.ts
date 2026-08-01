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
    registerPluginSlot: () => undefined,
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
    'decision-composer',
    'question-composer',
  ])
  expect([...registered.taskExtensions.keys()]).toEqual(['ai-work-assistant'])
})

it.each([
  ['meeting-summary-editor', 'AI 协助纪要', '生成会议纪要'],
  ['project-update-editor', 'AI 协助进展', '总结项目进展'],
  ['action-composer', 'AI 协助行动项', '生成行动项建议'],
  ['decision-composer', 'AI 协助决策', '生成决策建议'],
  ['question-composer', 'AI 协助问题', '梳理开放问题'],
])('renders the %s contextual menu action', (slot, title, actionLabel) => {
  const registered = registerAssistant()
  renderAssistant(registered, slot)

  expect(screen.getByText(title)).toHaveClass('ai-work-assistant-menu-title')
  expect(screen.getByText('当前编辑块')).toHaveClass('ai-work-assistant-menu-tag')
  expect(screen.getByRole('button', { name: actionLabel })).toHaveClass('ai-work-assistant-menu-action', 'is-primary')
})

it('writes the terminal job markdown directly into the active editor after polling', async () => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: 'job-1', status: 'queued' })
    .mockResolvedValueOnce({ id: 'job-1', status: 'succeeded', result: { markdown: '# 真实 AI 结果' } })
  const { emitted } = renderAssistant(registered, 'meeting-summary-editor')

  await fireEvent.click(screen.getByRole('button', { name: '生成会议纪要' }))
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
  expect(emitted().draft).toBeUndefined()
  expect(emitted()['update:busy']).toEqual([
    [{ active: true, label: '正在生成会议纪要…' }],
    [{ active: false, label: '' }],
  ])
})

it('writes an action suggestion directly into the active editor', async () => {
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

  await fireEvent.click(screen.getByRole('button', { name: '生成行动项建议' }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(emitted()['update:modelValue']).toEqual([['- 明确负责人并补充截止日期']])
  expect(emitted().draft).toBeUndefined()
  expect(screen.queryByRole('button', { name: /创建所选行动项/ })).not.toBeInTheDocument()
})

it.each([
  ['decision-composer', '生成决策建议', 'decision_suggestions', '采用灰度发布。'],
  ['question-composer', '梳理开放问题', 'open_question_suggestions', '- 如何确认发布范围？'],
])('writes %s output directly into the active editor', async (slot, label, actionId, markdown) => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: `job-${actionId}`, status: 'queued' })
    .mockResolvedValueOnce({ id: `job-${actionId}`, status: 'succeeded', result: { markdown } })
  const { emitted } = renderAssistant(registered, slot, '原有内容')

  await fireEvent.click(screen.getByRole('button', { name: label }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(registered.apiMock).toHaveBeenNthCalledWith(1, '/api/plugin-jobs', {
    method: 'POST',
    body: JSON.stringify({
      action_id: `ai-work-assistant.${actionId}`,
      target_type: 'meeting',
      target_id: 'target-1',
      input: { current_markdown: '原有内容' },
    }),
  })
  expect(emitted()['update:modelValue']).toEqual([[markdown]])
  expect(emitted().draft).toBeUndefined()
})

it('does not mutate editor content when a job fails', async () => {
  vi.useFakeTimers()
  const registered = registerAssistant()
  registered.apiMock
    .mockResolvedValueOnce({ id: 'job-2', status: 'queued' })
    .mockResolvedValueOnce({ id: 'job-2', status: 'failed', error_message: '模型不可用' })
  const { emitted } = renderAssistant(registered, 'action-composer', '保留的行动内容')

  await fireEvent.click(screen.getByRole('button', { name: '生成行动项建议' }))
  await vi.advanceTimersByTimeAsync(3_000)

  expect(emitted()['update:modelValue']).toBeUndefined()
  expect(emitted().draft).toBeUndefined()
  expect(emitted().notice).toEqual([['模型不可用']])
})
