import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

import {
  refreshUnread,
  resetUnread,
  startUnreadPolling,
  unreadCount,
} from '../composables/useInboxUnread'

const CHANGES_ENDPOINT = '/api/inbox/changes?cursor=0&limit=1'

let routeHooks: Array<() => void>
let stopPolling: (() => void) | null

const fakeRouter = {
  afterEach(callback: () => void) {
    routeHooks.push(callback)
  },
}

/** Flushes the microtasks queued by the refresh triggered from a fake timer/listener. */
async function flush() {
  await vi.advanceTimersByTimeAsync(0)
}

beforeEach(() => {
  vi.useFakeTimers()
  apiMock.mockReset()
  unreadCount.value = 0
  routeHooks = []
  stopPolling = null
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})

afterEach(() => {
  stopPolling?.()
  stopPolling = null
  vi.useRealTimers()
})

describe('useInboxUnread', () => {
  it('loads the unread count as soon as polling starts', async () => {
    apiMock.mockResolvedValue({ notifications: [], next_cursor: 4, has_more: false, unread_count: 3 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()

    expect(apiMock).toHaveBeenCalledWith(CHANGES_ENDPOINT)
    expect(unreadCount.value).toBe(3)
  })

  it('polls every 60 seconds', async () => {
    apiMock.mockResolvedValue({ unread_count: 1 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()
    expect(apiMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('refreshes when the document becomes visible again', async () => {
    apiMock.mockResolvedValue({ unread_count: 2 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()

    document.dispatchEvent(new Event('visibilitychange'))
    await flush()

    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('refreshes after each route change', async () => {
    apiMock.mockResolvedValue({ unread_count: 2 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()

    routeHooks.forEach((hook) => hook())
    await flush()

    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('falls back to the inbox endpoint when the changes request fails', async () => {
    apiMock
      .mockRejectedValueOnce(new Error('changes unavailable'))
      .mockResolvedValueOnce({ items: [], next_cursor: null, unread_count: 7 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()

    expect(apiMock).toHaveBeenNthCalledWith(1, CHANGES_ENDPOINT)
    expect(apiMock).toHaveBeenNthCalledWith(2, '/api/inbox')
    expect(unreadCount.value).toBe(7)
  })

  it('keeps the previous count when both endpoints fail', async () => {
    unreadCount.value = 5
    apiMock.mockRejectedValue(new Error('offline'))

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()

    expect(unreadCount.value).toBe(5)
  })

  it('resets the count and stops the timer, route hook and visibility listener', async () => {
    apiMock.mockResolvedValue({ unread_count: 3 })

    stopPolling = startUnreadPolling(fakeRouter)
    await flush()
    expect(unreadCount.value).toBe(3)

    resetUnread()
    expect(unreadCount.value).toBe(0)

    stopPolling()
    stopPolling()

    await vi.advanceTimersByTimeAsync(120_000)
    document.dispatchEvent(new Event('visibilitychange'))
    routeHooks.forEach((hook) => hook())
    await flush()

    expect(apiMock).toHaveBeenCalledTimes(1)
    expect(unreadCount.value).toBe(0)
  })

  it('exposes a standalone refresh', async () => {
    apiMock.mockResolvedValue({ unread_count: 4 })

    await refreshUnread()

    expect(unreadCount.value).toBe(4)
  })
})
