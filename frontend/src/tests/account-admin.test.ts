import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountView from '../views/AccountView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushMock }) }))

describe('account and user administration', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
  })

  it('changes password and redirects to login', async () => {
    apiMock.mockResolvedValue(undefined)
    render(AccountView)
    await fireEvent.update(screen.getByLabelText('当前密码'), 'old-password-123')
    await fireEvent.update(screen.getByLabelText('新密码'), 'new-password-123')
    await fireEvent.click(screen.getByRole('button', { name: '修改密码' }))
    expect(apiMock).toHaveBeenCalledWith('/api/auth/change-password', expect.objectContaining({ method: 'POST' }))
    expect(pushMock).toHaveBeenCalledWith('/login')
  })

  it('approves a pending user and reloads the list', async () => {
    apiMock
      .mockResolvedValueOnce([{ id: 'u2', username: 'new', display_name: '新人', role: 'member', status: 'pending' }])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce([{ id: 'u2', username: 'new', display_name: '新人', role: 'member', status: 'active' }])
    render(AdminUsersView)
    await screen.findByText('新人')
    await fireEvent.click(screen.getByRole('button', { name: '批准' }))
    expect(apiMock).toHaveBeenCalledWith('/api/admin/users/u2/approve', { method: 'POST' })
    expect(await screen.findByText('已启用')).toBeInTheDocument()
  })
})
