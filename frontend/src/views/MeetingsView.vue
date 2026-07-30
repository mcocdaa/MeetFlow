<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { X } from '@lucide/vue'
import { RouterLink, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { MeetingStatus } from '../domain/meetings'
import type { Project } from '../domain/projects'

type MeetingRow = { id: string; project: { id: string; name: string }; series: { id: string; title: string } | null; occurrence_kind: 'scheduled' | 'manual'; title: string; purpose_markdown: string; scheduled_start: string; scheduled_end: string; status: MeetingStatus; host: UserRef | null; agenda_count: number; snapshot_count: number; amendment_count: number }
const router = useRouter()
const projects = ref<Project[]>([])
const meetings = ref<MeetingRow[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const projectFilter = ref('')
const activeSeriesFilter = ref(new URLSearchParams(window.location.search).get('series_id') ?? '')
const statusFilter = ref<MeetingStatus | ''>('')
const advancedOpen = ref(Boolean(activeSeriesFilter.value))
const createOpen = ref(false)
const creating = ref(false)
const form = ref({ project_id: '', title: '', purpose_markdown: '', scheduled_start: '', scheduled_end: '' })
const seriesOptions = computed(() => {
  const seen = new Map<string, { id: string; title: string }>()
  meetings.value.forEach((item) => { if (item.series) seen.set(item.series.id, item.series) })
  return [...seen.values()].sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
})
const hasActiveSeriesOption = computed(() => seriesOptions.value.some((item) => item.id === activeSeriesFilter.value))
const advancedFilterCount = computed(() => [projectFilter.value, activeSeriesFilter.value, statusFilter.value].filter(Boolean).length)
const visible = computed(() => meetings.value.filter((item) => (
  (!projectFilter.value || item.project.id === projectFilter.value)
  && (!activeSeriesFilter.value || item.series?.id === activeSeriesFilter.value)
  && (!statusFilter.value || item.status === statusFilter.value)
  && (!search.value || `${item.title} ${item.project.name} ${item.series?.title ?? ''}`.toLowerCase().includes(search.value.toLowerCase()))
)))
function syncSeriesFilterToUrl() {
  const url = new URL(window.location.href)
  if (activeSeriesFilter.value) url.searchParams.set('series_id', activeSeriesFilter.value)
  else url.searchParams.delete('series_id')
  window.history.replaceState(null, '', url)
}
function clearAdvancedFilters() {
  projectFilter.value = ''
  activeSeriesFilter.value = ''
  statusFilter.value = ''
  syncSeriesFilterToUrl()
}
const groups = computed(() => [
  { id: 'active', title: '进行中的会议', items: visible.value.filter((item) => item.status === 'in_progress') },
  { id: 'upcoming', title: '即将开始', items: visible.value.filter((item) => item.status === 'draft' || item.status === 'ready').sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start)) },
  { id: 'completed', title: '最近完成', items: visible.value.filter((item) => item.status === 'completed').sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [projectRows, page] = await Promise.all([api<Project[]>('/api/projects'), api<Page<MeetingRow>>('/api/meetings')])
    projects.value = projectRows
    meetings.value = page.items
    if (!form.value.project_id && projectRows.length) form.value.project_id = projectRows[0].id
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议加载失败' }
  finally { loading.value = false }
}

async function createMeeting() {
  if (!form.value.project_id || !session.user) return
  creating.value = true
  error.value = ''
  try {
    const created = await api<{ id: string }>(`/api/projects/${form.value.project_id}/meetings`, { method: 'POST', body: JSON.stringify({ title: form.value.title.trim(), purpose_markdown: form.value.purpose_markdown, scheduled_start: new Date(form.value.scheduled_start).toISOString(), scheduled_end: new Date(form.value.scheduled_end).toISOString(), host_user_id: session.user.id, recorder_user_id: session.user.id, summary_markdown: '', raw_notes_markdown: '', participants: [{ user_id: session.user.id, participation_role: 'host' }] }) })
    await router.push(`/meetings/${created.id}`)
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议创建失败' }
  finally { creating.value = false }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">Meeting workspace</p><h1>会议</h1><p>围绕项目组织准备、现场议题、产出和会后档案。</p></div>
      <button class="button button-primary" @click="createOpen = !createOpen">{{ createOpen ? '收起' : '新建会议' }}</button>
    </header>
    <form v-if="createOpen" class="workspace-section meeting-create-form" @submit.prevent="createMeeting">
      <header class="section-heading"><h2>创建项目会议</h2><button type="button" class="icon-button" aria-label="关闭" @click="createOpen = false"><X :size="18" :stroke-width="2" aria-hidden="true" /></button></header>
      <div class="form-grid"><label>所属项目<select v-model="form.project_id" required><option value="" disabled>选择项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label><label>会议标题<input v-model.trim="form.title" required /></label><label>开始时间<input v-model="form.scheduled_start" type="datetime-local" required /></label><label>结束时间<input v-model="form.scheduled_end" type="datetime-local" required /></label><label class="span-2">会议目的<textarea v-model="form.purpose_markdown" rows="3" /></label></div>
      <div class="form-actions"><button class="button button-primary" :disabled="creating">{{ creating ? '创建中…' : '创建会议' }}</button></div>
    </form>
    <section class="meeting-list-filters" aria-label="会议搜索与筛选">
      <label class="search-box"><span aria-hidden="true">⌕</span><input v-model.trim="search" aria-label="搜索会议" placeholder="搜索会议、项目或系列" /></label>
      <button class="button button-quiet meeting-advanced-toggle" type="button" :class="{ 'is-active': advancedFilterCount }" :aria-label="advancedFilterCount ? `高级筛选（已启用 ${advancedFilterCount} 项）` : '高级筛选'" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
        高级筛选<span v-if="advancedFilterCount" class="meeting-filter-count">{{ advancedFilterCount }}</span>
      </button>
      <section v-if="advancedOpen" class="meeting-advanced-panel" aria-label="高级筛选条件">
        <header><div><strong>高级筛选</strong><span v-if="advancedFilterCount">已启用 {{ advancedFilterCount }} 项</span></div><button v-if="advancedFilterCount" class="button button-quiet button-small" type="button" aria-label="清除全部高级筛选" @click="clearAdvancedFilters">清除全部</button></header>
        <div class="meeting-advanced-fields">
          <label>项目<select v-model="projectFilter"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
          <label>会议系列<select v-model="activeSeriesFilter" @change="syncSeriesFilterToUrl"><option value="">全部系列</option><option v-if="activeSeriesFilter && !hasActiveSeriesOption" :value="activeSeriesFilter">当前筛选系列（不可用）</option><option v-for="series in seriesOptions" :key="series.id" :value="series.id">{{ series.title }}</option></select></label>
          <label>会议状态<select v-model="statusFilter"><option value="">全部状态</option><option value="draft">草稿</option><option value="ready">待开始</option><option value="in_progress">进行中</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label>
        </div>
        <p>当前显示 {{ visible.length }} 场会议。</p>
      </section>
    </section>
    <p v-if="error" class="notice notice-error">{{ error }}</p><p v-if="loading" class="empty-state">正在加载会议…</p>
    <template v-else><section v-for="group in groups" :key="group.id" class="meeting-group"><header><h2>{{ group.title }}</h2><span>{{ group.items.length }}</span></header><div v-if="group.items.length" class="meeting-workspace-list"><RouterLink v-for="item in group.items" :key="item.id" :to="`/meetings/${item.id}`" class="workspace-section meeting-workspace-row"><time>{{ new Date(item.scheduled_start).toLocaleString('zh-CN') }}</time><div><div class="tag-row"><span class="tag tag-project">{{ item.project.name }}</span><span v-if="item.series" class="tag">{{ item.series.title }}</span><span v-if="item.occurrence_kind === 'manual'" class="tag">临时</span><span class="status-pill" :data-status="item.status">{{ item.status }}</span></div><h3>{{ item.title }}</h3><p>{{ item.purpose_markdown || '尚未填写会议目的' }}</p></div><dl><div><dt>议题</dt><dd>{{ item.agenda_count }}</dd></div><div><dt>快照</dt><dd>{{ item.snapshot_count }}</dd></div><div><dt>更正</dt><dd>{{ item.amendment_count }}</dd></div></dl></RouterLink></div><p v-else class="empty-inline">暂无{{ group.title }}</p></section></template>
  </main>
</template>
