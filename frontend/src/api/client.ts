export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function throwApiError(response: Response): Promise<never> {
  const payload = await response.json().catch(() => ({
    error: { code: 'request_failed', message: '请求失败，请稍后重试' },
  })) as { error?: { code?: string; message?: string; details?: Record<string, unknown> } }
  if (response.status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('meetflow:auth-expired'))
  }
  throw new ApiError(
    response.status,
    payload.error?.code ?? 'request_failed',
    payload.error?.message ?? '请求失败，请稍后重试',
    payload.error?.details,
  )
}

function requestHeaders(init: RequestInit) {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  return headers
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: requestHeaders(init),
    credentials: 'include',
  })

  if (!response.ok) await throwApiError(response)

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function apiDownload(path: string, init: RequestInit = {}): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(path, {
    ...init,
    headers: requestHeaders(init),
    credentials: 'include',
  })
  if (!response.ok) await throwApiError(response)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  let filename = 'download'
  if (encoded) {
    try { filename = decodeURIComponent(encoded) } catch { filename = encoded }
  }
  return { blob: await response.blob(), filename }
}
