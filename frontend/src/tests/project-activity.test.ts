import { defineComponent, onMounted } from 'vue'
import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectActivityTab from '../components/ProjectActivityTab.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'label', 'disabled', 'registerEditor'],
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      onMounted(() => props.registerEditor?.((markdown: string) => emit('update:modelValue', markdown)))
      return {}
    },
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  }),
}))

const lin = { id: 'u1', username: 'lin', display_name: '林宇' }

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: lin, target_date: null, version: 3,
  memberships: [{ role: 'member', user: lin }],
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
  updates: [], next_meeting: null, recent_decisions: [], meeting_count: 0, decision_count: 0, open_action_count: 0,
  series_summaries: [], attachments: [], created_by: lin, updated_by: lin, created_at: '', updated_at: '',
} as any

const update = {
  id: 'up1', project_id: 'p1', health: 'on_track', content_markdown: '完成后端契约',
  source: 'ai_draft_applied', version: 2, created_by: lin,
  created_at: '2026-07-21T02:00:00Z', updated_at: '2026-07-21T02:00:00Z',
}

const activityItem = (overrides: Record<string, unknown>) => ({
  id: 5,
  project_id: 'p1',
  meeting_id: null,
  actor: lin,
  event_type: 'project.created',
  subject: { type: 'project', id: 'p1' },
  payload: { name: 'MeetFlow' },
  created_at: '2026-07-20T02:00:00Z',
  ...overrides,
})

function renderActivity(canContribute = true) {
  return renderWithProviders(ProjectActivityTab, { props: { project, canContribute } })
}

describe('project activity ledger', () => {
  beforeEach(() => {
    apiMock.mockReset()
  })

  it('renders ledger labels and appends the next page by cursor', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects/p1/activity?limit=50') {
        return Promise.resolve({
          items: [
            activityItem({ id: 5, event_type: 'project.created', payload: { name: 'MeetFlow' } }),
            activityItem({ id: 4, event_type: 'project.progress_posted', subject: { type: 'project_update', id: 'up1' }, payload: { health: 'on_track' } }),
          ],
          next_cursor: 4,
        })
      }
      if (path === '/api/projects/p1/activity?limit=50&before=4') {
        return Promise.resolve({
          items: [activityItem({ id: 3, event_type: 'meeting.created', payload: { title: '迭代评审' } })],
          next_cursor: null,
        })
      }
      if (path === '/api/projects/p1/updates?limit=50&offset=0') return Promise.resolve([update])
      return Promise.resolve({})
    })

    renderActivity()

    expect(await screen.findByText(/创建了项目「MeetFlow」/)).toBeInTheDocument()
    expect(document.querySelector('.n-timeline')).not.toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/activity?limit=50&before=4'))
    expect(await screen.findByText(/创建了会议「迭代评审」/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '加载更多' })).not.toBeInTheDocument()
  })

  it('loads the progress history and offers more only when the page is full', async () => {
    const fullPage = Array.from({ length: 50 }, (_, index) => ({
      ...update,
      id: `up${index + 1}`,
      content_markdown: `进展 ${index + 1}`,
    }))
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects/p1/activity?limit=50') {
        return Promise.resolve({ items: [], next_cursor: null })
      }
      if (path === '/api/projects/p1/updates?limit=50&offset=0') return Promise.resolve(fullPage)
      if (path === '/api/projects/p1/updates?limit=50&offset=50') {
        return Promise.resolve([{ ...update, id: 'up51', content_markdown: '第 51 条进展' }])
      }
      return Promise.resolve({})
    })

    renderActivity()

    expect(await screen.findByText('进展 50')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/updates?limit=50&offset=50'))
    expect(await screen.findByText('第 51 条进展')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '加载更多' })).not.toBeInTheDocument()
  })

  it('edits a progress update and passes the original source through', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects/p1/activity?limit=50') {
        return Promise.resolve({ items: [activityItem({ id: 4, subject: { type: 'project_update', id: 'up1' }, event_type: 'project.progress_posted' })], next_cursor: null })
      }
      if (path === '/api/projects/p1/updates?limit=50&offset=0') return Promise.resolve([update])
      if (path === '/api/project-updates/up1' && init?.method === 'PUT') return Promise.resolve({ ...update, version: 3 })
      return Promise.resolve({})
    })

    renderActivity()
    await screen.findByText(/发布了项目进展/)
    await fireEvent.click(screen.getByRole('button', { name: '编辑进展 up1' }))

    expect(await screen.findByRole('heading', { name: '编辑项目进展' })).toBeInTheDocument()
    expect(screen.getByLabelText('进展内容')).toHaveValue('完成后端契约')
    await fireEvent.update(screen.getByLabelText('进展内容'), '完成后端契约并发布')
    await fireEvent.click(screen.getByRole('button', { name: '保存进展' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/project-updates/up1', expect.objectContaining({ method: 'PUT' })))
    const call = apiMock.mock.calls.find(([path, init]) => (
      path === '/api/project-updates/up1' && (init as RequestInit | undefined)?.method === 'PUT'
    ))
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      health: 'on_track',
      content_markdown: '完成后端契约并发布',
      source: 'ai_draft_applied',
      expected_version: 2,
    })
  })

  it('hides the composer and edit entries from read-only members', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects/p1/activity?limit=50') {
        return Promise.resolve({ items: [activityItem({ id: 4, subject: { type: 'project_update', id: 'up1' }, event_type: 'project.progress_posted' })], next_cursor: null })
      }
      if (path === '/api/projects/p1/updates?limit=50&offset=0') return Promise.resolve([update])
      return Promise.resolve({})
    })

    renderActivity(false)
    await screen.findByText(/发布了项目进展/)

    expect(screen.queryByRole('button', { name: '发布进展' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑进展 up1' })).not.toBeInTheDocument()
  })
})
