import { fireEvent, screen } from '@testing-library/vue'
import { NButton, NDataTable, type DataTableColumns, useDialog } from 'naive-ui'
import { defineComponent, h, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import AppAvatar from '../components/AppAvatar.vue'
import MeetingParticipantEditor from '../components/MeetingParticipantEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusPill from '../components/StatusPill.vue'
import type { ParticipationRole } from '../domain/meetings'
import { naiveThemeOverrides, priorityTone, statusTone } from '../theme/naive'
import { activityLabel } from '../utils/activity'
import { can } from '../utils/capabilities'
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

describe('MeetingParticipantEditor', () => {
  type Row = { user_id: string; participation_role: ParticipationRole }
  const members = [
    { id: 'u1', username: 'lin', display_name: '林宇' },
    { id: 'u2', username: 'chen', display_name: '陈晨' },
  ]

  function renderEditor(initial: Row[], disabled = false) {
    const updates: Row[][] = []
    const value = ref<Row[]>(initial)
    const Host = defineComponent({
      setup() {
        return () =>
          h(MeetingParticipantEditor, {
            modelValue: value.value,
            memberOptions: members,
            disabled,
            'onUpdate:modelValue': (next: Row[]) => {
              updates.push(next)
              value.value = next
            },
          })
      },
    })

    return { ...renderWithProviders(Host), updates }
  }

  it('renders controlled participant rows and appends an attendee row', async () => {
    const { updates, container } = renderEditor([{ user_id: 'u1', participation_role: 'host' }])

    expect(container.querySelectorAll('.participant-editor-row')).toHaveLength(1)
    expect(screen.getByText('林宇')).toBeInTheDocument()
    expect(screen.getByText('主持')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '添加参与人' }))

    expect(updates).toEqual([
      [
        { user_id: 'u1', participation_role: 'host' },
        { user_id: '', participation_role: 'attendee' },
      ],
    ])
    expect(container.querySelectorAll('.participant-editor-row')).toHaveLength(2)
  })

  it('removes a row through the update event', async () => {
    const { updates, container } = renderEditor([
      { user_id: 'u1', participation_role: 'host' },
      { user_id: 'u2', participation_role: 'attendee' },
    ])

    await fireEvent.click(screen.getAllByRole('button', { name: '移除参与人' })[1])

    expect(updates).toEqual([[{ user_id: 'u1', participation_role: 'host' }]])
    expect(container.querySelectorAll('.participant-editor-row')).toHaveLength(1)
  })

  it('hides add and remove actions when disabled', () => {
    const { container } = renderEditor([{ user_id: 'u1', participation_role: 'host' }], true)

    expect(container.querySelectorAll('.participant-editor-row')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: '添加参与人' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '移除参与人' })).not.toBeInTheDocument()
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

describe('PageHeader', () => {
  it('keeps the workspace heading contract for the converged typography', () => {
    const { container } = renderWithProviders(PageHeader, {
      props: { eyebrow: 'E', title: '标题', summary: '摘要' },
    })

    expect(screen.getByRole('heading', { level: 1, name: '标题' })).toBeInTheDocument()
    expect(container.querySelector('.workspace-page-heading')).not.toBeNull()
    expect(screen.getByText('摘要')).toBeInTheDocument()
  })
})

describe('capabilities', () => {
  it('reads only server-provided capabilities', () => {
    expect(
      can({ capabilities: { can_manage: false, can_contribute: false, can_comment: false } }, 'contribute'),
    ).toBe(false)
    expect(
      can({ capabilities: { can_manage: true, can_contribute: true, can_comment: true } }, 'manage'),
    ).toBe(true)
    expect(can(null, 'view')).toBe(false)
    expect(can({}, 'comment')).toBe(false)
  })
})

describe('activity labels', () => {
  it('renders Chinese labels including the subject when present', () => {
    const projectLabel = activityLabel('project.created', { name: 'MeetFlow' })
    expect(projectLabel).toContain('MeetFlow')
    expect(projectLabel).toMatch(/[\u4e00-\u9fff]/)
    expect(activityLabel('agenda.started', { title: '发布方案' })).toContain('发布方案')
  })

  it('falls back to the raw event type and tolerates missing subjects', () => {
    expect(activityLabel('unknown.event', {})).toBe('unknown.event')
    expect(activityLabel('project.created', {})).not.toContain('undefined')
    expect(activityLabel('agenda.reordered')).not.toContain('undefined')
  })

  it('covers every activity event type the backend records', () => {
    // Mirrors the event_type strings emitted by ActivityRecorder in backend/app
    // (verified 2026-09-15). When the backend adds an event type, add it here and
    // to ACTIVITY_TEMPLATES in the same change.
    const backendEventTypes = [
      'project.created', 'project.updated', 'project.progress_posted',
      'project.progress_updated', 'project.deleted',
      'meeting.created', 'meeting.updated', 'meeting.started', 'meeting.finished',
      'meeting.amended', 'meeting.canceled', 'meeting.reopened',
      'agenda.created', 'agenda.updated', 'agenda.deleted', 'agenda.moved',
      'agenda.reordered', 'agenda.started', 'agenda.completed', 'agenda.skipped',
      'agenda.canceled', 'agenda.converted_to_question', 'agenda.copied',
      'agenda.outcomes_migrated',
      'attachment.uploaded', 'attachment.deleted',
      'decision.created', 'decision.updated', 'decision.reviewed',
      'decision.finalized', 'decision.withdrawn', 'decision.superseded',
      'action.created', 'action.updated', 'action.completed', 'action.reopened',
      'action.status_changed',
      'question.created', 'question.updated', 'question.scheduled', 'question.resolved',
      'comment.created', 'comment.replied', 'comment.updated', 'comment.deleted',
      'comment.resolved', 'comment.reopened',
    ]

    const uncovered = backendEventTypes.filter(
      (eventType) => activityLabel(eventType, { title: '冒烟' }) === eventType,
    )

    expect(uncovered).toEqual([])
  })
})
