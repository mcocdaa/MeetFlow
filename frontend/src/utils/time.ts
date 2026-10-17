import { locale } from '../i18n'

export function parseUtcTimestamp(value: string): Date {
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

export function formatDateTime(value: string, options?: Intl.DateTimeFormatOptions) {
  const date = parseUtcTimestamp(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value === 'en' ? 'en-US' : 'zh-CN', options)
}

export function formatDate(value: string) {
  const date = parseUtcTimestamp(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN')
}

/** Shared duration formatting for agenda items and completed-meeting summaries. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const hours = Math.floor(seconds / 3600)
  const remainingSeconds = seconds % 3600
  const minutes = Math.floor(remainingSeconds / 60)
  const remainder = remainingSeconds % 60
  if (locale.value === 'en') {
    if (hours) return `${hours}h${minutes ? ` ${minutes}m` : ''}${remainder ? ` ${remainder}s` : ''}`
    if (!minutes) return `${remainder}s`
    return remainder ? `${minutes}m ${remainder}s` : `${minutes} min`
  }
  if (hours) return `${hours} 小时${minutes ? ` ${minutes} 分` : ''}${remainder ? ` ${remainder} 秒` : ''}`
  if (!minutes) return `${remainder} 秒`
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
}

/** Converts an ISO timestamp to the `datetime-local` / `n-date-picker` value shape. */
export function toLocalInput(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}
