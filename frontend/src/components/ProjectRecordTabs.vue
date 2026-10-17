<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopconfirm } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import StatusPill from './StatusPill.vue'
import { useI18n } from '../i18n'
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

const { tr } = useI18n()

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
    error.value = errorMessage(reason, tr('记录加载失败', 'Failed to load records'))
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
  if (!userId) return tr('未指派', 'Unassigned')
  const row = props.project.memberships.find((item) => item.user.id === userId)
  return row?.user.display_name || row?.user.username || tr('未指派', 'Unassigned')
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
    error.value = errorMessage(reason, tr('行动项更新失败', 'Failed to update action item'))
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
    error.value = errorMessage(reason, tr('系列归档失败', 'Failed to archive series'))
  } finally {
    archivingId.value = ''
  }
}

function openOccurrence(series: SeriesRow) {
  if (!props.canContribute) return
  occurrenceSeries.value = series
  occurrenceTitle.value = `${series.title} · ${tr('临时会议', 'Ad-hoc Meeting')}`
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
    occurrenceError.value = errorMessage(reason, tr('临时会议添加失败', 'Failed to add ad-hoc meeting'))
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
        <h2>{{ tr('会议与系列', 'Meetings & Series') }}</h2>
        <div v-if="canContribute" class="row-actions">
          <button class="button button-primary" @click="emit('create', 'meeting')">{{ tr('添加会议', 'Add Meeting') }}</button>
          <button class="button button-quiet" @click="emit('create', 'series')">{{ tr('添加系列', 'Add Series') }}</button>
        </div>
      </header>
      <div v-if="project.series_summaries.length" class="project-dashboard-list">
        <div v-for="series in project.series_summaries as SeriesRow[]" :key="series.id" class="compact-row series-row">
          <RouterLink :to="`/meetings?series_id=${series.id}`"><strong>{{ series.title }}</strong><span>{{ series.recurrence_description || series.status }}</span></RouterLink>
          <div v-if="canContribute" class="row-actions">
            <button class="button button-quiet" type="button" :aria-label="tr(`编辑系列“${series.title}”`, `Edit series &quot;${series.title}&quot;`)" @click="openSeriesEdit(series)">{{ tr('编辑', 'Edit') }}</button>
            <n-popconfirm :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="archiveSeries(series)">
              <template #trigger>
                <button class="button button-quiet" type="button" :aria-label="tr(`归档系列“${series.title}”`, `Archive series &quot;${series.title}&quot;`)" :disabled="archivingId === series.id">{{ tr('归档', 'Archive') }}</button>
              </template>
              {{ tr(`确定归档系列“${series.title}”吗？`, `Archive series "${series.title}"?`) }}
            </n-popconfirm>
            <button class="button button-quiet" type="button" :aria-label="tr(`临时添加会议“${series.title}”`, `Add ad-hoc meeting to &quot;${series.title}&quot;`)" @click="openOccurrence(series)">{{ tr('临时添加会议', 'Add Occurrence') }}</button>
          </div>
        </div>
      </div>
      <p v-if="loading" class="muted">{{ tr('正在加载会议…', 'Loading meetings…') }}</p>
      <div class="project-record-list">
        <RouterLink v-for="item in rows as MeetingRow[]" :key="item.id" class="project-record-row" :to="`/meetings/${item.id}`"><strong>{{ item.title }}</strong><span>{{ formatDateTime(item.scheduled_start) }} · <StatusPill :status="item.status" kind="meeting" /></span></RouterLink>
      </div>
    </template>

    <template v-else-if="tab === 'actions'">
      <header class="section-heading"><h2>{{ tr('项目行动项', 'Project Actions') }}</h2><button v-if="canContribute" class="button button-primary" @click="emit('create', 'action')">{{ tr('添加行动项', 'Add Action') }}</button></header>
      <p v-if="loading" class="muted">{{ tr('正在加载行动项…', 'Loading actions…') }}</p>
      <div class="project-record-list action-list">
        <div v-for="item in rows as ProjectActionSummary[]" :key="item.id" class="project-record-row action-row">
          <div class="action-row-main">
            <strong>{{ item.content }}</strong>
            <span><StatusPill :status="item.status" kind="action" /> · {{ ownerName(item.owner_user_id) }} · {{ item.due_date ?? tr('未设期限', 'No due date') }} · {{ priorityLabel(item.priority) }}</span>
            <span v-if="item.completed_at" class="muted">{{ tr('完成于 ', 'Completed ') }}{{ formatDateTime(item.completed_at) }}</span>
          </div>
          <div v-if="canContribute && !item.is_derived" class="row-actions">
            <button class="button button-quiet" type="button" :aria-label="tr(`编辑行动项“${item.content}”`, `Edit action &quot;${item.content}&quot;`)" :disabled="actionBusy === item.id" @click="openActionEdit(item)">{{ tr('编辑', 'Edit') }}</button>
            <button v-if="item.status === 'open'" class="button button-primary" type="button" :aria-label="tr(`开始行动项“${item.content}”`, `Start action &quot;${item.content}&quot;`)" :disabled="actionBusy === item.id" @click="transitionAction(item, 'in_progress')">{{ tr('开始', 'Start') }}</button>
            <button v-if="item.status === 'in_progress'" class="button button-primary" type="button" :aria-label="tr(`完成行动项“${item.content}”`, `Complete action &quot;${item.content}&quot;`)" :disabled="actionBusy === item.id" @click="transitionAction(item, 'done')">{{ tr('完成', 'Complete') }}</button>
            <n-popconfirm v-if="item.status === 'open' || item.status === 'in_progress'" :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="transitionAction(item, 'canceled')">
              <template #trigger>
                <button class="button button-quiet" type="button" :aria-label="tr(`取消行动项“${item.content}”`, `Cancel action &quot;${item.content}&quot;`)" :disabled="actionBusy === item.id">{{ tr('取消', 'Cancel') }}</button>
              </template>
              {{ tr(`确定取消行动项“${item.content}”吗？`, `Cancel action item "${item.content}"?`) }}
            </n-popconfirm>
          </div>
        </div>
      </div>
      <p v-if="!loading && !rows.length" class="muted">{{ tr('当前没有行动项。', 'No action items.') }}</p>
    </template>

    <template v-else-if="tab === 'decisions'">
      <header class="section-heading"><h2>{{ tr('项目决策', 'Project Decisions') }}</h2><button v-if="canContribute" class="button button-primary" @click="emit('create', 'decision')">{{ tr('添加决策', 'Add Decision') }}</button></header>
      <p v-if="loading" class="muted">{{ tr('正在加载决策…', 'Loading decisions…') }}</p>
      <div class="project-record-list">
        <div v-for="item in rows as Decision[]" :key="item.id" class="project-record-row decision-row">
          <button type="button" class="decision-open" :aria-label="tr(`查看决策“${item.title}”`, `View decision &quot;${item.title}&quot;`)" @click="openDecision(item)">
            <strong>{{ item.title }}</strong>
            <span><StatusPill :status="item.status" kind="decision" /></span>
          </button>
          <RouterLink v-if="item.meeting_id" class="decision-source" :to="`/meetings/${item.meeting_id}`">{{ tr('来源会议', 'Source Meeting') }}</RouterLink>
        </div>
      </div>
      <p v-if="!loading && !rows.length" class="muted">{{ tr('尚未形成项目决策。', 'No project decisions recorded yet.') }}</p>
    </template>

    <template v-else>
      <header class="section-heading"><h2>{{ tr('项目文件', 'Project Files') }}</h2></header>
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
      <NDrawerContent :title="`${tr('临时添加', 'Add Occurrence')} · ${occurrenceSeries?.title ?? ''}`" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem :label="tr('会议标题', 'Meeting Title')">
            <NInput v-model:value="occurrenceTitle" :input-props="{ 'aria-label': tr('临时会议标题', 'Ad-hoc meeting title') }" />
          </NFormItem>
          <NFormItem :label="tr('开始时间', 'Start Time')">
            <input v-model="occurrenceStart" class="native-datetime-input" type="datetime-local" :aria-label="tr('临时会议开始时间', 'Ad-hoc meeting start time')" />
          </NFormItem>
          <NFormItem :label="tr('结束时间', 'End Time')">
            <input v-model="occurrenceEnd" class="native-datetime-input" type="datetime-local" :aria-label="tr('临时会议结束时间', 'Ad-hoc meeting end time')" />
          </NFormItem>
        </NForm>
        <p v-if="occurrenceError" class="notice notice-error" role="alert">{{ occurrenceError }}</p>
        <template #footer>
          <NButton quaternary :disabled="occurrenceSaving" @click="occurrenceSeries = null">{{ tr('取消', 'Cancel') }}</NButton>
          <NButton type="primary" :loading="occurrenceSaving" :disabled="occurrenceSaving" @click="createOccurrence">{{ tr('添加临时会议', 'Add Occurrence') }}</NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>
