<script setup lang="ts">
import { NAlert, NDataTable, NSelect, NTag, type DataTableColumns } from 'naive-ui'
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import DecisionDetailDrawer from '../components/DecisionDetailDrawer.vue'
import StatusPill from '../components/StatusPill.vue'
import { loadUserNames, nameOf, userNames } from '../composables/useUserNameMap'
import type { Decision } from '../domain/outcomes'
import type { Project } from '../domain/projects'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { reviewStatusLabel } from '../utils/labels'
import { formatDateTime } from '../utils/time'

const { tr } = useI18n()

const PAGE_SIZE = 50

const REVIEW_STATUS_TYPES: Record<string, 'default' | 'warning' | 'success' | 'error'> = {
  pending: 'warning',
  approved: 'success',
  changes_requested: 'error',
}

const route = useRoute()
const projects = ref<Project[]>([])
const rows = ref<Decision[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const error = ref('')
const filters = reactive({ project: '', status: '', reviewer: '' })
const target = ref<Decision | null>(null)
const highlightedId = ref<string | null>(null)
let firstRun = true
let highlightHandle: number | undefined
let loadToken = 0
let appliedHighlight = ''

const projectNames = computed(() => Object.fromEntries(projects.value.map((project) => [project.id, project.name])))
const reviewerOptions = computed(() => Object.entries(userNames.value).map(([id, name]) => ({ label: name, value: id })))
/** The global list carries no capabilities payload; the backend stays the write authority (403/409). */
const memberOptions = computed<UserRef[]>(() => Object.entries(userNames.value).map(([id, displayName]) => ({
  id,
  username: displayName,
  display_name: displayName,
})))
const pagination = computed(() => ({ page: page.value, pageSize: PAGE_SIZE, itemCount: total.value }))

function query() {
  const params = new URLSearchParams()
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String((page.value - 1) * PAGE_SIZE))
  if (filters.project) params.set('project_id', filters.project)
  if (filters.status) params.set('status', filters.status)
  if (filters.reviewer) params.set('reviewer_user_id', filters.reviewer)
  return `/api/decisions?${params.toString()}`
}

/** Locates the `?highlight=` row: scroll to it and flash the row unless reduced motion is requested. */
function focusHighlight() {
  const highlighted = typeof route.query.highlight === 'string' ? route.query.highlight : ''
  if (!highlighted || highlighted === appliedHighlight || !rows.value.some((row) => row.id === highlighted)) return
  appliedHighlight = highlighted
  void nextTick(() => {
    const element = document.querySelector(`[data-row-key="${highlighted}"]`)
    element?.scrollIntoView?.({ block: 'center' })
  })
  const reduceMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduceMotion) return
  highlightedId.value = highlighted
  if (highlightHandle !== undefined) window.clearTimeout(highlightHandle)
  highlightHandle = window.setTimeout(() => { highlightedId.value = null }, 2_000)
}

async function load() {
  const token = ++loadToken
  loading.value = true
  error.value = ''
  try {
    const result = await api<Page<Decision>>(query())
    if (token !== loadToken) return
    rows.value = result?.items ?? []
    total.value = result?.total ?? 0
    focusHighlight()
  } catch (caught) {
    if (token !== loadToken) return
    error.value = errorMessage(caught, tr('决策加载失败', 'Failed to load decisions'))
  } finally {
    if (token === loadToken) loading.value = false
  }
}

function changePage(next: number) {
  if (next === page.value || loading.value) return
  page.value = next
  void load()
}

function openDetail(row: Decision) {
  target.value = row
}

async function decisionSaved() {
  const current = target.value
  await load()
  if (!current) return
  target.value = rows.value.find((row) => row.id === current.id) ?? null
}

function rowProps(row: Decision) {
  const classes = ['decision-row']
  if (highlightedId.value === row.id) classes.push('decision-row-highlight')
  return {
    'data-row-key': row.id,
    class: classes.join(' '),
    onClick: () => openDetail(row),
  }
}

function reviewerBadges(row: Decision) {
  const reviewers = row.reviewers ?? []
  if (!reviewers.length) return h('span', { class: 'muted' }, '—')
  return h('div', { class: 'reviewer-badges' }, reviewers.map((reviewer) => h(NTag, {
    size: 'small',
    type: REVIEW_STATUS_TYPES[reviewer.status] ?? 'default',
    class: 'reviewer-badge',
  }, {
    default: () => `${nameOf(reviewer.user_id)}·${reviewStatusLabel(reviewer.status)}`,
  })))
}

