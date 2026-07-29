import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { session } from '../auth/session'

const { apiMock, pushMock, loadPluginFrontendModulesMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  pushMock: vi.fn(),
  loadPluginFrontendModulesMock: vi.fn(),
}))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('../plugins/runtime', () => ({ loadPluginFrontendModules: loadPluginFrontendModulesMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  RouterView: {
    emits: ['logged-in'],
    template: '<button type="button" @click="$emit(\'logged-in\', { id: \'u2\', username: \'member\', display_name: \'成员\', role: \'member\', status: \'active\' })">模拟登录</button>',
  },
}))

beforeEach(() => {
  apiMock.mockReset()
  pushMock.mockReset()
  loadPluginFrontendModulesMock.mockReset()
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

it('shows administrator navigation only to administrators', async () => {
  render(App)
  expect(screen.getByRole('link', { name: '用户' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '插件' })).toBeInTheDocument()
  session.user = { ...session.user!, role: 'member' }
  await waitFor(() => expect(screen.queryByRole('link', { name: '用户' })).not.toBeInTheDocument())
})

it('logs out, clears the session, and returns to login', async () => {
  apiMock.mockResolvedValue(undefined)
  render(App)
  await fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
  expect(apiMock).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST' })
  expect(session.user).toBeNull()
  expect(pushMock).toHaveBeenCalledWith('/login')
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
