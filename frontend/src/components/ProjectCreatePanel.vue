<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import { session } from '../auth/session'
import type { RecurrenceFrequency } from '../domain/meetings'
import type { ProjectDetail } from '../domain/projects'
import { errorMessage } from '../utils/errors'
import { priorityLabel } from '../utils/labels'

type Kind = 'series' | 'decision' | 'action'
const props = defineProps<{ show: boolean; kind: Kind; project: ProjectDetail }>()
const emit = defineEmits<{ close: []; created: [kind: Kind, entity: Record<string, unknown>] }>()

const title = ref('')
const content = ref('')
const rationale = ref('')
const reviewerIds = ref<string[]>([])
const ownerUserId = ref<string | null>(null)
const dueDate = ref('')
const priority = ref('normal')
const saving = ref(false)
const error = ref('')

const recurrenceFrequency = ref<RecurrenceFrequency | ''>('weekly')
const recurrenceInterval = ref(1)
const recurrenceWeekday = ref(0)
const recurrenceMonthDay = ref(1)
const recurrenceMonth = ref(1)
const recurrenceLocalTime = ref('09:00')
const recurrenceTimezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
const recurrenceAnchorDate = ref(todayLocalDate())
const defaultDurationMinutes = ref(60)

const drawerTitle = computed(() => ({ series: '添加系列', decision: '添加决策', action: '添加行动项' }[props.kind]))
const memberOptions = computed(() => props.project.memberships.map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const priorityOptions = (['low', 'normal', 'high', 'urgent'] as const)
  .map((value) => ({ label: priorityLabel(value), value }))
const canSubmit = computed(() => {
  if (props.kind === 'action') return Boolean(content.value.trim())
  return Boolean(title.value.trim())
})
const label = computed(() => ({ series: '系列', decision: '决策', action: '行动项' }[props.kind]))
const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const recurrenceDescription = computed(() => {
  const prefix = recurrenceInterval.value === 1 ? '每' : `每 ${recurrenceInterval.value}`
  if (recurrenceFrequency.value === 'daily') return `${prefix} 天 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'weekly') return `${prefix} 周${weekdayLabels[recurrenceWeekday.value]} ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'monthly') return `${prefix} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  if (recurrenceFrequency.value === 'yearly') return `${prefix} 年 ${recurrenceMonth.value} 月 ${recurrenceMonthDay.value} 日 ${recurrenceLocalTime.value}（${recurrenceTimezone.value}）`
  return '仅手动临时添加会议'
})

function todayLocalDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function resetForm() {
  title.value = ''
  content.value = ''
  rationale.value = ''
  reviewerIds.value = []
  ownerUserId.value = null
  dueDate.value = ''
  priority.value = 'normal'
  error.value = ''
  recurrenceFrequency.value = 'weekly'
  recurrenceInterval.value = 1
  recurrenceWeekday.value = 0
  recurrenceMonthDay.value = 1
  recurrenceMonth.value = 1
  recurrenceLocalTime.value = '09:00'
  recurrenceTimezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  recurrenceAnchorDate.value = todayLocalDate()
  defaultDurationMinutes.value = 60
}

watch(() => [props.show, props.kind], () => {
  if (props.show) resetForm()
}, { immediate: true })

function close() {
  if (saving.value) return
  emit('close')
}

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
  if (saving.value || !canSubmit.value) return
  saving.value = true
  error.value = ''
  try {
    const base = `/api/projects/${props.project.id}`
    let entity: Record<string, unknown>
    if (props.kind === 'decision') {
      entity = await api(`${base}/decisions`, {
        method: 'POST',
        body: JSON.stringify({
          title: title.value.trim(),
          decision_markdown: content.value.trim() || title.value.trim(),
          rationale_markdown: rationale.value,
          reviewer_ids: reviewerIds.value,
        }),
      }) as Record<string, unknown>
    } else if (props.kind === 'action') {
      entity = await api(`${base}/actions`, {
        method: 'POST',
        body: JSON.stringify({
          project_id: props.project.id,
          content: content.value.trim(),
          owner_user_id: ownerUserId.value || null,
          due_date: dueDate.value || null,
          priority: priority.value,
        }),
      }) as Record<string, unknown>
    } else {
      entity = await api(`${base}/meeting-series`, {
        method: 'POST',
        body: JSON.stringify(seriesPayload()),
      }) as Record<string, unknown>
    }
    emit('created', props.kind, entity)
  } catch (reason) {
    error.value = errorMessage(reason, `${label.value}创建失败`)
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
      <NForm v-if="kind !== 'series'" label-placement="top" :show-require-mark="false">
        <template v-if="kind === 'decision'">
          <NFormItem label="决策标题">
            <NInput v-model:value="title" :input-props="{ 'aria-label': '决策标题' }" placeholder="例如：采用项目工作区方案" />
          </NFormItem>
          <NFormItem label="决策内容">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 4 }" :input-props="{ 'aria-label': '决策内容' }" />
          </NFormItem>
          <p class="form-hint">内容为空时以标题作为决策内容。</p>
          <NFormItem label="决策理由">
            <NInput v-model:value="rationale" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '决策理由' }" />
          </NFormItem>
          <NFormItem label="评审人">
            <NSelect
              v-model:value="reviewerIds"
              class="project-decision-reviewer-select"
              :options="memberOptions"
              :virtual-scroll="false"
              multiple
              placeholder="选择评审人"
            />
          </NFormItem>
        </template>
        <template v-else>
          <NFormItem label="行动项内容">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '行动项内容' }" placeholder="要完成什么？" />
          </NFormItem>
          <NFormItem label="负责人">
            <NSelect
              v-model:value="ownerUserId"
              class="project-action-owner-select"
              :options="memberOptions"
              :virtual-scroll="false"
              clearable
              placeholder="选择负责人"
            />
          </NFormItem>
          <NFormItem label="截止日期">
            <input v-model="dueDate" class="native-date-input" type="date" aria-label="截止日期" />
          </NFormItem>
          <NFormItem label="优先级">
            <NSelect v-model:value="priority" class="project-action-priority-select" :options="priorityOptions" :virtual-scroll="false" />
          </NFormItem>
        </template>
      </NForm>
      <form v-else class="project-series-form" @submit.prevent="save">
        <label>系列标题<input v-model.trim="title" required /></label>
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
        <label>说明<textarea v-model="content" rows="5" /></label>
        <p class="form-hint">{{ recurrenceDescription }}</p>
      </form>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">取消</NButton>
        <NButton type="primary" :loading="saving" :disabled="saving || !canSubmit" @click="save">{{ drawerTitle }}</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