const columns = computed<DataTableColumns<Decision>>(() => [
  { title: tr('标题', 'Title'), key: 'title', minWidth: 120, ellipsis: { tooltip: true } },
  {
    title: tr('项目', 'Project'),
    key: 'project',
    width: 124,
    ellipsis: { tooltip: true },
    render: (row) => projectNames.value[row.project_id] ?? row.project_id,
  },
  {
    title: tr('状态', 'Status'),
    key: 'status',
    width: 90,
    render: (row) => h(StatusPill, { status: row.status, kind: 'decision' }),
  },
  {
    title: tr('评审人', 'Reviewers'),
    key: 'reviewers',
    width: 98,
    render: (row) => reviewerBadges(row),
  },
  {
    title: tr('更新时间', 'Updated'),
    key: 'updated_at',
    width: 132,
    render: (row) => formatDateTime(row.updated_at),
  },
  {
    title: tr('来源会议', 'Meeting'),
    key: 'meeting',
    width: 86,
    render: (row) => (row.meeting_id
      ? h(RouterLink, {
        to: `/meetings/${row.meeting_id}`,
        onClick: (event: MouseEvent) => event.stopPropagation(),
      }, { default: () => tr('来源会议', 'Meeting') })
      : h('span', { class: 'muted' }, '—')),
  },
])

watch(() => [filters.project, filters.status, filters.reviewer], () => {
  if (firstRun) return
  page.value = 1
  void load()
})

onMounted(async () => {
  projects.value = await loadUserNames()
  firstRun = false
  await load()
})

onBeforeUnmount(() => {
  if (highlightHandle !== undefined) window.clearTimeout(highlightHandle)
})
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading">
      <div><p class="eyebrow">{{ tr('决策台账', 'Decision log') }}</p><h1>{{ tr('决策日志', 'Decisions') }}</h1><p>{{ tr('跨项目查看提案、最终决策及其评审状态。', 'Browse proposals, final decisions, and review status across projects.') }}</p></div>
      <span class="metric"><strong>{{ total }}</strong>{{ tr('项', ' items') }}</span>
    </header>
    <section class="workspace-section filter-panel">
      <label>{{ tr('项目', 'Project') }}<select v-model="filters.project"><option value="">{{ tr('全部项目', 'All Projects') }}</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
      <label>{{ tr('状态', 'Status') }}<select v-model="filters.status"><option value="">{{ tr('全部状态', 'All Statuses') }}</option><option value="proposed">{{ tr('待确认', 'Proposed') }}</option><option value="final">{{ tr('已生效', 'Final') }}</option><option value="superseded">{{ tr('已替代', 'Superseded') }}</option><option value="withdrawn">{{ tr('已撤回', 'Withdrawn') }}</option></select></label>
      <label>{{ tr('评审人', 'Reviewer') }}<n-select v-model:value="filters.reviewer" class="decision-reviewer-filter" :options="reviewerOptions" :virtual-scroll="false" clearable :placeholder="tr('全部评审人', 'All Reviewers')" /></label>
    </section>
    <n-alert v-if="error" type="error" class="workspace-section">{{ error }}</n-alert>
    <section class="workspace-section decision-table-section">
      <n-data-table
        :columns="columns"
        :data="rows"
        :loading="loading"
        :remote="true"
        :row-key="(row: Decision) => row.id"
        :row-props="rowProps"
        :pagination="pagination"
        :scroll-x="650"
        :bordered="false"
        @update:page="changePage"
      />
    </section>
    <DecisionDetailDrawer
      :show="Boolean(target)"
      :decision="target"
      :members="memberOptions"
      :user-names="userNames"
      :can-contribute="true"
      @close="target = null"
      @saved="decisionSaved"
    />
  </main>
</template>

<style scoped>
.reviewer-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

:deep(.decision-row) {
  cursor: pointer;
}

:deep(.decision-row-highlight) td {
  animation: decision-row-flash 2s ease-out;
  background: var(--green-soft, #d9efe8);
}

@keyframes decision-row-flash {
  0% { background: var(--green-soft, #d9efe8); }
  70% { background: var(--green-soft, #d9efe8); }
  100% { background: transparent; }
}

/* 规格 §6.6：reduced-motion 下深链只滚动，不做闪烁高亮。 */
@media (prefers-reduced-motion: reduce) {
  :deep(.decision-row-highlight) td { background: transparent; animation: none; }
}
</style>
