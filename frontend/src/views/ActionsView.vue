<script setup lang="ts">
import { NAlert, NButton, NDataTable, NPopconfirm, type DataTableColumns } from 'naive-ui'
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import { session } from '../auth/session'
import ActionEditDrawer from '../components/ActionEditDrawer.vue'
import StatusPill from '../components/StatusPill.vue'
import { loadUserNames, nameOf, userNames } from '../composables/useUserNameMap'
import type { Project } from '../domain/projects'
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/time'

type ActionRow = {
  id: string
  project_id: string
  meeting_id: string | null
  content: string
  owner_user_id: string | null
  due_date: string | null
  priority: string
  status: string
  version?: number
  is_derived?: boolean
  completed_at?: string | null
}

const PAGE_SIZE = 50

const route = useRoute()
const projects = ref<Project[]>([])
const rows = ref<ActionRow[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const error = ref('')
const filters = reactive({ owner: 'me', status: 'open', project: '', due: '' })
const editTarget = ref<ActionRow | null>(null)
const actionBusy = ref('')
const highlightedId = ref<string | null>(null)
let firstRun = true
let highlightHandle: number | undefined
let loadToken = 0
let appliedHighlight = ''

/** Owner options for the edit drawer, aggregated from project memberships (no directory endpoint). */
const memberOptions = computed<UserRef[]>(() => Object.entries(userNames.value).map(([id, displayName]) => ({
  id,
  username: displayName,
  display_name: displayName,
})))
const pagination = computed(() => ({ page: page.value, pageSize: PAGE_SIZE, itemCount: total.value }))

function today() {
  return new Date().toISOString().slice(0, 10)
}

function isOverdue(row: ActionRow) {
  return Boolean(row.due_date) && row.status !== 'done' && row.status !== 'canceled' && String(row.due_date) < today()
}

function query() {
  const params = new URLSearchParams()
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String((page.value - 1) * PAGE_SIZE))
  if (filters.status) params.set('status', filters.status)
  if (filters.owner === 'me' && session.user) params.set('owner_user_id', session.user.id)
  if (filters.project) params.set('project_id', filters.project)
  if (filters.due === 'overdue') params.set('due_before', today())
  if (filters.due === 'upcoming') params.set('due_after', today())
  return `/api/actions?${params.toString()}`
}

/** Locates the `?highlight=` row: scroll to it and flash the row unless reduced motion is requested. */
function focusHighlight() {
  const target = typeof route.query.highlight === 'string' ? route.query.highlight : ''
  if (!target || target === appliedHighlight || !rows.value.some((row) => row.id === target)) return
  appliedHighlight = target
  void nextTick(() => {
    const element = document.querySelector(`[data-row-key="${target}"]`)
    element?.scrollIntoView?.({ block: 'center' })
  })
  const reduceMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduceMotion) return
  highlightedId.value = target
  if (highlightHandle !== undefined) window.clearTimeout(highlightHandle)
  highlightHandle = window.setTimeout(() => { highlightedId.value = null }, 2_000)
}

async function load() {
  const token = ++loadToken
  loading.value = true
  error.value = ''
  try {
    const result = await api<Page<ActionRow>>(query())
    if (token !== loadToken) return
    rows.value = result?.items ?? []
    total.value = result?.total ?? 0
    focusHighlight()
  } catch (caught) {
    if (token !== loadToken) return
    error.value = errorMessage(caught, '行动项加载失败')
  } finally {
    if (token === loadToken) loading.value = false
  }
}

function changePage(next: number) {
  if (next === page.value || loading.value) return
  page.value = next
  void load()
}

function openEdit(row: ActionRow) {
  if (row.is_derived) return
  editTarget.value = row
}

async function actionSaved() {
  editTarget.value = null
  await load()
}

async function transitionStatus(row: ActionRow, status: string) {
  if (actionBusy.value || row.is_derived) return
  actionBusy.value = row.id
  error.value = ''
  try {
    await api(`/api/actions/${row.id}`, {
      method: 'PUT',
      body: JSON.stringify({ status, expected_version: row.version ?? 1 }),
    })
    await load()
  } catch (caught) {
    error.value = errorMessage(caught, '行动项更新失败')
  } finally {
    actionBusy.value = ''
  }
}

function rowKey(row: ActionRow) {
  return row.id
}

function rowProps(row: ActionRow) {
  return {
    'data-row-key': row.id,
    class: highlightedId.value === row.id ? 'action-row-highlight' : undefined,
  }
}

