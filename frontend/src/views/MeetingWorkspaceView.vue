<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'

import { api } from '../api/client'
import { downloadMeetingExport, getMeeting, runMeetingLifecycle } from '../api/meetings'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import CompletedMeetingChain from '../components/CompletedMeetingChain.vue'
import ContextDrawer from '../components/ContextDrawer.vue'
import MeetingCommentsPanel from '../components/MeetingCommentsPanel.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import SaveStateIndicator from '../components/meeting/SaveStateIndicator.vue'
import PageHeader from '../components/PageHeader.vue'
import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import PluginSlot from '../components/PluginSlot.vue'
import type { Attachment, Meeting } from '../domain/meetings'
import { useMeetingWorkspace } from '../composables/useMeetingWorkspace'

type LifecycleAction = 'start' | 'finish'
type MarkdownEditorHandle = { flush: () => string }

const route = useRoute()
const loading = ref(true)
const lifecycleAction = ref<LifecycleAction | null>(null)
const error = ref('')
const commentsOpen = ref(false)
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
const workspace = useMeetingWorkspace({ autoSave: false })
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
const liveElapsed = computed(() => {
  if (!meeting.value?.started_at) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(meeting.value.started_at).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(hours ? 2 : 1, '0')}:${String(seconds).padStart(2, '0')}`
})

function parseUtcTimestamp(value: string) {
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`)
}

function acceptMeeting(value: Meeting, resetDraft: boolean) {
  workspace.accept(value, resetDraft)
  if (resetDraft) materialItems.value = value.attachments ?? []
}

async function persistMeetingDraft(): Promise<boolean> {
  if (!canContribute.value) return false
  const summary = typeof summaryEditor.value?.flush === 'function' ? summaryEditor.value.flush() : undefined
  if (summary !== undefined) draft.value.summary_markdown = summary
  const purpose = typeof purposeEditor.value?.flush === 'function' ? purposeEditor.value.flush() : undefined
  if (purpose !== undefined) draft.value.purpose_markdown = purpose
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
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议加载失败' }
  finally { loading.value = false }
}

async function saveMeeting() {
  if (!meeting.value || !canContribute.value) return
  saving.value = true
  error.value = ''
  try {
    await persistMeetingDraft()
    preparationOpen.value = false
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议保存失败' }
  finally { saving.value = false }
}

async function saveMinutes() {
  if (!meeting.value || !canContribute.value) return
  saving.value = true
  error.value = ''
  try {
    await persistMeetingDraft()
    minutesSaved.value = true
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议纪要保存失败' }
  finally { saving.value = false }
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
    error.value = caught instanceof Error ? caught.message : '会议状态更新失败'
  } finally { lifecycleAction.value = null }
}

async function refreshAgenda(): Promise<boolean> {
  if (!meeting.value) return false
  try {
    const value = await api<Meeting>(`/api/meetings/${meeting.value.id}`)
    acceptMeeting(value, false)
    return true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题刷新失败'
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
    error.value = caught instanceof Error ? caught.message : '会议导出失败'
  } finally { exportAction.value = null }
}

let clockHandle: number | undefined
onMounted(() => {
  void load()
  clockHandle = window.setInterval(() => { now.value = Date.now() }, 1_000)
  window.addEventListener('beforeunload', handleBeforeUnload)
})
onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <main class="workspace-page meeting-workspace" :class="{ 'meeting-live': meeting?.status === 'in_progress' }">
    <p v-if="loading" class="empty-state">正在打开会议工作区…</p>
    <template v-else-if="meeting">
      <PageHeader :eyebrow="meeting.project.name" :title="meeting.title" :summary="`${new Date(meeting.scheduled_start).toLocaleString('zh-CN')} · ${meeting.participants.length} 位参与者`">
        <template #meta>
          <div class="project-context">
            <span class="status-pill" :data-status="meeting.status">{{ meeting.status === 'draft' || meeting.status === 'ready' ? '待开始' : meeting.status === 'in_progress' ? '会议进行中' : '会议已完成' }}</span>
            <span v-if="meeting.status === 'in_progress' && liveElapsed" class="meeting-live-clock">进行 {{ liveElapsed }}</span>
            <span>主持：{{ meeting.host?.display_name ?? '未指定' }}</span>
            <span>记录：{{ meeting.recorder?.display_name ?? '未指定' }}</span>
          </div>
        </template>
        <template #actions>
          <button v-if="canContribute && meeting.status === 'completed'" class="button button-quiet" :disabled="busy || exportAction !== null" @click="downloadExport('meeting-export.markdown')">{{ exportAction === 'meeting-export.markdown' ? '导出中…' : '导出 Markdown' }}</button>
          <button v-if="canContribute && meeting.status === 'completed'" class="button button-quiet" :disabled="busy || exportAction !== null" @click="downloadExport('meeting-export.json')">{{ exportAction === 'meeting-export.json' ? '导出中…' : '导出 JSON' }}</button>
          <button v-if="canContribute && (meeting.status === 'draft' || meeting.status === 'ready')" class="button button-quiet" :disabled="busy" @click="preparationOpen = true">准备信息</button>
          <button v-if="canContribute && (meeting.status === 'draft' || meeting.status === 'ready')" class="button button-primary" :disabled="busy" @click="lifecycle('start')">{{ lifecycleAction === 'start' ? '开始中' : '开始会议' }}</button>
          <button v-else-if="canContribute && meeting.status === 'in_progress'" class="button button-primary" :disabled="busy" @click="lifecycle('finish')">{{ lifecycleAction === 'finish' ? '结束中' : '结束会议' }}</button>
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

        <ContextDrawer v-if="canContribute" :open="preparationOpen" title="准备信息" @close="preparationOpen = false">
          <section class="meeting-preparation">
            <header class="section-heading"><div><p class="eyebrow">Preparation</p><h2>会议准备</h2></div><button class="button button-primary" :disabled="busy" @click="saveMeeting">保存会议信息</button></header>
            <div class="meeting-prep-grid"><label>会议标题<input v-model="draft.title" /></label><label>开始时间<input v-model="draft.scheduled_start" type="datetime-local" /></label><label>结束时间<input v-model="draft.scheduled_end" type="datetime-local" /></label></div>
            <label>会议目的<MarkdownEditor ref="purposeEditor" v-model="draft.purpose_markdown" label="会议目的" :disabled="busy" /></label>
            <div class="participant-chips"><span v-for="participant in meeting.participants" :key="participant.user.id"><b>{{ participant.user.display_name }}</b> · {{ participant.participation_role }}</span><span v-if="!meeting.participants.length">尚未添加参与者</span></div>
          </section>
        </ContextDrawer>
        <ContextDrawer :open="materialsOpen" title="会议材料" @close="materialsOpen = false"><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="materialItems" :can-contribute="canContribute" @uploaded="addMaterial" @deleted="removeMaterial" /></ContextDrawer>
        <ContextDrawer v-if="canComment" :open="commentsOpen" title="评论" @close="commentsOpen = false"><MeetingCommentsPanel :meeting="meeting" /></ContextDrawer>
      </template>
    </template>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
