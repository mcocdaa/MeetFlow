import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, expect, it, vi } from 'vitest'

import RegisterView from '../views/RegisterView.vue'

afterEach(() => vi.unstubAllGlobals())

it('keeps registration fields and shows the API error after a failed request', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: 'username_taken', message: '用户名已存在' },
  }), { status: 409, headers: { 'Content-Type': 'application/json' } })))
  render(RegisterView, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })

  await fireEvent.update(screen.getByLabelText('用户名'), 'member')
  await fireEvent.update(screen.getByLabelText('显示名称'), '新成员')
  await fireEvent.update(screen.getByLabelText('密码'), 'long-password-123')
  await fireEvent.click(screen.getByRole('button', { name: '提交申请' }))

  expect(await screen.findByText('用户名已存在')).toBeInTheDocument()
  expect(screen.getByLabelText('用户名')).toHaveValue('member')
})
