<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { session } from '../auth/session'
import type { Project, ProjectHealth, ProjectStatus } from '../domain/projects'

const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref('')
const status = ref<ProjectStatus | ''>('')
const health = ref<ProjectHealth | ''>('')
const createOpen = ref(false)
const creating = ref(false)
const form = ref({ name: '', slug: '', summary: '' })

const statusLabels: Record<ProjectStatus, string> = { planned: '计划中', active: '进行中', paused: '已暂停', completed: '已完成', canceled: '已取消' }
const healthLabels: Record<ProjectHealth, string> = { on_track: '进展正常', at_risk: '存在风险', off_track: '偏离计划', unset: '未设置' }
const filtered = computed(() => projects.value.filter((project) => (!status.value || project.status === status.value) && (!health.value || project.health === health.value)))

function updateSlug(event: Event) {
  const input = event.target as HTMLInputElement
  form.value.slug = input.value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

async function load() {
  loading.value = true
  error.value = ''
  try { projects.value = await api<Project[]>('/api/projects') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '项目加载失败' }
  finally { loading.value = false }
}

async function createProject() {
  if (!session.user) return
  creating.value = true
  error.value = ''
  try {
    await api('/api/projects', {
      method: 'POST',
      body: JSON.stringify({
        ...form.value,
        status: 'active', health: 'unset', description_markdown: '',
        lead_user_id: session.user.id, member_ids: [session.user.id], target_date: null,
      }),
    })
    form.value = { name: '', slug: '', summary: '' }
    createOpen.value = false
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '项目创建失败' }
  finally { creating.value = false }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading"><div><p class="eyebrow">Projects</p><h1>项目</h1><p>从项目脉络进入会议、决策和后续行动。</p></div><button class="button button-primary" @click="createOpen = !createOpen">{{ createOpen ? '收起' : '新建项目' }}</button></header>
    <form v-if="createOpen" class="panel project-create" @submit.prevent="createProject">
      <label>项目名称<input v-model.trim="form.name" required /></label><label>项目标识<input aria-label="项目标识" :value="form.slug" placeholder="meetflow" maxlength="80" required @input="updateSlug" /><small class="muted">仅使用小写字母、数字和连字符，例如 meetflow。</small></label><label class="grow">一句话说明<input v-model.trim="form.summary" /></label><button class="button button-primary" :disabled="creating">{{ creating ? '创建中…' : '创建' }}</button>
    </form>
    <div class="project-filters"><label>项目状态<select v-model="status"><option value="">全部状态</option><option value="active">进行中</option><option value="planned">计划中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label><label>健康度<select v-model="health"><option value="">全部健康度</option><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label><span class="muted">{{ filtered.length }} 个项目</span></div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在加载项目…</p>
    <section v-else-if="filtered.length" class="project-grid">
      <RouterLink v-for="project in filtered" :key="project.id" class="project-card" :to="`/projects/${project.id}`">
        <div class="project-card-top"><span class="health-dot" :data-health="project.health"></span><span>{{ healthLabels[project.health] }}</span><span class="status-pill">{{ statusLabels[project.status] }}</span></div>
        <h2>{{ project.name }}</h2><p>{{ project.summary || '尚未填写项目说明' }}</p>
        <dl><div><dt>负责人</dt><dd>{{ project.lead?.display_name ?? '未指定' }}</dd></div><div><dt>目标日期</dt><dd>{{ project.target_date ?? '未设置' }}</dd></div><div><dt>成员</dt><dd>{{ project.memberships.length }}</dd></div></dl>
        <span class="text-link">打开项目 →</span>
      </RouterLink>
    </section>
    <div v-else class="empty-state"><strong>没有匹配的项目</strong><p>调整筛选条件，或建立一个新项目。</p></div>
  </main>
</template>
