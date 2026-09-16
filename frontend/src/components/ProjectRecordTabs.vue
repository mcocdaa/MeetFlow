<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopconfirm } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import StatusPill from './StatusPill.vue'
import { errorMessage } from '../utils/errors'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { priorityLabel } from '../utils/labels'
import { formatDateTime } from '../utils/time'
import AttachmentPanel from './AttachmentPanel.vue'
import ActionEditDrawer from './ActionEditDrawer.vue'
import DecisionDetailDrawer from './DecisionDetailDrawer.vue'
import SeriesEditDrawer from './SeriesEditDrawer.vue'
import type { MeetingSeriesDetail } from '../domain/meetings'
import type { ActionStatus, Decision } from '../domain/outcomes'
import type { Page } from '../api/contracts'
import type { ProjectActionSummary, ProjectDetail } from '../domain/projects'

type Tab = 'meetings' | 'actions' | 'decisions' | 'files'
type MeetingRow = { id: string; title: string; scheduled_start: string; status: string }
type SeriesRow = { id: string; title: string; recurrence_description: string; status: string }

const props = defineProps<{
  project: ProjectDetail
  tab: Tab
  canContribute: boolean
}>()
const emit = defineEmits<{
  create: [kind: 'meeting' | 'series' | 'decision' | 'action']
  uploaded: [attachment: ProjectDetail['attachments'][number]]
  deleted: [id: string]
  changed: []
}>()

const rows = ref<Array<MeetingRow | ProjectActionSummary | Decision>>([])
const loading = ref(false)
const error = ref('')
const editSeries = ref<SeriesRow | null>(null)
const editAction = ref<ProjectActionSummary | null>(null)
const decisionTarget = ref<Decision | null>(null)
const actionBusy = ref('')
const archivingId = ref('')
const occurrenceSeries = ref<SeriesRow | null>(null)
const occurrenceTitle = ref('')
const occurrenceStart = ref('')
const occurrenceEnd = ref('')
const occurrenceSaving = ref(false)
const occurrenceError = ref('')

const memberRefs = () => props.project.memberships.map((row) => row.user)
const userNames = computed<Record<string, string>>(() => Object.fromEntries(
  props.project.memberships.map((row) => [row.user.id, row.user.display_name || row.user.username]),
))

function endpoint() {
  if (props.tab === 'meetings') return `/api/meetings?project_id=${props.project.id}`
  if (props.tab === 'actions') return `/api/actions?project_id=${props.project.id}`
  return `/api/decisions?project_id=${props.project.id}`
}

async function load() {
  if (props.tab === 'files') return
  loading.value = true
  error.value = ''
  try {
    const value = await api<Page<typeof rows.value[number]>>(endpoint())
    rows.value = Array.isArray(value?.items) ? value.items : []
  } catch (reason) {
    error.value = errorMessage(reason, '记录加载失败')
  } finally {
    loading.value = false
  }
}

function openSeriesEdit(series: SeriesRow) {
  if (!props.canContribute) return
  editSeries.value = series
}

function seriesSaved() {
  editSeries.value = null
  emit('changed')
}

function ownerName(userId: string | null) {
  if (!userId) return '未指派'
  const row = props.project.memberships.find((item) => item.user.id === userId)
  return row?.user.display_name || row?.user.username || '未指派'
}

function openActionEdit(item: ProjectActionSummary) {
  if (!props.canContribute || item.is_derived) return
  editAction.value = item
}

async function actionSaved() {
  editAction.value = null
  await load()
  emit('changed')
}

function openDecision(item: Decision) {
  decisionTarget.value = item
}

async function decisionSaved() {
  const current = decisionTarget.value
  await load()
  if (current) {
    decisionTarget.value = (rows.value as Decision[]).find((item) => item.id === current.id) ?? null
  }
  emit('changed')
}

async function transitionAction(item: ProjectActionSummary, status: ActionStatus) {
  if (!props.canContribute || item.is_derived || actionBusy.value) return
  actionBusy.value = item.id
  error.value = ''
  try {
    await api(`/api/actions/${item.id}`, {
      method: 'PUT',
      body: JSON.stringify({ status, expected_version: item.version ?? 1 }),
    })
    await load()
    emit('changed')
  } catch (reason) {
    error.value = errorMessage(reason, '行动项更新失败')
  } finally {
    actionBusy.value = ''
  }
}

