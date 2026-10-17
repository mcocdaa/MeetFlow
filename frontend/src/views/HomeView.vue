<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { errorMessage } from '../utils/errors'
import { RouterLink } from 'vue-router'

import { NBadge, NCard, NEmpty, NSkeleton } from 'naive-ui'

import { api } from '../api/client'
import { useI18n } from '../i18n'
import { formatDateTime } from '../utils/time'
import { streamPluginAction } from '../api/plugin-stream'
import AttentionCard, { type AttentionItem } from '../components/AttentionCard.vue'
import MarkdownView from '../components/MarkdownView.vue'
import PluginSlot from '../components/PluginSlot.vue'

type AttentionResponse = {
  items: AttentionItem[]
  unread_count: number
  truncated: boolean
}

type PluginAction = { action_id: string }
type WorkBriefResponse = { content_markdown: string; generated_at: string | null }

const { tr } = useI18n()
const response = ref<AttentionResponse | null>(null)
const loading = ref(true)
const error = ref('')
const workBriefEnabled = ref(false)
const workBrief = ref<WorkBriefResponse | null>(null)
const workBriefStreamMarkdown = ref('')
const workBriefError = ref('')
const workBriefRunning = ref(false)
const workBriefController = ref<AbortController | null>(null)
let workBriefRevision = 0

const meetings = computed(() => response.value?.items.filter((item) => item.subject_type === 'meeting').slice(0, 5) ?? [])
const priorities = computed(() => response.value?.items.filter((item) => item.subject_type !== 'meeting') ?? [])
const displayedWorkBriefMarkdown = computed(() => (
  workBriefRunning.value ? workBriefStreamMarkdown.value : workBrief.value?.content_markdown ?? ''
))

async function loadAttention() {
  response.value = await api<AttentionResponse>('/api/attention')
}

function isCurrentWorkBriefRevision(revision: number) {
  return revision === workBriefRevision
}

async function loadWorkBriefCapability(revision: number) {
  try {
    const actions = await api<PluginAction[]>('/api/plugins/actions')
    if (!isCurrentWorkBriefRevision(revision)) return
    workBriefEnabled.value = actions.some((action) => action.action_id === 'ai-work-assistant.user_work_brief')
  } catch (reason) {
    if (!isCurrentWorkBriefRevision(revision)) return
    workBriefEnabled.value = false
    workBriefError.value = errorMessage(reason, tr('AI 插件状态读取失败', 'Failed to load AI plugin status'))
  }
}

async function loadWorkBrief(revision: number) {
  try {
    const brief = await api<WorkBriefResponse>('/api/work-brief')
    if (!isCurrentWorkBriefRevision(revision)) return
    workBrief.value = brief
  } catch (reason) {
    if (!isCurrentWorkBriefRevision(revision)) return
    if (!workBriefError.value) {
      workBriefError.value = errorMessage(reason, tr('AI 工作简报读取失败', 'Failed to load AI work brief'))
    }
  }
}

async function loadOptionalResources(revision: number) {
  if (!isCurrentWorkBriefRevision(revision)) return
  workBriefError.value = ''
  await Promise.all([loadWorkBriefCapability(revision), loadWorkBrief(revision)])
}

async function load() {
  const revision = ++workBriefRevision
  cancelWorkBrief()
  loading.value = true
  error.value = ''
  try {
    await loadAttention()
  } catch (reason) {
    error.value = errorMessage(reason, tr('工作区加载失败', 'Failed to load workspace'))
  } finally {
    loading.value = false
  }
  if (!error.value) void loadOptionalResources(revision)
}

