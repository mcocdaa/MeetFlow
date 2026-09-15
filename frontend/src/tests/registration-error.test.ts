import { fireEvent, screen } from '@testing-library/vue'
import { afterEach, expect, it, vi } from 'vitest'

import RegisterView from '../views/RegisterView.vue'
import { renderWithProviders } from './helpers'

afterEach(() => vi.unstubAllGlobals())

const routerStubs = {
  RouterLink: { template: '<a><slot /></a>' },
}

function stubRegisterResponse(body: unknown, status: number) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function fillRegistrationForm() {
  await fireEvent.update(screen.getByLabelText('用户名'), 'member')
  await fireEvent.update(screen.getByLabelText('显示名称'), '新成员')
  await fireEvent.update(screen.getByLabelText('密码'), 'long-password-123')
}

it('keeps registration fields and shows the API error after a failed request', async () => {
  stubRegisterResponse({ error: { code: 'username_taken', message: '用户名已存在' } }, 409)
  renderWithProviders(RegisterView, {
    global: { stubs: routerStubs },
  })

  await fillRegistrationForm()
  await fireEvent.click(screen.getByRole('button', { name: '提交申请' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('用户名已存在')
  expect(screen.getByLabelText('用户名')).toHaveValue('member')
})

it('shows the registration_closed error after a rejected request', async () => {
  const fetchMock = stubRegisterResponse(
    { error: { code: 'registration_closed', message: '注册已关闭' } },
    403,
  )
  renderWithProviders(RegisterView, {
    global: { stubs: routerStubs },
  })

  await fillRegistrationForm()
  await fireEvent.click(screen.getByRole('button', { name: '提交申请' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('注册已关闭')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('does not call the register endpoint when the form is empty', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  renderWithProviders(RegisterView, {
    global: { stubs: routerStubs },
  })

  await fireEvent.click(screen.getByRole('button', { name: '提交申请' }))

  expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})
