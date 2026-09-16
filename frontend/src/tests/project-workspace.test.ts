import { defineComponent, onBeforeUnmount, onMounted } from 'vue'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectDetailView from '../views/ProjectDetailView.vue'
import { ApiError } from '../api/client'
import { session } from '../auth/session'
import { registerEditorAssistant } from '../plugins/registry'
import { renderWithProviders } from './helpers'
import '../styles.css'

const { apiMock, pushMock, replaceMock, routeMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  routeMock: { params: { id: 'p1' }, query: {} as Record<string, string> },
}))
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  api: apiMock,
}))
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'label', 'disabled', 'registerEditor'],
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      const writer = (markdown: string) => emit('update:modelValue', markdown)
      onMounted(() => props.registerEditor?.(writer))
      onBeforeUnmount(() => props.registerEditor?.(null))
      return {}
    },
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  }),
}))

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '团队会议工作区', description_markdown: '项目说明',
  status: 'active', health: 'on_track', lead: { id: 'u1', username: 'lin', display_name: '林宇' }, target_date: '2026-08-01', version: 3,
  memberships: [
    { role: 'member', user: { id: 'u1', username: 'lin', display_name: '林宇' } },
    { role: 'stakeholder', user: { id: 'u2', username: 'qiao', display_name: '乔一' } },
  ],
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
  updates: [{ id: 'up1', project_id: 'p1', health: 'on_track', content_markdown: '完成后端契约', source: 'human', created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '2026-07-22T10:00:00Z', updated_at: '2026-07-22T10:00:00Z' }],
  next_meeting: { id: 'm1', title: '迭代评审', scheduled_start: '2026-07-24T02:00:00Z', status: 'ready' },
  recent_decisions: [{ id: 'd1', title: '采用项目工作区', status: 'final' }],
  meeting_count: 4, decision_count: 2, open_action_count: 3, series_summaries: [], attachments: [],
  created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, updated_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '', updated_at: '',
}

const ProjectUpdateAssistant = defineComponent({
  emits: ['update:modelValue'],
  template: '<button type="button" @click="$emit(\'update:modelValue\', \'# AI 项目进展\')">AI 提示</button>',
})

function defaultProjectResponse(path: string) {
  if (path === '/api/projects/p1') return Promise.resolve(project)
  if (path === '/api/attention') return Promise.resolve({ items: [], unread_count: 0, truncated: false })
  return Promise.resolve([])
}

