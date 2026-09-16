import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { session } from '../auth/session'
import { unreadCount } from '../composables/useInboxUnread'

const { apiMock, pushMock, routeAfterEachMock, loadPluginFrontendModulesMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  pushMock: vi.fn(),
  routeAfterEachMock: vi.fn(() => vi.fn()),
  loadPluginFrontendModulesMock: vi.fn(),
}))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('../plugins/runtime', () => ({ loadPluginFrontendModules: loadPluginFrontendModulesMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock, afterEach: routeAfterEachMock }),
  useRoute: () => ({ path: '/' }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  RouterView: {
    emits: ['logged-in'],
    template: '<button type="button" @click="$emit(\'logged-in\', { id: \'u2\', username: \'member\', display_name: \'成员\', role: \'member\', status: \'active\' })">模拟登录</button>',
  },
}))

beforeEach(() => {
  apiMock.mockReset()
  pushMock.mockReset()
  routeAfterEachMock.mockReset()
  routeAfterEachMock.mockImplementation(() => vi.fn())
  loadPluginFrontendModulesMock.mockReset()
  unreadCount.value = 0
  session.user = { id: 'u1', username: 'admin', display_name: '管理员', role: 'admin', status: 'active' }
  session.loaded = true
})

it('uses workspace navigation instead of the legacy meeting archive shell', () => {
  render(App)

  const workspaceNavigation = screen.getByRole('navigation', { name: '工作区导航' })
  for (const label of ['为你', '项目', '会议', '行动项', '决策', '收件箱', 'AI 任务']) {
    const link = within(workspaceNavigation).getByRole('link', { name: label })
    expect(link.querySelector('svg')).not.toBeNull()
  }

  const administratorNavigation = screen.getByRole('navigation', { name: '管理员导航' })
  for (const label of ['用户', '插件', '设置']) {
    const link = within(administratorNavigation).getByRole('link', { name: label })
    expect(link.querySelector('svg')).not.toBeNull()
  }

  expect(screen.queryByText('会议不是终点')).not.toBeInTheDocument()
})

it('nests the workspace shell in a naive layout with sider and content', () => {
  const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  try {
    render(App)

    const layout = document.querySelector('.n-layout.shell-layout')
    const sider = document.querySelector('.n-layout-sider.workspace-sidebar')
    const content = document.querySelector('.n-layout-content.workspace-main')

    expect(layout).not.toBeNull()
    expect(sider).not.toBeNull()
    expect(content).not.toBeNull()
    expect(sider?.parentElement?.style.display).toBe('flex')
    // Naive warns when a sider sits in a layout without `has-sider`.
    expect(warnSpy.mock.calls.flat().join(' ')).not.toContain('has-sider')
  } finally {
    warnSpy.mockRestore()
  }
})

it('shows administrator navigation only to administrators', async () => {
  render(App)
  expect(screen.getByRole('link', { name: '用户' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '插件' })).toBeInTheDocument()
  session.user = { ...session.user!, role: 'member' }
  await waitFor(() => expect(screen.queryByRole('link', { name: '用户' })).not.toBeInTheDocument())
})

it('shows the unread badge on the inbox entry', () => {
  unreadCount.value = 3
  render(App)

  const workspaceNavigation = screen.getByRole('navigation', { name: '工作区导航' })
  const inboxLink = within(workspaceNavigation).getByRole('link', { name: '收件箱' })

  // NBadge animates numbers through a slot machine, so assert on the badge element instead of
  // a single text node.
  const badge = inboxLink.querySelector('.n-badge[aria-hidden="true"]')
  expect(badge).not.toBeNull()
  expect(badge).toHaveTextContent('3')
})

it('logs out from the account dropdown, clears the session, and returns to login', async () => {
  apiMock.mockResolvedValue(undefined)
  unreadCount.value = 5
  render(App)

  await fireEvent.click(screen.getByRole('button', { name: '账户菜单' }))
  await fireEvent.click(await screen.findByText('退出登录'))

  expect(apiMock).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST' })
  expect(session.user).toBeNull()
  expect(unreadCount.value).toBe(0)
  expect(pushMock).toHaveBeenCalledWith('/login')
})

it('opens account settings from the account dropdown', async () => {
  render(App)

  await fireEvent.click(screen.getByRole('button', { name: '账户菜单' }))
  await fireEvent.click(await screen.findByText('账号设置'))

  expect(pushMock).toHaveBeenCalledWith('/account')
})

it('shows the unread bell and opens the inbox', async () => {
  apiMock.mockImplementation((path: string) =>
    path.startsWith('/api/inbox/changes')
      ? Promise.resolve({ notifications: [], next_cursor: 4, has_more: false, unread_count: 2 })
      : Promise.resolve(undefined),
  )
  render(App)

  const bell = await screen.findByRole('button', { name: '收件箱' })
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/inbox/changes?cursor=0&limit=1'))
  await waitFor(() => expect(bell.closest('.n-badge')).toHaveTextContent('2'))

  await fireEvent.click(bell)
  expect(pushMock).toHaveBeenCalledWith('/inbox')
})

it('clears the shell when the API announces an expired session', async () => {
  render(App)
  window.dispatchEvent(new CustomEvent('meetflow:auth-expired'))
  await waitFor(() => expect(session.user).toBeNull())
  expect(pushMock).toHaveBeenCalledWith('/login')
})

it('loads plugin frontend modules after a successful login', async () => {
  session.user = null
  session.loaded = false
  render(App)

  await fireEvent.click(screen.getByRole('button', { name: '模拟登录' }))

  expect(session.user).toMatchObject({ id: 'u2', username: 'member' })
  expect(loadPluginFrontendModulesMock).toHaveBeenCalledTimes(1)
  expect(pushMock).toHaveBeenCalledWith('/')
})
