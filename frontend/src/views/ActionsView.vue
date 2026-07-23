<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { Page } from '../api/contracts'
import { session } from '../auth/session'
import type { Project } from '../domain/projects'

type ActionRow = { id: string; project_id: string; meeting_id: string | null; content: string; owner_user_id: string | null; due_date: string | null; priority: string; status: string; updated_at: string }
const projects = ref<Project[]>([])
const rows = ref<ActionRow[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const filters = reactive({ owner: 'me', status: 'open', project: '', due: '', priority: '' })
const projectNames = computed(() => Object.fromEntries(projects.value.map((project) => [project.id, project.name])))
const visible = computed(() => rows.value.filter((row) => !filters.priority || row.priority === filters.priority))
let firstRun = true

function query() {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.owner === 'me' && session.user) params.set('owner_user_id', session.user.id)
  if (filters.project) params.set('project_id', filters.project)
  if (filters.due === 'overdue') params.set('due_before', new Date().toISOString().slice(0, 10))
  return `/api/actions${params.size ? `?${params}` : ''}`
}

async function load() {
  loading.value = true
  error.value = ''
  try { const page = await api<Page<ActionRow>>(query()); rows.value = page.items; total.value = page.total }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '行动项加载失败' }
  finally { loading.value = false }
}

watch(() => [filters.owner, filters.status, filters.project, filters.due], () => { if (!firstRun) void load() })
onMounted(async () => { try { projects.value = await api<Project[]>('/api/projects') } catch { projects.value = [] }; firstRun = false; await load() })
</script>

<template>
  <main class="workspace-page"><header class="workspace-page-heading"><div><p class="eyebrow">Action hub</p><h1>行动项</h1><p>会议产生的行动在这里汇总、筛选并持续跟踪。</p></div><span class="metric"><strong>{{ total }}</strong>项</span></header>
    <section class="workspace-section filter-panel"><label>负责人<select v-model="filters.owner"><option value="me">分配给我</option><option value="all">所有负责人</option></select></label><label>状态<select v-model="filters.status"><option value="open">待开始</option><option value="in_progress">进行中</option><option value="done">已完成</option><option value="canceled">已取消</option><option value="">全部状态</option></select></label><label>项目<select v-model="filters.project"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label><label>期限<select v-model="filters.due"><option value="">全部期限</option><option value="overdue">已逾期</option></select></label><label>优先级<select v-model="filters.priority"><option value="">全部优先级</option><option value="urgent">紧急</option><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select></label></section>
    <p v-if="error" class="notice notice-error">{{ error }}</p><p v-if="loading" class="empty-state">正在加载行动项…</p>
    <section v-else-if="visible.length" class="global-record-list"><article v-for="item in visible" :key="item.id" class="workspace-section action-record"><span class="action-check">{{ item.status === 'done' ? '✓' : '○' }}</span><div><div class="tag-row"><span class="tag">{{ item.priority }}</span><span class="tag tag-project">{{ projectNames[item.project_id] ?? item.project_id }}</span></div><h2>{{ item.content }}</h2><p>{{ item.owner_user_id === session.user?.id ? '负责人：我' : item.owner_user_id ? `负责人：${item.owner_user_id}` : '未指定负责人' }} · {{ item.due_date ? `截止 ${item.due_date}` : '未设截止日期' }}</p></div><RouterLink v-if="item.meeting_id" :to="`/meetings/${item.meeting_id}`">来源会议 →</RouterLink></article></section>
    <div v-else class="empty-state"><strong>当前没有行动项</strong><p>会议议题中产生的行动会自动汇总到这里。</p></div>
  </main>
</template>
