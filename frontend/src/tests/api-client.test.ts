import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, apiDownload, ApiError, apiErrorMessage } from '../api/client'
import { setLocale } from '../i18n'
import { errorMessage, translateBackendError } from '../utils/errors'

describe('api client', () => {
  afterEach(() => {
    setLocale('zh')
    vi.unstubAllGlobals()
  })

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

  it('preserves structured conflict details for recovery UI', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'version_conflict', message: '内容已更新', details: { actual_version: 4 } },
    }), { status: 409, headers: { 'Content-Type': 'application/json' } })))

    await expect(api('/api/agenda-items/a1', { method: 'PUT', body: '{}' })).rejects.toMatchObject({
      status: 409,
      code: 'version_conflict',
      details: { actual_version: 4 },
    })
  })

  it('returns a bounded download and decodes its server filename', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('hello', {
      status: 200,
      headers: { 'Content-Disposition': "attachment; filename*=UTF-8''meeting%20notes.md" },
    })))

    const result = await apiDownload('/api/meetings/m1/plugin-exports/meeting-export.markdown', { method: 'POST' })

    expect(result.filename).toBe('meeting notes.md')
    expect(result.blob.size).toBe(5)
  })

  it('translates backend Chinese errors and worker diagnostics in en mode', () => {
    setLocale('en')

    expect(apiErrorMessage({ error: { code: 'invalid_credentials', message: '用户名或密码错误' } }))
      .toBe('Incorrect username or password')
    expect(apiErrorMessage({ error: { code: 'validation_error', message: '请求参数无效' } }))
      .toBe('Invalid request parameters')
    expect(apiErrorMessage({ error: { code: 'meeting_locked', message: '已结束的会议不可直接修改' } }))
      .toBe('Meeting is locked')
    expect(translateBackendError('认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。', 'provider_auth_failed'))
      .toBe('Authentication or permission failed; check API Key, endpoint URL, and permissions in plugin settings.')
    expect(translateBackendError('插件清单无效', 'ManifestError'))
      .toBe('Invalid plugin manifest')
    expect(errorMessage(new Error('未知后端中文错误'), 'Sign in failed'))
      .toBe('Sign in failed')
  })
})
