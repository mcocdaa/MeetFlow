import { defineComponent, ref } from 'vue'
import { waitFor } from '@testing-library/dom'
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it, vi } from 'vitest'

const { action, create, getMarkdown, replaceAll, setReadonly } = vi.hoisted(() => ({
  action: vi.fn(),
  create: vi.fn().mockResolvedValue(undefined),
  getMarkdown: vi.fn(() => ({ type: 'get-markdown' })),
  replaceAll: vi.fn((markdown: string) => ({ markdown })),
  setReadonly: vi.fn(),
}))

vi.mock('@milkdown/crepe', () => ({
  Crepe: class {
    static Feature = { ImageBlock: 'image', Latex: 'latex', Placeholder: 'placeholder' }
    editor = { action }
    on(listener: (value: { markdownUpdated: (callback: (ctx: unknown, markdown: string) => void) => void }) => void) {
      listener({ markdownUpdated: () => undefined })
    }
    create = create
    setReadonly = setReadonly
    destroy = vi.fn().mockResolvedValue(undefined)
  },
}))

vi.mock('@milkdown/kit/utils', () => ({ getMarkdown, replaceAll }))

import MarkdownEditor from '../components/MarkdownEditor.vue'

it('registers a direct AI write that dispatches one editor replacement transaction', async () => {
  const registerEditor = vi.fn()
  const { emitted } = render(MarkdownEditor, {
    props: { modelValue: '原内容', registerEditor },
  })

  await waitFor(() => expect(registerEditor).toHaveBeenCalledTimes(1))
  const applyMarkdown = registerEditor.mock.calls[0][0] as (markdown: string) => void
  applyMarkdown('# AI 结果')

  expect(replaceAll).toHaveBeenCalledTimes(1)
  expect(replaceAll).toHaveBeenCalledWith('# AI 结果')
  expect(action).toHaveBeenCalledTimes(1)
  expect(action).toHaveBeenCalledWith({ markdown: '# AI 结果' })
  expect(emitted()['update:modelValue']).toEqual([['# AI 结果']])
})

const FlushHarness = defineComponent({
  components: { MarkdownEditor },
  setup() {
    const editor = ref<{ flush?: () => string } | null>(null)
    const value = ref('原内容')
    const flushed = ref('')
    function flush() { flushed.value = editor.value?.flush?.() ?? 'unavailable' }
    return { editor, flushed, flush, value }
  },
  template: '<MarkdownEditor ref="editor" v-model="value" /><button type="button" @click="flush">立即同步</button><output data-testid="flushed-markdown">{{ flushed }}</output>',
})

it('exposes the current editor markdown for an immediate save', async () => {
  action.mockImplementation((operation) => operation?.type === 'get-markdown' ? '@决策: 立即保存' : undefined)
  render(FlushHarness)
  await waitFor(() => expect(create).toHaveBeenCalled())

  await fireEvent.click(screen.getByRole('button', { name: '立即同步' }))

  expect(getMarkdown).toHaveBeenCalled()
  expect(screen.getByTestId('flushed-markdown')).toHaveTextContent('@决策: 立即保存')
})
