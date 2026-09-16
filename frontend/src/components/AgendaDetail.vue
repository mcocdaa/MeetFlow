<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInputNumber, NPopconfirm, NSelect, NTag } from 'naive-ui'
import StatusPill from './StatusPill.vue'
import { errorMessage } from '../utils/errors'

import { api, ApiError } from '../api/client'
import type { Page, UserRef } from '../api/contracts'
import type { AgendaDraft, AgendaItem, Attachment, Meeting } from '../domain/meetings'
import type { Project } from '../domain/projects'
import { assistantsForSlot } from '../plugins/registry'
import AttachmentPanel from './AttachmentPanel.vue'
import MarkdownEditor from './MarkdownEditor.vue'
import type { MarkdownEditorHandle } from './MarkdownEditor.vue'
import OutcomeComposer from './OutcomeComposer.vue'
import PluginEditorSlot from './PluginEditorSlot.vue'
import VersionConflictDialog from './VersionConflictDialog.vue'
import { formatDateTime, parseUtcTimestamp } from '../utils/time'

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
const error = ref('')
const conflict = ref<{ version: number; server: string } | null>(null)
const hasAgendaNotesAssistant = computed(() => assistantsForSlot('agenda-notes-editor').length > 0)
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
  return `实际用时 ${formatDuration(seconds)}`
})
const completedWindow = computed(() => {
  if (props.item.status !== 'completed') return ''
  const parts: string[] = []
  if (props.item.started_at) parts.push(`开始 ${formatDateTime(props.item.started_at)}`)
  if (props.item.completed_at) parts.push(`完成 ${formatDateTime(props.item.completed_at)}`)
  return parts.join(' · ')
})
const liveElapsed = computed(() => {
  if (props.item.status !== 'in_progress' || !props.meeting.started_at) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(props.meeting.started_at).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, '0')).join(':')
})

function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  if (hours) return `${hours} 小时${minutes ? ` ${minutes} 分` : ''}${remainder ? ` ${remainder} 秒` : ''}`
  if (!minutes) return `${remainder} 秒`
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
}

watch(() => props.item, (item) => {
  const next = draftFor(item)
  Object.assign(draft, next)
  accepted.value = next
  currentVersion.value = item.version
  attachmentItems.value = null
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
      conflict.value = { version: Number(caught.details?.actual_version ?? currentVersion.value), server: props.item.notes_markdown }
    } else error.value = errorMessage(caught, '议题保存失败')
    throw caught
  } finally {
    saving.value = false
  }
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
    error.value = errorMessage(caught, '议题状态更新失败')
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
    migrateError.value = '请选择目标议题'
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
    migrateError.value = errorMessage(caught, '产出迁移失败')
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
    error.value = errorMessage(caught, '转为开放问题失败')
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
    copyError.value = errorMessage(caught, '目标会议加载失败')
  } finally {
    copyLoading.value = false
  }
}

async function submitCopy() {
  if (copySaving.value) return
  if (!copyTargetId.value) {
    copyError.value = '请选择目标会议'
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
    copyError.value = errorMessage(caught, '议题复制失败')
  } finally {
    copySaving.value = false
  }
}
</script>

