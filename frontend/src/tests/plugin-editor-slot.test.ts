import { defineComponent } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it } from 'vitest'

import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import { registerEditorAssistant } from '../plugins/registry'

const FakeAssistant = defineComponent({
  emits: ['update:busy'],
  template: '<button type="button" @click="$emit(\'update:busy\', { active: true, label: \'正在生成建议…\' })">插件建议</button>',
})

it('places registered assistants in compact editor chrome and keeps busy feedback local', async () => {
  registerEditorAssistant('meeting-summary-editor', FakeAssistant)

  render(PluginEditorSlot, {
    props: {
      modelValue: '原记录',
      targetType: 'meeting',
      targetId: 'meeting-1',
      slot: 'meeting-summary-editor',
      editorLabel: '会议纪要',
      metadata: {},
    },
    slots: {
      editor: '<textarea aria-label="编辑器" />',
    },
  })

  expect(screen.getByText('会议纪要')).toBeVisible()
  expect(screen.getByRole('button', { name: 'AI 工具' })).toBeVisible()
  expect(screen.queryByRole('button', { name: '插件建议' })).not.toBeInTheDocument()

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  expect(screen.getByRole('button', { name: '插件建议' })).toBeVisible()
  await fireEvent.keyDown(screen.getByRole('button', { name: 'AI 工具' }), { key: 'Escape' })
  expect(screen.queryByRole('button', { name: '插件建议' })).not.toBeInTheDocument()

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  await fireEvent.click(screen.getByRole('button', { name: '插件建议' }))

  const host = screen.getByText('正在生成建议…').closest('.plugin-editor-slot')
  expect(host).toHaveAttribute('data-busy', 'true')
  expect(host?.querySelector('.plugin-editor-assistants')).toBeNull()
  expect(host?.querySelector('.plugin-editor-chrome')).not.toBeNull()
})

it('does not render editor chrome without registered assistants', () => {
  render(PluginEditorSlot, {
    props: {
      modelValue: '原记录',
      targetType: 'meeting',
      targetId: 'meeting-1',
      slot: 'plain-editor',
      editorLabel: '普通内容',
    },
    slots: {
      editor: '<textarea aria-label="编辑器" />',
    },
  })

  expect(screen.getByLabelText('编辑器')).toBeVisible()
  expect(screen.queryByText('普通内容')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'AI 工具' })).not.toBeInTheDocument()
})
