import { defineComponent, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it, vi } from 'vitest'

vi.mock('../components/MarkdownEditor.vue', () => ({
  default: {
    props: ['modelValue', 'label', 'placeholder', 'disabled'],
    emits: ['update:modelValue'],
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}))

import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import { registerEditorAssistant } from '../plugins/registry'

const FakeAssistant = defineComponent({
  emits: ['update:busy'],
  template: '<button type="button" @click="$emit(\'update:busy\', { active: true, label: \'正在生成建议…\' })">插件建议</button>',
})

const DraftAssistant = defineComponent({
  emits: ['draft'],
  template: '<button type="button" @click="$emit(\'draft\', \'# AI 草稿\')">生成草稿</button>',
})

const DirectUpdateAssistant = defineComponent({
  emits: ['update:modelValue'],
  template: '<button type="button" @click="$emit(\'update:modelValue\', \'兼容的直接更新\')">直接更新</button>',
})

const DraftReviewHarness = defineComponent({
  components: { PluginEditorSlot },
  setup() {
    const content = ref('原内容')
    return { content }
  },
  template: `
    <PluginEditorSlot v-model="content" target-type="project" target-id="p1" slot="project-update-editor" editor-label="进展记录">
      <template #editor="{ disabled }"><textarea aria-label="编辑器" :disabled="disabled" :value="content" /></template>
    </PluginEditorSlot>
    <output data-testid="editor-content">{{ content }}</output>
  `,
})

const DirectUpdateHarness = defineComponent({
  components: { PluginEditorSlot },
  setup() {
    const content = ref('原内容')
    return { content }
  },
  template: `
    <PluginEditorSlot v-model="content" target-type="meeting" target-id="m1" slot="direct-update-editor" editor-label="会议纪要">
      <template #editor="{ disabled }"><textarea aria-label="编辑器" :disabled="disabled" :value="content" /></template>
    </PluginEditorSlot>
    <output data-testid="editor-content">{{ content }}</output>
  `,
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

it('keeps an AI draft editable until the user applies or discards it', async () => {
  registerEditorAssistant('project-update-editor', DraftAssistant)
  render(DraftReviewHarness)

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  await fireEvent.click(screen.getByRole('button', { name: '生成草稿' }))

  expect(screen.getByTestId('editor-content')).toHaveTextContent('原内容')
  expect(screen.getByLabelText('编辑器')).toBeDisabled()
  expect(screen.getByLabelText('AI 草稿')).toHaveValue('# AI 草稿')
  await fireEvent.update(screen.getByLabelText('AI 草稿'), '# 修改后的草稿')
  await fireEvent.click(screen.getByRole('button', { name: '应用草稿' }))
  expect(screen.getByTestId('editor-content')).toHaveTextContent('# 修改后的草稿')
  expect(screen.getByLabelText('编辑器')).not.toBeDisabled()

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  await fireEvent.click(screen.getByRole('button', { name: '生成草稿' }))
  await fireEvent.click(screen.getByRole('button', { name: '放弃' }))
  expect(screen.queryByLabelText('AI 草稿')).not.toBeInTheDocument()
  expect(screen.getByTestId('editor-content')).toHaveTextContent('# 修改后的草稿')
})

it('continues to apply direct model updates from non-draft assistants', async () => {
  registerEditorAssistant('direct-update-editor', DirectUpdateAssistant)
  render(DirectUpdateHarness)

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  await fireEvent.click(screen.getByRole('button', { name: '直接更新' }))

  expect(screen.getByTestId('editor-content')).toHaveTextContent('兼容的直接更新')
})
