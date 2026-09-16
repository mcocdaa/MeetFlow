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
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/time'

const TERMINAL_STATUSES = ['succeeded', 'failed', 'interrupted', 'canceled']

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
  if (job.target_type === 'meeting' || job.target_type === 'agenda_item') return '会议'
  return '项目'
}

function statusLabel(job: PluginJob) {
  if (job.dismissed_at) return '已丢弃结果'
  if (job.applied_at) return '已应用'
  if (job.status === 'queued') return '排队中'
  if (job.status === 'requesting') return '生成中'
  if (job.status === 'succeeded') return '已生成'
  if (job.status === 'canceled') return '已取消'
  return '未完成'
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
    error.value = errorMessage(reason, 'AI 任务加载失败')
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
  return runAction(job, 'cancel', '任务取消失败')
}

function rerun(job: PluginJob) {
  return runAction(job, 'rerun', '任务重跑失败')
}

function dismiss(job: PluginJob) {
  return runAction(job, 'dismiss', '当前 AI 草稿无法丢弃')
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
    <PageHeader eyebrow="AI work" title="AI 任务" summary="这里保留运行状态、结果与失败恢复；生成内容会直接写入发起时的编辑器。" />
    <section class="workspace-section ai-task-filters">
      <span>显示范围</span>
      <n-radio-group v-model:value="includeHistory" size="small" aria-label="显示范围">
        <n-radio-button :value="false">进行中</n-radio-button>
        <n-radio-button :value="true">全部</n-radio-button>
      </n-radio-group>
    </section>
    <n-alert v-if="error" type="error" class="workspace-section">{{ error }}</n-alert>
    <p v-if="loading" class="empty-state">正在加载 AI 任务…</p>
    <section v-else-if="jobs.length" class="task-list">
      <n-card v-for="job in jobs" :key="job.id" class="workspace-section ai-task-card" size="small">
        <header class="section-heading">
          <div>
            <p class="eyebrow">{{ job.plugin_id }} · {{ job.action_id }}</p>
            <div class="ai-task-title-row">
              <h2>AI 任务</h2>
              <StatusPill class="ai-task-status" kind="job" :status="statusTone(job)" :label="statusLabel(job)" />
            </div>
          </div>
          <RouterLink class="text-link" :to="source(job)">
            回到{{ sourceLabel(job) }}
          </RouterLink>
        </header>
        <p class="ai-task-apply-hint">在发起页面应用此结果</p>
        <p v-if="job.error_code" class="ai-task-error-code">错误码：{{ job.error_code }}</p>
        <p v-if="job.error_message" class="notice notice-error">{{ job.error_message }}</p>
        <details v-if="job.error_detail" class="task-error-detail"><summary>查看技术详情</summary><pre>{{ job.error_detail }}</pre></details>
        <ul class="ai-task-meta">
          <li v-if="job.rerun_of_id">重跑自任务 #{{ job.rerun_of_id }}</li>
          <li v-if="job.applied_by">应用人：{{ nameOf(job.applied_by) }}</li>
          <li v-if="job.applied_at">应用时间：{{ formatDateTime(job.applied_at) }}</li>
          <li v-if="job.dismissed_by">丢弃人：{{ nameOf(job.dismissed_by) }}</li>
          <li v-if="job.dismissed_at">丢弃时间：{{ formatDateTime(job.dismissed_at) }}</li>
          <li v-if="job.created_at">创建时间：{{ formatDateTime(job.created_at) }}</li>
          <li v-if="job.finished_at">完成时间：{{ formatDateTime(job.finished_at) }}</li>
        </ul>
        <PluginTaskExtension :job="job" />
        <p v-if="job.applied_at" class="notice">已应用</p>
        <p v-else-if="job.dismissed_at" class="notice">已丢弃</p>
        <div class="row-actions">
          <n-button v-if="canCancel(job)" quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)" @click="cancel(job)">取消任务</n-button>
          <n-button v-if="canRerun(job)" quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)" @click="rerun(job)">重新运行</n-button>
          <n-popconfirm v-if="canDismiss(job)" positive-text="确认" negative-text="取消" @positive-click="dismiss(job)">
            <template #trigger>
              <n-button quaternary :loading="jobBusy === job.id" :disabled="Boolean(jobBusy)">丢弃</n-button>
            </template>
            确定丢弃这份 AI 结果吗？丢弃后不会再出现在进行中列表。
          </n-popconfirm>
        </div>
      </n-card>
    </section>
    <p v-else class="empty-state">尚无 AI 任务。可从会议或项目页面发起生成。</p>
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

.ai-task-error-code {
  margin: 0 0 6px;
  color: var(--red, #ae3f36);
  font-size: 13px;
}

.ai-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 20px;
  margin: 8px 0;
  padding: 0;
  list-style: none;
  color: var(--muted, #66727f);
  font-size: 13px;
}
</style>
