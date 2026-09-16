<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NInputNumber, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { AgendaType, MeetingSeriesDetail, RecurrenceFrequency } from '../domain/meetings'
import { errorMessage } from '../utils/errors'
import MeetingParticipantEditor, { type ParticipantValue } from './MeetingParticipantEditor.vue'

type StandingRow = {
  title: string
  agenda_type: AgendaType
  default_owner_user_id: string | null
  default_duration_minutes: number | null
}

const props = defineProps<{
  show: boolean
  mode: 'create' | 'edit'
  projectId: string
  seriesId?: string
  members: UserRef[]
}>()
const emit = defineEmits<{ close: []; saved: [series: Record<string, unknown>] }>()

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const loaded = ref<MeetingSeriesDetail | null>(null)
const title = ref('')
const purpose = ref('')
const recurrenceFrequency = ref<RecurrenceFrequency | ''>('weekly')
const recurrenceInterval = ref(1)
const recurrenceWeekday = ref(0)
const recurrenceMonthDay = ref(1)
const recurrenceMonth = ref(1)
const recurrenceLocalTime = ref('09:00')
const recurrenceTimezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
const recurrenceAnchorDate = ref(todayLocalDate())
const defaultDurationMinutes = ref(60)
const defaultHostUserId = ref<string | null>(null)
const defaultRecorderUserId = ref<string | null>(null)
const participants = ref<ParticipantValue[]>([])
const standingItems = ref<StandingRow[]>([])

const drawerTitle = computed(() => (props.mode === 'create' ? '添加系列' : '编辑系列'))
const memberOptions = computed(() => props.members.map((member) => ({
  label: member.display_name || member.username,
  value: member.id,
})))
const frequencyOptions = [
  { label: '不设固定周期', value: '' },
  { label: '每天', value: 'daily' },
  { label: '每周', value: 'weekly' },
  { label: '每月', value: 'monthly' },
  { label: '每年', value: 'yearly' },
]
const weekdayOptions = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  .map((label, value) => ({ label, value }))
const agendaTypeOptions = [
  { label: '信息同步', value: 'information' },
  { label: '讨论', value: 'discussion' },
  { label: '决策', value: 'decision' },
]

const recurrenceDescription = computed(() => {
  const interval = recurrenceInterval.value
  const prefix = interval === 1 ? '每' : `每 ${interval}`
  if (recurrenceFrequency.value === 'daily') return `${prefix} 天 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'weekly') return `${prefix} 周${weekdayOptions[recurrenceWeekday.value]?.label ?? ''} ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'monthly') return `${prefix} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'yearly') return `${prefix} 年 ${recurrenceMonth.value} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  return '仅手动临时添加会议'
})

function todayLocalDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function resetForm() {
  loaded.value = null
  error.value = ''
  title.value = ''
  purpose.value = ''
  recurrenceFrequency.value = 'weekly'
  recurrenceInterval.value = 1
  recurrenceWeekday.value = 0
  recurrenceMonthDay.value = 1
  recurrenceMonth.value = 1
  recurrenceLocalTime.value = '09:00'
  recurrenceTimezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  recurrenceAnchorDate.value = todayLocalDate()
  defaultDurationMinutes.value = 60
  defaultHostUserId.value = session.user?.id ?? null
  defaultRecorderUserId.value = session.user?.id ?? null
  participants.value = session.user ? [{ user_id: session.user.id, participation_role: 'host' }] : []
  standingItems.value = []
}

