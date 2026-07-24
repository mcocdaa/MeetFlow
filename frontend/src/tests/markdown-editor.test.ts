import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MarkdownEditor from '../components/MarkdownEditor.vue'
import VersionConflictDialog from '../components/VersionConflictDialog.vue'

const milkdown = vi.hoisted(() => {
  let updated: ((ctx: unknown, markdown: string, previous: string) => void) | undefined
  return {
    configs: [] as Array<Record<string, unknown>>,
    create: vi.fn(() => Promise.resolve()),
    destroy: vi.fn(() => Promise.resolve()),
    setReadonly: vi.fn(),
    emit(markdown: string, previous = '') { updated?.({}, markdown, previous) },
    bind(callback: typeof updated) { updated = callback },
    reset() { updated = undefined },
  }
})

vi.mock('@milkdown/crepe', () => ({
  Crepe: class {
    static Feature = { Placeholder: 'placeholder', CodeMirror: 'code', Latex: 'latex', ImageBlock: 'image' }
    constructor(config: Record<string, unknown>) { milkdown.configs.push(config) }
    on(register: (listener: { markdownUpdated: (callback: (ctx: unknown, markdown: string, previous: string) => void) => void }) => void) {
      register({ markdownUpdated: (callback) => milkdown.bind(callback) })
    }
    create = milkdown.create
    destroy = milkdown.destroy
    setReadonly = milkdown.setReadonly
  },
}))

describe('Markdown editing and conflict recovery', () => {
  beforeEach(() => {
    milkdown.configs.length = 0
    milkdown.create.mockClear()
    milkdown.destroy.mockClear()
    milkdown.setReadonly.mockClear()
    milkdown.reset()
  })

  it('emits Markdown updates from one editor instance and destroys it on unmount', async () => {
    const view = render(MarkdownEditor, { props: { modelValue: '# Notes', placeholder: '记录讨论' } })
    await waitFor(() => expect(milkdown.configs[0]).toEqual(expect.objectContaining({ defaultValue: '# Notes' })))

    milkdown.emit('**Decision**', '# Notes')
    expect(view.emitted('update:modelValue')).toEqual([['**Decision**']])
    view.unmount()
    expect(milkdown.destroy).toHaveBeenCalledTimes(1)
  })

  it('uses the shared top-aligned editor baseline', () => {
    render(MarkdownEditor, { props: { modelValue: '', label: '会议记录', placeholder: '记录讨论上下文…' } })
    expect(screen.getByRole('textbox', { name: '会议记录' })).toHaveClass('markdown-editor-top-aligned')
  })

  it('shows both drafts and requires an explicit conflict choice', async () => {
    const view = render(VersionConflictDialog, { props: { localMarkdown: 'local text', serverMarkdown: 'server text', actualVersion: 4 } })
    expect(screen.getByText('local text')).toBeInTheDocument()
    expect(screen.getByText('server text')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '载入服务器版本' }))
    expect(view.emitted('reload')).toEqual([[]])
    expect(view.emitted('overwrite')).toBeUndefined()
  })
})
