<script setup lang="ts">
import { NAlert, NButton, NEmpty, NList, NListItem } from 'naive-ui'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { refreshUnread } from '../composables/useInboxUnread'
import { errorMessage } from '../utils/errors'
import { notificationHref, subjectLabel } from '../utils/links'
import { formatDateTime } from '../utils/time'

type NotificationItem = {
  id: number
  actor: { id: string; username: string; display_name: string; avatar_color: string } | null
  kind: string
  subject: { type: string; id: string }
  project: { id: string } | null
  meeting: { id: string } | null
  source_comment: { id: string } | null
  data: Record<string, unknown>
  read_at: string | null
  created_at: string
}

type InboxChanges = {
  notifications: NotificationItem[]
  next_cursor: number
  has_more: boolean
  unread_count: number
}

const CHANGES_PAGE_SIZE = 50

const items = ref<NotificationItem[]>([])
const nextCursor = ref<number | null>(null)
const changesCursor = ref(0)
const hasMoreChanges = ref(false)
const unreadCount = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const readAllBusy = ref(false)
const error = ref('')
let changesInFlight = false

const kindLabels: Record<string, string> = {
  'action.assigned': '分配了行动项给你',
  'decision.review_requested': '请求你评审决策',
  'comment.mention': '提到了你',
  'comment.reply': '回复了你',
}

const actorLabel = (item: NotificationItem) =>
  item.actor?.display_name || item.actor?.username || '系统'

const message = (item: NotificationItem) =>
  `${actorLabel(item)} · ${kindLabels[item.kind] ?? item.kind} · ${subjectLabel(item.subject.type)}`

async function load() {
  loading.value = true
  error.value = ''
  try {
    const value = await api<{ items: NotificationItem[]; next_cursor: number | null; unread_count: number }>('/api/inbox')
    items.value = value.items
    nextCursor.value = value.next_cursor
    unreadCount.value = value.unread_count
    changesCursor.value = value.items.length ? value.items[value.items.length - 1].id : 0
    hasMoreChanges.value = false
    void refreshChanges()
  } catch (reason) {
    error.value = errorMessage(reason, '通知加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * Incremental refresh: `cursor` is the id of the last notification already shown; the endpoint
 * returns ids above it in ascending order. New rows are prepended newest-first and deduplicated
 * by id, because the cursor can re-send rows that are already on screen.
 */
async function refreshChanges() {
  if (changesInFlight) return
  changesInFlight = true
  try {
    const value = await api<InboxChanges>(
      `/api/inbox/changes?cursor=${changesCursor.value}&limit=${CHANGES_PAGE_SIZE}`,
    )
    const known = new Set(items.value.map((item) => item.id))
    const fresh = (value.notifications ?? [])
      .filter((item) => !known.has(item.id))
      .sort((left, right) => right.id - left.id)
    if (fresh.length) items.value = [...fresh, ...items.value]
    if (typeof value.next_cursor === 'number') changesCursor.value = value.next_cursor
    hasMoreChanges.value = value.has_more === true
    if (typeof value.unread_count === 'number') unreadCount.value = value.unread_count
  } catch {
    // Incremental refresh is best-effort: a failure keeps the currently displayed notifications.
  } finally {
    changesInFlight = false
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') void refreshChanges()
}

async function loadMore() {
  if (!nextCursor.value || loadingMore.value) return
  loadingMore.value = true
  error.value = ''
  try {
    const value = await api<{ items: NotificationItem[]; next_cursor: number | null }>(
      `/api/inbox?before=${nextCursor.value}`,
    )
    items.value.push(...value.items)
    nextCursor.value = value.next_cursor
  } catch (reason) {
    error.value = errorMessage(reason, '通知加载失败')
  } finally {
    loadingMore.value = false
  }
}

async function markRead(item: NotificationItem) {
  if (item.read_at) return
  item.read_at = new Date().toISOString()
  if (unreadCount.value > 0) unreadCount.value -= 1
  try {
    await api(`/api/inbox/${item.id}/read`, { method: 'POST' })
    await refreshUnread()
  } catch (reason) {
    item.read_at = null
    unreadCount.value += 1
    error.value = errorMessage(reason, '标记已读失败')
  }
}

async function readAll() {
  if (!unreadCount.value || readAllBusy.value) return
  readAllBusy.value = true
  error.value = ''
  try {
    await api('/api/inbox/read-all', { method: 'POST' })
    items.value.forEach((item) => { item.read_at = item.read_at ?? new Date().toISOString() })
    unreadCount.value = 0
    await refreshUnread()
  } catch (reason) {
    error.value = errorMessage(reason, '全部已读失败')
  } finally {
    readAllBusy.value = false
  }
}

onMounted(() => {
  void load()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">Inbox</p><h1>收件箱</h1><p>评论提及、指派和评审请求都会汇总到这里。</p></div>
      <n-button secondary :disabled="!unreadCount" :loading="readAllBusy" @click="readAll">全部已读</n-button>
    </header>
    <n-alert v-if="error" type="error" class="workspace-section">{{ error }}</n-alert>
    <p v-if="loading" class="empty-state">正在加载通知…</p>
    <template v-else-if="items.length">
      <n-list bordered class="inbox-list">
        <n-list-item
          v-for="item in items"
          :key="item.id"
          :data-unread="item.read_at ? 'false' : 'true'"
          :class="{ 'inbox-item-unread': !item.read_at }"
          @click="markRead(item)"
        >
          <RouterLink :to="notificationHref(item)" class="inbox-item-link">
            <span v-if="!item.read_at" class="inbox-unread-dot" aria-hidden="true" />
            <span class="attention-kind" :data-kind="item.subject.type">{{ subjectLabel(item.subject.type) }}</span>
            <div class="grow">
              <h3>{{ message(item) }}</h3>
              <p class="attention-reasons"><time>{{ formatDateTime(item.created_at) }}</time><span v-if="item.read_at" class="muted"> · 已读</span></p>
            </div>
            <span class="arrow-link" aria-hidden="true">→</span>
          </RouterLink>
        </n-list-item>
      </n-list>
      <div v-if="nextCursor" class="inbox-load-more">
        <n-button quaternary :loading="loadingMore" :disabled="loadingMore" @click="loadMore">加载更多</n-button>
      </div>
      <div v-if="hasMoreChanges" class="inbox-changes-more">
        <n-button text @click="load">点击刷新查看全部</n-button>
      </div>
    </template>
    <n-empty v-else class="workspace-section" description="暂无通知">
      <template #extra>新的提及、指派和评审请求会出现在这里。</template>
    </n-empty>
  </main>
</template>

<style scoped>
.inbox-list {
  margin-top: 8px;
}

.inbox-item-link {
  display: flex;
  align-items: center;
  gap: 14px;
}

.inbox-unread-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green, #0b6a58);
}

.inbox-list :deep(.n-list-item[data-unread='true']) {
  background: rgba(217, 239, 232, 0.45);
}

.inbox-list :deep(.n-list-item[data-unread='true'] h3) {
  font-weight: 700;
}

.inbox-load-more,
.inbox-changes-more {
  display: flex;
  justify-content: center;
  margin-top: 12px;
}
</style>