<template>
  <div class="agenda-detail" data-testid="agenda-detail">
    <header class="agenda-detail-header">
      <div><p class="eyebrow">Current topic</p><input v-model="draft.title" class="agenda-title-input" aria-label="议题标题" :readonly="!canContribute" /></div>
      <div class="agenda-detail-status">
        <StatusPill :status="props.item.status" kind="agenda" />
        <n-tag v-if="item.carry_from_open_question_id" size="small" :bordered="false">来自开放问题</n-tag>
      </div>
    </header>
    <p v-if="actualDurationText || completedWindow || liveElapsed" class="agenda-timing">
      <span v-if="actualDurationText" class="agenda-actual-duration">{{ actualDurationText }}</span>
      <span v-if="completedWindow" class="agenda-actual-window">{{ completedWindow }}</span>
      <span v-if="liveElapsed" class="agenda-live-elapsed">已进行 {{ liveElapsed }}</span>
    </p>
    <div class="agenda-meta-fields">
      <label>类型<select v-model="draft.agenda_type" :disabled="!canContribute"><option value="information">信息同步</option><option value="discussion">讨论</option><option value="decision">决策</option></select></label>
      <label>预计时长<n-input-number v-model:value="draft.estimated_minutes" :min="1" :max="480" :disabled="!canContribute" :input-props="{ 'aria-label': '预计时长' }" /></label>
      <label>提案人<n-select v-model:value="draft.proposer_user_id" :options="memberSelectOptions" filterable clearable :virtual-scroll="false" :disabled="!canContribute" :input-props="{ 'aria-label': '提案人' }" placeholder="未指定" @update:show="onMemberMenu" /></label>
      <label>主讲人<n-select v-model:value="draft.presenter_user_id" :options="memberSelectOptions" filterable clearable :virtual-scroll="false" :disabled="!canContribute" :input-props="{ 'aria-label': '主讲人' }" placeholder="未指定" @update:show="onMemberMenu" /></label>
    </div>
    <div class="agenda-notes">
      <span v-if="!canContribute || !hasAgendaNotesAssistant" class="agenda-notes-label">议题记录</span>
      <PluginEditorSlot v-if="canContribute" v-model="draft.notes_markdown" editor-label="议题记录" data-testid="agenda-notes-editor" target-type="agenda_item" :target-id="item.id" slot="agenda-notes-editor" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, agendaId: item.id }" @notice="error = $event">
        <template #editor="{ disabled, registerEditor }">
          <MarkdownEditor ref="notesEditor" v-model="draft.notes_markdown" label="议题记录" placeholder="记录讨论上下文、材料和过程…" :disabled="saving || disabled" :register-editor="registerEditor" />
        </template>
      </PluginEditorSlot>
      <MarkdownEditor v-else ref="notesEditor" v-model="draft.notes_markdown" label="议题记录" placeholder="记录讨论上下文、材料和过程…" :disabled="true" />
    </div>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div v-if="canContribute" class="agenda-save-row"><span class="muted">保存后会同步识别记录中的 @决策:、@行动:、@开放问题:。</span><button class="button button-quiet" :disabled="saving || !draft.title.trim()" @click="save()">保存议题</button></div>

    <div v-if="canMigrate || canConvert || canCopy" class="agenda-command-actions" data-testid="agenda-commands">
      <n-button v-if="canMigrate" quaternary size="small" @click="openMigrate">迁移产出</n-button>
      <n-popconfirm v-if="canConvert" positive-text="确认" negative-text="取消" @positive-click="convertToQuestion">
        <template #trigger>
          <n-button quaternary size="small" :loading="converting" :disabled="converting">转为开放问题</n-button>
        </template>
        转为开放问题后，议题标题会成为一条待跟进的开放问题。
      </n-popconfirm>
      <n-button v-if="canCopy" quaternary size="small" @click="openCopy">复制到其他会议</n-button>
    </div>

    <section class="agenda-outcomes"><header class="section-heading"><div><p class="eyebrow">Outcomes</p><h2>本议题产出</h2></div><div v-if="canContribute" class="outcome-action-group" data-testid="outcome-actions"><button class="button button-small button-quiet" @click="composer = 'decision'">+ 决策</button><button class="button button-small button-quiet" @click="composer = 'action'">+ 行动</button><button class="button button-small button-quiet" @click="composer = 'question'">+ 开放问题</button></div></header>
      <OutcomeComposer v-if="canContribute && composer" :mode="composer" :meeting="meeting" :item="item" @close="composer = null" @saved="emit('changed')" />
      <div class="outcome-list"><article v-for="decision in item.decisions" :key="decision.id"><span>{{ decision.is_derived ? '来自议题记录' : '决策' }}</span><strong>{{ decision.title }}</strong></article><article v-for="action in item.actions" :key="action.id"><span>{{ action.is_derived ? '来自议题记录' : '行动' }}</span><strong>{{ action.content }}</strong></article><article v-for="question in item.open_questions" :key="question.id"><span>{{ question.is_derived ? '来自议题记录' : '问题' }}</span><strong>{{ question.question_markdown }}</strong></article><p v-if="!item.decisions.length && !item.actions.length && !item.open_questions.length" class="empty-inline">讨论结果会在这里形成可追踪的链条。</p></div>
    </section>

    <section class="agenda-attachments" data-testid="agenda-attachments">
      <header class="section-heading"><div><p class="eyebrow">Attachments</p><h2>议题附件</h2></div></header>
      <AttachmentPanel target-type="agenda_item" :target-id="item.id" :attachments="attachments" :can-contribute="canContribute" @uploaded="onAttachmentUploaded" @deleted="onAttachmentDeleted" />
    </section>

    <footer v-if="canContribute && item.status === 'in_progress'" class="agenda-flow-actions" data-testid="flow-actions"><button class="button button-primary" :disabled="saving" @click="complete">完成议题并进入下一项</button></footer>
    <VersionConflictDialog v-if="conflict" :local-markdown="draft.notes_markdown" :server-markdown="conflict.server" :actual-version="conflict.version" @close="conflict = null" @reload="emit('changed'); conflict = null" @overwrite="save" />

    <n-drawer :show="migrateOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!migrateSaving" @update:show="(value: boolean) => { if (!value && !migrateSaving) migrateOpen = false }">
      <n-drawer-content title="迁移产出" closable>
        <p class="muted">把“{{ item.title }}”的直接产出移动到同一会议的另一项议题。</p>
        <label class="agenda-command-field">目标议题
          <n-select v-model:value="migrateTargetId" class="migrate-target-select" :options="migrateOptions" :disabled="migrateSaving" :virtual-scroll="false" :input-props="{ 'aria-label': '目标议题' }" placeholder="选择目标议题" />
        </label>
        <p v-if="migrateError" class="notice notice-error" role="alert">{{ migrateError }}</p>
        <template #footer>
          <n-button quaternary :disabled="migrateSaving" @click="migrateOpen = false">取消</n-button>
          <n-button type="primary" :loading="migrateSaving" :disabled="migrateSaving" @click="submitMigrate">确认迁移</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>

    <n-drawer :show="copyOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!copySaving" @update:show="(value: boolean) => { if (!value && !copySaving) copyOpen = false }">
      <n-drawer-content title="复制到其他会议" closable>
        <p class="muted">只有已跳过的议题可以复制到之后的会议。</p>
        <label class="agenda-command-field">目标会议
          <n-select v-model:value="copyTargetId" class="copy-target-select" :options="copyOptions.map((option) => ({ label: option.title, value: option.id }))" :loading="copyLoading" :disabled="copySaving" :virtual-scroll="false" :input-props="{ 'aria-label': '目标会议' }" placeholder="选择目标会议" />
        </label>
        <p v-if="copyError" class="notice notice-error" role="alert">{{ copyError }}</p>
        <template #footer>
          <n-button quaternary :disabled="copySaving" @click="copyOpen = false">取消</n-button>
          <n-button type="primary" :loading="copySaving" :disabled="copySaving || copyLoading" @click="submitCopy">确认复制</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>
