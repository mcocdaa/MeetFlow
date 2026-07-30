<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api/client'
import { session } from '../auth/session'
import type { ProjectDetail } from '../domain/projects'

type Kind = 'meeting' | 'series' | 'decision' | 'action'
const props = defineProps<{ kind: Kind; project: ProjectDetail }>()
const emit = defineEmits<{ close: []; created: [kind: Kind, entity: Record<string, unknown>] }>()
const title = ref('')
const content = ref('')
const start = ref('')
const end = ref('')
type RecurrenceFrequency = '' | 'daily' | 'weekly' | 'monthly' | 'yearly'
const recurrenceFrequency = ref<RecurrenceFrequency>('weekly')
const recurrenceInterval = ref(1)
const recurrenceWeekday = ref(0)
const recurrenceMonthDay = ref(1)
const recurrenceMonth = ref(1)
const recurrenceLocalTime = ref('09:00')
const recurrenceTimezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
const recurrenceAnchorDate = ref(new Date().toISOString().slice(0, 10))
const defaultDurationMinutes = ref(60)
const saving = ref(false)
const error = ref('')
const label = computed(() => ({ meeting: '添加会议', series: '添加系列', decision: '添加决策', action: '添加行动项' }[props.kind]))
const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const recurrenceDescription = computed(() => {
  const prefix = recurrenceInterval.value === 1 ? '每' : `每 ${recurrenceInterval.value}`
  if (recurrenceFrequency.value === 'daily') return `${prefix} 天 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'weekly') return `${prefix} 周${weekdayLabels[recurrenceWeekday.value]} ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'monthly') return `${prefix} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'yearly') return `${prefix} 年 ${recurrenceMonth.value} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  return '仅手动临时添加会议'
})

function seriesPayload() {
  const payload: Record<string, unknown> = {
    title: title.value.trim(),
    purpose_markdown: content.value,
    recurrence_description: recurrenceDescription.value,
    default_duration_minutes: defaultDurationMinutes.value,
    default_host_user_id: session.user?.id ?? null,
    default_recorder_user_id: session.user?.id ?? null,
    participants: session.user ? [{ user_id: session.user.id, participation_role: 'host' }] : [],
  }
  if (!recurrenceFrequency.value) return payload
  Object.assign(payload, {
    recurrence_frequency: recurrenceFrequency.value,
    recurrence_interval: recurrenceInterval.value,
    recurrence_local_time: `${recurrenceLocalTime.value}:00`,
    recurrence_timezone: recurrenceTimezone.value.trim(),
    recurrence_anchor_date: recurrenceAnchorDate.value,
  })
  if (recurrenceFrequency.value === 'weekly') payload.recurrence_weekday = recurrenceWeekday.value
  if (recurrenceFrequency.value === 'monthly' || recurrenceFrequency.value === 'yearly') payload.recurrence_month_day = recurrenceMonthDay.value
  if (recurrenceFrequency.value === 'yearly') payload.recurrence_month = recurrenceMonth.value
  return payload
}

async function save() {
  if (saving.value || !title.value.trim() || (props.kind === 'meeting' && (!start.value || !end.value)) || (props.kind === 'action' && !content.value.trim())) return
  saving.value = true; error.value = ''
  try {
    let entity: Record<string, unknown>
    if (props.kind === 'meeting') {
      entity = await api(`/api/projects/${props.project.id}/meetings`, { method: 'POST', body: JSON.stringify({ title: title.value.trim(), purpose_markdown: content.value, scheduled_start: new Date(start.value).toISOString(), scheduled_end: new Date(end.value).toISOString(), host_user_id: session.user?.id ?? null, recorder_user_id: session.user?.id ?? null, summary_markdown: '', raw_notes_markdown: '', participants: session.user ? [{ user_id: session.user.id, participation_role: 'host' }] : [] }) }) as Record<string, unknown>
    } else if (props.kind === 'series') {
      entity = await api(`/api/projects/${props.project.id}/meeting-series`, { method: 'POST', body: JSON.stringify(seriesPayload()) }) as Record<string, unknown>
    } else if (props.kind === 'decision') {
      entity = await api(`/api/projects/${props.project.id}/decisions`, { method: 'POST', body: JSON.stringify({ title: title.value.trim(), decision_markdown: content.value || title.value.trim(), rationale_markdown: '', reviewer_ids: [] }) }) as Record<string, unknown>
    } else {
      entity = await api(`/api/projects/${props.project.id}/actions`, { method: 'POST', body: JSON.stringify({ project_id: props.project.id, content: content.value.trim(), owner_user_id: null, due_date: null, priority: 'normal' }) }) as Record<string, unknown>
    }
    emit('created', props.kind, entity)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : `${label.value}失败` }
  finally { saving.value = false }
}
</script>

<template>
  <form class="project-create-panel" @submit.prevent="save">
    <label v-if="kind !== 'action'">{{ kind === 'decision' ? '决策标题' : kind === 'series' ? '系列标题' : '会议标题' }}<input v-model.trim="title" required /></label>
    <label v-if="kind === 'meeting'">开始时间<input v-model="start" type="datetime-local" required /></label>
    <label v-if="kind === 'meeting'">结束时间<input v-model="end" type="datetime-local" required /></label>
    <template v-if="kind === 'series'">
      <label>重复频率<select v-model="recurrenceFrequency"><option value="">不设固定周期</option><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option><option value="yearly">每年</option></select></label>
      <template v-if="recurrenceFrequency">
        <label>重复间隔<input v-model.number="recurrenceInterval" type="number" min="1" max="365" required /></label>
        <label v-if="recurrenceFrequency === 'weekly'">每周星期<select v-model.number="recurrenceWeekday"><option v-for="(weekday, index) in weekdayLabels" :key="weekday" :value="index">{{ weekday }}</option></select></label>
        <label v-if="recurrenceFrequency === 'monthly' || recurrenceFrequency === 'yearly'">每月日期<input v-model.number="recurrenceMonthDay" type="number" min="1" max="31" required /></label>
        <label v-if="recurrenceFrequency === 'yearly'">月份<input v-model.number="recurrenceMonth" type="number" min="1" max="12" required /></label>
        <label>开始时间<input v-model="recurrenceLocalTime" type="time" required /></label>
        <label>时区<input v-model.trim="recurrenceTimezone" list="meeting-timezones" required /><datalist id="meeting-timezones"><option value="Asia/Shanghai" /><option value="UTC" /><option value="America/Los_Angeles" /><option value="Europe/London" /></datalist></label>
        <label>起始日期<input v-model="recurrenceAnchorDate" type="date" required /></label>
      </template>
      <label>默认会议时长（分钟）<input v-model.number="defaultDurationMinutes" type="number" min="1" max="1440" required /></label>
      <p class="form-hint">{{ recurrenceDescription }}</p>
    </template>
    <label>{{ kind === 'action' ? '行动项内容' : kind === 'decision' ? '决策内容' : '说明' }}<textarea v-model="content" rows="5" :required="kind === 'action'" /></label>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div class="form-actions"><button type="button" class="button button-quiet" @click="emit('close')">取消</button><button class="button button-primary" :disabled="saving">{{ saving ? '保存中…' : label }}</button></div>
  </form>
</template>
