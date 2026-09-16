<script setup lang="ts">
import { Search } from '@lucide/vue'
import { NDatePicker, NIcon } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import MeetingCreateDrawer from '../components/MeetingCreateDrawer.vue'
import StatusPill from '../components/StatusPill.vue'
import { api } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import type { MeetingStatus } from '../domain/meetings'
import type { Project } from '../domain/projects'
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/time'

type MeetingRow = { id: string; project: { id: string; name: string }; series: { id: string; title: string } | null; occurrence_kind: 'scheduled' | 'manual'; title: string; purpose_markdown: string; scheduled_start: string; scheduled_end: string; status: MeetingStatus; host: UserRef | null; agenda_count: number; snapshot_count: number; amendment_count: number }

const PAGE_SIZE = 50

const router = useRouter()
const projects = ref<Project[]>([])
const meetings = ref<MeetingRow[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref('')
const search = ref('')
const projectFilter = ref('')
const participantFilter = ref('')
const activeSeriesFilter = ref(new URLSearchParams(window.location.search).get('series_id') ?? '')
const statusFilter = ref<MeetingStatus | ''>('')
const startAfter = ref<number | null>(null)
const startBefore = ref<number | null>(null)
const advancedOpen = ref(Boolean(activeSeriesFilter.value))
const createOpen = ref(false)

const memberOptions = computed<UserRef[]>(() => {
  const seen = new Set<string>()
  const options: UserRef[] = []
  for (const project of projects.value) {
    for (const membership of project.memberships ?? []) {
      if (seen.has(membership.user.id)) continue
      seen.add(membership.user.id)
      options.push(membership.user)
    }
  }
  return options
})
const createProjects = computed(() => projects.value.map((project) => ({ id: project.id, name: project.name })))
const seriesOptions = computed(() => {
  const seen = new Map<string, { id: string; title: string }>()
  meetings.value.forEach((item) => { if (item.series) seen.set(item.series.id, item.series) })
  return [...seen.values()].sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
})
const hasActiveSeriesOption = computed(() => seriesOptions.value.some((item) => item.id === activeSeriesFilter.value))
const advancedFilterCount = computed(() => [
  projectFilter.value,
  participantFilter.value,
  activeSeriesFilter.value,
  statusFilter.value,
  startAfter.value,
  startBefore.value,
].filter(Boolean).length)
const visible = computed(() => meetings.value.filter((item) => (
  (!activeSeriesFilter.value || item.series?.id === activeSeriesFilter.value)
  && (!search.value || `${item.title} ${item.project.name} ${item.series?.title ?? ''}`.toLowerCase().includes(search.value.toLowerCase()))
)))
const groups = computed(() => [
  { id: 'active', title: '进行中的会议', items: visible.value.filter((item) => item.status === 'in_progress') },
  { id: 'upcoming', title: '即将开始', items: visible.value.filter((item) => item.status === 'draft' || item.status === 'ready').sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start)) },
  { id: 'completed', title: '最近完成', items: visible.value.filter((item) => item.status === 'completed').sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
  { id: 'canceled', title: '已取消', items: visible.value.filter((item) => item.status === 'canceled').sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
])

function syncSeriesFilterToUrl() {
  const url = new URL(window.location.href)
  if (activeSeriesFilter.value) url.searchParams.set('series_id', activeSeriesFilter.value)
  else url.searchParams.delete('series_id')
  window.history.replaceState(null, '', url)
}

function clearAdvancedFilters() {
  projectFilter.value = ''
  participantFilter.value = ''
  activeSeriesFilter.value = ''
  statusFilter.value = ''
  startAfter.value = null
  startBefore.value = null
  syncSeriesFilterToUrl()
}

function buildQuery() {
  const params = new URLSearchParams()
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(offset.value))
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (projectFilter.value) params.set('project_id', projectFilter.value)
  if (participantFilter.value) params.set('participant_user_id', participantFilter.value)
  if (startAfter.value) params.set('start_after', new Date(startAfter.value).toISOString())
  if (startBefore.value) params.set('start_before', new Date(startBefore.value).toISOString())
  return params.toString()
}

let loadRevision = 0

async function load(more = false) {
  const revision = ++loadRevision
  if (!more) offset.value = 0
  loading.value = true
  error.value = ''
  const query = buildQuery()
  try {
    const [projectRows, page] = await Promise.all([
      api<Project[]>('/api/projects'),
      api<Page<MeetingRow>>(`/api/meetings?${query}`),
    ])
    if (revision !== loadRevision) return
    projects.value = projectRows
    meetings.value = more ? [...meetings.value, ...page.items] : page.items
    total.value = page.total
    offset.value += PAGE_SIZE
  } catch (caught) {
    if (revision === loadRevision) error.value = errorMessage(caught, '会议加载失败')
  } finally {
    if (revision === loadRevision) loading.value = false
  }
}

