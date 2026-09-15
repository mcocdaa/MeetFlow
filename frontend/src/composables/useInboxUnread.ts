import { ref } from 'vue'

import { api } from '../api/client'

/**
 * Shell-level inbox unread singleton.
 *
 * The source of truth is `GET /api/inbox/changes?cursor=0&limit=1` (`unread_count`), with a
 * fallback to `GET /api/inbox` when the cursor endpoint fails. Only the shell starts the
 * polling loop; views (including the inbox page) call `refreshUnread()` instead of owning
 * their own timers so the app never polls twice for the same badge.
 */

type UnreadPayload = { unread_count?: number }

const POLL_INTERVAL_MS = 60_000
const CHANGES_ENDPOINT = '/api/inbox/changes?cursor=0&limit=1'
const INBOX_ENDPOINT = '/api/inbox'

export const unreadCount = ref(0)

let stopActivePolling: (() => void) | null = null

/** Refreshes the unread count, silently keeping the previous value when both endpoints fail. */
export async function refreshUnread(): Promise<void> {
  try {
    const value = await api<UnreadPayload>(CHANGES_ENDPOINT)
    if (typeof value?.unread_count === 'number') unreadCount.value = value.unread_count
    return
  } catch {
    // Fall through to the inbox endpoint below.
  }
  try {
    const value = await api<UnreadPayload>(INBOX_ENDPOINT)
    if (typeof value?.unread_count === 'number') unreadCount.value = value.unread_count
  } catch {
    // Unread polling must never interrupt the current page; keep the previous value.
  }
}

export function resetUnread(): void {
  unreadCount.value = 0
}

/**
 * Starts the 60s poll, the route-change refresh and the foreground refresh.
 * Returns an idempotent stop function that clears the timer and removes the listeners.
 */
export function startUnreadPolling(router: { afterEach: (callback: () => void) => () => void }): () => void {
  stopActivePolling?.()

  let stopped = false
  const refresh = () => {
    if (!stopped) void refreshUnread()
  }
  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') refresh()
  }

  const timer = window.setInterval(refresh, POLL_INTERVAL_MS)
  const removeRouteHook = router.afterEach(refresh)
  document.addEventListener('visibilitychange', onVisibilityChange)
  refresh()

  const stop = () => {
    if (stopped) return
    stopped = true
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    removeRouteHook()
    if (stopActivePolling === stop) stopActivePolling = null
  }
  stopActivePolling = stop
  return stop
}
