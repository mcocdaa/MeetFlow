<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import PluginTaskExtension from '../components/PluginTaskExtension.vue'
import type { PluginJob } from '../domain/plugin-jobs'

const jobs = ref<PluginJob[]>([])
const loading = ref(true)
const error = ref('')
let poller: ReturnType<typeof setInterval> | undefined

const active = computed(() => jobs.value.some((job) => job.status === 'queued' || job.status === 'requesting'))
function source(job: PluginJob) {
  return job.target_type === 'meeting' ? `/meetings/${job.target_id}` : `/projects/${job.target_id}`
}

function statusLabel(job: PluginJob) {
  if (job.dismissed_at) return '已丢弃草稿'
  if (job.applied_at) return '已应用'
  if (job.status === 'queued') return '排队中'
  if (job.status === 'requesting') return '生成中'
  if (job.status === 'succeeded') return '已生成草稿'
  if (job.status === 'canceled') return '已取消'
  return '未完成'
}

async function load() {
  try {
    const value = await api<{ items: PluginJob[] }>('/api/plugin-jobs?include_history=true')
    jobs.value = value.items
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'AI 任务加载失败'
  } finally {
    loading.value = false
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
    <PageHeader eyebrow="AI work" title="AI 任务" summary="这里保留运行状态与失败恢复；草稿请在对应会议或项目中编辑并确认。" />
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在加载 AI 任务…</p>
    <section v-else-if="jobs.length" class="task-list">
      <article v-for="job in jobs" :key="job.id" class="workspace-section ai-task-card">
        <header class="section-heading">
          <div>
            <p class="eyebrow">{{ job.plugin_id }} · {{ job.action_id }}</p>
            <h2>{{ statusLabel(job) }}</h2>
          </div>
          <RouterLink class="text-link" :to="source(job)">
            回到{{ job.target_type === 'meeting' ? '会议' : '项目' }}处理草稿
          </RouterLink>
        </header>
        <p v-if="job.error_message" class="notice notice-error">{{ job.error_message }}</p>
        <details v-if="job.error_detail" class="task-error-detail"><summary>查看技术详情</summary><pre>{{ job.error_detail }}</pre></details>
        <PluginTaskExtension :job="job" />
        <p v-if="job.applied_at" class="notice">已应用</p>
        <p v-else-if="job.dismissed_at" class="notice">已丢弃</p>
        <div class="row-actions">
          <button v-if="job.status === 'queued'" class="button button-quiet" @click="cancel(job)">取消任务</button>
          <button v-if="['succeeded', 'failed', 'interrupted', 'canceled'].includes(job.status)" class="button button-quiet" @click="rerun(job)">重新运行</button>
        </div>
      </article>
    </section>
    <p v-else class="empty-state">尚无 AI 任务。可从会议或项目页面发起生成。</p>
  </main>
</template>
