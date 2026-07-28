import { defineComponent, onBeforeUnmount, onMounted, ref } from 'vue'
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

const DirectUpdateAssistant = defineComponent({
  emits: ['update:modelValue'],
  template: '<button type="button" @click="$emit(\'update:modelValue\', \'# AI 结果\')">生成建议</button>',
})

const NativeEditor = defineComponent({
  props: {
    modelValue: { type: String, required: true },
    disabled: { type: Boolean, default: false },
    registerEditor: { type: Function, default: undefined },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const applyCount = ref(0)
    const applyMarkdown = (markdown: string) => {
      applyCount.value += 1
      emit('update:modelValue', markdown)
    }
    onMounted(() => props.registerEditor?.(applyMarkdown))
    onBeforeUnmount(() => props.registerEditor?.(null))
    return { applyCount }
  },
  template: '<textarea aria-label="编辑器" :disabled="disabled" :value="modelValue" /><output data-testid="native-apply-count">{{ applyCount }}</output>',
})

const DirectEditorHarness = defineComponent({
  components: { NativeEditor, PluginEditorSlot },
  setup() {
    const content = ref('原内容')
    return { content }
  },
  template: `
    <PluginEditorSlot v-model="content" target-type="project" target-id="p1" slot="project-update-editor" editor-label="进展记录">
      <template #editor="{ disabled, registerEditor }"><NativeEditor v-model="content" :disabled="disabled" :register-editor="registerEditor" /></template>
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

it('routes an AI result through the registered editor once without rendering a draft review', async () => {
  registerEditorAssistant('project-update-editor', DirectUpdateAssistant)
  render(DirectEditorHarness)

  await fireEvent.click(screen.getByRole('button', { name: 'AI 工具' }))
  await fireEvent.click(screen.getByRole('button', { name: '生成建议' }))

  expect(screen.getByTestId('editor-content')).toHaveTextContent('# AI 结果')
  expect(screen.getByTestId('native-apply-count')).toHaveTextContent('1')
  expect(screen.queryByText('AI 草稿')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '应用草稿' })).not.toBeInTheDocument()
})
