<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInputNumber, NPopconfirm, NSelect, NTag } from 'naive-ui'
import StatusPill from './StatusPill.vue'
import { errorMessage } from '../utils/errors'

import { api, ApiError } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import { ingestMeetingNotes, smartStructureAgendaNotes } from '../api/meetings'
import type { AgendaDraft, AgendaItem, Attachment, Meeting } from '../domain/meetings'
import type { ActionItem, ActionStatus } from '../domain/outcomes'
import type { Project } from '../domain/projects'
import { Check } from '@lucide/vue'
import AttachmentPanel from './AttachmentPanel.vue'
import MarkdownEditor from './MarkdownEditor.vue'
import type { MarkdownEditorHandle } from './MarkdownEditor.vue'
import OutcomeComposer from './OutcomeComposer.vue'
import PluginEditorSlot from './PluginEditorSlot.vue'
import VersionConflictDialog from './VersionConflictDialog.vue'
import { useI18n } from '../i18n'
import { formatDateTime, formatDuration, parseUtcTimestamp } from '../utils/time'

const { locale, tr } = useI18n()
const props = defineProps<{ meeting: Meeting; item: AgendaItem; canContribute: boolean }>()
const emit = defineEmits<{ changed: []; advance: [nextId: string | null] }>()
type AgendaAdvanceResult = { next_agenda_item_id: string | null }
type AgendaDetailDraft = AgendaDraft & {
  proposer_user_id: string | null
  presenter_user_id: string | null
}
type MeetingOption = { id: string; title: string; version: number }

function draftFor(item: AgendaItem): AgendaDetailDraft {
  return {
    title: item.title,
    agenda_type: item.agenda_type,
    notes_markdown: item.notes_markdown,
    estimated_minutes: item.estimated_minutes,
    proposer_user_id: item.proposer?.id ?? null,
    presenter_user_id: item.presenter?.id ?? null,
  }
}

const draft = reactive<AgendaDetailDraft>(draftFor(props.item))
const notesEditor = ref<MarkdownEditorHandle | null>(null)
const accepted = ref<AgendaDetailDraft>(draftFor(props.item))
const currentVersion = ref(props.item.version)
const dirty = computed(() => draft.title !== accepted.value.title
  || draft.agenda_type !== accepted.value.agenda_type
  || draft.notes_markdown !== accepted.value.notes_markdown
  || draft.estimated_minutes !== accepted.value.estimated_minutes
  || draft.proposer_user_id !== accepted.value.proposer_user_id
  || draft.presenter_user_id !== accepted.value.presenter_user_id)
const composer = ref<'decision' | 'action' | 'question' | null>(null)
const saving = ref(false)
const extractingNotes = ref(false)
const extractStatus = ref('')
const error = ref('')
const conflict = ref<{ version: number; server: string } | null>(null)
const projectMembers = ref<UserRef[]>([])
let memberRequest: Promise<void> | null = null
const attachmentItems = ref<Attachment[] | null>(null)
const attachments = computed(() => attachmentItems.value ?? props.item.attachments ?? [])
const migrateOpen = ref(false)
const migrateSaving = ref(false)
const migrateError = ref('')
const migrateTargetId = ref<string | null>(null)
const converting = ref(false)
const copyOpen = ref(false)
const copySaving = ref(false)
const copyError = ref('')
const copyLoading = ref(false)
const copyOptions = ref<MeetingOption[]>([])
const copyTargetId = ref<string | null>(null)
const now = ref(Date.now())

const memberSelectOptions = computed(() => {
  const seen = new Set<string>()
  const options: Array<{ label: string; value: string }> = []
  const candidates = [
    ...props.meeting.participants.map((participant) => participant.user),
    ...projectMembers.value,
    ...(props.item.proposer ? [props.item.proposer] : []),
    ...(props.item.presenter ? [props.item.presenter] : []),
  ]
  for (const person of candidates) {
    if (seen.has(person.id)) continue
    seen.add(person.id)
    options.push({ label: person.display_name, value: person.id })
  }
  return options
})
const meetingLocked = computed(() => props.meeting.status === 'completed' || props.meeting.status === 'canceled')
const hasDirectOutcomes = computed(() => [
  ...props.item.decisions,
  ...props.item.actions,
  ...props.item.open_questions,
].some((outcome) => !outcome.is_derived))
const canMigrate = computed(() => props.canContribute && !meetingLocked.value && hasDirectOutcomes.value)
const canConvert = computed(() => props.canContribute && !meetingLocked.value && props.item.status === 'skipped')
const canCopy = computed(() => props.canContribute && !meetingLocked.value && props.item.status === 'skipped')
const migrateOptions = computed(() => props.meeting.agenda_items
  .filter((row) => row.id !== props.item.id)
  .map((row) => ({ label: row.title, value: row.id })))
