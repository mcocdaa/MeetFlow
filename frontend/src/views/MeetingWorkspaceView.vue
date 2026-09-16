<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopconfirm, NSelect, useMessage, type FormInst, type FormRules } from 'naive-ui'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'
import { onBeforeRouteLeave, useRoute } from 'vue-router'

import { api, ApiError } from '../api/client'
import type { UserRef } from '../api/contracts'
import { downloadMeetingExport, getMeeting, runMeetingLifecycle, type LifecycleAction } from '../api/meetings'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import CompletedMeetingChain from '../components/CompletedMeetingChain.vue'
import MeetingCommentsPanel from '../components/MeetingCommentsPanel.vue'
import MeetingParticipantEditor from '../components/MeetingParticipantEditor.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import type { MarkdownEditorHandle } from '../components/MarkdownEditor.vue'
import SaveStateIndicator from '../components/meeting/SaveStateIndicator.vue'
import PageHeader from '../components/PageHeader.vue'
import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import PluginSlot from '../components/PluginSlot.vue'
import type { Attachment, Meeting, MeetingParticipantWrite } from '../domain/meetings'
import type { Project } from '../domain/projects'
import { useMeetingWorkspace } from '../composables/useMeetingWorkspace'
import { formatDateTime, parseUtcTimestamp } from '../utils/time'


