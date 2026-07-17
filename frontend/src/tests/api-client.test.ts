import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from '../api/client'

describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends cookies and JSON content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api('/api/example', { method: 'POST', body: JSON.stringify({ value: 1 }) })

    expect(fetchMock).toHaveBeenCalledWith('/api/example', expect.objectContaining({
      credentials: 'include',
      headers: expect.any(Headers),
    }))
    const init = fetchMock.mock.calls[0][1]
    expect(init.headers.get('Content-Type')).toBe('application/json')
  })

  it('converts the uniform error envelope into ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'not_authenticated', message: '请先登录' },
    }), { status: 401, headers: { 'Content-Type': 'application/json' } })))

    await expect(api('/api/private')).rejects.toEqual(expect.objectContaining({
      status: 401,
      code: 'not_authenticated',
      message: '请先登录',
    }))
  })

  it('announces an expired session on HTTP 401', async () => {
    const listener = vi.fn()
    window.addEventListener('meetflow:auth-expired', listener)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'not_authenticated', message: '请先登录' },
    }), { status: 401, headers: { 'Content-Type': 'application/json' } })))
    await expect(api('/api/private')).rejects.toBeInstanceOf(ApiError)
    expect(listener).toHaveBeenCalledTimes(1)
    window.removeEventListener('meetflow:auth-expired', listener)
  })
})
