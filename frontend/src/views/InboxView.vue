<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { errorMessage } from '../utils/errors'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { formatDateTime } from '../utils/time'
import { subjectHref, subjectLabel } from '../utils/links'

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

const items = ref<NotificationItem[]>([])
const nextCursor = ref<number | null>(null)
const unreadCount = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')

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
  } catch (reason) {
    error.value = errorMessage(reason, '通知加载失败')
  } finally {
    loading.value = false
  }
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
  } catch (reason) {
    item.read_at = null
    unreadCount.value += 1
    error.value = errorMessage(reason, '标记已读失败')
  }
}

async function readAll() {
  if (!unreadCount.value) return
  error.value = ''
  try {
    await api('/api/inbox/read-all', { method: 'POST' })
    items.value.forEach((item) => { item.read_at = item.read_at ?? new Date().toISOString() })
    unreadCount.value = 0
  } catch (reason) {
    error.value = errorMessage(reason, '全部已读失败')
  }
}

const unreadItems = computed(() => items.value.filter((item) => !item.read_at).length)

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">Inbox</p><h1>收件箱</h1><p>评论提及、指派和评审请求都会汇总到这里。</p></div>
      <button class="button button-quiet" :disabled="!unreadCount" @click="readAll">全部已读</button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在加载通知…</p>
    <div v-else-if="items.length" class="attention-list">
      <article
        v-for="item in items"
        :key="item.id"
        class="attention-card"
        :class="{ resolved: item.read_at }"
        @click="markRead(item)"
      >
        <RouterLink :to="subjectHref(item.subject.type, item.subject.id, item.meeting?.id)" class="attention-card-link">
          <span class="attention-kind" :data-kind="item.subject.type">{{ subjectLabel(item.subject.type) }}</span>
          <div class="grow">
            <h3>{{ message(item) }}</h3>
            <p class="attention-reasons"><time>{{ formatDateTime(item.created_at) }}</time><span v-if="item.read_at" class="muted"> · 已读</span></p>
          </div>
          <span class="arrow-link" aria-hidden="true">→</span>
        </RouterLink>
      </article>
      <button v-if="nextCursor" class="button button-quiet" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? '加载中…' : '加载更多' }}
      </button>
    </div>
    <div v-else class="empty-state compact"><strong>暂无通知</strong><p>新的提及、指派和评审请求会出现在这里。</p></div>
  </main>
</template>

<style scoped>
.attention-card.resolved { opacity: .62; }
.attention-card-link { display: flex; align-items: center; gap: 14px; }
</style>
