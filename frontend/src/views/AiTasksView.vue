<script setup lang="ts">
import { NAlert, NButton, NCard, NPopconfirm, NRadioButton, NRadioGroup } from 'naive-ui'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import PluginTaskExtension from '../components/PluginTaskExtension.vue'
import StatusPill from '../components/StatusPill.vue'
import { loadUserNames, nameOf } from '../composables/useUserNameMap'
import type { PluginJob } from '../domain/plugin-jobs'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/time'

const TERMINAL_STATUSES = ['succeeded', 'failed', 'interrupted', 'canceled']

const { tr } = useI18n()
const jobs = ref<PluginJob[]>([])
const loading = ref(true)
const error = ref('')
const includeHistory = ref(false)
const jobBusy = ref('')
let poller: ReturnType<typeof setInterval> | undefined

const active = computed(() => jobs.value.some((job) => job.status === 'queued' || job.status === 'requesting'))

function source(job: PluginJob) {
  if (job.target_type === 'meeting') return `/meetings/${job.target_id}`
  if (job.target_type === 'agenda_item') return job.meeting_id ? `/meetings/${job.meeting_id}` : '/ai-tasks'
  return `/projects/${job.target_id}`
}

function sourceLabel(job: PluginJob) {
  if (job.target_type === 'meeting' || job.target_type === 'agenda_item') return tr('会议', 'Meeting')
  return tr('项目', 'Project')
}

function statusLabel(job: PluginJob) {
  if (job.dismissed_at) return tr('已丢弃结果', 'Dismissed')
  if (job.applied_at) return tr('已应用', 'Applied')
  if (job.status === 'queued') return tr('排队中', 'Queued')
  if (job.status === 'requesting') return tr('生成中', 'Generating')
  if (job.status === 'succeeded') return tr('已生成', 'Generated')
  if (job.status === 'canceled') return tr('已取消', 'Canceled')
  return tr('未完成', 'Incomplete')
}

function canApplyHint(job: PluginJob) {
  return job.status === 'succeeded' && !job.applied_at && !job.dismissed_at
}

function statusTone(job: PluginJob) {
  if (job.dismissed_at) return 'dismissed'
  if (job.applied_at) return 'applied'
  if (job.status === 'queued' || job.status === 'requesting') return job.status
  if (job.status === 'succeeded') return 'succeeded'
  if (job.status === 'canceled') return 'canceled'
  return 'failed'
}

/** An applied or dismissed job is history: it must not offer actions the backend would reject. */
function isResolved(job: PluginJob) {
  return Boolean(job.applied_at || job.dismissed_at)
}

function canCancel(job: PluginJob) {
  return job.status === 'queued' && !isResolved(job)
}

function canRerun(job: PluginJob) {
  return TERMINAL_STATUSES.includes(job.status)
}

function canDismiss(job: PluginJob) {
  return TERMINAL_STATUSES.includes(job.status) && !isResolved(job)
}

async function load() {
  try {
    const value = await api<{ items: PluginJob[] }>(`/api/plugin-jobs?include_history=${includeHistory.value}`)
    jobs.value = value.items
    error.value = ''
  } catch (reason) {
    error.value = errorMessage(reason, tr('AI 任务加载失败', 'Failed to load AI tasks'))
  } finally {
    loading.value = false
  }
}

async function runAction(job: PluginJob, action: 'cancel' | 'rerun' | 'dismiss', fallback: string) {
  if (jobBusy.value) return
  jobBusy.value = job.id
  error.value = ''
  try {
    await api(`/api/plugin-jobs/${job.id}/${action}`, { method: 'POST' })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, fallback)
  } finally {
    jobBusy.value = ''
  }
}

function cancel(job: PluginJob) {
  return runAction(job, 'cancel', tr('任务取消失败', 'Failed to cancel task'))
}

function rerun(job: PluginJob) {
  return runAction(job, 'rerun', tr('任务重跑失败', 'Failed to rerun task'))
}

function dismiss(job: PluginJob) {
  return runAction(job, 'dismiss', tr('当前 AI 草稿无法丢弃', 'Failed to dismiss AI draft'))
}

watch(includeHistory, () => { void load() })

