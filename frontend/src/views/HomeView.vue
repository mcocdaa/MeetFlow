<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { streamPluginAction } from '../api/plugin-stream'
import AttentionCard, { type AttentionItem } from '../components/AttentionCard.vue'
import MarkdownView from '../components/MarkdownView.vue'

type AttentionResponse = {
  items: AttentionItem[]
  unread_count: number
  truncated: boolean
}

type PluginAction = { action_id: string }
type WorkBriefResponse = { content_markdown: string; generated_at: string | null }

const response = ref<AttentionResponse | null>(null)
const loading = ref(true)
const error = ref('')
const workBriefEnabled = ref(false)
const workBrief = ref<WorkBriefResponse | null>(null)
const workBriefStreamMarkdown = ref('')
const workBriefError = ref('')
const workBriefRunning = ref(false)
const workBriefController = ref<AbortController | null>(null)

const meetings = computed(() => response.value?.items.filter((item) => item.subject_type === 'meeting').slice(0, 5) ?? [])
const priorities = computed(() => response.value?.items.filter((item) => item.subject_type !== 'meeting') ?? [])
const displayedWorkBriefMarkdown = computed(() => (
  workBriefRunning.value ? workBriefStreamMarkdown.value : workBrief.value?.content_markdown ?? ''
))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [attention, actions, brief] = await Promise.all([
      api<AttentionResponse>('/api/attention'),
      api<PluginAction[]>('/api/plugins/actions'),
      api<WorkBriefResponse>('/api/work-brief'),
    ])
    response.value = attention
    workBriefEnabled.value = actions.some((action) => action.action_id === 'ai-work-assistant.user_work_brief')
    workBrief.value = brief
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '工作区加载失败'
  } finally {
    loading.value = false
  }
}

async function generateWorkBrief() {
  if (!workBriefEnabled.value || workBriefRunning.value) return
  const controller = new AbortController()
  workBriefController.value = controller
  workBriefStreamMarkdown.value = ''
  workBriefError.value = ''
  workBriefRunning.value = true
  try {
    await streamPluginAction(
      'ai-work-assistant.user_work_brief',
      (text) => { workBriefStreamMarkdown.value += text },
      controller.signal,
    )
    if (!controller.signal.aborted) {
      workBrief.value = await api<WorkBriefResponse>('/api/work-brief')
    }
  } catch (reason) {
    if (!controller.signal.aborted) {
      workBriefError.value = reason instanceof Error ? reason.message : 'AI 工作简报生成失败，请稍后重试'
    }
  } finally {
    if (workBriefController.value === controller) workBriefController.value = null
    workBriefRunning.value = false
  }
}

function cancelWorkBrief() {
  workBriefController.value?.abort()
}

onMounted(load)
onBeforeUnmount(cancelWorkBrief)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">For you</p><h1>今天需要你关注的事</h1><p>把跨项目的待办、评审和会议准备收拢到一个队列。</p></div>
      <button class="button button-quiet" @click="load">刷新</button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在整理你的工作区…</p>
    <div v-else class="home-workspace">
      <div class="attention-layout">
        <section class="workspace-section">
          <div class="section-heading"><div><p class="eyebrow">Priority queue</p><h2>需要关注</h2></div><span class="metric"><strong>{{ priorities.length }}</strong> 项</span></div>
          <div v-if="priorities.length" class="attention-list"><AttentionCard v-for="item in priorities" :key="`${item.subject_type}:${item.subject_id}`" :item="item" /></div>
          <div v-else class="empty-state compact"><strong>目前没有需要立即处理的事项</strong><p>新的指派、评审和回复会出现在这里。</p></div>
        </section>
        <aside class="workspace-section upcoming-panel">
          <div class="section-heading"><div><p class="eyebrow">Next up</p><h2>近期会议</h2></div><RouterLink class="text-link" to="/meetings">全部</RouterLink></div>
          <RouterLink v-for="item in meetings" :key="item.subject_id" class="upcoming-meeting" :to="`/meetings/${item.subject_id}`"><strong>{{ item.title }}</strong><span>{{ item.project.name }}</span><time v-if="item.scheduled_start">{{ new Date(item.scheduled_start).toLocaleString('zh-CN') }}</time></RouterLink>
          <p v-if="!meetings.length" class="muted">未来七天没有需要你参加的会议。</p>
        </aside>
      </div>

      <section class="workspace-section ai-work-brief-panel">
        <div class="ai-work-brief-heading">
          <div>
            <p class="eyebrow">Work brief</p>
            <h2>AI 工作简报</h2>
            <p>{{ workBriefEnabled ? '汇总你全部项目中的当前工作，仅供阅读。' : '加载工作简报插件后，可汇总你的跨项目工作。' }}</p>
          </div>
          <div v-if="workBriefEnabled" class="ai-brief-actions">
            <button class="button button-small" :disabled="workBriefRunning" @click="generateWorkBrief">{{ workBriefRunning ? '正在生成…' : '生成工作简报' }}</button>
            <button v-if="workBriefRunning" class="button button-small button-quiet" @click="cancelWorkBrief">取消</button>
          </div>
          <button v-else class="button button-small" disabled>尚未启用</button>
        </div>
        <p v-if="workBriefError" class="notice notice-error ai-brief-output" role="alert">{{ workBriefError }}</p>
        <section v-else-if="workBriefRunning || displayedWorkBriefMarkdown" class="ai-brief-output" aria-live="polite">
          <p v-if="workBriefRunning && !workBriefStreamMarkdown" class="muted">正在汇总全部项目的当前工作…</p>
          <MarkdownView v-else :source="displayedWorkBriefMarkdown" />
        </section>
      </section>
    </div>
  </main>
</template>
