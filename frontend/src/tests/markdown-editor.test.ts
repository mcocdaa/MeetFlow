import { waitFor } from '@testing-library/dom'
import { render } from '@testing-library/vue'
import { expect, it, vi } from 'vitest'

const { action, create, replaceAll, setReadonly } = vi.hoisted(() => ({
  action: vi.fn(),
  create: vi.fn().mockResolvedValue(undefined),
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

vi.mock('@milkdown/kit/utils', () => ({ replaceAll }))

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