const actualDurationText = computed(() => {
  const seconds = props.item.actual_duration_seconds
  if (props.item.status !== 'completed' || seconds === null || seconds === undefined) return ''
  return `${tr('实际用时', 'Actual')} ${formatDuration(seconds)}`
})
const completedWindow = computed(() => {
  if (props.item.status !== 'completed') return ''
  const parts: string[] = []
  if (props.item.started_at) parts.push(`${tr('开始', 'Start')} ${formatDateTime(props.item.started_at)}`)
  if (props.item.completed_at) parts.push(`${tr('完成', 'End')} ${formatDateTime(props.item.completed_at)}`)
  return parts.join(' · ')
})
const liveElapsed = computed(() => {
  const startedAt = props.item.started_at ?? props.meeting.started_at
  if (props.item.status !== 'in_progress' || !startedAt) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(startedAt).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, '0')).join(':')
})

const currentItemId = ref(props.item.id)
watch(() => props.item, (item) => {
  const switchedItem = item.id !== currentItemId.value
  currentItemId.value = item.id
  const next = draftFor(item)
  if (switchedItem || !dirty.value) {
    Object.assign(draft, next)
    accepted.value = next
    currentVersion.value = item.version
  }
  if (switchedItem) {
    attachmentItems.value = null
    conflict.value = null
  }
}, { deep: true })

let clockHandle: number | undefined
onMounted(() => {
  clockHandle = window.setInterval(() => { now.value = Date.now() }, 1_000)
})
onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
})

function loadProjectMembers() {
  if (memberRequest) return memberRequest
  memberRequest = (async () => {
    try {
      const project = await api<Project>(`/api/projects/${props.meeting.project.id}`)
      projectMembers.value = (project.memberships ?? []).map((membership) => membership.user)
    } catch {
      projectMembers.value = []
      memberRequest = null
    }
  })()
  return memberRequest
}

function onMemberMenu(show: boolean) {
  if (show) void loadProjectMembers()
}

function onAttachmentUploaded(attachment: Attachment) {
  attachmentItems.value = [attachment, ...attachments.value]
  emit('changed')
}

function onAttachmentDeleted(id: string) {
  attachmentItems.value = attachments.value.filter((attachment) => attachment.id !== id)
  emit('changed')
}

async function persistIfDirty(expectedVersion = currentVersion.value): Promise<boolean> {
  if (!props.canContribute) return false
  const markdown = typeof notesEditor.value?.flush === 'function' ? notesEditor.value.flush() : undefined
  if (markdown !== undefined) draft.notes_markdown = markdown

  if (!dirty.value) return false
  saving.value = true
  error.value = ''
  try {
    const payload: Record<string, unknown> = {
      expected_version: expectedVersion,
      title: draft.title.trim(),
      agenda_type: draft.agenda_type,
      notes_markdown: draft.notes_markdown,
      estimated_minutes: draft.estimated_minutes ?? null,
      proposer_user_id: draft.proposer_user_id,
      presenter_user_id: draft.presenter_user_id,
    }
    const saved = await api<AgendaItem>(`/api/agenda-items/${props.item.id}`, { method: 'PUT', body: JSON.stringify(payload) })
    const next = draftFor(saved)
    Object.assign(draft, next)
    accepted.value = next
    currentVersion.value = saved.version
    conflict.value = null
    return true
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'version_conflict') {
      let serverNotes = props.item.notes_markdown
      let actualVersion = Number(caught.details?.actual_version ?? currentVersion.value)
      try {
        const latestMeeting = await api<Meeting>(`/api/meetings/${props.meeting.id}`)
        const latestItem = latestMeeting.agenda_items?.find((row) => row.id === props.item.id)
        if (latestItem) {
          serverNotes = latestItem.notes_markdown
          actualVersion = latestItem.version
        }
      } catch {
        // Fallback to conflict details and current props if fetching latest meeting fails.
      }
      conflict.value = { version: actualVersion, server: serverNotes }
    } else error.value = errorMessage(caught, tr('议题保存失败', 'Failed to save agenda item'))
    throw caught
  } finally {
    saving.value = false
  }
}

