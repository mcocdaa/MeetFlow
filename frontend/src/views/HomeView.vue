<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import AttentionCard, { type AttentionItem } from '../components/AttentionCard.vue'

type AttentionResponse = {
  items: AttentionItem[]
  unread_count: number
  truncated: boolean
}

const response = ref<AttentionResponse | null>(null)
const loading = ref(true)
const error = ref('')

const meetings = computed(() => response.value?.items.filter((item) => item.subject_type === 'meeting').slice(0, 5) ?? [])
const priorities = computed(() => response.value?.items.filter((item) => item.subject_type !== 'meeting') ?? [])

async function load() {
  loading.value = true
  error.value = ''
  try {
    response.value = await api<AttentionResponse>('/api/attention')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '工作区加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">For you</p><h1>今天需要你关注的事</h1><p>把跨项目的待办、评审和会议准备收拢到一个队列。</p></div>
      <button class="button button-quiet" @click="load">刷新</button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在整理你的工作区…</p>
    <div v-else class="attention-layout">
      <section class="workspace-section">
        <div class="section-heading"><div><p class="eyebrow">Priority queue</p><h2>需要关注</h2></div><span class="metric"><strong>{{ priorities.length }}</strong> 项</span></div>
        <div v-if="priorities.length" class="attention-list"><AttentionCard v-for="item in priorities" :key="`${item.subject_type}:${item.subject_id}`" :item="item" /></div>
        <div v-else class="empty-state compact"><strong>目前没有需要立即处理的事项</strong><p>新的指派、评审和回复会出现在这里。</p></div>
      </section>
      <aside class="workspace-section upcoming-panel">
        <div class="section-heading"><div><p class="eyebrow">Next up</p><h2>近期会议</h2></div><RouterLink class="text-link" to="/meetings">全部</RouterLink></div>
        <RouterLink v-for="item in meetings" :key="item.subject_id" class="upcoming-meeting" :to="`/meetings/${item.subject_id}`"><strong>{{ item.title }}</strong><span>{{ item.project.name }}</span><time v-if="item.scheduled_start">{{ new Date(item.scheduled_start).toLocaleString('zh-CN') }}</time></RouterLink>
        <p v-if="!meetings.length" class="muted">未来七天没有需要你参加的会议。</p>
        <div class="ai-brief-card"><span>✦</span><div><strong>AI 工作简报</strong><p>启用摘要插件后，可从当前项目与会议生成简报。</p></div><button class="button button-small" disabled>尚未启用</button></div>
      </aside>
    </div>
  </main>
</template>
