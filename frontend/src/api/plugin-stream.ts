function streamErrorMessage(payload: unknown): string {
  if (
    payload
    && typeof payload === 'object'
    && 'error' in payload
    && payload.error
    && typeof payload.error === 'object'
    && 'message' in payload.error
    && typeof payload.error.message === 'string'
  ) {
    return payload.error.message
  }
  return '请求失败，请稍后重试'
}

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
    throw new Error('AI 工作简报返回格式无效')
  }
  if (event === 'delta') {
    if (payload && typeof payload === 'object' && 'text' in payload && typeof payload.text === 'string') {
      onDelta(payload.text)
    }
    return false
  }
  if (event === 'error') {
    if (payload && typeof payload === 'object' && 'message' in payload && typeof payload.message === 'string') {
      throw new Error(payload.message)
    }
    throw new Error('AI 工作简报生成失败，请稍后重试')
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
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('meetflow:auth-expired'))
    }
    throw new Error(streamErrorMessage(payload))
  }
  if (!response.body) throw new Error('AI 工作简报未返回流式内容')

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