function reloadFromServer() {
  const next = draftFor(props.item)
  if (conflict.value) {
    next.notes_markdown = conflict.value.server
    currentVersion.value = conflict.value.version
  }
  Object.assign(draft, next)
  accepted.value = next
  conflict.value = null
  emit('changed')
}

async function flushIfDirty(): Promise<boolean> {
  return persistIfDirty()
}

async function save(expectedVersion = currentVersion.value) {
  try {
    if (await persistIfDirty(expectedVersion)) emit('changed')
  } catch {
    // The persistence helper keeps the error and conflict state local to this editor.
  }
}

async function smartExtractNotes() {
  if (!props.canContribute || meetingLocked.value || extractingNotes.value || saving.value) return
  extractingNotes.value = true
  extractStatus.value = ''
  error.value = ''
  try {
    const flushed = typeof notesEditor.value?.flush === 'function' ? notesEditor.value.flush() : undefined
    if (flushed !== undefined) draft.notes_markdown = flushed
    const structured = smartStructureAgendaNotes(draft.notes_markdown, draft.title || props.item.title, locale.value)
    draft.notes_markdown = structured

    const res = await ingestMeetingNotes(props.meeting.id, {
      agenda_item_id: props.item.id,
      agenda_title: draft.title.trim() || props.item.title,
      notes_markdown: structured,
      auto_complete_agenda: false,
    })
    const updatedItem = res.agenda_items?.find((row) => row.id === props.item.id)
    if (updatedItem) {
      const next = draftFor(updatedItem)
      next.notes_markdown = structured
      Object.assign(draft, next)
      accepted.value = { ...next }
      currentVersion.value = updatedItem.version
    } else {
      accepted.value = { ...draft }
      currentVersion.value += 1
    }
    const decisions = res.decisions ?? res.extracted?.decisions ?? 0
    const actions = res.actions ?? res.extracted?.actions ?? 0
    const questions = res.questions ?? res.extracted?.questions ?? 0
    extractStatus.value = locale.value === 'en'
      ? `✨ Extracted ${decisions} decisions · ${actions} actions · ${questions} open questions`
      : `✨ 已智能提炼 ${decisions} 项决策 · ${actions} 项行动 · ${questions} 项开放问题`
    emit('changed')
  } catch (caught) {
    error.value = errorMessage(caught, tr('AI 提炼失败，请检查议题记录格式', 'AI extraction failed, please check notes format'))
  } finally {
    extractingNotes.value = false
  }
}

defineExpose({ flushIfDirty })

async function complete() {
  if (!props.canContribute) return
  try {
    await persistIfDirty()
  } catch {
    return
  }
  saving.value = true
  error.value = ''
  try {
    const result = await api<AgendaAdvanceResult>(`/api/agenda-items/${props.item.id}/complete-and-advance`, {
      method: 'POST', body: JSON.stringify({ expected_version: currentVersion.value }),
    })
    emit('advance', result.next_agenda_item_id)
  } catch (caught) {
    error.value = errorMessage(caught, tr('议题状态更新失败', 'Failed to update agenda status'))
  } finally {
    saving.value = false
  }
}

function openMigrate() {
  migrateTargetId.value = null
  migrateError.value = ''
  migrateOpen.value = true
}

async function submitMigrate() {
  if (migrateSaving.value) return
  const target = props.meeting.agenda_items.find((row) => row.id === migrateTargetId.value)
  if (!target) {
    migrateError.value = tr('请选择目标议题', 'Please select a target agenda item')
    return
  }
  migrateSaving.value = true
  migrateError.value = ''
  try {
    await api(`/api/agenda-items/${props.item.id}/migrate-outcomes`, {
      method: 'POST',
      body: JSON.stringify({
        target_agenda_item_id: target.id,
        expected_source_version: currentVersion.value,
        expected_target_version: target.version,
        expected_source_meeting_version: props.meeting.version,
        expected_target_meeting_version: props.meeting.version,
      }),
    })
    migrateOpen.value = false
    emit('changed')
  } catch (caught) {
    migrateError.value = errorMessage(caught, tr('产出迁移失败', 'Failed to migrate outcomes'))
  } finally {
    migrateSaving.value = false
  }
}