function loadMore() {
  if (!loading.value && meetings.value.length < total.value) void load(true)
}

function onCreated(created: { id: string }) {
  createOpen.value = false
  void router.push(`/meetings/${created.id}`)
}

watch([projectFilter, participantFilter, statusFilter, startAfter, startBefore], () => { void load() })

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">Meeting workspace</p><h1>会议</h1><p>围绕项目组织准备、现场议题、产出和会后档案。</p></div>
      <button class="button button-primary" @click="createOpen = true">新建会议</button>
    </header>
    <MeetingCreateDrawer
      :show="createOpen"
      :projects="createProjects"
      :member-options="memberOptions"
      @close="createOpen = false"
      @created="onCreated"
    />
    <section class="meeting-list-filters" aria-label="会议搜索与筛选">
      <label class="search-box"><span class="search-icon" aria-hidden="true"><n-icon><Search :size="16" /></n-icon></span><input v-model.trim="search" aria-label="搜索会议" placeholder="搜索会议、项目或系列" /></label>
      <button class="button button-quiet meeting-advanced-toggle" type="button" :class="{ 'is-active': advancedFilterCount }" :aria-label="advancedFilterCount ? `高级筛选（已启用 ${advancedFilterCount} 项）` : '高级筛选'" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
        高级筛选<span v-if="advancedFilterCount" class="meeting-filter-count">{{ advancedFilterCount }}</span>
      </button>
      <section v-if="advancedOpen" class="meeting-advanced-panel" aria-label="高级筛选条件">
        <header><div><strong>高级筛选</strong><span v-if="advancedFilterCount">已启用 {{ advancedFilterCount }} 项</span></div><button v-if="advancedFilterCount" class="button button-quiet button-small" type="button" aria-label="清除全部高级筛选" @click="clearAdvancedFilters">清除全部</button></header>
        <div class="meeting-advanced-fields">
          <label>项目<select v-model="projectFilter"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
          <label>会议系列<select v-model="activeSeriesFilter" @change="syncSeriesFilterToUrl"><option value="">全部系列</option><option v-if="activeSeriesFilter && !hasActiveSeriesOption" :value="activeSeriesFilter">当前筛选系列（不可用）</option><option v-for="series in seriesOptions" :key="series.id" :value="series.id">{{ series.title }}</option></select></label>
          <label>会议状态<select v-model="statusFilter"><option value="">全部状态</option><option value="draft">草稿</option><option value="ready">待开始</option><option value="in_progress">进行中</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label>
          <label>参与者<select v-model="participantFilter"><option value="">全部参与者</option><option v-for="member in memberOptions" :key="member.id" :value="member.id">{{ member.display_name }}</option></select></label>
          <label>开始时间窗<n-date-picker v-model:value="startAfter" type="datetime" clearable :virtual-scroll="false" /></label>
          <label>结束时间窗<n-date-picker v-model:value="startBefore" type="datetime" clearable :virtual-scroll="false" /></label>
        </div>
        <p>已加载 {{ meetings.length }} / 共 {{ total }} 场会议</p>
        <p class="meeting-scope-note">搜索与系列筛选仅作用于已加载页</p>
      </section>
    </section>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <p v-if="loading && !meetings.length" class="empty-state">正在加载会议…</p>
    <template v-else>
      <section v-for="group in groups" :key="group.id" class="meeting-group"><header><h2>{{ group.title }}</h2><span>{{ group.items.length }}</span></header><div v-if="group.items.length" class="meeting-workspace-list"><RouterLink v-for="item in group.items" :key="item.id" :to="`/meetings/${item.id}`" class="workspace-section meeting-workspace-row"><time>{{ formatDateTime(item.scheduled_start) }}</time><div><div class="tag-row"><span class="tag tag-project">{{ item.project.name }}</span><span v-if="item.series" class="tag">{{ item.series.title }}</span><span v-if="item.occurrence_kind === 'manual'" class="tag">临时</span><StatusPill :status="item.status" kind="meeting" /></div><h3>{{ item.title }}</h3><p>{{ item.purpose_markdown || '尚未填写会议目的' }}</p></div><dl><div><dt>议题</dt><dd>{{ item.agenda_count }}</dd></div><div><dt>快照</dt><dd>{{ item.snapshot_count }}</dd></div><div><dt>更正</dt><dd>{{ item.amendment_count }}</dd></div></dl></RouterLink></div><p v-else class="empty-inline">暂无{{ group.title }}</p></section>
      <div v-if="meetings.length < total" class="meeting-load-more">
        <p v-if="activeSeriesFilter && !visible.length">当前系列不在已加载页内，请继续加载更多会议。</p>
        <button class="button button-quiet" :disabled="loading" @click="loadMore">{{ loading ? '正在加载…' : '加载更多' }}</button>
      </div>
    </template>
  </main>
</template>
