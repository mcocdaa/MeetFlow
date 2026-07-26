import { defineComponent } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it } from 'vitest'

import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import { registerEditorAssistant } from '../plugins/registry'

const FakeAssistant = defineComponent({
  emits: ['update:busy'],
  template: '<button type="button" @click="$emit(\'update:busy\', { active: true, label: \'正在生成建议…\' })">插件建议</button>',
})

it('renders a registered assistant and its generic busy overlay', async () => {
  registerEditorAssistant('meeting-summary-editor', FakeAssistant)

  render(PluginEditorSlot, {
    props: {
      modelValue: '原记录',
      targetType: 'meeting',
      targetId: 'meeting-1',
      slot: 'meeting-summary-editor',
      metadata: {},
    },
    slots: {
      editor: '<textarea aria-label="编辑器" />',
    },
  })

  await fireEvent.click(screen.getByRole('button', { name: '插件建议' }))

  const host = screen.getByText('正在生成建议…').closest('.plugin-editor-slot')
  const toolbar = screen.getByRole('button', { name: '插件建议' }).parentElement
  const editor = screen.getByLabelText('编辑器')
  expect(host).toHaveAttribute('data-busy', 'true')
  expect(toolbar).toHaveClass('plugin-editor-assistants')
  expect(toolbar?.dataset.placement).toBe('editor-toolbar')
  expect(toolbar?.compareDocumentPosition(editor)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
})