async function convertToQuestion() {
  if (!props.canContribute || converting.value) return
  converting.value = true
  error.value = ''
  try {
    await api(`/api/agenda-items/${props.item.id}/convert-to-question`, {
      method: 'POST',
      body: JSON.stringify({
        expected_source_version: currentVersion.value,
        expected_source_meeting_version: props.meeting.version,
      }),
    })
    emit('changed')
  } catch (caught) {
    error.value = errorMessage(caught, tr('转为开放问题失败', 'Failed to convert to open question'))
  } finally {
    converting.value = false
  }
}

async function openCopy() {
  copyTargetId.value = null
  copyError.value = ''
  copyOpen.value = true
  copyLoading.value = true
  try {
    const page = await api<Page<MeetingOption>>(`/api/meetings?project_id=${props.meeting.project.id}&limit=200`)
    copyOptions.value = (page.items ?? []).filter((row) => row.id !== props.meeting.id)
  } catch (caught) {
    copyError.value = errorMessage(caught, tr('目标会议加载失败', 'Failed to load target meetings'))
  } finally {
    copyLoading.value = false
  }
}

async function submitCopy() {
  if (copySaving.value) return
  if (!copyTargetId.value) {
    copyError.value = tr('请选择目标会议', 'Please select a target meeting')
    return
  }
  copySaving.value = true
  copyError.value = ''
  try {
    let targetVersion = copyOptions.value.find((row) => row.id === copyTargetId.value)?.version
    if (targetVersion === undefined) {
      const target = await api<Meeting>(`/api/meetings/${copyTargetId.value}`)
      targetVersion = target.version
    }
    await api(`/api/agenda-items/${props.item.id}/copy-to-meeting`, {
      method: 'POST',
      body: JSON.stringify({
        target_meeting_id: copyTargetId.value,
        expected_source_version: currentVersion.value,
        expected_source_meeting_version: props.meeting.version,
        expected_target_meeting_version: targetVersion,
      }),
    })
    copyOpen.value = false
    emit('changed')
  } catch (caught) {
    copyError.value = errorMessage(caught, tr('议题复制失败', 'Failed to copy agenda item'))
  } finally {
    copySaving.value = false
  }
}

const hoveredOutcomeId = ref<string | null>(null)