const route = useRoute()
const loading = ref(true)
const lifecycleAction = ref<LifecycleAction | null>(null)
const error = ref('')
const commentsOpen = ref(false)
const focusCommentId = ref<string | null>(null)
const preparationOpen = ref(false)
const materialsOpen = ref(false)
const materialItems = ref<Attachment[]>([])
const now = ref(Date.now())
const minutesSaved = ref(false)
const summaryEditor = ref<MarkdownEditorHandle | null>(null)
const purposeEditor = ref<MarkdownEditorHandle | null>(null)
const rawNotesEditor = ref<MarkdownEditorHandle | null>(null)
const workbench = ref<{ flushCurrentDraft: () => Promise<boolean> } | null>(null)
const exportAction = ref<string | null>(null)
const message = useMessage()
const memberOptions = ref<UserRef[]>([])
const membersUnavailable = ref(false)
const preparationFormRef = ref<FormInst | null>(null)
const preparationSaving = ref(false)
const preparationError = ref('')
const preparationForm = ref({
  title: '',
  scheduled_start: '',
  scheduled_end: '',
  purpose_markdown: '',
  host_user_id: null as string | null,
  recorder_user_id: null as string | null,
  participants: [] as MeetingParticipantWrite[],
})
const workspace = useMeetingWorkspace()
const meeting = workspace.meeting
const draft = workspace.draft
const acceptedDraft = workspace.acceptedDraft
const saving = workspace.saving
const saveState = workspace.saveState
const conflict = workspace.conflict
const unresolved = computed(() => meeting.value?.agenda_items.filter((item) => item.status === 'planned' || item.status === 'in_progress') ?? [])
const dirty = workspace.dirty
const needsSave = computed(() => dirty.value || saveState.value === 'error' || saveState.value === 'conflict')
const busy = computed(() => saving.value || lifecycleAction.value !== null)
const canContribute = computed(() => meeting.value?.capabilities?.can_contribute ?? false)
const canComment = computed(() => meeting.value?.capabilities?.can_comment ?? false)
const isPreparationStatus = computed(() => meeting.value?.status === 'draft' || meeting.value?.status === 'ready')
const canCancelMeeting = computed(() => isPreparationStatus.value || meeting.value?.status === 'in_progress')
const canExportMeeting = computed(() => meeting.value?.status === 'completed' || meeting.value?.status === 'canceled')
const liveElapsed = computed(() => {
  if (!meeting.value?.started_at) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(meeting.value.started_at).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(hours ? 2 : 1, '0')}:${String(seconds).padStart(2, '0')}`
})
const hostOptions = computed(() => memberOptions.value.map((member) => ({ label: member.display_name, value: member.id })))
const preparationRules: FormRules = {
  title: {
    required: true,
    message: '请输入会议标题',
    trigger: ['input', 'blur'],
    transform: (value: string) => value.trim(),
  },
  scheduled_end: {
    validator: () => {
      if (!preparationForm.value.scheduled_start || !preparationForm.value.scheduled_end) return true
      const start = new Date(preparationForm.value.scheduled_start).getTime()
      const end = new Date(preparationForm.value.scheduled_end).getTime()
      if (Number.isNaN(start) || Number.isNaN(end)) return true
      return end > start
    },
    message: '结束时间必须晚于开始时间',
    trigger: ['change', 'blur'],
  },
}

function toLocalInput(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

/** Participants plus host/recorder, deduplicated: the fallback member list when the project cannot be read. */
function currentMemberRefs(value: Meeting): UserRef[] {
  const seen = new Set<string>()
  const options: UserRef[] = []
  for (const participant of value.participants) {
    if (seen.has(participant.user.id)) continue
    seen.add(participant.user.id)
    options.push(participant.user)
  }
  for (const person of [value.host, value.recorder]) {
    if (!person || seen.has(person.id)) continue
    seen.add(person.id)
    options.push(person)
  }
  return options
}

async function loadMemberOptions(value: Meeting) {
  try {
    const project = await api<Project>(`/api/projects/${value.project.id}`)
    const seen = new Set<string>()
    const options: UserRef[] = []
    for (const membership of project.memberships ?? []) {
      if (seen.has(membership.user.id)) continue
      seen.add(membership.user.id)
      options.push(membership.user)
    }
    for (const member of currentMemberRefs(value)) {
      if (seen.has(member.id)) continue
      seen.add(member.id)
      options.push(member)
    }
    memberOptions.value = options
    membersUnavailable.value = false
  } catch {
    memberOptions.value = currentMemberRefs(value)
    membersUnavailable.value = true
  }
}

function openPreparation() {
  if (!meeting.value) return
  preparationForm.value = {
    title: meeting.value.title,
    scheduled_start: toLocalInput(meeting.value.scheduled_start),
    scheduled_end: toLocalInput(meeting.value.scheduled_end),
    purpose_markdown: meeting.value.purpose_markdown,
    host_user_id: meeting.value.host?.id ?? null,
    recorder_user_id: meeting.value.recorder?.id ?? null,
    participants: meeting.value.participants.map((participant) => ({
      user_id: participant.user.id,
      participation_role: participant.participation_role,
    })),
  }
  preparationError.value = ''
  preparationOpen.value = true
}

async function savePreparation() {
  if (!meeting.value || !canContribute.value || preparationSaving.value) return
  preparationSaving.value = true
  preparationError.value = ''
  try {
    const purpose = typeof purposeEditor.value?.flush === 'function' ? purposeEditor.value.flush() : undefined
    if (purpose !== undefined) preparationForm.value.purpose_markdown = purpose
    try {
      await preparationFormRef.value?.validate()
    } catch {
      return
    }
    const start = new Date(preparationForm.value.scheduled_start)
    const end = new Date(preparationForm.value.scheduled_end)
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
      preparationError.value = '结束时间必须晚于开始时间'
      return
    }
    const saved = await api<Meeting>(`/api/meetings/${meeting.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        expected_version: meeting.value.version,
        title: preparationForm.value.title.trim(),
        purpose_markdown: preparationForm.value.purpose_markdown,
        scheduled_start: start.toISOString(),
        scheduled_end: end.toISOString(),
        host_user_id: preparationForm.value.host_user_id,
        recorder_user_id: preparationForm.value.recorder_user_id,
        participants: preparationForm.value.participants.filter((row) => row.user_id),
      }),
    })
    acceptPreparation(saved)
    preparationOpen.value = false
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'meeting_locked') message.error(caught.message)
    else preparationError.value = errorMessage(caught, '准备信息保存失败')
  } finally {
    preparationSaving.value = false
  }
}

function acceptMeeting(value: Meeting, resetDraft: boolean) {
  workspace.accept(value, resetDraft)
  if (resetDraft) materialItems.value = value.attachments ?? []
}

/**
 * Replaces the prep-owned meeting fields after a preparation save without resetting the
 * workspace draft, so unsaved 会议纪要/原始笔记 stay in the editor and stay dirty.
 * The prep PUT omits those fields, so `draftFor(value)` would otherwise restore stale text.
 */
function acceptPreparation(value: Meeting) {
  acceptMeeting(value, false)
  draft.value.title = value.title
  draft.value.purpose_markdown = value.purpose_markdown
  draft.value.scheduled_start = toLocalInput(value.scheduled_start)
  draft.value.scheduled_end = toLocalInput(value.scheduled_end)
}