onMounted(() => {
  void load()
  void loadUserNames()
  poller = setInterval(() => { if (active.value) void load() }, 3000)
})
onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<template>
  <main class="workspace-page ai-tasks-page">
    <PageHeader eyebrow="AI work" :title="tr('AI 任务', 'AI Tasks')" :summary="tr('这里保留运行状态、结果与失败恢复；生成内容会直接写入发起时的编辑器。', 'Track AI execution status, results, and recovery; generated content is applied directly to the originating editor.')" />
    <section class="workspace-section ai-task-filters">
      <span>{{ tr('显示范围', 'Scope') }}</span>
      <n-radio-group v-model:value="includeHistory" size="small" :aria-label="tr('显示范围', 'Scope')">
        <n-radio-button :value="false">{{ tr('进行中', 'Active') }}</n-radio-button>
        <n-radio-button :value="true">{{ tr('全部', 'All') }}</n-radio-button>
      </n-radio-group>
    </section>
    <n-alert v-if="error" type="error" class="workspace-section">{{ error }}</n-alert>
    <p v-if="loading" class="empty-state">{{ tr('正在加载 AI 任务…', 'Loading AI tasks…') }}</p>
    <section v-else-if="jobs.length" class="task-list">
      <n-card v-for="job in jobs" :key="job.id" class="workspace-section ai-task-card" size="small">
        <header class="section-heading">
          <div>
            <p class="eyebrow">{{ job.plugin_id }} · {{ job.action_id }}</p>
            <div class="ai-task-title-row">
              <h2>{{ tr('AI 任务', 'AI Task') }}</h2>
              <StatusPill class="ai-task-status" kind="job" :status="statusTone(job)" :label="statusLabel(job)" />
            </div>
          </div>
          <RouterLink class="text-link" :to="source(job)">
            {{ tr(`回到${sourceLabel(job)}`, `Back to ${sourceLabel(job)}`) }}
          </RouterLink>
        </header>
        <p v-if="canApplyHint(job)" class="ai-task-apply-hint">{{ tr('在发起页面应用此结果', 'Apply this result on the originating page') }}</p>
        <div v-if="job.error_message" class="ai-task-error">
          <p>{{ job.error_message }}</p>
        </div>
        <ul class="ai-task-meta">
          <li v-if="job.rerun_of_id">{{ tr(`重跑自任务 #${job.rerun_of_id}`, `Rerun of task #${job.rerun_of_id}`) }}</li>
          <li v-if="job.applied_by">{{ tr('应用人：', 'Applied by: ') }}{{ nameOf(job.applied_by) }}</li>
          <li v-if="job.applied_at">{{ tr('应用时间：', 'Applied at: ') }}{{ formatDateTime(job.applied_at) }}</li>
          <li v-if="job.dismissed_by">{{ tr('丢弃人：', 'Dismissed by: ') }}{{ nameOf(job.dismissed_by) }}</li>
          <li v-if="job.dismissed_at">{{ tr('丢弃时间：', 'Dismissed at: ') }}{{ formatDateTime(job.dismissed_at) }}</li>
          <li v-if="job.created_at">{{ tr('创建时间：', 'Created at: ') }}{{ formatDateTime(job.created_at) }}</li>
          <li v-if="job.finished_at">{{ tr('完成时间：', 'Finished at: ') }}{{ formatDateTime(job.finished_at) }}</li>
        </ul>
        <PluginTaskExtension :job="job" />
        <div class="row-actions">
          <n-button v-if="canCancel(job)" quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)" @click="cancel(job)">{{ tr('取消任务', 'Cancel Task') }}</n-button>
          <n-button v-if="canRerun(job)" quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)" @click="rerun(job)">{{ tr('重新运行', 'Rerun') }}</n-button>
          <n-popconfirm v-if="canDismiss(job)" :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="dismiss(job)">
            <template #trigger>
              <n-button quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)">{{ tr('丢弃', 'Dismiss') }}</n-button>
            </template>
            {{ tr('确定丢弃这份 AI 结果吗？丢弃后不会再出现在进行中列表。', 'Are you sure you want to dismiss this AI result? It will be removed from the active list.') }}
          </n-popconfirm>
        </div>
      </n-card>
    </section>
    <p v-else class="empty-state">{{ tr('尚无 AI 任务。可从会议或项目页面发起生成。', 'No AI tasks yet. Start generation from a meeting or project page.') }}</p>
  </main>
</template>

<style scoped>
.ai-task-filters {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-task-apply-hint {
  margin: 0 0 8px;
  color: var(--muted, #66727f);
  font-size: 13px;
}

.ai-task-error {
  display: grid;
  gap: 4px;
  margin: 0 0 8px;
  padding: 10px 12px;
  border: 1px solid #f0d3ce;
  border-radius: 8px;
  color: #8d312a;
  background: #fdf6f5;
  font-size: 13px;
}

.ai-task-error p {
  margin: 0;
}

.ai-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 20px;
  margin: 10px 0 4px;
  padding: 0;
  list-style: none;
  color: var(--muted, #66727f);
  font-size: 13px;
}
</style>
