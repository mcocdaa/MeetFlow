<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'

type PluginJob = {
  id: string
  action_id: string
  target_type: 'meeting' | 'project'
  target_id: string
  status: 'queued' | 'requesting' | 'succeeded' | 'failed' | 'interrupted' | 'canceled'
  result: { markdown?: string; candidates?: Array<{ content: string }> } | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  applied_at: string | null
}

const jobs = ref<PluginJob[]>([])
const loading = ref(true)
const error = ref('')
const applying = ref('')
const drafts = reactive<Record<string, string>>({})
const selectedIndexes = reactive<Record<string, number[]>>({})
let poller: ReturnType<typeof setInterval> | undefined

const active = computed(() => jobs.value.some((job) => job.status === 'queued' || job.status === 'requesting'))
const labels: Record<string, string> = {
  'ai-work-assistant.meeting_summary': '会议纪要',
  'ai-work-assistant.project_progress': '项目进展',
  'ai-work-assistant.action_suggestions': '行动项建议',
}

function source(job: PluginJob) {
  return job.target_type === 'meeting' ? `/meetings/${job.target_id}` : `/projects/${job.target_id}`
}

function draftLabel(job: PluginJob) {
  if (job.action_id === 'ai-work-assistant.project_progress') return '编辑项目进展草稿'
  if (job.action_id === 'ai-work-assistant.action_suggestions') return '行动项建议草稿'
  return '编辑会议纪要草稿'
}

async function load() {
  try {
    const value = await api<{ items: PluginJob[] }>('/api/plugin-jobs')
    jobs.value = value.items
    for (const job of value.items) {
      if (drafts[job.id] === undefined) drafts[job.id] = job.result?.markdown ?? ''
      if (selectedIndexes[job.id] === undefined) selectedIndexes[job.id] = []
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'AI 任务加载失败'
  } finally {
    loading.value = false
  }
}

async function applySummary(job: PluginJob) {
  applying.value = job.id
  error.value = ''
  try {
    const meeting = await api<{ version: number }>(`/api/meetings/${job.target_id}`)
    await api(`/api/plugin-jobs/${job.id}/apply`, {
      method: 'POST',
      body: JSON.stringify({ edited_markdown: drafts[job.id], expected_version: meeting.version }),
    })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '应用 AI 草稿失败'
  } finally {
    applying.value = ''
  }
}

async function applyProjectProgress(job: PluginJob) {
  applying.value = job.id
  error.value = ''
  try {
    await api(`/api/plugin-jobs/${job.id}/apply`, {
      method: 'POST',
      body: JSON.stringify({ edited_markdown: drafts[job.id] }),
    })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '发布项目进展失败'
  } finally {
    applying.value = ''
  }
}

async function applyActionSuggestions(job: PluginJob) {
  applying.value = job.id
  error.value = ''
  try {
    await api(`/api/plugin-jobs/${job.id}/apply`, {
      method: 'POST',
      body: JSON.stringify({ selected_indexes: selectedIndexes[job.id] }),
    })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '创建行动项失败'
  } finally {
    applying.value = ''
  }
}

async function cancel(job: PluginJob) {
  await api(`/api/plugin-jobs/${job.id}/cancel`, { method: 'POST' })
  await load()
}

async function rerun(job: PluginJob) {
  await api(`/api/plugin-jobs/${job.id}/rerun`, { method: 'POST' })
  await load()
}

onMounted(() => {
  void load()
  poller = setInterval(() => { if (active.value) void load() }, 3000)
})
onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<template>
  <main class="workspace-page ai-tasks-page">
    <PageHeader eyebrow="AI work" title="AI 任务" summary="生成结果始终是草稿；确认后才会写入会议或项目。" />
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在加载 AI 任务…</p>
    <section v-else-if="jobs.length" class="task-list">
      <article v-for="job in jobs" :key="job.id" class="workspace-section ai-task-card">
        <header class="section-heading"><div><p class="eyebrow">{{ labels[job.action_id] ?? job.action_id }}</p><h2>{{ job.status === 'queued' ? '排队中' : job.status === 'requesting' ? '生成中' : job.status === 'succeeded' ? '已生成草稿' : job.status === 'canceled' ? '已取消' : '未完成' }}</h2></div><RouterLink class="text-link" :to="source(job)">查看来源</RouterLink></header>
        <p v-if="job.error_message" class="notice notice-error">{{ job.error_message }}</p>
        <label v-if="job.status === 'succeeded' && job.result?.markdown">{{ draftLabel(job) }}<textarea v-model="drafts[job.id]" rows="10" /></label>
        <fieldset v-if="job.action_id === 'ai-work-assistant.action_suggestions' && job.result?.candidates?.length" class="mini-fields"><legend>选择要创建的行动项</legend><label v-for="(candidate, index) in job.result.candidates" :key="`${job.id}-${index}`"><input v-model="selectedIndexes[job.id]" type="checkbox" :value="index" />{{ candidate.content }}</label></fieldset>
        <p v-if="job.applied_at" class="notice">已应用</p>
        <div class="row-actions">
          <button v-if="job.status === 'queued'" class="button button-quiet" @click="cancel(job)">取消任务</button>
          <button v-if="['succeeded', 'failed', 'interrupted', 'canceled'].includes(job.status)" class="button button-quiet" @click="rerun(job)">重新运行</button>
          <button v-if="job.action_id === 'ai-work-assistant.meeting_summary' && job.status === 'succeeded' && !job.applied_at" class="button button-primary" :disabled="applying === job.id" @click="applySummary(job)">{{ applying === job.id ? '应用中…' : '应用到会议纪要' }}</button>
          <button v-if="job.action_id === 'ai-work-assistant.project_progress' && job.status === 'succeeded' && !job.applied_at" class="button button-primary" :disabled="applying === job.id" @click="applyProjectProgress(job)">{{ applying === job.id ? '发布中…' : '发布项目进展' }}</button>
          <button v-if="job.action_id === 'ai-work-assistant.action_suggestions' && job.status === 'succeeded' && !job.applied_at" class="button button-primary" :disabled="applying === job.id || !selectedIndexes[job.id]?.length" @click="applyActionSuggestions(job)">{{ applying === job.id ? '创建中…' : '创建选中的行动项' }}</button>
        </div>
      </article>
    </section>
    <p v-else class="empty-state">尚无 AI 任务。可从会议或项目页面发起生成。</p>
  </main>
</template>
