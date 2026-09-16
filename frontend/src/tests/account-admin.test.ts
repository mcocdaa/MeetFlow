import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountView from '../views/AccountView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import { renderWithProviders } from './helpers'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushMock }) }))

const member = (overrides: Record<string, unknown> = {}) => ({
  id: 'u2',
  username: 'member',
  display_name: '成员甲',
  role: 'member',
  status: 'active',
  avatar_color: '#123456',
  ...overrides,
})

describe('account and user administration', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
  })

  it('changes password, shows a success message, and redirects to login', async () => {
    apiMock.mockResolvedValue(undefined)
    renderWithProviders(AccountView)

    await fireEvent.update(screen.getByLabelText('当前密码'), 'old-password-123')
    await fireEvent.update(screen.getByLabelText('新密码'), 'new-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '修改密码' }))

    expect(await screen.findByText('密码已修改，请重新登录')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/api/auth/change-password',
      expect.objectContaining({ method: 'POST' }),
    )
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })

  it('shows the wrong_password error inline and keeps the page', async () => {
    apiMock.mockRejectedValue(new Error('当前密码不正确'))
    renderWithProviders(AccountView)

    await fireEvent.update(screen.getByLabelText('当前密码'), 'wrong-password')
    await fireEvent.update(screen.getByLabelText('新密码'), 'new-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '修改密码' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('当前密码不正确')
    expect(pushMock).not.toHaveBeenCalled()
  })

  it('renders the member list as a table with the backend avatar color', async () => {
    apiMock.mockResolvedValueOnce([member({ avatar_color: '#123456' })])
    renderWithProviders(AdminUsersView)

    expect(await screen.findByText('成员甲')).toBeInTheDocument()
    expect(document.querySelector('.n-data-table')).not.toBeNull()
    const avatar = document.querySelector('.n-avatar')
    expect(avatar).not.toBeNull()
    expect(avatar?.getAttribute('style') ?? '').toMatch(/123456|18,\s*52,\s*86/)
  })

  it('approves a pending user after confirming in the popconfirm and reloads the list', async () => {
    apiMock
      .mockResolvedValueOnce([member({ status: 'pending' })])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([member({ status: 'active' })])
    renderWithProviders(AdminUsersView)
    await screen.findByText('成员甲')

    await fireEvent.click(screen.getByRole('button', { name: /^批准/ }))
    expect(await screen.findByText('确定批准 成员甲 的账号申请吗？')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/approve', { method: 'POST' })
    expect(await screen.findByText('已启用')).toBeInTheDocument()
  })

  it('rejects a pending user after confirming in the popconfirm', async () => {
    apiMock
      .mockResolvedValueOnce([member({ status: 'pending' })])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([member({ status: 'rejected' })])
    renderWithProviders(AdminUsersView)
    await screen.findByText('成员甲')

    await fireEvent.click(screen.getByRole('button', { name: /^拒绝/ }))
    expect(await screen.findByText('确定拒绝 成员甲 的账号申请吗？')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/reject', { method: 'POST' })
    expect(await screen.findByText('已拒绝')).toBeInTheDocument()
  })

  it('archives a member after the blocking dialog confirmation and restores them', async () => {
    apiMock
      .mockResolvedValueOnce([member()])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([member({ status: 'disabled' })])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([member({ status: 'active' })])
    renderWithProviders(AdminUsersView)
    await screen.findByText('成员甲')

    await fireEvent.click(screen.getByRole('button', { name: /^归档成员/ }))
    expect(await screen.findByText(/归档后 成员甲 将无法登录或执行操作/)).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/disable', { method: 'POST' })
    expect(await screen.findByText('已归档成员 (1)')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: /^恢复成员/ }))
    expect(await screen.findByText('确定恢复 成员甲 的成员资格吗？')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/restore', { method: 'POST' })
    expect(await screen.findByRole('button', { name: /^归档成员/ })).toBeInTheDocument()
  })

  it('resets a password through the drawer and blocks short passwords', async () => {
    apiMock
      .mockResolvedValueOnce([member()])
      .mockResolvedValueOnce(undefined)
    renderWithProviders(AdminUsersView)
    await screen.findByText('成员甲')

    await fireEvent.click(screen.getByRole('button', { name: /^重置密码/ }))
    expect(await screen.findByRole('heading', { name: '重置密码' })).toBeInTheDocument()

    await fireEvent.update(screen.getByLabelText('新密码'), 'short')
    await fireEvent.click(screen.getByRole('button', { name: '确认重置' }))
    expect(await screen.findByText('新密码至少 12 位')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalledWith('/api/admin/users/u2/reset-password', expect.anything())

    await fireEvent.update(screen.getByLabelText('新密码'), 'new-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '确认重置' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/reset-password', {
      method: 'POST',
      body: JSON.stringify({ password: 'new-password-123' }),
    }))
  })

  it('creates a fixed account from the retained form', async () => {
    apiMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ id: 'u9' })
      .mockResolvedValueOnce([member({ id: 'u9', username: 'fixed', display_name: '固定账号' })])
    renderWithProviders(AdminUsersView)

    await fireEvent.update(await screen.findByLabelText('固定账号用户名'), 'fixed')
    await fireEvent.update(screen.getByLabelText('显示名称'), '固定账号')
    await fireEvent.update(screen.getByLabelText('初始密码'), 'fixed-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '创建固定账号' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ username: 'fixed', display_name: '固定账号', password: 'fixed-password-123' }),
    }))
    expect(await screen.findByText('固定账号')).toBeInTheDocument()
  })
})
