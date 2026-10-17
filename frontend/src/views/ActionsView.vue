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
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/time'

const { tr } = useI18n()

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
      'aria-label': tr(`编辑行动项“${row.content}”`, `Edit action "${row.content}"`),
      onClick: () => openEdit(row),
    }, { default: () => tr('编辑', 'Edit') }),
  ]
  if (row.status === 'open') {
    buttons.push(h(NButton, {
      size: 'small',
      type: 'primary',
      loading: busy,
      disabled: busy,
      'aria-label': tr(`开始行动项“${row.content}”`, `Start action "${row.content}"`),
      onClick: () => void transitionStatus(row, 'in_progress'),
    }, { default: () => tr('开始', 'Start') }))
  }
  if (row.status === 'in_progress') {
    buttons.push(h(NButton, {
      size: 'small',
      type: 'primary',
      loading: busy,
      disabled: busy,
      'aria-label': tr(`完成行动项“${row.content}”`, `Complete action "${row.content}"`),
      onClick: () => void transitionStatus(row, 'done'),
    }, { default: () => tr('完成', 'Done') }))
  }
  if (row.status === 'open' || row.status === 'in_progress') {
    buttons.push(h(NPopconfirm, {
      positiveText: tr('确认', 'Confirm'),
      negativeText: tr('取消', 'Cancel'),
      onPositiveClick: () => void transitionStatus(row, 'canceled'),
    }, {
      trigger: () => h(NButton, {
        size: 'small',
        quaternary: true,
        disabled: busy,
        'aria-label': tr(`取消行动项“${row.content}”`, `Cancel action "${row.content}"`),
      }, { default: () => tr('取消', 'Cancel') }),
      default: () => tr(`确定取消行动项“${row.content}”吗？`, `Cancel action "${row.content}"?`),
    }))
  }
  return buttons
}

const columns = computed<DataTableColumns<ActionRow>>(() => [
  { title: tr('内容', 'Action'), key: 'content', minWidth: 120, ellipsis: { tooltip: true } },
  { title: tr('负责人', 'Owner'), key: 'owner', width: 76, render: (row) => nameOf(row.owner_user_id) },
  {
    title: tr('优先级', 'Priority'),
    key: 'priority',
    width: 84,
    render: (row) => h(StatusPill, { status: row.priority, kind: 'priority' }),
  },
  {
    title: tr('状态', 'Status'),
    key: 'status',
    width: 156,
    render: (row) => h('div', { class: 'action-status-cell' }, [
      h(StatusPill, { status: row.status, kind: 'action' }),
      row.is_derived
        ? h('span', { class: 'muted' }, tr('由议题派生', 'From Agenda'))
        : h('div', { class: 'row-actions action-row-actions' }, actionButtons(row)),
    ]),
  },
  {
    title: tr('截止日期', 'Due Date'),
    key: 'due_date',
    width: 120,
    render: (row) => {
      const lines: VNodeChild[] = [
        row.due_date
          ? h('span', { class: isOverdue(row) ? 'action-due-overdue' : undefined }, `${tr('截止', 'Due')} ${row.due_date}`)
          : h('span', { class: 'muted' }, tr('未设截止日期', 'No due date')),
      ]
      if (row.completed_at) lines.push(h('span', { class: 'muted' }, `${tr('完成于', 'Done')} ${formatDateTime(row.completed_at)}`))
      return h('div', { class: 'action-due-cell' }, lines)
    },
  },
  {
    title: tr('来源会议', 'Meeting'),
    key: 'meeting',
    width: 84,
    render: (row) => (row.meeting_id
      ? h(RouterLink, { to: `/meetings/${row.meeting_id}` }, { default: () => tr('来源会议', 'Meeting') })
      : h('span', { class: 'muted' }, '—')),
  },
])

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
      <div><p class="eyebrow">Action hub</p><h1>{{ tr('行动项', 'Actions') }}</h1><p>{{ tr('会议产生的行动在这里汇总、筛选并持续跟踪。', 'Track, filter, and follow up on action items across all meetings.') }}</p></div>
      <span class="metric"><strong>{{ total }}</strong>{{ tr('项', ' items') }}</span>
    </header>
    <section class="workspace-section filter-panel">
      <label>{{ tr('负责人', 'Owner') }}<select v-model="filters.owner"><option value="me">{{ tr('分配给我', 'Assigned to Me') }}</option><option value="all">{{ tr('所有负责人', 'All Owners') }}</option></select></label>
      <label>{{ tr('状态', 'Status') }}<select v-model="filters.status"><option value="open">{{ tr('待开始', 'Open') }}</option><option value="in_progress">{{ tr('进行中', 'In Progress') }}</option><option value="done">{{ tr('已完成', 'Done') }}</option><option value="canceled">{{ tr('已取消', 'Canceled') }}</option><option value="">{{ tr('全部状态', 'All Statuses') }}</option></select></label>
      <label>{{ tr('项目', 'Project') }}<select v-model="filters.project"><option value="">{{ tr('全部项目', 'All Projects') }}</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
      <label>{{ tr('期限', 'Due') }}<select v-model="filters.due"><option value="">{{ tr('全部期限', 'All Dates') }}</option><option value="overdue">{{ tr('已逾期', 'Overdue') }}</option><option value="upcoming">{{ tr('今天及以后', 'Upcoming') }}</option></select></label>
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
        :scroll-x="624"
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
:deep(.action-status-cell) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

:deep(.action-due-cell) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  white-space: nowrap;
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

/* 规格 §6.6：reduced-motion 下深链只滚动，不做闪烁高亮。 */
@media (prefers-reduced-motion: reduce) {
  :deep(.action-row-highlight) td { background: transparent; animation: none; }
}
</style>
