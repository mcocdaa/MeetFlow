import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../api/client', () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}))

const routerStubs = {
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}

describe('authentication views', () => {
  // A block body matters: `() => apiMock.mockReset()` returns the mock, which Vitest
  // treats as a teardown callback and would invoke (once) after each test.
  beforeEach(() => {
    apiMock.mockReset()
  })

  it('submits credentials and emits the logged-in user', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/auth/config') return Promise.resolve({ allow_registration: true })
      return Promise.resolve({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'admin', status: 'active' })
    })
    // `renderWithProviders` mounts the providers as the root component, so `emitted()` would
    // record the wrapper instead of the view; a listener prop asserts the same contract.
    const onLoggedIn = vi.fn()
    renderWithProviders(LoginView, { props: { onLoggedIn }, global: { stubs: routerStubs } })

    await fireEvent.update(screen.getByLabelText('用户名'), 'admin')
    await fireEvent.update(screen.getByLabelText('密码'), 'correct-horse-battery')
    await fireEvent.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: 'admin', password: 'correct-horse-battery' }),
      }),
    )
    expect(onLoggedIn).toHaveBeenCalledTimes(1)
    expect(onLoggedIn).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'u1', username: 'admin' }),
    )
  })

  it('ignores repeated submits while the login request is pending', async () => {
    let resolveLogin: ((value: unknown) => void) | undefined
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/auth/config') return Promise.resolve({ allow_registration: false })
      return new Promise((resolve) => { resolveLogin = resolve })
    })
    const onLoggedIn = vi.fn()
    renderWithProviders(LoginView, { props: { onLoggedIn }, global: { stubs: routerStubs } })

    await fireEvent.update(screen.getByLabelText('用户名'), 'admin')
    await fireEvent.update(screen.getByLabelText('密码'), 'correct-horse-battery')
    const button = screen.getByRole('button', { name: '登录' })
    // Two synchronous clicks: the guard must be set before the async validation resolves.
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    const loginCalls = () => apiMock.mock.calls.filter(([path]) => path === '/api/auth/login')
    await waitFor(() => expect(loginCalls()).toHaveLength(1))

    resolveLogin?.({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'admin', status: 'active' })
    await waitFor(() => expect(onLoggedIn).toHaveBeenCalledTimes(1))
  })

  it('keeps the API error message visible when login fails', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/auth/login') return Promise.reject(new Error('用户名或密码错误'))
      return Promise.resolve({ allow_registration: true })
    })
    renderWithProviders(LoginView, { global: { stubs: routerStubs } })

    await fireEvent.update(screen.getByLabelText('用户名'), 'admin')
    await fireEvent.update(screen.getByLabelText('密码'), 'bad-password')
    await fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('用户名或密码错误')
  })

  it('does not call the API when the login form is empty', async () => {
    apiMock.mockResolvedValue({ allow_registration: false })
    renderWithProviders(LoginView, { global: { stubs: routerStubs } })
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/auth/config'))
    apiMock.mockClear()

    await fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('shows the registration link only when registration is enabled', async () => {
    apiMock.mockResolvedValue({ allow_registration: true })
    renderWithProviders(LoginView, { global: { stubs: routerStubs } })
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
