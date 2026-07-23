<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { Page } from '../api/contracts'
import type { Project } from '../domain/projects'

type DecisionRow = { id: string; project_id: string; meeting_id: string | null; title: string; decision_markdown: string; status: string; updated_at: string; reviewers?: Array<{ user_id: string; status: string }> }
const projects = ref<Project[]>([])
const rows = ref<DecisionRow[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const filters = reactive({ project: '', status: '', reviewer: '', from: '', to: '' })
const projectNames = computed(() => Object.fromEntries(projects.value.map((project) => [project.id, project.name])))
const visible = computed(() => rows.value.filter((row) => {
  const date = row.updated_at.slice(0, 10)
  return (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to)
}))
let firstRun = true

function query() {
  const params = new URLSearchParams()
  if (filters.project) params.set('project_id', filters.project)
  if (filters.status) params.set('status', filters.status)
  if (filters.reviewer) params.set('reviewer_user_id', filters.reviewer)
  return `/api/decisions${params.size ? `?${params}` : ''}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await api<Page<DecisionRow>>(query())
    rows.value = page.items
    total.value = page.total
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '决策加载失败' }
  finally { loading.value = false }
}

watch(() => [filters.project, filters.status, filters.reviewer], () => { if (!firstRun) void load() })
onMounted(async () => {
  try { projects.value = await api<Project[]>('/api/projects') } catch { projects.value = [] }
  firstRun = false
  await load()
})
</script>

<template>
  <main class="workspace-page"><header class="workspace-page-heading"><div><p class="eyebrow">Decision log</p><h1>决策日志</h1><p>跨项目查看提案、最终决策及其评审状态。</p></div><span class="metric"><strong>{{ total }}</strong>项</span></header>
    <section class="workspace-section filter-panel"><label>项目<select v-model="filters.project"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label><label>状态<select v-model="filters.status"><option value="">全部状态</option><option value="proposed">待确认</option><option value="final">已生效</option><option value="superseded">已替代</option><option value="withdrawn">已撤回</option></select></label><label>评审人 ID<input v-model.trim="filters.reviewer" placeholder="可选" /></label><label>更新日期从<input v-model="filters.from" type="date" /></label><label>到<input v-model="filters.to" type="date" /></label></section>
    <p v-if="error" class="notice notice-error">{{ error }}</p><p v-if="loading" class="empty-state">正在加载决策…</p>
    <section v-else-if="visible.length" class="global-record-list"><article v-for="item in visible" :key="item.id" class="workspace-section global-record"><div><span class="status-pill" :data-status="item.status">{{ item.status }}</span><span class="muted">{{ projectNames[item.project_id] ?? item.project_id }}</span></div><h2>{{ item.title }}</h2><p>{{ item.decision_markdown }}</p><footer><span>{{ new Date(item.updated_at).toLocaleString('zh-CN') }}</span><RouterLink v-if="item.meeting_id" :to="`/meetings/${item.meeting_id}`">查看来源会议 →</RouterLink></footer></article></section>
    <div v-else class="empty-state"><strong>没有匹配的决策</strong><p>调整筛选条件，或在会议议题中创建决策。</p></div>
  </main>
</template>
