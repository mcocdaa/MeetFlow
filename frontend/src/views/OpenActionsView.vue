<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/client'
import type { ActionItem } from '../meetings/types'

const actions = ref<ActionItem[]>([])
const loading = ref(true)
const error = ref('')
const groups = computed(() => {
  const result = new Map<string, { meetingId: string; title: string; items: ActionItem[] }>()
  for (const item of actions.value) {
    const group = result.get(item.meeting_id) ?? { meetingId: item.meeting_id, title: item.meeting_title ?? '来源会议', items: [] }
    group.items.push(item)
    result.set(item.meeting_id, group)
  }
  return [...result.values()]
})

async function load() {
  loading.value = true
  try { actions.value = await api<ActionItem[]>('/api/actions?status=open') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '行动项加载失败' }
  finally { loading.value = false }
}

async function complete(item: ActionItem) {
  await api(`/api/meetings/${item.meeting_id}/actions/${item.id}`, {
    method: 'PUT',
    body: JSON.stringify({ content: item.content, owner: item.owner, due_date: item.due_date, status: 'done' }),
  })
  await load()
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="page-heading"><div><p class="eyebrow">Across meetings</p><h1>全部待办</h1><p>把散落在每次会议里的承诺，集中变成下一步。</p></div><span class="metric"><strong>{{ actions.length }}</strong> 未完成</span></header>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在汇总行动项…</p>
    <div v-else-if="groups.length" class="action-groups">
      <section v-for="group in groups" :key="group.meetingId" class="panel action-group">
        <div class="section-heading"><div><p class="eyebrow">Source meeting</p><h2>{{ group.title }}</h2></div><RouterLink class="text-link" :to="`/meetings/${group.meetingId}`">进入会议 ↗</RouterLink></div>
        <article v-for="item in group.items" :key="item.id" class="open-action-row">
          <span class="action-check" aria-hidden="true"></span>
          <div class="grow"><strong>{{ item.content }}</strong><p>{{ item.owner || '未指定负责人' }}<template v-if="item.due_date"> · {{ item.due_date }}</template></p></div>
          <button class="button button-small button-primary" @click="complete(item)">标记完成</button>
        </article>
      </section>
    </div>
    <div v-else class="empty-state success-empty"><strong>所有行动项都已完成</strong><p>漂亮。现在可以回到会议档案，继续推动新的讨论。</p></div>
  </main>
</template>