async function archiveSeries(series: SeriesRow) {
  if (!props.canContribute || archivingId.value) return
  archivingId.value = series.id
  error.value = ''
  try {
    const detail = await api<MeetingSeriesDetail>(`/api/meeting-series/${series.id}`)
    await api(`/api/meeting-series/${series.id}`, {
      method: 'PUT',
      body: JSON.stringify({ expected_version: detail.version, status: 'archived' }),
    })
    emit('changed')
  } catch (reason) {
    error.value = errorMessage(reason, '系列归档失败')
  } finally {
    archivingId.value = ''
  }
}

function openOccurrence(series: SeriesRow) {
  if (!props.canContribute) return
  occurrenceSeries.value = series
  occurrenceTitle.value = `${series.title} · 临时会议`
  occurrenceStart.value = ''
  occurrenceEnd.value = ''
  occurrenceError.value = ''
}

async function createOccurrence() {
  if (!props.canContribute || !occurrenceSeries.value || !occurrenceTitle.value.trim() || !occurrenceStart.value || !occurrenceEnd.value || occurrenceSaving.value) return
  occurrenceSaving.value = true
  occurrenceError.value = ''
  try {
    await api<{ id: string }>(`/api/meeting-series/${occurrenceSeries.value.id}/occurrences`, {
      method: 'POST',
      body: JSON.stringify({
        title: occurrenceTitle.value.trim(),
        scheduled_start: new Date(occurrenceStart.value).toISOString(),
        scheduled_end: new Date(occurrenceEnd.value).toISOString(),
      }),
    })
    occurrenceSeries.value = null
    await load()
  } catch (reason) {
    occurrenceError.value = errorMessage(reason, '临时会议添加失败')
  } finally {
    occurrenceSaving.value = false
  }
}

watch(() => props.tab, () => void load())
onMounted(load)
</script>

