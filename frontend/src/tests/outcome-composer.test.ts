import { defineComponent } from 'vue'
import { fireEvent, render, screen, within } from '@testing-library/vue'
import { expect, it, vi } from 'vitest'

vi.mock('../components/MarkdownEditor.vue', () => ({
  default: {
    props: ['modelValue', 'label', 'disabled'],
    emits: ['update:modelValue'],
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}))

import OutcomeComposer from '../components/OutcomeComposer.vue'
import { registerEditorAssistant } from '../plugins/registry'

const OutcomeAssistant = defineComponent({
  template: '<button type="button">AI 建议决策</button>',
})

const user = { id: 'u1', username: 'lin', display_name: '林宇' }
const meeting = {
  id: 'm1',
  project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' },
  participants: [{ user, participation_role: 'host', position: 0 }],
} as any
const item = { id: 'a1' } as any

it('passes the outcome field label into its editor chrome', async () => {
  registerEditorAssistant('decision-composer', OutcomeAssistant)

  render(OutcomeComposer, { props: { mode: 'decision', meeting, item } })

  const editor = screen.getByTestId('decision-composer')
  expect(editor).toContainElement(screen.getByLabelText('决策内容'))
  expect(within(editor).getByText('决策内容')).toBeVisible()
  await fireEvent.click(within(editor).getByRole('button', { name: 'AI 工具' }))
  expect(within(editor).getByRole('button', { name: 'AI 建议决策' })).toBeVisible()
})
