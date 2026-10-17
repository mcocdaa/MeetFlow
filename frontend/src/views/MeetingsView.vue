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
import { useI18n } from '../i18n'
import { errorMessage, translateBackendError } from '../utils/errors'
import { formatDateTime } from '../utils/time'

type MeetingRow = { id: string; project: { id: string; name: string }; series: { id: string; title: string } | null; occurrence_kind: 'scheduled' | 'manual'; title: string; purpose_markdown: string; scheduled_start: string; scheduled_end: string; status: MeetingStatus; host: UserRef | null; agenda_count: number; snapshot_count: number; amendment_count: number }

const PAGE_SIZE = 50

const router = useRouter()
const { locale, tr, translateSeededText } = useI18n()
const projects = ref<Project[]>([])
const meetings = ref<MeetingRow[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref('')

watch(locale, () => {
  if (error.value) error.value = translateBackendError(error.value)
})
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
const createProjects = computed(() => projects.value.map((project) => ({ id: project.id, name: translateSeededText(project.name) })))
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
  { id: 'active', title: tr('进行中的会议', 'In Progress'), items: visible.value.filter((item) => item.status === 'in_progress') },
  { id: 'upcoming', title: tr('即将开始', 'Upcoming'), items: visible.value.filter((item) => item.status === 'draft' || item.status === 'ready').sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start)) },
  { id: 'completed', title: tr('最近完成', 'Recently Completed'), items: visible.value.filter((item) => item.status === 'completed').sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
  { id: 'canceled', title: tr('已取消', 'Canceled'), items: visible.value.filter((item) => item.status === 'canceled').sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start)) },
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
  const projectRequest = more ? Promise.resolve(null) : api<Project[]>('/api/projects')
  try {
    const [projectRows, page] = await Promise.all([
      projectRequest,
      api<Page<MeetingRow>>(`/api/meetings?${query}`),
    ])
    if (revision !== loadRevision) return
    if (projectRows) projects.value = projectRows
    meetings.value = more ? [...meetings.value, ...page.items] : page.items
    total.value = page.total
    offset.value = meetings.value.length
  } catch (caught) {
    if (revision === loadRevision) error.value = errorMessage(caught, tr('会议加载失败', 'Failed to load meetings'))
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
      <div><p class="eyebrow">{{ tr('会议工作区', 'Meeting workspace') }}</p><h1>{{ tr('会议', 'Meetings') }}</h1><p>{{ tr('围绕项目组织准备、现场议题、产出和会后档案。', 'Organize prep, live agenda items, outcomes, and archives around projects.') }}</p></div>
      <button class="button button-primary" @click="createOpen = true">{{ tr('新建会议', 'New Meeting') }}</button>
    </header>
    <MeetingCreateDrawer
      :show="createOpen"
      :projects="createProjects"
      :member-options="memberOptions"
      @close="createOpen = false"
      @created="onCreated"
    />
    <section class="meeting-list-filters" :aria-label="tr('会议搜索与筛选', 'Meeting search and filters')">
      <label class="search-box"><span class="search-icon" aria-hidden="true"><n-icon><Search :size="16" /></n-icon></span><input v-model.trim="search" :aria-label="tr('搜索会议', 'Search meetings')" :placeholder="tr('搜索会议、项目或系列', 'Search meetings, projects, or series')" /></label>
      <button class="button button-quiet meeting-advanced-toggle" type="button" :class="{ 'is-active': advancedFilterCount }" :aria-label="advancedFilterCount ? tr(`高级筛选（已启用 ${advancedFilterCount} 项）`, `Advanced Filters (${advancedFilterCount} active)`) : tr('高级筛选', 'Advanced Filters')" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
        {{ tr('高级筛选', 'Advanced Filters') }}<span v-if="advancedFilterCount" class="meeting-filter-count">{{ advancedFilterCount }}</span>
      </button>
      <section v-if="advancedOpen" class="meeting-advanced-panel" :aria-label="tr('高级筛选条件', 'Advanced filter options')">
        <header><div><strong>{{ tr('高级筛选', 'Advanced Filters') }}</strong><span v-if="advancedFilterCount">{{ tr(`已启用 ${advancedFilterCount} 项`, `${advancedFilterCount} active`) }}</span></div><button v-if="advancedFilterCount" class="button button-quiet button-small" type="button" :aria-label="tr('清除全部高级筛选', 'Clear all advanced filters')" @click="clearAdvancedFilters">{{ tr('清除全部', 'Clear all') }}</button></header>
        <div class="meeting-advanced-fields">
          <label>{{ tr('项目', 'Project') }}<select v-model="projectFilter"><option value="">{{ tr('全部项目', 'All Projects') }}</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ translateSeededText(project.name) }}</option></select></label>
          <label>{{ tr('会议系列', 'Series') }}<select v-model="activeSeriesFilter" @change="syncSeriesFilterToUrl"><option value="">{{ tr('全部系列', 'All Series') }}</option><option v-if="activeSeriesFilter && !hasActiveSeriesOption" :value="activeSeriesFilter">{{ tr('当前筛选系列（不可用）', 'Current series (unavailable)') }}</option><option v-for="series in seriesOptions" :key="series.id" :value="series.id">{{ translateSeededText(series.title) }}</option></select></label>
          <label>{{ tr('会议状态', 'Status') }}<select v-model="statusFilter"><option value="">{{ tr('全部状态', 'All Statuses') }}</option><option value="draft">{{ tr('草稿', 'Draft') }}</option><option value="ready">{{ tr('待开始', 'Ready') }}</option><option value="in_progress">{{ tr('进行中', 'In Progress') }}</option><option value="completed">{{ tr('已完成', 'Completed') }}</option><option value="canceled">{{ tr('已取消', 'Canceled') }}</option></select></label>
          <label>{{ tr('参与者', 'Participant') }}<select v-model="participantFilter"><option value="">{{ tr('全部参与者', 'All Participants') }}</option><option v-for="member in memberOptions" :key="member.id" :value="member.id">{{ translateSeededText(member.display_name) }}</option></select></label>
          <label>{{ tr('开始时间不早于', 'Start After') }}<n-date-picker v-model:value="startAfter" type="datetime" clearable :virtual-scroll="false" /></label>
          <label>{{ tr('开始时间不晚于', 'Start Before') }}<n-date-picker v-model:value="startBefore" type="datetime" clearable :virtual-scroll="false" /></label>
        </div>
        <p>{{ tr(`已加载 ${meetings.length} / 共 ${total} 场会议`, `Loaded ${meetings.length} / ${total} meetings`) }}</p>
        <p class="meeting-scope-note">{{ tr('搜索与系列筛选仅作用于已加载页', 'Search and series filters apply to loaded pages only') }}</p>
      </section>
    </section>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <p v-if="loading && !meetings.length" class="empty-state">{{ tr('正在加载会议…', 'Loading meetings…') }}</p>
    <template v-else>
      <section v-for="group in groups" :key="group.id" class="meeting-group"><header><h2>{{ group.title }}</h2><span>{{ group.items.length }}</span></header><div v-if="group.items.length" class="meeting-workspace-list"><RouterLink v-for="item in group.items" :key="item.id" :to="`/meetings/${item.id}`" class="workspace-section meeting-workspace-row"><time>{{ formatDateTime(item.scheduled_start) }}</time><div><div class="tag-row"><span class="tag tag-project">{{ translateSeededText(item.project.name) }}</span><span v-if="item.series" class="tag">{{ translateSeededText(item.series.title) }}</span><span v-if="item.occurrence_kind === 'manual'" class="tag">{{ tr('临时', 'Ad-hoc') }}</span><StatusPill :status="item.status" kind="meeting" /></div><h3>{{ translateSeededText(item.title) }}</h3><p>{{ translateSeededText(item.purpose_markdown) || tr('尚未填写会议目的', 'No meeting purpose provided') }}</p></div><dl><div><dt>{{ tr('议题', 'Agendas') }}</dt><dd>{{ item.agenda_count }}</dd></div><div><dt>{{ tr('快照', 'Snapshots') }}</dt><dd>{{ item.snapshot_count }}</dd></div><div><dt>{{ tr('更正', 'Amendments') }}</dt><dd>{{ item.amendment_count }}</dd></div></dl></RouterLink></div><p v-else class="empty-inline">{{ tr(`暂无${group.title}`, `No ${group.title.toLowerCase()} meetings`) }}</p></section>
      <div v-if="meetings.length < total" class="meeting-load-more">
        <p v-if="activeSeriesFilter && !visible.length">{{ tr('当前系列不在已加载页内，请继续加载更多会议。', 'Series not in loaded page; please load more meetings.') }}</p>
        <button class="button button-quiet" :disabled="loading" @click="loadMore">{{ loading ? tr('正在加载…', 'Loading…') : tr('加载更多', 'Load more') }}</button>
      </div>
    </template>
  </main>
</template>
