import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../api/client', () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}))

const routerStubs = {
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}

describe('authentication views', () => {
  beforeEach(() => apiMock.mockReset())

  it('submits credentials and emits the logged-in user', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/auth/config') return Promise.resolve({ allow_registration: true })
      return Promise.resolve({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'admin', status: 'active' })
    })
    const { emitted } = render(LoginView, { global: { stubs: routerStubs } })

    await fireEvent.update(screen.getByLabelText('用户名'), 'admin')
    await fireEvent.update(screen.getByLabelText('密码'), 'correct-horse-battery')
    await fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(apiMock).toHaveBeenCalledWith('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: 'admin', password: 'correct-horse-battery' }),
    })
    expect(emitted().loggedIn).toHaveLength(1)
  })

  it('shows the registration link only when registration is enabled', async () => {
    apiMock.mockResolvedValue({ allow_registration: true })
    render(LoginView, { global: { stubs: routerStubs } })
    expect(await screen.findByRole('link', { name: '申请账号' })).toBeInTheDocument()
  })

  it('confirms that a successful registration is waiting for approval', async () => {
    apiMock.mockResolvedValue({ status: 'pending' })
    render(RegisterView, { global: { stubs: routerStubs } })

    await fireEvent.update(screen.getByLabelText('用户名'), 'member')
    await fireEvent.update(screen.getByLabelText('显示名称'), '新成员')
    await fireEvent.update(screen.getByLabelText('密码'), 'long-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '提交申请' }))

    await waitFor(() => expect(screen.getByText('申请已提交，请等待管理员批准。')).toBeInTheDocument())
  })
})