async function persistMeetingDraft(): Promise<boolean> {
  if (!canContribute.value) return false
  const summary = typeof summaryEditor.value?.flush === 'function' ? summaryEditor.value.flush() : undefined
  if (summary !== undefined) draft.value.summary_markdown = summary
  const rawNotes = typeof rawNotesEditor.value?.flush === 'function' ? rawNotesEditor.value.flush() : undefined
  if (rawNotes !== undefined) draft.value.raw_notes_markdown = rawNotes

  const saved = await workspace.persistIfDirty()
  if (saved) minutesSaved.value = true
  return saved
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const value = await getMeeting(String(route.params.id))
    acceptMeeting(value, true)
    await loadMemberOptions(value)
  } catch (caught) { error.value = errorMessage(caught, '会议加载失败') }
  finally { loading.value = false }
}

async function saveMeeting() {
  if (!meeting.value || !canContribute.value) return false
  saving.value = true
  error.value = ''
  try {
    await persistMeetingDraft()
    return true
  } catch (caught) { error.value = errorMessage(caught, '会议保存失败') }
  finally { saving.value = false }
  return false
}

async function saveMinutes() {
  if (await saveMeeting()) minutesSaved.value = true
}

watch(() => draft.value.summary_markdown, () => {
  if (draft.value.summary_markdown !== acceptedDraft.value.summary_markdown) minutesSaved.value = false
})

function addMaterial(attachment: Attachment) {
  materialItems.value = [attachment, ...materialItems.value]
}

function removeMaterial(id: string) {
  materialItems.value = materialItems.value.filter((attachment) => attachment.id !== id)
}

function syncCommentDeepLink() {
  const comment = route.query.comment
  if (typeof comment === 'string' && comment) {
    focusCommentId.value = comment
    commentsOpen.value = true
  } else {
    focusCommentId.value = null
  }
}

function confirmLeave() {
  return window.confirm('会议草稿尚未保存，确定离开吗？')
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!needsSave.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => {
  if (!needsSave.value) return true
  return confirmLeave()
})

async function lifecycle(action: LifecycleAction) {
  if (!meeting.value || !canContribute.value || lifecycleAction.value) return
  lifecycleAction.value = action
  error.value = ''
  try {
    const agendaSaved = await workbench.value?.flushCurrentDraft() ?? false
    if (agendaSaved && !(await refreshAgenda())) return
    await persistMeetingDraft()
    const value = await runMeetingLifecycle(meeting.value.id, action, meeting.value.version)
    acceptMeeting(value, true)
  } catch (caught) {
    error.value = errorMessage(caught, '会议状态更新失败')
  } finally { lifecycleAction.value = null }
}

async function refreshAgenda(): Promise<boolean> {
  if (!meeting.value) return false
  try {
    const value = await api<Meeting>(`/api/meetings/${meeting.value.id}`)
    acceptMeeting(value, false)
    return true
  } catch (caught) {
    error.value = errorMessage(caught, '议题刷新失败')
    return false
  }
}