function actionButtons(row: ActionRow): VNodeChild[] {
  const busy = actionBusy.value === row.id
  const buttons: VNodeChild[] = [
    h(NButton, {
      size: 'small',
      quaternary: true,
      disabled: busy,
      'aria-label': `编辑行动项“${row.content}”`,
      onClick: () => openEdit(row),
    }, { default: () => '编辑' }),
  ]
  if (row.status === 'open') {
    buttons.push(h(NButton, {
      size: 'small',
      type: 'primary',
      loading: busy,
      disabled: busy,
      'aria-label': `开始行动项“${row.content}”`,
      onClick: () => void transitionStatus(row, 'in_progress'),
    }, { default: () => '开始' }))
  }
  if (row.status === 'in_progress') {
    buttons.push(h(NButton, {
      size: 'small',
      type: 'primary',
      loading: busy,
      disabled: busy,
      'aria-label': `完成行动项“${row.content}”`,
      onClick: () => void transitionStatus(row, 'done'),
    }, { default: () => '完成' }))
  }
  if (row.status === 'open' || row.status === 'in_progress') {
    buttons.push(h(NPopconfirm, {
      positiveText: '确认',
      negativeText: '取消',
      onPositiveClick: () => void transitionStatus(row, 'canceled'),
    }, {
      trigger: () => h(NButton, {
        size: 'small',
        quaternary: true,
        disabled: busy,
        'aria-label': `取消行动项“${row.content}”`,
      }, { default: () => '取消' }),
      default: () => `确定取消行动项“${row.content}”吗？`,
    }))
  }
  return buttons
}

const columns: DataTableColumns<ActionRow> = [
  { title: '内容', key: 'content', minWidth: 260, ellipsis: { tooltip: true } },
  { title: '负责人', key: 'owner', minWidth: 130, render: (row) => nameOf(row.owner_user_id) },
  {
    title: '优先级',
    key: 'priority',
    minWidth: 100,
    render: (row) => h(StatusPill, { status: row.priority, kind: 'priority' }),
  },
  {
    title: '状态',
    key: 'status',
    minWidth: 260,
    render: (row) => h('div', { class: 'action-status-cell' }, [
      h(StatusPill, { status: row.status, kind: 'action' }),
      row.is_derived
        ? h('span', { class: 'muted' }, '由议题派生')
        : h('div', { class: 'row-actions action-row-actions' }, actionButtons(row)),
    ]),
  },
  {
    title: '截止日期',
    key: 'due_date',
    minWidth: 170,
    render: (row) => {
      const lines: VNodeChild[] = [
        row.due_date
          ? h('span', { class: isOverdue(row) ? 'action-due-overdue' : undefined }, `截止 ${row.due_date}`)
          : h('span', { class: 'muted' }, '未设截止日期'),
      ]
      if (row.completed_at) lines.push(h('span', { class: 'muted' }, `完成于 ${formatDateTime(row.completed_at)}`))
      return h('div', { class: 'action-due-cell' }, lines)
    },
  },
  {
    title: '来源会议',
    key: 'meeting',
    minWidth: 120,
    render: (row) => (row.meeting_id
      ? h(RouterLink, { to: `/meetings/${row.meeting_id}` }, { default: () => '来源会议' })
      : h('span', { class: 'muted' }, '—')),
  },
]

watch(() => [filters.owner, filters.status, filters.project, filters.due], () => {
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
      <div><p class="eyebrow">Action hub</p><h1>行动项</h1><p>会议产生的行动在这里汇总、筛选并持续跟踪。</p></div>
      <span class="metric"><strong>{{ total }}</strong>项</span>
    </header>
    <section class="workspace-section filter-panel">
      <label>负责人<select v-model="filters.owner"><option value="me">分配给我</option><option value="all">所有负责人</option></select></label>
      <label>状态<select v-model="filters.status"><option value="open">待开始</option><option value="in_progress">进行中</option><option value="done">已完成</option><option value="canceled">已取消</option><option value="">全部状态</option></select></label>
      <label>项目<select v-model="filters.project"><option value="">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
      <label>期限<select v-model="filters.due"><option value="">全部期限</option><option value="overdue">已逾期</option><option value="upcoming">今天及以后</option></select></label>
    </section>
    <n-alert v-if="error" type="error" class="workspace-section">{{ error }}</n-alert>
    <section class="workspace-section action-table-section">
      <n-data-table
        :columns="columns"
        :data="rows"
        :loading="loading"
        :remote="true"
        :row-key="rowKey"
        :row-props="rowProps"
        :pagination="pagination"
        :scroll-x="960"
        :bordered="false"
        @update:page="changePage"
      />
    </section>
    <ActionEditDrawer
      :show="Boolean(editTarget)"
      :action="editTarget"
      :members="memberOptions"
      @close="editTarget = null"
      @saved="actionSaved"
    />
  </main>
</template>

<style scoped>
.action-status-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.action-due-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.action-due-overdue {
  color: var(--red, #ae3f36);
  font-weight: 600;
}

:deep(.action-row-highlight) td {
  animation: action-row-flash 2s ease-out;
  background: var(--green-soft, #d9efe8);
}

@keyframes action-row-flash {
  0% { background: var(--green-soft, #d9efe8); }
  70% { background: var(--green-soft, #d9efe8); }
  100% { background: transparent; }
}
</style>