function applyDetail(detail: MeetingSeriesDetail) {
  loaded.value = detail
  title.value = detail.title
  purpose.value = detail.purpose_markdown
  const recurrence = detail.recurrence
  recurrenceFrequency.value = recurrence.frequency ?? ''
  recurrenceInterval.value = recurrence.interval || 1
  recurrenceWeekday.value = recurrence.weekday ?? 0
  recurrenceMonthDay.value = recurrence.month_day ?? 1
  recurrenceMonth.value = recurrence.month ?? 1
  recurrenceLocalTime.value = (recurrence.local_time ?? '09:00').slice(0, 5)
  recurrenceTimezone.value = recurrence.timezone ?? (Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  recurrenceAnchorDate.value = recurrence.anchor_date ?? todayLocalDate()
  defaultDurationMinutes.value = detail.default_duration_minutes
  defaultHostUserId.value = detail.default_host?.id ?? null
  defaultRecorderUserId.value = detail.default_recorder?.id ?? null
  participants.value = detail.participants.map((row) => ({
    user_id: row.user.id,
    participation_role: row.participation_role,
  }))
  standingItems.value = detail.standing_items.map((row) => ({
    title: row.title,
    agenda_type: row.agenda_type,
    default_owner_user_id: row.default_owner?.id ?? null,
    default_duration_minutes: row.default_duration_minutes,
  }))
}

async function loadDetail() {
  if (props.mode !== 'edit' || !props.seriesId) return
  loading.value = true
  error.value = ''
  try {
    applyDetail(await api<MeetingSeriesDetail>(`/api/meeting-series/${props.seriesId}`))
  } catch (reason) {
    error.value = errorMessage(reason, '系列加载失败')
  } finally {
    loading.value = false
  }
}

watch(() => [props.show, props.mode, props.seriesId], () => {
  if (!props.show) return
  resetForm()
  void loadDetail()
}, { immediate: true })

/**
 * The recurrence group is all-or-nothing on the backend: clearing the frequency must send the
 * remaining group fields as explicit `null` so no stale weekday/month/time values survive.
 */
function recurrencePayload(): Record<string, unknown> {
  const frequency = recurrenceFrequency.value || null
  if (!frequency) {
    return {
      recurrence_frequency: null,
      recurrence_interval: recurrenceInterval.value,
      recurrence_weekday: null,
      recurrence_month_day: null,
      recurrence_month: null,
      recurrence_local_time: null,
      recurrence_timezone: null,
      recurrence_anchor_date: null,
    }
  }
  return {
    recurrence_frequency: frequency,
    recurrence_interval: recurrenceInterval.value,
    recurrence_weekday: frequency === 'weekly' ? recurrenceWeekday.value : null,
    recurrence_month_day: frequency === 'monthly' || frequency === 'yearly' ? recurrenceMonthDay.value : null,
    recurrence_month: frequency === 'yearly' ? recurrenceMonth.value : null,
    recurrence_local_time: `${recurrenceLocalTime.value}:00`,
    recurrence_timezone: recurrenceTimezone.value.trim(),
    recurrence_anchor_date: recurrenceAnchorDate.value,
  }
}

function standingItemsPayload() {
  return standingItems.value
    .filter((row) => row.title.trim())
    .map((row) => ({
      title: row.title.trim(),
      agenda_type: row.agenda_type,
      default_owner_user_id: row.default_owner_user_id,
      default_duration_minutes: row.default_duration_minutes,
    }))
}

function createPayload(): Record<string, unknown> {
  return {
    title: title.value.trim(),
    purpose_markdown: purpose.value,
    recurrence_description: recurrenceDescription.value,
    default_duration_minutes: defaultDurationMinutes.value,
    default_host_user_id: defaultHostUserId.value,
    default_recorder_user_id: defaultRecorderUserId.value,
    participants: participants.value.filter((row) => row.user_id),
    standing_items: standingItemsPayload(),
    ...recurrencePayload(),
  }
}

/** Only send fields this drawer owns and that actually changed; arrays are compared as a whole. */
function editPayload(detail: MeetingSeriesDetail): Record<string, unknown> {
  const payload: Record<string, unknown> = { expected_version: detail.version }
  if (title.value.trim() !== detail.title) payload.title = title.value.trim()
  if (purpose.value !== detail.purpose_markdown) payload.purpose_markdown = purpose.value
  const originalRecurrence = {
    recurrence_frequency: detail.recurrence.frequency ?? null,
    recurrence_interval: detail.recurrence.interval,
    recurrence_weekday: detail.recurrence.weekday,
    recurrence_month_day: detail.recurrence.month_day,
    recurrence_month: detail.recurrence.month,
    recurrence_local_time: detail.recurrence.local_time,
    recurrence_timezone: detail.recurrence.timezone,
    recurrence_anchor_date: detail.recurrence.anchor_date,
  }
  const nextRecurrence = recurrencePayload()
  const recurrenceChanged = Object.keys(originalRecurrence)
    .some((key) => originalRecurrence[key as keyof typeof originalRecurrence] !== nextRecurrence[key])
  if (recurrenceChanged) {
    payload.recurrence_description = recurrenceDescription.value
    Object.assign(payload, nextRecurrence)
  }
  if (defaultDurationMinutes.value !== detail.default_duration_minutes) {
    payload.default_duration_minutes = defaultDurationMinutes.value
  }
  if (defaultHostUserId.value !== (detail.default_host?.id ?? null)) {
    payload.default_host_user_id = defaultHostUserId.value
  }
  if (defaultRecorderUserId.value !== (detail.default_recorder?.id ?? null)) {
    payload.default_recorder_user_id = defaultRecorderUserId.value
  }
  const nextParticipants = participants.value.filter((row) => row.user_id)
  const originalParticipants = detail.participants.map((row) => ({
    user_id: row.user.id,
    participation_role: row.participation_role,
  }))
  if (JSON.stringify(nextParticipants) !== JSON.stringify(originalParticipants)) {
    payload.participants = nextParticipants
  }
  const nextStanding = standingItemsPayload()
  const originalStanding = detail.standing_items.map((row) => ({
    title: row.title,
    agenda_type: row.agenda_type,
    default_owner_user_id: row.default_owner?.id ?? null,
    default_duration_minutes: row.default_duration_minutes,
  }))
  if (JSON.stringify(nextStanding) !== JSON.stringify(originalStanding)) {
    payload.standing_items = nextStanding
  }
  return payload
}

function addStandingItem() {
  standingItems.value.push({
    title: '',
    agenda_type: 'discussion',
    default_owner_user_id: null,
    default_duration_minutes: null,
  })
}

function removeStandingItem(index: number) {
  standingItems.value.splice(index, 1)
}

function close() {
  if (saving.value) return
  emit('close')
}

async function save() {
  if (saving.value || !title.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    let result: Record<string, unknown>
    if (props.mode === 'create') {
      result = await api(`/api/projects/${props.projectId}/meeting-series`, {
        method: 'POST',
        body: JSON.stringify(createPayload()),
      }) as Record<string, unknown>
    } else {
      const detail = loaded.value
      if (!detail) return
      result = await api(`/api/meeting-series/${detail.id}`, {
        method: 'PUT',
        body: JSON.stringify(editPayload(detail)),
      }) as Record<string, unknown>
    }
    emit('saved', result)
  } catch (reason) {
    error.value = errorMessage(reason, '系列保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <NDrawer
    :show="show"
    placement="right"
    :width="'min(560px, 100vw)'"
    :mask-closable="!saving"
    @update:show="(value: boolean) => { if (!value) close() }"
  >
    <NDrawerContent :title="drawerTitle" closable>
      <p v-if="loading" class="muted">正在加载系列详情…</p>
      <NForm v-else label-placement="top" :show-require-mark="false">
        <NFormItem label="系列标题">
          <NInput v-model:value="title" :input-props="{ 'aria-label': '系列标题' }" />
        </NFormItem>
        <NFormItem label="系列说明">
          <NInput v-model:value="purpose" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '系列说明' }" />
        </NFormItem>
        <NFormItem label="重复频率">
          <NSelect
            v-model:value="recurrenceFrequency"
            class="series-recurrence-frequency"
            :options="frequencyOptions"
            :virtual-scroll="false"
          />
        </NFormItem>
        <template v-if="recurrenceFrequency">
          <NFormItem label="重复间隔">
            <NInputNumber v-model:value="recurrenceInterval" :min="1" :max="365" :input-props="{ 'aria-label': '重复间隔' }" />
          </NFormItem>
          <NFormItem v-if="recurrenceFrequency === 'weekly'" label="每周星期">
            <NSelect
              v-model:value="recurrenceWeekday"
              class="series-recurrence-weekday"
              :options="weekdayOptions"
              :virtual-scroll="false"
            />
          </NFormItem>
          <NFormItem v-if="recurrenceFrequency === 'monthly' || recurrenceFrequency === 'yearly'" label="每月日期">
            <NInputNumber v-model:value="recurrenceMonthDay" :min="1" :max="31" :input-props="{ 'aria-label': '每月日期' }" />
          </NFormItem>
          <NFormItem v-if="recurrenceFrequency === 'yearly'" label="月份">
            <NInputNumber v-model:value="recurrenceMonth" :min="1" :max="12" :input-props="{ 'aria-label': '月份' }" />
          </NFormItem>
          <NFormItem label="开始时间">
            <input v-model="recurrenceLocalTime" class="native-time-input" type="time" aria-label="开始时间" />
          </NFormItem>
          <NFormItem label="时区">
            <NInput v-model:value="recurrenceTimezone" :input-props="{ 'aria-label': '时区' }" />
          </NFormItem>
          <NFormItem label="起始日期">
            <input v-model="recurrenceAnchorDate" class="native-date-input" type="date" aria-label="起始日期" />
          </NFormItem>
          <p class="form-hint">{{ recurrenceDescription }}</p>
        </template>
        <NFormItem label="默认会议时长（分钟）">
          <NInputNumber v-model:value="defaultDurationMinutes" :min="1" :max="1440" :input-props="{ 'aria-label': '默认会议时长' }" />
        </NFormItem>
        <NFormItem label="默认主持">
          <NSelect
            v-model:value="defaultHostUserId"
            class="series-default-host"
            :options="memberOptions"
            :virtual-scroll="false"
            clearable
            placeholder="选择默认主持"
          />
        </NFormItem>
        <NFormItem label="默认记录">
          <NSelect
            v-model:value="defaultRecorderUserId"
            class="series-default-recorder"
            :options="memberOptions"
            :virtual-scroll="false"
            clearable
            placeholder="选择默认记录"
          />
        </NFormItem>
        <NFormItem label="参与人">
          <MeetingParticipantEditor v-model="participants" :member-options="members" />
        </NFormItem>
      </NForm>

      <section v-if="!loading" class="series-standing-items">
        <header class="section-heading">
          <h3>常设议题</h3>
          <NButton size="small" @click="addStandingItem">添加常设议题</NButton>
        </header>
        <div v-for="(row, index) in standingItems" :key="index" class="standing-item-row">
          <NInput v-model:value="row.title" :input-props="{ 'aria-label': '常设议题标题' }" placeholder="议题标题" />
          <NSelect
            v-model:value="row.agenda_type"
            class="standing-agenda-type"
            :options="agendaTypeOptions"
            :virtual-scroll="false"
          />
          <NSelect
            v-model:value="row.default_owner_user_id"
            class="standing-agenda-owner"
            :options="memberOptions"
            :virtual-scroll="false"
            clearable
            placeholder="默认负责人"
          />
          <NInputNumber
            v-model:value="row.default_duration_minutes"
            :min="1"
            :max="1440"
            :input-props="{ 'aria-label': '默认时长' }"
            placeholder="默认时长"
          />
          <NButton quaternary aria-label="移除常设议题" @click="removeStandingItem(index)">移除</NButton>
        </div>
        <p v-if="!standingItems.length" class="muted">尚未配置常设议题。</p>
      </section>

      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">取消</NButton>
        <NButton
          type="primary"
          :loading="saving"
          :disabled="saving || loading || (mode === 'edit' && !loaded) || !title.trim()"
          @click="save"
        >
          保存系列
        </NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
