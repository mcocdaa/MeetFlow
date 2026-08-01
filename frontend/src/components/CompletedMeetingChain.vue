<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api/client'
import type { Meeting } from '../domain/meetings'
import AttachmentPanel from './AttachmentPanel.vue'
import MarkdownEditor from './MarkdownEditor.vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps<{ meeting: Meeting; canContribute: boolean }>()
const emit = defineEmits<{ reload: [] }>()
const amendmentOpen = ref(false)
const reason = ref('')
const content = ref('')
const saving = ref(false)
const error = ref('')

type SnapshotRecord = Record<string, unknown>
type SnapshotDecision = { id: string; title: string; decisionMarkdown: string; rationaleMarkdown: string; status: string }
type SnapshotAction = { id: string; content: string; priority: string; dueDate: string | null; status: string }
type SnapshotQuestion = { id: string; questionMarkdown: string; status: string }
type SnapshotOutcomeGroup = {
  id: string
  testId: string
  title: string
  status: string | null
  decisions: SnapshotDecision[]
  actions: SnapshotAction[]
  openQuestions: SnapshotQuestion[]
  notesMarkdown?: string
  estimatedMinutes?: number | null
  actualDurationSeconds?: number | null
}
type SnapshotAgenda = Required<Pick<SnapshotOutcomeGroup, 'notesMarkdown' | 'estimatedMinutes' | 'actualDurationSeconds'>> & SnapshotOutcomeGroup

function record(value: unknown): SnapshotRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as SnapshotRecord : {}
}