async function downloadExport(exporterId: string) {
  if (!meeting.value || !canContribute.value || exportAction.value) return
  exportAction.value = exporterId
  error.value = ''
  try {
    const { blob, filename } = await downloadMeetingExport(meeting.value.id, exporterId)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.style.display = 'none'
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (caught) {
    error.value = errorMessage(caught, '会议导出失败')
  } finally { exportAction.value = null }
}

let clockHandle: number | undefined
onMounted(() => {
  void load()
  syncCommentDeepLink()
  clockHandle = window.setInterval(() => { now.value = Date.now() }, 1_000)
  window.addEventListener('beforeunload', handleBeforeUnload)
})
watch(() => route.query.comment, () => { syncCommentDeepLink() })
onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <main class="workspace-page meeting-workspace" :class="{ 'meeting-live': meeting?.status === 'in_progress' }">
    <p v-if="loading" class="empty-state">正在打开会议工作区…</p>
    <template v-else-if="meeting">
      <PageHeader :eyebrow="meeting.project.name" :title="meeting.title" :summary="`${formatDateTime(meeting.scheduled_start)} · ${meeting.participants.length} 位参与者`">
        <template #meta>
          <div class="project-context">
            <StatusPill :status="meeting.status" kind="meeting" />
            <span v-if="meeting.status === 'in_progress' && liveElapsed" class="meeting-live-clock">进行 {{ liveElapsed }}</span>
            <span>主持：{{ meeting.host?.display_name ?? '未指定' }}</span>
            <span>记录：{{ meeting.recorder?.display_name ?? '未指定' }}</span>
            <span v-if="meeting.series_slot_at">系列槽位 {{ formatDateTime(meeting.series_slot_at) }}</span>
            <span v-if="meeting.status === 'completed' && meeting.started_at" class="meeting-actual-window">开始：{{ formatDateTime(meeting.started_at) }}</span>
            <span v-if="meeting.status === 'completed' && meeting.completed_at" class="meeting-actual-window">完成：{{ formatDateTime(meeting.completed_at) }}</span>
          </div>
        </template>
        <template #actions>
          <n-button v-if="canContribute && canExportMeeting" quaternary :disabled="busy || exportAction !== null" @click="downloadExport('meeting-export.markdown')">{{ exportAction === 'meeting-export.markdown' ? '导出中…' : '导出 Markdown' }}</n-button>
          <n-button v-if="canContribute && canExportMeeting" quaternary :disabled="busy || exportAction !== null" @click="downloadExport('meeting-export.json')">{{ exportAction === 'meeting-export.json' ? '导出中…' : '导出 JSON' }}</n-button>
          <n-button v-if="canContribute && isPreparationStatus" quaternary :disabled="busy" @click="openPreparation">准备信息</n-button>
          <n-button v-if="canContribute && isPreparationStatus" type="primary" :loading="lifecycleAction === 'start'" :disabled="busy" @click="lifecycle('start')">开始会议</n-button>
          <n-button v-else-if="canContribute && meeting.status === 'in_progress'" type="primary" :loading="lifecycleAction === 'finish'" :disabled="busy" @click="lifecycle('finish')">结束会议</n-button>
          <n-popconfirm v-if="canContribute && canCancelMeeting" positive-text="确认" negative-text="取消" @positive-click="lifecycle('cancel')">
            <template #trigger>
              <n-button quaternary :loading="lifecycleAction === 'cancel'" :disabled="busy">取消会议</n-button>
            </template>
            <span data-testid="meeting-cancel-confirm">会议将标记为已取消且不可重开。</span>
          </n-popconfirm>
          <n-popconfirm v-if="canContribute && meeting.status === 'completed'" positive-text="确认" negative-text="取消" @positive-click="lifecycle('reopen')">
            <template #trigger>
              <n-button quaternary :loading="lifecycleAction === 'reopen'" :disabled="busy">重新打开</n-button>
            </template>
            <span data-testid="meeting-reopen-confirm">重新打开后会议回到进行中，再次结束时生成新的历史快照。</span>
          </n-popconfirm>
        </template>
      </PageHeader>

      <p v-if="meeting.status === 'in_progress' && unresolved.length" class="meeting-unresolved">还有 {{ unresolved.length }} 个议题未结束。结束后，未结束议题会记为跳过。</p>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

      <CompletedMeetingChain v-if="meeting.status === 'completed'" :meeting="meeting" :can-contribute="canContribute" @reload="load" />
      <template v-else>
        <AgendaWorkbench ref="workbench" :meeting="meeting" :can-contribute="canContribute" @reload="refreshAgenda" />

        <section class="workspace-section meeting-summary-section">
          <header class="section-heading">
            <div><p class="eyebrow">Summary</p><h2>会议纪要</h2></div>
            <div class="row-actions">
              <span v-if="minutesSaved || saveState === 'saved'" class="muted" role="status">纪要已保存</span>
              <button v-if="canContribute" class="button button-quiet" :disabled="busy || !dirty" @click="saveMinutes">保存会议纪要</button>
            </div>
          </header>
          <PluginEditorSlot v-if="canContribute" editor-label="会议纪要" v-model="draft.summary_markdown" data-testid="meeting-summary-editor" target-type="meeting" :target-id="meeting.id" slot="meeting-summary-editor" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, participants: meeting.participants.map((participant) => participant.user) }" @notice="error = $event">
            <template #editor="{ disabled, registerEditor }">
              <MarkdownEditor ref="summaryEditor" v-model="draft.summary_markdown" label="会议纪要" placeholder="记录会议结论、行动项和后续安排…" :disabled="busy || disabled" :register-editor="registerEditor" />
            </template>
          </PluginEditorSlot>
          <MarkdownEditor v-else v-model="draft.summary_markdown" label="会议纪要" placeholder="记录会议结论、行动项和后续安排…" :disabled="true" />
        </section>

        <section class="workspace-section meeting-raw-notes">
          <header class="section-heading"><div><p class="eyebrow">Notes</p><h2>整场会议原始笔记</h2></div><SaveStateIndicator role="note" :state="saveState" /></header>
          <MarkdownEditor ref="rawNotesEditor" v-model="draft.raw_notes_markdown" label="整场会议原始笔记" placeholder="记录整场会议的原始讨论内容…" :disabled="busy || !canContribute" />
          <p v-if="conflict" class="notice notice-error" role="alert">保存版本已变化，请刷新会议后重新确认本地笔记。</p>
        </section>

        <div class="meeting-tools workspace-section">
          <div><p class="eyebrow">Meeting tools</p><h2>材料与协作</h2><p class="muted">材料、评论都可以在会议进行中持续添加，不会离开当前议题。</p></div>
          <div class="row-actions">
            <PluginSlot v-if="canContribute" slot="meeting.toolbar.action" target-type="meeting" :target-id="meeting.id" :metadata="{ projectId: meeting.project.id }" />
            <button class="button button-quiet" @click="materialsOpen = true">材料 ({{ materialItems.length }})</button>
            <button v-if="canComment" class="button button-primary" @click="commentsOpen = true">评论</button>
          </div>
        </div>

        <n-drawer :show="preparationOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!preparationSaving" @update:show="(value: boolean) => { if (!value) preparationOpen = false }">
          <n-drawer-content title="准备信息" closable>
            <section class="meeting-preparation">
              <header class="section-heading"><div><p class="eyebrow">Preparation</p><h2>会议准备</h2></div></header>
              <n-form ref="preparationFormRef" :model="preparationForm" :rules="preparationRules" label-placement="top" :show-require-mark="false">
                <n-form-item label="会议标题" path="title">
                  <n-input v-model:value="preparationForm.title" :input-props="{ 'aria-label': '会议标题' }" placeholder="会议标题" />
                </n-form-item>
                <n-form-item label="开始时间" path="scheduled_start">
                  <input v-model="preparationForm.scheduled_start" class="native-datetime-input" type="datetime-local" aria-label="开始时间" />
                </n-form-item>
                <n-form-item label="结束时间" path="scheduled_end">
                  <input v-model="preparationForm.scheduled_end" class="native-datetime-input" type="datetime-local" aria-label="结束时间" />
                </n-form-item>
                <n-form-item label="会议目的" path="purpose_markdown">
                  <PluginEditorSlot v-model="preparationForm.purpose_markdown" editor-label="会议目的" target-type="meeting" :target-id="meeting.id" slot="meeting-purpose-editor" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id }" @notice="preparationError = $event">
                    <template #editor="{ disabled, registerEditor }">
                      <MarkdownEditor ref="purposeEditor" v-model="preparationForm.purpose_markdown" label="会议目的" placeholder="这次会议要解决什么问题？" :disabled="preparationSaving || disabled" :register-editor="registerEditor" />
                    </template>
                  </PluginEditorSlot>
                </n-form-item>
                <n-form-item label="主持" path="host_user_id">
                  <n-select v-model:value="preparationForm.host_user_id" :options="hostOptions" :virtual-scroll="false" :input-props="{ 'aria-label': '主持' }" filterable clearable placeholder="未指定" />
                </n-form-item>
                <n-form-item label="记录" path="recorder_user_id">
                  <n-select v-model:value="preparationForm.recorder_user_id" :options="hostOptions" :virtual-scroll="false" :input-props="{ 'aria-label': '记录' }" filterable clearable placeholder="未指定" />
                </n-form-item>
                <n-form-item label="参与人">
                  <MeetingParticipantEditor v-model="preparationForm.participants" :member-options="memberOptions" :disabled="preparationSaving" />
                </n-form-item>
              </n-form>
              <p v-if="membersUnavailable" class="empty-inline">成员列表不可用，仅显示当前参与人</p>
              <p v-if="preparationError" class="notice notice-error" role="alert">{{ preparationError }}</p>
            </section>
            <template #footer>
              <n-button quaternary :disabled="preparationSaving" @click="preparationOpen = false">取消</n-button>
              <n-button type="primary" :loading="preparationSaving" :disabled="preparationSaving" @click="savePreparation">保存准备信息</n-button>
            </template>
          </n-drawer-content>
        </n-drawer>
        <n-drawer :show="materialsOpen" placement="right" :width="'min(560px, 100vw)'" @update:show="(value: boolean) => { if (!value) materialsOpen = false }">
          <n-drawer-content title="会议材料" closable>
            <AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="materialItems" :can-contribute="canContribute" @uploaded="addMaterial" @deleted="removeMaterial" />
          </n-drawer-content>
        </n-drawer>
        <n-drawer v-if="canComment" :show="commentsOpen" placement="right" :width="'min(560px, 100vw)'" @update:show="(value: boolean) => { if (!value) commentsOpen = false }">
          <n-drawer-content title="评论" closable>
            <MeetingCommentsPanel :meeting="meeting" :focus-comment-id="focusCommentId" />
          </n-drawer-content>
        </n-drawer>
      </template>
    </template>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
