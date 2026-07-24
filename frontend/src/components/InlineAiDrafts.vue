<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import { api } from '../api/client'

type UserRef = { id: string; display_name: string; username: string }
type Mode = 'summary' | 'progress' | 'actions'
type PluginJob = {
  id: string
  action_id: string
  status: 'queued' | 'requesting' | 'succeeded' | 'failed' | 'interrupted' | 'canceled'
  result: { markdown?: string; candidates?: Array<{ content: string }> } | null
  error_message?: string | null
  applied_at: string | null
}
type DraftAction = {
  index: number
  selected: boolean
  content: string
  owner_user_id: string | null
  due_date: string
  priority: 'low' | 'normal' | 'high' | 'urgent'
}

const props = withDefaults(defineProps<{
  targetType: 'meeting' | 'project'
  targetId: string
  mode: Mode
  participants?: UserRef[]
}>(), { participants: () => [] })
const emit = defineEmits<{ applied: []; submitted: [] }>()

const actionIds: Record<Mode, string[]> = {
  summary: ['ai-work-assistant.meeting_summary'],
  progress: ['ai-work-assistant.project_progress'],
  actions: ['ai-work-assistant.action_suggestions'],
}
const jobs = ref<PluginJob[]>([])
const loading = ref(true)
const error = ref('')
const applying = ref('')
const drafts = reactive<Record<string, string>>({})
const actionDrafts = reactive<Record<string, DraftAction[]>>({})
const discardedIds = ref(new Set<string>())
let timer: ReturnType<typeof setInterval> | undefined

const visibleJobs = computed(() => jobs.value.filter((job) => !discardedIds.value.has(job.id)))

function actionCount(job: PluginJob) {
  return actionDrafts[job.id]?.filter((item) => item.selected).length ?? 0
}

function discard(jobId: string) {
  discardedIds.value = new Set([...discardedIds.value, jobId])
}

function initDraft(job: PluginJob) {
  if (drafts[job.id] === undefined) drafts[job.id] = job.result?.markdown ?? ''
  if (actionDrafts[job.id] === undefined) {
    actionDrafts[job.id] = (job.result?.candidates ?? []).map((candidate, index) => ({
      index,
      selected: false,
      content: candidate.content,
      owner_user_id: null,
      due_date: '',
      priority: 'normal',
    }))
  }
}

async function reload() {
  error.value = ''
  try {
    const query = new URLSearchParams({ target_type: props.targetType, target_id: props.targetId })
    const response = await api<{ items: PluginJob[] }>(`/api/plugin-jobs?${query}`)
    jobs.value = response.items.filter((job) => actionIds[props.mode].includes(job.action_id))
    jobs.value.forEach(initDraft)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'AI 草稿加载失败'
  } finally {
    loading.value = false
  }
}

async function apply(job: PluginJob) {
  applying.value = job.id
  error.value = ''
  try {
    if (props.mode === 'summary') {
      const meeting = await api<{ version: number }>(`/api/meetings/${props.targetId}`)
      await api(`/api/plugin-jobs/${job.id}/apply`, {
        method: 'POST', body: JSON.stringify({ edited_markdown: drafts[job.id], expected_version: meeting.version }),
      })
    } else if (props.mode === 'progress') {
      await api(`/api/plugin-jobs/${job.id}/apply`, {
        method: 'POST', body: JSON.stringify({ edited_markdown: drafts[job.id] }),
      })
    } else {
      const candidates = actionDrafts[job.id]
        .filter((candidate) => candidate.selected)
        .map(({ index, content, owner_user_id, due_date, priority }) => ({
          index, content, owner_user_id, due_date: due_date || null, priority,
        }))
      await api(`/api/plugin-jobs/${job.id}/apply`, {
        method: 'POST', body: JSON.stringify({ candidates }),
      })
    }
    discard(job.id)
    emit('applied')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '应用 AI 草稿失败'
  } finally {
    applying.value = ''
  }
}

onMounted(() => {
  void reload()
  timer = setInterval(() => {
    if (jobs.value.some((job) => job.status === 'queued' || job.status === 'requesting')) void reload()
  }, 3000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
defineExpose({ reload })
</script>

<template>
  <section v-if="loading || visibleJobs.length || error" class="inline-ai-drafts">
    <article v-if="loading" class="inline-ai-draft" data-status="loading">AI 草稿加载中…</article>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <article v-for="job in visibleJobs" :key="job.id" class="inline-ai-draft" :data-status="job.status">
      <div class="section-heading"><div><p class="eyebrow">AI 建议 · 尚未创建</p><h3>{{ job.status === 'queued' ? 'AI 任务排队中…' : job.status === 'requesting' ? '正在生成草稿…' : job.status === 'succeeded' ? '待确认草稿' : 'AI 任务未完成' }}</h3></div><button class="button button-quiet" @click="discard(job.id)">丢弃草稿</button></div>
      <p v-if="job.error_message" class="notice notice-error">{{ job.error_message }}</p>
      <template v-if="job.status === 'succeeded'">
        <label v-if="mode === 'summary'">AI 会议纪要草稿<textarea v-model="drafts[job.id]" rows="8" /></label>
        <label v-else-if="mode === 'progress'">AI 项目进展草稿<textarea v-model="drafts[job.id]" rows="8" /></label>
        <template v-else>
          <fieldset class="inline-action-drafts"><legend>待创建行动项</legend><div v-for="item in actionDrafts[job.id]" :key="item.index" class="inline-action-row"><label><input v-model="item.selected" type="checkbox" :aria-label="item.content" /></label><input v-model.trim="item.content" :aria-label="`行动项：${item.content}`" /><select v-model="item.owner_user_id"><option :value="null">未指定负责人</option><option v-for="person in participants" :key="person.id" :value="person.id">{{ person.display_name || person.username }}</option></select><input v-model="item.due_date" type="date" /><select v-model="item.priority"><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></div></fieldset>
          <details><summary>查看 AI 依据</summary><pre>{{ drafts[job.id] }}</pre></details>
        </template>
        <div class="row-actions"><button v-if="mode === 'summary'" class="button button-primary" :disabled="applying === job.id" @click="apply(job)">应用到会议纪要</button><button v-else-if="mode === 'progress'" class="button button-primary" :disabled="applying === job.id" @click="apply(job)">发布项目进展</button><button v-else class="button button-primary" :disabled="applying === job.id || !actionCount(job)" @click="apply(job)">创建已选 {{ actionCount(job) }} 项</button></div>
      </template>
    </article>
  </section>
</template>