function records(value: unknown): SnapshotRecord[] {
  return Array.isArray(value) ? value.filter((item): item is SnapshotRecord => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : []
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function nullableText(value: unknown): string | null {
  const result = text(value)
  return result || null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function duration(seconds: number | null): string {
  if (seconds === null) return '—'
  const hours = Math.floor(seconds / 3600)
  const remainingSeconds = seconds % 3600
  const minutes = Math.floor(remainingSeconds / 60)
  const remainder = remainingSeconds % 60
  if (hours) return `${hours} 小时${minutes ? ` ${minutes} 分` : ''}${remainder ? ` ${remainder} 秒` : ''}`
  if (!minutes) return `${remainder} 秒`
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
}

function utcMilliseconds(value: string | null): number | null {
  if (!value) return null
  const timestamp = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`).getTime()
  return Number.isFinite(timestamp) ? timestamp : null
}

function decision(value: SnapshotRecord): SnapshotDecision {
  return { id: text(value.id), title: text(value.title), decisionMarkdown: text(value.decision_markdown), rationaleMarkdown: text(value.rationale_markdown), status: text(value.status) }
}

function action(value: SnapshotRecord): SnapshotAction {
  return { id: text(value.id), content: text(value.content), priority: text(value.priority), dueDate: nullableText(value.due_date), status: text(value.status) }
}

function question(value: SnapshotRecord): SnapshotQuestion {
  return { id: text(value.id), questionMarkdown: text(value.question_markdown), status: text(value.status) }
}

function group(source: SnapshotRecord, id: string, testId: string, title: string, status: string | null, decisionKey = 'decisions', actionKey = 'actions', questionKey = 'open_questions'): SnapshotOutcomeGroup {
  return {
    id,
    testId,
    title,
    status,
    decisions: records(source[decisionKey]).map(decision),
    actions: records(source[actionKey]).map(action),
    openQuestions: records(source[questionKey]).map(question),
  }
}

const snapshot = computed(() => record(props.meeting.current_snapshot?.snapshot_json ?? props.meeting.current_snapshot?.snapshot ?? {}))
const snapshotMeeting = computed(() => record(snapshot.value.meeting))
const actualMeetingDurationSeconds = computed(() => {
  const startedAt = nullableText(snapshotMeeting.value.started_at) ?? props.meeting.started_at ?? null
  const completedAt = nullableText(snapshotMeeting.value.completed_at) ?? props.meeting.completed_at ?? null
  const startMilliseconds = utcMilliseconds(startedAt)
  const completedMilliseconds = utcMilliseconds(completedAt)
  if (startMilliseconds === null || completedMilliseconds === null) return null
  return Math.max(0, Math.floor((completedMilliseconds - startMilliseconds) / 1000))
})
const snapshotAgenda = computed<SnapshotAgenda[]>(() => records(snapshot.value.agenda_items).map((item) => {
  const id = text(item.id)
  return {
    ...group(item, id, `completed-agenda-${id}`, text(item.title) || '未命名议题', nullableText(item.status)),
    notesMarkdown: text(item.notes_markdown),
    estimatedMinutes: nullableNumber(item.estimated_minutes),
    actualDurationSeconds: nullableNumber(item.actual_duration_seconds),
  }
}))
const meetingOutcomes = computed<SnapshotOutcomeGroup | null>(() => {
  const value = group(snapshot.value, 'meeting-outcomes', 'completed-meeting-outcomes', '会议级产出', null, 'meeting_decisions', 'meeting_actions', 'meeting_open_questions')
  return value.decisions.length || value.actions.length || value.openQuestions.length ? value : null
})
const outcomeGroups = computed(() => meetingOutcomes.value ? [...snapshotAgenda.value, meetingOutcomes.value] : snapshotAgenda.value)

async function addAmendment() {
  if (!props.canContribute || !reason.value.trim() || !content.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/meetings/${props.meeting.id}/amendments`, { method: 'POST', body: JSON.stringify({ reason: reason.value.trim(), content_markdown: content.value, expected_version: props.meeting.version }) })
    amendmentOpen.value = false
    reason.value = ''
    content.value = ''
    emit('reload')
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '更正保存失败' }
  finally { saving.value = false }
}

async function reopen() {
  if (!props.canContribute) return
  if (!window.confirm('重新打开后可继续修改议题，并在再次结束时生成新的历史快照。确定继续？')) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/meetings/${props.meeting.id}/reopen`, { method: 'POST', body: JSON.stringify({ expected_version: props.meeting.version }) })
    emit('reload')
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议重新打开失败' }
  finally { saving.value = false }
}
</script>

<template>
  <div class="completed-chain">
    <section class="workspace-section completed-summary"><header class="section-heading"><div><p class="eyebrow">Trusted record</p><h2>会议完成链条</h2></div><div v-if="canContribute" class="page-header-actions"><button class="button button-quiet" @click="amendmentOpen = !amendmentOpen">添加更正</button><button class="button button-danger" :disabled="saving" @click="reopen">重新打开会议</button></div></header><p class="snapshot-meta">快照 #{{ meeting.current_snapshot?.completion_number ?? '—' }} · 原始记录保持只读</p><p class="completed-meeting-duration" data-testid="completed-meeting-duration">实际会议时长：{{ duration(actualMeetingDurationSeconds) }}</p><MarkdownView :source="String(snapshotMeeting.summary_markdown ?? meeting.summary_markdown)" empty-text="本次会议未填写摘要" /></section>

    <form v-if="canContribute && amendmentOpen" class="workspace-section amendment-form" @submit.prevent="addAmendment"><h2>添加更正</h2><p>更正会作为独立历史记录追加，不会修改完成快照。</p><label>更正原因<input v-model="reason" required /></label><label>更正内容<MarkdownEditor v-model="content" label="更正内容" /></label><div class="form-actions"><button type="button" class="button button-quiet" @click="amendmentOpen = false">取消</button><button class="button button-primary" :disabled="saving || !reason.trim() || !content.trim()">保存更正</button></div></form>
    <p v-if="error" class="notice notice-error">{{ error }}</p>

    <section class="workspace-section"><h2>议题记录与产出</h2><div class="completed-agenda-list"><details v-for="item in outcomeGroups" :key="item.testId" :data-testid="item.testId" class="completed-outcome-accordion" open><summary class="completed-outcome-summary"><div><span v-if="item.status" class="status-pill" :data-status="item.status">{{ item.status }}</span><strong>{{ item.title }}</strong></div><dl aria-label="产出数量"><div><dt>决策</dt><dd>{{ item.decisions.length }}</dd></div><div><dt>行动</dt><dd>{{ item.actions.length }}</dd></div><div><dt>开放问题</dt><dd>{{ item.openQuestions.length }}</dd></div></dl></summary><div class="completed-outcome-body"><template v-if="item.notesMarkdown !== undefined"><p class="completed-agenda-timing">预计 {{ item.estimatedMinutes ?? '—' }} 分钟 · 实际 {{ duration(item.actualDurationSeconds ?? null) }}</p><section class="completed-agenda-notes"><h3>议题记录</h3><MarkdownView :source="item.notesMarkdown" empty-text="本议题未填写记录" /></section></template><section v-if="item.decisions.length" class="completed-outcome-group"><h3>决策 <span>{{ item.decisions.length }}</span></h3><article v-for="decision in item.decisions" :key="decision.id || decision.title" class="completed-outcome-row"><header><strong>{{ decision.title || '未命名决策' }}</strong><span v-if="decision.status" class="status-pill" :data-status="decision.status">{{ decision.status }}</span></header><MarkdownView :source="decision.decisionMarkdown" empty-text="未记录决策正文" /><div v-if="decision.rationaleMarkdown" class="completed-outcome-rationale"><span>依据</span><MarkdownView :source="decision.rationaleMarkdown" /></div></article></section><section v-if="item.actions.length" class="completed-outcome-group"><h3>行动项 <span>{{ item.actions.length }}</span></h3><article v-for="action in item.actions" :key="action.id || action.content" class="completed-outcome-row"><header><strong>{{ action.content || '未记录行动内容' }}</strong><span v-if="action.status" class="status-pill" :data-status="action.status">{{ action.status }}</span></header><p class="completed-outcome-meta">优先级：{{ action.priority || '未设置' }}<template v-if="action.dueDate"> · 截止：{{ action.dueDate }}</template></p></article></section><section v-if="item.openQuestions.length" class="completed-outcome-group"><h3>开放问题 <span>{{ item.openQuestions.length }}</span></h3><article v-for="question in item.openQuestions" :key="question.id || question.questionMarkdown" class="completed-outcome-row"><header><span>问题</span><span v-if="question.status" class="status-pill" :data-status="question.status">{{ question.status }}</span></header><MarkdownView :source="question.questionMarkdown" empty-text="未记录问题正文" /></article></section><p v-if="!item.decisions.length && !item.actions.length && !item.openQuestions.length" class="empty-inline">{{ item.status ? '本议题未记录产出' : '本次会议未记录会议级产出' }}</p></div></details><p v-if="!snapshotAgenda.length" class="empty-inline">快照中没有议题</p></div></section>
    <section class="workspace-section"><h2>材料</h2><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="meeting.attachments ?? []" :can-contribute="canContribute" @changed="emit('reload')" /></section>
    <section class="workspace-section"><h2>更正历史</h2><article v-for="item in meeting.amendments ?? []" :key="item.id" class="amendment-item"><strong>{{ item.reason }}</strong><MarkdownView :source="item.content_markdown" /><small>{{ item.created_by.display_name }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></article><p v-if="!meeting.amendments?.length" class="empty-inline">尚未添加更正</p></section>
  </div>
</template>
