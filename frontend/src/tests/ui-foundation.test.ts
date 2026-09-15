import { fireEvent, screen } from '@testing-library/vue'
import { NButton, NDataTable, type DataTableColumns, useDialog } from 'naive-ui'
import { defineComponent, h } from 'vue'
import { describe, expect, it } from 'vitest'

import AppAvatar from '../components/AppAvatar.vue'
import StatusPill from '../components/StatusPill.vue'
import { naiveThemeOverrides, priorityTone, statusTone } from '../theme/naive'
import { renderWithProviders } from './helpers'

describe('naive theme', () => {
  it('maps the brand primary color from the styles.css :root token', () => {
    expect(naiveThemeOverrides.common?.primaryColor).toBe('#0b6a58')
  })

  it('maps statuses to tones', () => {
    expect(statusTone('in_progress')).toBe('success')
    expect(statusTone('proposed')).toBe('warning')
    expect(statusTone('completed')).toBe('completed')
    expect(statusTone('rejected')).toBe('error')
    expect(statusTone('disabled')).toBe('muted')
    expect(statusTone('unknown-status')).toBe('muted')
  })

  it('maps priorities to tones', () => {
    expect(priorityTone('urgent')).toBe('error')
    expect(priorityTone('high')).toBe('warning')
    expect(priorityTone('normal')).toBe('muted')
    expect(priorityTone('low')).toBe('completed')
  })
})

describe('naive smoke', () => {
  it('applies the global jsdom patches required by naive', () => {
    expect(typeof window.matchMedia).toBe('function')
    expect(typeof ResizeObserver).toBe('function')
    expect(typeof Element.prototype.scrollTo).toBe('function')
  })

  it('renders a component inside the naive providers', async () => {
    const Probe = defineComponent({
      setup() {
        return () => h(NButton, null, { default: () => '冒烟' })
      },
    })

    renderWithProviders(Probe)

    await screen.findByRole('button', { name: '冒烟' })
  })

  it('renders dialogs teleported to the document body', async () => {
    const Probe = defineComponent({
      setup() {
        const dialog = useDialog()
        return () =>
          h(
            NButton,
            { onClick: () => dialog.warning({ title: '冒烟对话框' }) },
            { default: () => '打开' },
          )
      },
    })

    renderWithProviders(Probe)
    await fireEvent.click(screen.getByRole('button', { name: '打开' }))

    await screen.findByText('冒烟对话框')
  })

  it('renders data tables without fixed columns or virtual scrolling', async () => {
    const columns: DataTableColumns<{ name: string }> = [{ title: '名称', key: 'name' }]
    const Probe = defineComponent({
      setup() {
        return () =>
          h(NDataTable, {
            columns,
            data: [{ name: '行一' }, { name: '行二' }],
            pagination: { page: 1, pageSize: 10, itemCount: 2 },
          })
      },
    })

    renderWithProviders(Probe)

    await screen.findByText('行一')
    expect(document.querySelector('.n-data-table')).not.toBeNull()
  })
})

describe('AppAvatar', () => {
  it('renders the name initial on a naive avatar using the supplied color', () => {
    const { container } = renderWithProviders(AppAvatar, {
      props: { name: '林宇', color: '#123456' },
    })

    expect(screen.getByText('林')).toBeInTheDocument()
    expect(container.querySelector('.n-avatar')).not.toBeNull()
  })

  it('falls back to the brand soft background when no color is supplied', () => {
    const { container } = renderWithProviders(AppAvatar, { props: { name: '林宇' } })

    const avatar = container.querySelector('.n-avatar')
    expect(avatar?.getAttribute('style') ?? '').toContain('green-soft')
  })
})

describe('StatusPill', () => {
  it('renders a naive tag that keeps the status contract', () => {
    renderWithProviders(StatusPill, { props: { status: 'in_progress' } })

    // `getByText` matches the inner `.n-tag__content`; the class/data-status contract
    // lives on the NTag root, so walk up to it before asserting.
    const pill = screen.getByText('进行中').closest('.n-tag')
    expect(pill).not.toBeNull()
    expect(pill).toHaveClass('status-pill', 'n-tag')
    expect(pill).toHaveAttribute('data-status', 'in_progress')
  })

  it('keeps label text from the shared status labels', () => {
    renderWithProviders(StatusPill, { props: { status: 'completed', kind: 'agenda' } })

    expect(screen.getByText('已完成')).toBeInTheDocument()
  })
})