async function generateWorkBrief() {
  if (!workBriefEnabled.value || workBriefRunning.value) return
  const revision = ++workBriefRevision
  const controller = new AbortController()
  workBriefController.value = controller
  workBriefStreamMarkdown.value = ''
  workBriefError.value = ''
  workBriefRunning.value = true
  try {
    await streamPluginAction(
      'ai-work-assistant.user_work_brief',
      (text) => {
        if (isCurrentWorkBriefRevision(revision) && workBriefController.value === controller) {
          workBriefStreamMarkdown.value += text
        }
      },
      controller.signal,
    )
    if (!controller.signal.aborted) {
      const brief = await api<WorkBriefResponse>('/api/work-brief')
      if (isCurrentWorkBriefRevision(revision) && workBriefController.value === controller) {
        workBrief.value = brief
      }
    }
  } catch (reason) {
    if (!controller.signal.aborted && isCurrentWorkBriefRevision(revision) && workBriefController.value === controller) {
      workBriefError.value = errorMessage(reason, tr('AI 工作简报生成失败，请稍后重试', 'Failed to generate AI work brief'))
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
      <div><p class="eyebrow">{{ tr('为你推荐', 'For you') }}</p><h1>{{ tr('今天需要你关注的事', 'What Needs Your Attention Today') }}</h1><p>{{ tr('把跨项目的待办、评审和会议准备收拢到一个队列。', 'Bring cross-project action items, reviews, and meeting prep into one queue.') }}</p></div>
      <div class="home-heading-actions">
        <span v-if="response" class="unread-summary">
          <n-badge :value="response.unread_count" :show="response.unread_count > 0" />
          <span>{{ tr(`${response.unread_count} 条未读提醒`, `${response.unread_count} unread alerts`) }}</span>
        </span>
        <button class="button button-quiet" @click="load">{{ tr('刷新', 'Refresh') }}</button>
      </div>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="home-loading">
      <p class="empty-state">{{ tr('正在整理你的工作区…', 'Organizing your workspace…') }}</p>
      <n-skeleton text :repeat="3" />
    </div>
    <div v-else class="home-workspace">
      <div class="attention-layout">
        <n-card
          tag="section"
          class="workspace-section home-attention-card"
          aria-labelledby="priority-queue-title"
          content-class="home-card-body"
          content-style="padding: 0"
        >
          <div class="section-heading"><div><p class="eyebrow">{{ tr('优先队列', 'Priority queue') }}</p><h2 id="priority-queue-title">{{ tr('需要关注', 'Attention Queue') }}</h2></div><span class="metric"><strong>{{ priorities.length }}</strong> {{ tr('项', 'items') }}</span></div>
          <div v-if="priorities.length" class="attention-list"><AttentionCard v-for="item in priorities" :key="`${item.subject_type}:${item.subject_id}`" :item="item" /></div>
          <n-empty v-else class="empty-state compact" :description="tr('目前没有需要立即处理的事项', 'No items require immediate attention')">
            <p>{{ tr('新的指派、评审和回复会出现在这里。', 'New assignments, reviews, and replies will appear here.') }}</p>
          </n-empty>
        </n-card>
        <n-card
          tag="aside"
          class="workspace-section upcoming-panel"
          aria-labelledby="upcoming-meetings-title"
          content-class="home-card-body"
          content-style="padding: 0"
        >
          <div class="section-heading"><div><p class="eyebrow">{{ tr('即将开始', 'Next up') }}</p><h2 id="upcoming-meetings-title">{{ tr('近期会议', 'Upcoming Meetings') }}</h2></div><RouterLink class="text-link" to="/meetings">{{ tr('全部', 'All') }}</RouterLink></div>
          <RouterLink v-for="item in meetings" :key="item.subject_id" class="upcoming-meeting" :to="`/meetings/${item.subject_id}`"><strong>{{ item.title }}</strong><span>{{ item.project.name }}</span><time v-if="item.scheduled_start">{{ formatDateTime(item.scheduled_start) }}</time></RouterLink>
          <n-empty v-if="!meetings.length" class="empty-state compact" :description="tr('未来七天没有需要你参加的会议。', 'No meetings scheduled for you in the next 7 days.')" />
        </n-card>
      </div>

      <n-card tag="section" class="workspace-section ai-work-brief-panel" content-class="home-card-body" content-style="padding: 0">
        <div class="ai-work-brief-heading">
          <div>
            <p class="eyebrow">{{ tr('工作简报', 'Work brief') }}</p>
            <h2>{{ tr('AI 工作简报', 'AI Work Brief') }}</h2>
            <p>{{ workBriefEnabled ? tr('汇总你全部项目中的当前工作，仅供阅读。', 'Summarizes your current work across all projects for quick reading.') : tr('加载工作简报插件后，可汇总你的跨项目工作。', 'Enable the work brief plugin to summarize cross-project work.') }}</p>
            <span v-if="workBrief?.generated_at" class="brief-generated-at">{{ tr('上次生成于', 'Last generated') }} {{ formatDateTime(workBrief.generated_at) }}</span>
          </div>
          <div v-if="workBriefEnabled" class="ai-brief-actions">
            <button class="button button-small" :disabled="workBriefRunning" @click="generateWorkBrief">{{ workBriefRunning ? tr('正在生成…', 'Generating…') : tr('生成工作简报', 'Generate Brief') }}</button>
            <button v-if="workBriefRunning" class="button button-small button-quiet" @click="cancelWorkBrief">{{ tr('取消', 'Cancel') }}</button>
          </div>
          <button v-else class="button button-small" disabled>{{ tr('尚未启用', 'Not Enabled') }}</button>
        </div>
        <p v-if="workBriefError" class="notice notice-error ai-brief-output" role="alert">{{ workBriefError }}</p>
        <section v-else-if="workBriefRunning || displayedWorkBriefMarkdown" class="ai-brief-output" aria-live="polite">
          <p v-if="workBriefRunning && !workBriefStreamMarkdown" class="muted">{{ tr('正在汇总全部项目的当前工作…', 'Summarizing current work across all projects…') }}</p>
          <MarkdownView v-else :source="displayedWorkBriefMarkdown" />
        </section>
      </n-card>
      <PluginSlot slot="home.secondary-card" target-type="home" target-id="home" />
    </div>
  </main>
</template>
