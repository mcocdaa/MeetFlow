export function parseUtcTimestamp(value: string): Date {
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

export function formatDateTime(value: string, options?: Intl.DateTimeFormatOptions) {
  const date = parseUtcTimestamp(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', options)
}

export function formatDate(value: string) {
  const date = parseUtcTimestamp(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('zh-CN')
}