<template>
  <section class="workspace-section tab-content project-record-tabs">
    <template v-if="tab === 'meetings'">
      <header class="section-heading">
        <h2>会议与系列</h2>
        <div v-if="canContribute" class="row-actions">
          <button class="button button-primary" @click="emit('create', 'meeting')">添加会议</button>
          <button class="button button-quiet" @click="emit('create', 'series')">添加系列</button>
        </div>
      </header>
      <div v-if="project.series_summaries.length" class="project-dashboard-list">
        <div v-for="series in project.series_summaries as SeriesRow[]" :key="series.id" class="compact-row series-row">
          <RouterLink :to="`/meetings?series_id=${series.id}`"><strong>{{ series.title }}</strong><span>{{ series.recurrence_description || series.status }}</span></RouterLink>
          <div v-if="canContribute" class="row-actions">
            <button class="button button-quiet" type="button" :aria-label="`编辑系列“${series.title}”`" @click="openSeriesEdit(series)">编辑</button>
            <n-popconfirm positive-text="确认" negative-text="取消" @positive-click="archiveSeries(series)">
              <template #trigger>
                <button class="button button-quiet" type="button" :aria-label="`归档系列“${series.title}”`" :disabled="archivingId === series.id">归档</button>
              </template>
              确定归档系列“{{ series.title }}”吗？
            </n-popconfirm>
            <button class="button button-quiet" type="button" :aria-label="`临时添加会议“${series.title}”`" @click="openOccurrence(series)">临时添加会议</button>
          </div>
        </div>
      </div>
      <p v-if="loading" class="muted">正在加载会议…</p>
      <div class="project-record-list">
        <RouterLink v-for="item in rows as MeetingRow[]" :key="item.id" class="project-record-row" :to="`/meetings/${item.id}`"><strong>{{ item.title }}</strong><span>{{ formatDateTime(item.scheduled_start) }} · <StatusPill :status="item.status" kind="meeting" /></span></RouterLink>
      </div>
    </template>

    <template v-else-if="tab === 'actions'">
      <header class="section-heading"><h2>项目行动项</h2><button v-if="canContribute" class="button button-primary" @click="emit('create', 'action')">添加行动项</button></header>
      <p v-if="loading" class="muted">正在加载行动项…</p>
      <div class="project-record-list action-list">
        <div v-for="item in rows as ProjectActionSummary[]" :key="item.id" class="project-record-row action-row">
          <div class="action-row-main">
            <strong>{{ item.content }}</strong>
            <span><StatusPill :status="item.status" kind="action" /> · {{ ownerName(item.owner_user_id) }} · {{ item.due_date ?? '未设期限' }} · {{ priorityLabel(item.priority) }}</span>
            <span v-if="item.completed_at" class="muted">完成于 {{ formatDateTime(item.completed_at) }}</span>
          </div>
          <div v-if="canContribute && !item.is_derived" class="row-actions">
            <button class="button button-quiet" type="button" :aria-label="`编辑行动项“${item.content}”`" :disabled="actionBusy === item.id" @click="openActionEdit(item)">编辑</button>
            <button v-if="item.status === 'open'" class="button button-primary" type="button" :aria-label="`开始行动项“${item.content}”`" :disabled="actionBusy === item.id" @click="transitionAction(item, 'in_progress')">开始</button>
            <button v-if="item.status === 'in_progress'" class="button button-primary" type="button" :aria-label="`完成行动项“${item.content}”`" :disabled="actionBusy === item.id" @click="transitionAction(item, 'done')">完成</button>
            <n-popconfirm v-if="item.status === 'open' || item.status === 'in_progress'" positive-text="确认" negative-text="取消" @positive-click="transitionAction(item, 'canceled')">
              <template #trigger>
                <button class="button button-quiet" type="button" :aria-label="`取消行动项“${item.content}”`" :disabled="actionBusy === item.id">取消</button>
              </template>
              确定取消行动项“{{ item.content }}”吗？
            </n-popconfirm>
          </div>
        </div>
      </div>
      <p v-if="!loading && !rows.length" class="muted">当前没有行动项。</p>
    </template>

    <template v-else-if="tab === 'decisions'">
      <header class="section-heading"><h2>项目决策</h2><button v-if="canContribute" class="button button-primary" @click="emit('create', 'decision')">添加决策</button></header>
      <p v-if="loading" class="muted">正在加载决策…</p>
      <div class="project-record-list">
        <div v-for="item in rows as Decision[]" :key="item.id" class="project-record-row decision-row">
          <button type="button" class="decision-open" :aria-label="`查看决策“${item.title}”`" @click="openDecision(item)">
            <strong>{{ item.title }}</strong>
            <span><StatusPill :status="item.status" kind="decision" /></span>
          </button>
          <RouterLink v-if="item.meeting_id" class="decision-source" :to="`/meetings/${item.meeting_id}`">来源会议</RouterLink>
        </div>
      </div>
      <p v-if="!loading && !rows.length" class="muted">尚未形成项目决策。</p>
    </template>

    <template v-else>
      <header class="section-heading"><h2>项目文件</h2></header>
      <AttachmentPanel target-type="project" :target-id="project.id" :attachments="project.attachments" :can-contribute="canContribute" @uploaded="emit('uploaded', $event)" @deleted="emit('deleted', $event)" />
    </template>

    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

    <SeriesEditDrawer
      :show="Boolean(editSeries)"
      mode="edit"
      :project-id="project.id"
      :series-id="editSeries?.id"
      :members="memberRefs()"
      @close="editSeries = null"
      @saved="seriesSaved"
    />

    <ActionEditDrawer
      :show="Boolean(editAction)"
      :action="editAction"
      :members="memberRefs()"
      @close="editAction = null"
      @saved="actionSaved"
    />

    <DecisionDetailDrawer
      :show="Boolean(decisionTarget)"
      :decision="decisionTarget"
      :members="memberRefs()"
      :user-names="userNames"
      :can-contribute="canContribute"
      @close="decisionTarget = null"
      @saved="decisionSaved"
    />

    <NDrawer
      :show="Boolean(occurrenceSeries)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!occurrenceSaving"
      @update:show="(value: boolean) => { if (!value) occurrenceSeries = null }"
    >
      <NDrawerContent :title="`临时添加 · ${occurrenceSeries?.title ?? ''}`" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem label="会议标题">
            <NInput v-model:value="occurrenceTitle" :input-props="{ 'aria-label': '临时会议标题' }" />
          </NFormItem>
          <NFormItem label="开始时间">
            <input v-model="occurrenceStart" class="native-datetime-input" type="datetime-local" aria-label="临时会议开始时间" />
          </NFormItem>
          <NFormItem label="结束时间">
            <input v-model="occurrenceEnd" class="native-datetime-input" type="datetime-local" aria-label="临时会议结束时间" />
          </NFormItem>
        </NForm>
        <p v-if="occurrenceError" class="notice notice-error" role="alert">{{ occurrenceError }}</p>
        <template #footer>
          <NButton quaternary :disabled="occurrenceSaving" @click="occurrenceSeries = null">取消</NButton>
          <NButton type="primary" :loading="occurrenceSaving" :disabled="occurrenceSaving" @click="createOccurrence">添加临时会议</NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>