describe('project workspace', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
    replaceMock.mockReset()
    routeMock.query = {}
    session.user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member', status: 'active' }
    session.loaded = true
    apiMock.mockImplementation(defaultProjectResponse)
  })

  it('keeps overview focused on project state and actionable summaries', async () => {
    renderWithProviders(ProjectDetailView)
    expect(await screen.findByRole('heading', { name: 'MeetFlow' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '项目状态' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '下一次会议' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '需要处理' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '近期行动项' })).toBeInTheDocument()
    expect(screen.queryByLabelText('进展记录')).not.toBeInTheDocument()
    expect(screen.queryByTestId('project-inline-progress')).not.toBeInTheDocument()
  })

  it('stretches dashboard cards within each overview row', async () => {
    const { container } = renderWithProviders(ProjectDetailView)

    await screen.findByRole('heading', { name: '项目状态' })
    const grid = container.querySelector<HTMLElement>('.project-overview-grid')

    expect(grid).not.toBeNull()
    expect(getComputedStyle(grid as HTMLElement).alignItems).toBe('stretch')
  })

  it('does not expose project mutation controls to a read-only stakeholder', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects/p1') {
        return Promise.resolve({
          ...project,
          capabilities: { can_manage: false, can_contribute: false, can_comment: false },
        })
      }
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)

    expect(await screen.findByRole('heading', { name: 'MeetFlow' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑项目' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除项目' })).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('tab', { name: '动态' }))
    expect(screen.queryByLabelText('进展记录')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '发布进展' })).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('tab', { name: '会议' }))
    expect(screen.queryByRole('button', { name: '添加会议' })).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('tab', { name: '文件' }))
    expect(screen.queryByLabelText('上传附件')).not.toBeInTheDocument()
  })

  it('keeps project progress editing with its AI assistance in Activity', async () => {
    registerEditorAssistant('project-update-editor', ProjectUpdateAssistant)
    renderWithProviders(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('tab', { name: '动态' }))
    expect(screen.getByLabelText('进展记录')).toBeInTheDocument()
    const updateEditor = screen.getByTestId('project-update-editor')
    expect(updateEditor).toContainElement(screen.getByLabelText('进展记录'))
    expect(within(updateEditor).getByText('进展记录')).toBeVisible()
    await fireEvent.click(within(updateEditor).getByRole('button', { name: 'AI 工具' }))
    expect(within(updateEditor).getByRole('button', { name: 'AI 提示' })).toBeVisible()
    await fireEvent.click(within(updateEditor).getByRole('button', { name: 'AI 提示' }))
    expect(screen.getByLabelText('进展记录')).toHaveValue('# AI 项目进展')
    expect(apiMock).not.toHaveBeenCalledWith('/api/projects/p1/updates', expect.anything())
    expect(screen.queryByTestId('project-inline-progress')).not.toBeInTheDocument()
  })

  it('opens an action drawer from the global New menu', async () => {
    renderWithProviders(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建' }))
    await fireEvent.click(await screen.findByRole('button', { name: '行动项' }))
    expect(await screen.findByRole('heading', { name: '添加行动项' })).toBeInTheDocument()
    expect(screen.getByLabelText('行动项内容')).toBeInTheDocument()
  })

  it('loads project actions in the Actions tab', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/actions?project_id=p1') {
        return Promise.resolve({ items: [{ id: 'a1', content: '确认范围', status: 'open', priority: 'high', owner_user_id: 'u1', due_date: '2026-07-25', meeting_id: 'm1', version: 1, is_derived: false }], total: 1 })
      }
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('tab', { name: '行动项' }))
    expect(await screen.findByText('确认范围')).toBeInTheDocument()
  })

  it('appends a human progress update and reloads authoritative data', async () => {
    renderWithProviders(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('tab', { name: '动态' }))
    await fireEvent.update(screen.getByLabelText('进展记录'), '完成 1.0 前端壳层')
    await fireEvent.click(screen.getByRole('button', { name: '发布进展' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/updates', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ health: 'on_track', content_markdown: '完成 1.0 前端壳层', source: 'human' }),
    })))
    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1')
  })

  it('opens a project-scoped meeting drawer from Next meeting', async () => {
    renderWithProviders(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建' }))
    await fireEvent.click(await screen.findByRole('button', { name: '会议' }))

    expect(await screen.findByRole('heading', { name: '新建会议' })).toBeInTheDocument()
    expect(screen.getByLabelText('会议标题')).toBeInTheDocument()
  })

  it('activates the tab from the ?tab= query and keeps the URL in sync', async () => {
    routeMock.query = { tab: 'activity' }
    renderWithProviders(ProjectDetailView)

    await screen.findByRole('heading', { name: 'MeetFlow' })
    expect(screen.getByRole('tab', { name: '动态' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByLabelText('进展记录')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('tab', { name: '会议' }))
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith({ query: { tab: 'meetings' } }))
  })

  it('opens the project edit drawer with members and read-only roles', async () => {
    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '编辑项目' }))

    expect(await screen.findByRole('heading', { name: '编辑项目' })).toBeInTheDocument()
    expect(screen.getByLabelText('名称')).toHaveValue('MeetFlow')
    expect(screen.getByLabelText('摘要')).toHaveValue('团队会议工作区')
    expect(screen.getByLabelText('目标日期')).toHaveValue('2026-08-01')
    const drawer = document.querySelector('.n-drawer-container') as HTMLElement
    expect(within(drawer).getByText('状态')).toBeInTheDocument()
    expect(within(drawer).getByText('健康度')).toBeInTheDocument()
    expect(within(drawer).getByText('负责人')).toBeInTheDocument()
    expect(within(drawer).getByText('成员')).toBeInTheDocument()
    expect(within(drawer).getByText('林宇 · 成员')).toBeInTheDocument()
    expect(within(drawer).getByText('乔一 · 干系人')).toBeInTheDocument()
    expect(screen.getByText('移除成员会立即撤销其项目访问，但不会删除其历史记录。')).toBeInTheDocument()
    expect(screen.getByText('干系人可查看不可编辑；当前没有成员角色指引入口。')).toBeInTheDocument()
  })

  it('saves project edits with expected version, lead, and the resulting member list', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects/p1' && init?.method === 'PUT') {
        return Promise.resolve({ ...project, name: 'MeetFlow 2', version: 4 })
      }
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '编辑项目' }))
    await screen.findByRole('heading', { name: '编辑项目' })

    await fireEvent.update(screen.getByLabelText('名称'), 'MeetFlow 2')
    await fireEvent.click(document.querySelector('.project-edit-member-select .n-base-selection')!)
    const memberOption = await waitFor(() => {
      const option = [...document.querySelectorAll('.n-base-select-option__content')]
        .find((candidate) => candidate.textContent === '乔一')
      if (!option) throw new Error('member option is not open yet')
      return option
    })
    await fireEvent.click(memberOption)
    await fireEvent.click(screen.getByRole('button', { name: '保存项目' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1', expect.objectContaining({ method: 'PUT' })))
    const putCall = apiMock.mock.calls.find(([path, init]) => (
      path === '/api/projects/p1' && (init as RequestInit | undefined)?.method === 'PUT'
    ))
    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload).toMatchObject({
      name: 'MeetFlow 2',
      expected_version: 3,
      lead_user_id: 'u1',
      member_ids: ['u1'],
    })
    await waitFor(() => expect(screen.queryByRole('heading', { name: '编辑项目' })).not.toBeInTheDocument())
  })

  it('resolves a project edit version conflict through the shared dialog', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects/p1' && init?.method === 'PUT') {
        const payload = JSON.parse(String((init as RequestInit).body))
        if (payload.expected_version === 3) {
          return Promise.reject(new ApiError(409, 'version_conflict', '内容已更新', { actual_version: 4 }))
        }
        return Promise.resolve({ ...project, name: 'MeetFlow 2', version: 5 })
      }
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '编辑项目' }))
    await screen.findByRole('heading', { name: '编辑项目' })
    await fireEvent.update(screen.getByLabelText('名称'), 'MeetFlow 2')
    await fireEvent.click(screen.getByRole('button', { name: '保存项目' }))

    expect(await screen.findByText('内容已被其他成员更新')).toBeInTheDocument()
    await screen.findByText(/名称：MeetFlow 2/)
    await fireEvent.click(screen.getByRole('button', { name: '用本地草稿覆盖' }))

    await waitFor(() => {
      const puts = apiMock.mock.calls.filter(([path, init]) => (
        path === '/api/projects/p1' && (init as RequestInit | undefined)?.method === 'PUT'
      ))
      expect(puts).toHaveLength(2)
      expect(JSON.parse(String((puts[1][1] as RequestInit).body)).expected_version).toBe(4)
    })
  })

  it('deletes an empty project after typing its name to confirm', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects/p1' && init?.method === 'DELETE') return Promise.resolve(undefined)
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '删除项目' }))
    expect(await screen.findByText(/仅当项目下没有会议且没有项目附件时才能删除/)).toBeInTheDocument()

    await fireEvent.update(screen.getByLabelText('输入项目名称确认'), 'MeetFlow')
    await fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1', { method: 'DELETE' }))
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/projects'))
  })

  it.each([
    [new ApiError(409, 'project_not_empty', '项目下已有会议，不能删除')],
    [new ApiError(409, 'project_has_attachments', '项目已有附件，不能删除')],
    [new ApiError(403, 'project_delete_forbidden', '只有管理员或项目负责人可以删除项目')],
  ])('shows the backend delete constraint without navigating away (%s)', async (failure) => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects/p1' && init?.method === 'DELETE') return Promise.reject(failure)
      return defaultProjectResponse(path)
    })

    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '删除项目' }))
    await fireEvent.update(await screen.findByLabelText('输入项目名称确认'), 'MeetFlow')
    await fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    expect(await screen.findByText(failure.message)).toBeInTheDocument()
    expect(pushMock).not.toHaveBeenCalled()
  })

  it('requires the exact project name before sending the delete request', async () => {
    renderWithProviders(ProjectDetailView)
    await screen.findByRole('heading', { name: 'MeetFlow' })
    await fireEvent.click(screen.getByRole('button', { name: '删除项目' }))
    await fireEvent.click(await screen.findByRole('button', { name: '确认删除' }))

    expect(await screen.findByText('请输入完整项目名称以确认删除')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalledWith('/api/projects/p1', { method: 'DELETE' })
    expect(pushMock).not.toHaveBeenCalled()
  })
})
