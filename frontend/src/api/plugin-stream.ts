import { locale } from '../i18n'
import { translateBackendError } from '../utils/errors'
import { apiErrorMessage, dispatchAuthExpired } from './client'

function consumeEvent(block: string, onDelta: (text: string) => void): boolean {
  const lines = block.split('\n')
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() ?? 'message'
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n')
  if (!data) return false

  let payload: unknown
  try {
    payload = JSON.parse(data)
  } catch {
    throw new Error(locale.value === 'en' ? 'Invalid AI work brief response format' : 'AI 工作简报返回格式无效')
  }
  if (event === 'delta') {
    if (payload && typeof payload === 'object' && 'text' in payload && typeof payload.text === 'string') {
      onDelta(payload.text)
    }
    return false
  }
  if (event === 'error') {
    if (payload && typeof payload === 'object' && 'message' in payload && typeof payload.message === 'string') {
      const code = 'code' in payload && typeof payload.code === 'string' ? payload.code : null
      throw new Error(translateBackendError(payload.message, code))
    }
    throw new Error(locale.value === 'en' ? 'Failed to generate AI work brief, please try again later' : 'AI 工作简报生成失败，请稍后重试')
  }
  return event === 'done'
}

export async function streamPluginAction(
  actionId: string,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/plugins/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ action_id: actionId, input: {} }),
    signal,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    if (response.status === 401) dispatchAuthExpired()
    throw new Error(apiErrorMessage(payload, locale.value === 'en' ? 'AI work brief request failed, please try again later' : 'AI 工作简报请求失败，请稍后重试'))
  }
  if (!response.body) throw new Error(locale.value === 'en' ? 'AI work brief returned no stream content' : 'AI 工作简报未返回流式内容')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  while (true) {
    const { done, value } = await reader.read()
    pending += decoder.decode(value, { stream: !done })
    let separator = pending.indexOf('\n\n')
    while (separator >= 0) {
      const complete = consumeEvent(pending.slice(0, separator), onDelta)
      pending = pending.slice(separator + 2)
      if (complete) return
      separator = pending.indexOf('\n\n')
    }
    if (done) break
  }
  if (pending.trim()) consumeEvent(pending, onDelta)
}
