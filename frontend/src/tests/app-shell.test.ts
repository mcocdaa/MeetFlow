import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { session } from '../auth/session'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  RouterView: { template: '<div></div>' },
}))

beforeEach(() => {
  apiMock.mockReset()
  pushMock.mockReset()
  session.user = { id: 'u1', username: 'admin', display_name: '管理员', role: 'admin', status: 'active' }
  session.loaded = true
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