async function toggleActionStatus(action: ActionItem, newStatus?: ActionStatus) {
  if (!props.canContribute) return
  const nextStatus: ActionStatus = newStatus ?? (action.status === 'done' ? 'open' : 'done')
  try {
    const updated = await api<ActionItem>(`/api/actions/${action.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        status: nextStatus,
        expected_version: action.version,
      }),
    })
    action.status = updated.status
    action.version = updated.version
    emit('changed')
  } catch (caught) {
    error.value = errorMessage(caught, tr('更新行动项失败', 'Failed to update action item'))
  }
}

function cycleActionStatus(action: ActionItem) {
  if (!props.canContribute) return
  const cycleMap: Record<ActionStatus, ActionStatus> = {
    open: 'in_progress',
    in_progress: 'done',
    done: 'open',
    canceled: 'open',
  }
  void toggleActionStatus(action, cycleMap[action.status] || 'open')
}

function actionStatusLabel(status: ActionStatus): string {
  if (locale.value === 'en') {
    const enMap: Record<ActionStatus, string> = {
      open: 'Todo',
      in_progress: 'Doing',
      done: 'Done',
      canceled: 'Canceled',
    }
    return enMap[status] || status
  }
  const map: Record<ActionStatus, string> = {
    open: '待办',
    in_progress: '进行中',
    done: '已完成',
    canceled: '已取消',
  }
  return map[status] || status
}

const noteActionTags = computed(() => {
  const regex = /@(?:行动|Action|action):(\[[^\]]*\])*\s*([^\n\r]+)/g
  const matches: string[] = []
  let match: RegExpExecArray | null
  while ((match = regex.exec(draft.notes_markdown)) !== null) {
    matches.push(match[2].trim())
  }
  return matches
})
</script>

<template>
  <div class="agenda-detail" data-testid="agenda-detail">
    <header class="agenda-detail-header">
      <div><p class="eyebrow">Current topic</p><input v-model="draft.title" class="agenda-title-input" :aria-label="tr('议题标题', 'Agenda Title')" :readonly="!canContribute" /></div>
      <div class="agenda-detail-status">
        <StatusPill :status="props.item.status" kind="agenda" />
        <n-tag v-if="item.carry_from_open_question_id" size="small" :bordered="false">{{ tr('来自开放问题', 'From Question') }}</n-tag>
      </div>
    </header>
    <p v-if="actualDurationText || completedWindow || liveElapsed" class="agenda-timing">
      <span v-if="actualDurationText" class="agenda-actual-duration">{{ actualDurationText }}</span>
      <span v-if="completedWindow" class="agenda-actual-window">{{ completedWindow }}</span>
      <span v-if="liveElapsed" class="agenda-live-elapsed">{{ tr('已进行', 'Elapsed') }} {{ liveElapsed }}</span>
    </p>
    <div class="agenda-meta-fields">
      <label>{{ tr('类型', 'Type') }}<select v-model="draft.agenda_type" :disabled="!canContribute"><option value="information">{{ tr('信息同步', 'Info Sync') }}</option><option value="discussion">{{ tr('讨论', 'Discussion') }}</option><option value="decision">{{ tr('决策', 'Decision') }}</option></select></label>
      <label>{{ tr('预计时长', 'Duration') }}<n-input-number v-model:value="draft.estimated_minutes" :min="1" :max="480" :disabled="!canContribute" :input-props="{ 'aria-label': tr('预计时长', 'Duration') }" /></label>
      <label>{{ tr('提案人', 'Proposer') }}<n-select v-model:value="draft.proposer_user_id" :options="memberSelectOptions" filterable clearable :virtual-scroll="false" :disabled="!canContribute" :input-props="{ 'aria-label': tr('提案人', 'Proposer') }" :placeholder="tr('未指定', 'Unassigned')" @update:show="onMemberMenu" /></label>
      <label>{{ tr('主讲人', 'Speaker') }}<n-select v-model:value="draft.presenter_user_id" :options="memberSelectOptions" filterable clearable :virtual-scroll="false" :disabled="!canContribute" :input-props="{ 'aria-label': tr('主讲人', 'Speaker') }" :placeholder="tr('未指定', 'Unassigned')" @update:show="onMemberMenu" /></label>
    </div>
    <div class="agenda-notes">
      <span v-if="!canContribute" class="agenda-notes-label">{{ tr('议题记录', 'Agenda Notes') }}</span>
      <PluginEditorSlot v-if="canContribute" v-model="draft.notes_markdown" :editor-label="tr('议题记录', 'Agenda Notes')" data-testid="agenda-notes-editor" target-type="agenda_item" :target-id="item.id" slot="agenda-notes-editor" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, agendaId: item.id }" @notice="error = $event">
        <template #header-actions="{ disabled }">
          <button
            v-if="!meetingLocked"
            type="button"
            class="ai-inline-extract-btn"
            data-testid="ai-extract-notes-btn"
            :disabled="saving || disabled || extractingNotes"
            @click="smartExtractNotes"
          >
            ✨ {{ extractingNotes ? tr('正在提炼…', 'Extracting…') : tr('AI 智能提炼', 'AI Extract') }}
          </button>
        </template>
        <template #editor="{ disabled, registerEditor }">
          <MarkdownEditor ref="notesEditor" v-model="draft.notes_markdown" :label="tr('议题记录', 'Agenda Notes')" :placeholder="tr('记录讨论上下文、材料和过程…', 'Capture discussion context, materials, and notes…')" :disabled="saving || disabled || extractingNotes" :register-editor="registerEditor" />
        </template>
      </PluginEditorSlot>
      <MarkdownEditor v-else ref="notesEditor" v-model="draft.notes_markdown" :label="tr('议题记录', 'Agenda Notes')" :placeholder="tr('记录讨论上下文、材料和过程…', 'Capture discussion context, materials, and notes…')" :disabled="true" />
    </div>
    <p v-if="extractStatus" class="ai-extract-status" data-testid="ai-extract-status" role="status">{{ extractStatus }}</p>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div v-if="canContribute" class="agenda-save-row"><span class="muted">{{ tr('保存后会同步识别记录中的 @决策:、@行动:、@开放问题:。', 'Saving syncs @Decision:, @Action:, and @Question: tags from notes.') }}</span><button class="button button-quiet" :disabled="saving || !draft.title.trim()" @click="save()">{{ tr('保存议题', 'Save Agenda') }}</button></div>

    <div v-if="canMigrate || canConvert || canCopy" class="agenda-command-actions" data-testid="agenda-commands">
      <n-button v-if="canMigrate" quaternary size="small" @click="openMigrate">{{ tr('迁移产出', 'Migrate Outcomes') }}</n-button>
      <n-popconfirm v-if="canConvert" :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="convertToQuestion">
        <template #trigger>
          <n-button quaternary size="small" :loading="converting" :disabled="converting">{{ tr('转为开放问题', 'To Question') }}</n-button>
        </template>
        {{ tr('转为开放问题后，议题标题会成为一条待跟进的开放问题。', 'Converting turns the agenda title into an open question for follow-up.') }}
      </n-popconfirm>
      <n-button v-if="canCopy" quaternary size="small" @click="openCopy">{{ tr('复制到其他会议', 'Copy to Meeting') }}</n-button>
    </div>

    <section class="agenda-outcomes"><header class="section-heading"><div><p class="eyebrow">Outcomes</p><h2>{{ tr('本议题产出', 'Topic Outcomes') }}</h2></div><div v-if="canContribute" class="outcome-action-group" data-testid="outcome-actions"><button class="button button-small button-quiet" @click="composer = 'decision'">{{ tr('+ 决策', '+ Decision') }}</button><button class="button button-small button-quiet" @click="composer = 'action'">{{ tr('+ 行动', '+ Action') }}</button><button class="button button-small button-quiet" @click="composer = 'question'">{{ tr('+ 开放问题', '+ Question') }}</button></div></header>
      <OutcomeComposer v-if="canContribute && composer" :mode="composer" :meeting="meeting" :item="item" @close="composer = null" @saved="emit('changed')" />
      <div class="outcome-list">
        <article
          v-for="decision in item.decisions"
          :key="decision.id"
          :class="{ 'linked-glow': hoveredOutcomeId === decision.id }"
          @mouseenter="hoveredOutcomeId = decision.id"
          @mouseleave="hoveredOutcomeId = null"
        >
          <span>{{ decision.is_derived ? tr('来自议题记录', 'From Notes') : tr('决策', 'Decision') }}</span>
          <strong>{{ decision.title }}</strong>
        </article>

        <article
          v-for="action in item.actions"
          :key="action.id"
          class="outcome-action-item"
          :class="{
            'action-item--done': action.status === 'done',
            'linked-glow': hoveredOutcomeId === action.id || noteActionTags.includes(action.content)
          }"
          @mouseenter="hoveredOutcomeId = action.id"
          @mouseleave="hoveredOutcomeId = null"
        >
          <span>{{ action.is_derived ? tr('来自议题记录', 'From Notes') : tr('行动', 'Action') }}</span>
          <div class="outcome-action-content">
            <button
              type="button"
              class="action-checkbox-btn"
              :class="[`status-${action.status}`]"
              :disabled="!canContribute"
              :title="tr('切换完成状态', 'Toggle completion')"
              @click="toggleActionStatus(action)"
            >
              <span v-if="action.status === 'done'" class="action-check-icon"><Check :size="12" :stroke-width="3" /></span>
              <span v-else-if="action.status === 'in_progress'" class="action-dot-icon"></span>
            </button>
            <strong :class="{ 'text-strikethrough': action.status === 'done' }">{{ action.content }}</strong>
            <div class="action-tags-inline">
              <span v-if="action.owner" class="action-user-pill">@{{ action.owner.display_name }}</span>
              <span v-if="action.due_date" class="action-date-pill">{{ tr('截止', 'Due') }} {{ action.due_date }}</span>
              <button
                type="button"
                class="action-status-pill-btn"
                :class="[`pill-${action.status}`]"
                :disabled="!canContribute"
                :title="tr('点击切换状态', 'Click to cycle status')"
                @click="cycleActionStatus(action)"
              >
                {{ actionStatusLabel(action.status) }}
              </button>
            </div>
          </div>
        </article>

        <article
          v-for="question in item.open_questions"
          :key="question.id"
          :class="{ 'linked-glow': hoveredOutcomeId === question.id }"
          @mouseenter="hoveredOutcomeId = question.id"
          @mouseleave="hoveredOutcomeId = null"
        >
          <span>{{ question.is_derived ? tr('来自议题记录', 'From Notes') : tr('问题', 'Question') }}</span>
          <strong>{{ question.question_markdown }}</strong>
        </article>
        <p v-if="!item.decisions.length && !item.actions.length && !item.open_questions.length" class="empty-inline">{{ tr('讨论结果会在这里形成可追踪的链条。', 'Decisions, actions, and questions captured during discussion appear here.') }}</p>
      </div>
    </section>

    <section class="agenda-attachments" data-testid="agenda-attachments">
      <header class="section-heading"><div><p class="eyebrow">Attachments</p><h2>{{ tr('议题附件', 'Attachments') }}</h2></div></header>
      <AttachmentPanel target-type="agenda_item" :target-id="item.id" :attachments="attachments" :can-contribute="canContribute" @uploaded="onAttachmentUploaded" @deleted="onAttachmentDeleted" />
    </section>

    <footer v-if="canContribute && item.status === 'in_progress'" class="agenda-flow-actions" data-testid="flow-actions"><button class="button button-primary" :disabled="saving" @click="complete">{{ tr('完成议题并进入下一项', 'Complete & Next') }}</button></footer>
    <VersionConflictDialog v-if="conflict" :local-markdown="draft.notes_markdown" :server-markdown="conflict.server" :actual-version="conflict.version" @close="conflict = null" @reload="reloadFromServer" @overwrite="save" />

    <n-drawer :show="migrateOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!migrateSaving" @update:show="(value: boolean) => { if (!value && !migrateSaving) migrateOpen = false }">
      <n-drawer-content :title="tr('迁移产出', 'Migrate Outcomes')" closable>
        <p class="muted">{{ tr(`把“${item.title}”的直接产出移动到同一会议的另一项议题。`, `Move direct outcomes from "${item.title}" to another agenda item in this meeting.`) }}</p>
        <label class="agenda-command-field">{{ tr('目标议题', 'Target Agenda') }}
          <n-select v-model:value="migrateTargetId" class="migrate-target-select" :options="migrateOptions" :disabled="migrateSaving" :virtual-scroll="false" :input-props="{ 'aria-label': tr('目标议题', 'Target Agenda') }" :placeholder="tr('选择目标议题', 'Select target agenda')" />
        </label>
        <p v-if="migrateError" class="notice notice-error" role="alert">{{ migrateError }}</p>
        <template #footer>
          <n-button quaternary :disabled="migrateSaving" @click="migrateOpen = false">{{ tr('取消', 'Cancel') }}</n-button>
          <n-button type="primary" :loading="migrateSaving" :disabled="migrateSaving" @click="submitMigrate">{{ tr('确认迁移', 'Confirm Migration') }}</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>

    <n-drawer :show="copyOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!copySaving" @update:show="(value: boolean) => { if (!value && !copySaving) copyOpen = false }">
      <n-drawer-content :title="tr('复制到其他会议', 'Copy to Meeting')" closable>
        <p class="muted">{{ tr('只有已跳过的议题可以复制到之后的会议。', 'Only skipped agenda items can be copied to another meeting.') }}</p>
        <label class="agenda-command-field">{{ tr('目标会议', 'Target Meeting') }}
          <n-select v-model:value="copyTargetId" class="copy-target-select" :options="copyOptions.map((option) => ({ label: option.title, value: option.id }))" :loading="copyLoading" :disabled="copySaving" :virtual-scroll="false" :input-props="{ 'aria-label': tr('目标会议', 'Target Meeting') }" :placeholder="tr('选择目标会议', 'Select target meeting')" />
        </label>
        <p v-if="copyError" class="notice notice-error" role="alert">{{ copyError }}</p>
        <template #footer>
          <n-button quaternary :disabled="copySaving" @click="copyOpen = false">{{ tr('取消', 'Cancel') }}</n-button>
          <n-button type="primary" :loading="copySaving" :disabled="copySaving || copyLoading" @click="submitCopy">{{ tr('确认复制', 'Confirm Copy') }}</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>
