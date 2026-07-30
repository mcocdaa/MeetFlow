<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import CompletedMeetingChain from '../components/CompletedMeetingChain.vue'
import ContextDrawer from '../components/ContextDrawer.vue'
import MeetingCommentsPanel from '../components/MeetingCommentsPanel.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import PluginEditorSlot from '../components/PluginEditorSlot.vue'
import type { Attachment, Meeting } from '../domain/meetings'

type MeetingDraft = {
  title: string
  purpose_markdown: string
  raw_notes_markdown: string
  summary_markdown: string
  scheduled_start: string
  scheduled_end: string
}

type LifecycleAction = 'start' | 'finish'
type MarkdownEditorHandle = { flush: () => string }

const route = useRoute()
const meeting = ref<Meeting | null>(null)
const loading = ref(true)
const saving = ref(false)
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
const draft = ref<MeetingDraft>({ title: '', purpose_markdown: '', raw_notes_markdown: '', summary_markdown: '', scheduled_start: '', scheduled_end: '' })
const acceptedDraft = ref<MeetingDraft>({ ...draft.value })
const workbench = ref<{ flushCurrentDraft: () => Promise<boolean> } | null>(null)
const unresolved = computed(() => meeting.value?.agenda_items.filter((item) => item.status === 'planned' || item.status === 'in_progress') ?? [])
const dirty = computed(() => draft.value.title !== acceptedDraft.value.title
  || draft.value.purpose_markdown !== acceptedDraft.value.purpose_markdown
  || draft.value.raw_notes_markdown !== acceptedDraft.value.raw_notes_markdown
  || draft.value.summary_markdown !== acceptedDraft.value.summary_markdown
  || draft.value.scheduled_start !== acceptedDraft.value.scheduled_start
  || draft.value.scheduled_end !== acceptedDraft.value.scheduled_end)
const busy = computed(() => saving.value || lifecycleAction.value !== null)
const liveElapsed = computed(() => {
  if (!meeting.value?.started_at) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(meeting.value.started_at).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(hours ? 2 : 1, '0')}:${String(seconds).padStart(2, '0')}`
})

function toLocalInput(value: string) {
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function parseUtcTimestamp(value: string) {
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`)
}

function draftFor(value: Meeting): MeetingDraft {
  return {
    title: value.title,
    purpose_markdown: value.purpose_markdown,
    raw_notes_markdown: value.raw_notes_markdown,
    summary_markdown: value.summary_markdown,
    scheduled_start: toLocalInput(value.scheduled_start),
    scheduled_end: toLocalInput(value.scheduled_end),
  }
}

function acceptMeeting(value: Meeting, resetDraft: boolean) {
  meeting.value = value
  if (!resetDraft) return

  const next = draftFor(value)
  draft.value = next
  acceptedDraft.value = { ...next }
  materialItems.value = value.attachments ?? []
}

async function persistMeetingDraft(): Promise<boolean> {
  const summary = typeof summaryEditor.value?.flush === 'function' ? summaryEditor.value.flush() : undefined
  if (summary !== undefined) draft.value.summary_markdown = summary
  const purpose = typeof purposeEditor.value?.flush === 'function' ? purposeEditor.value.flush() : undefined
  if (purpose !== undefined) draft.value.purpose_markdown = purpose

  if (!meeting.value || !dirty.value) return false
  const value = await api<Meeting>(`/api/meetings/${meeting.value.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      expected_version: meeting.value.version,
      ...draft.value,
      scheduled_start: new Date(draft.value.scheduled_start).toISOString(),
      scheduled_end: new Date(draft.value.scheduled_end).toISOString(),
    }),
  })
  acceptMeeting(value, true)
  return true
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const value = await api<Meeting>(`/api/meetings/${route.params.id}`)
    acceptMeeting(value, true)
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议加载失败' }
  finally { loading.value = false }
}

async function saveMeeting() {
  if (!meeting.value) return
  saving.value = true
  error.value = ''
  try {
    await persistMeetingDraft()
    preparationOpen.value = false
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议保存失败' }
  finally { saving.value = false }
}

async function saveMinutes() {
  if (!meeting.value) return
  saving.value = true
  error.value = ''
  try {
    await persistMeetingDraft()
    minutesSaved.value = true
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议纪要保存失败' }
  finally { saving.value = false }
}

watch(() => draft.value.summary_markdown, () => { minutesSaved.value = false })

function addMaterial(attachment: Attachment) {
  materialItems.value = [attachment, ...materialItems.value]
}

function removeMaterial(id: string) {
  materialItems.value = materialItems.value.filter((attachment) => attachment.id !== id)
}

async function lifecycle(action: LifecycleAction) {
  if (!meeting.value || lifecycleAction.value) return
  lifecycleAction.value = action
  error.value = ''
  try {
    const agendaSaved = await workbench.value?.flushCurrentDraft() ?? false
    if (agendaSaved && !(await refreshAgenda())) return
    await persistMeetingDraft()
    const value = await api<Meeting>(`/api/meetings/${meeting.value.id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: meeting.value.version }) })
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

let clockHandle: number | undefined
onMounted(() => {
  void load()
  clockHandle = window.setInterval(() => { now.value = Date.now() }, 1_000)
})
onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
})
</script>

<template>
  <main class="workspace-page meeting-workspace" :class="{ 'meeting-live': meeting?.status === 'in_progress' }">
    <p v-if="loading" class="empty-state">正在打开会议工作区…</p>
    <template v-else-if="meeting">
      <PageHeader :eyebrow="meeting.project.name" :title="meeting.title" :summary="`${new Date(meeting.scheduled_start).toLocaleString('zh-CN')} · ${meeting.participants.length} 位参与者`">
        <template #meta><div class="project-context"><span class="status-pill" :data-status="meeting.status">{{ meeting.status === 'draft' || meeting.status === 'ready' ? '待开始' : meeting.status === 'in_progress' ? '会议进行中' : '会议已完成' }}</span><span v-if="meeting.status === 'in_progress' && liveElapsed" class="meeting-live-clock">进行 {{ liveElapsed }}</span><span>主持：{{ meeting.host?.display_name ?? '未指定' }}</span><span>记录：{{ meeting.recorder?.display_name ?? '未指定' }}</span></div></template>
        <template #actions><button v-if="meeting.status === 'draft' || meeting.status === 'ready'" class="button button-quiet" :disabled="busy" @click="preparationOpen = true">准备信息</button><button v-if="meeting.status === 'draft' || meeting.status === 'ready'" class="button button-primary" :disabled="busy" @click="lifecycle('start')">{{ lifecycleAction === 'start' ? '开始中' : '开始会议' }}</button><button v-else-if="meeting.status === 'in_progress'" class="button button-primary" :disabled="busy" @click="lifecycle('finish')">{{ lifecycleAction === 'finish' ? '结束中' : '结束会议' }}</button></template>
      </PageHeader>
      <p v-if="meeting.status === 'in_progress' && unresolved.length" class="meeting-unresolved">还有 {{ unresolved.length }} 个议题未结束。结束后，未结束议题会记为跳过。</p>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

      <CompletedMeetingChain v-if="meeting.status === 'completed'" :meeting="meeting" @reload="load" />
      <template v-else>
        <AgendaWorkbench ref="workbench" :meeting="meeting" @reload="refreshAgenda" />
        <section class="workspace-section meeting-summary-section">
          <header class="section-heading"><div><p class="eyebrow">Summary</p><h2>会议纪要</h2></div><div class="row-actions"><span v-if="minutesSaved" class="muted" role="status">纪要已保存</span><button class="button button-quiet" :disabled="busy || !dirty" @click="saveMinutes">保存会议纪要</button></div></header>
          <PluginEditorSlot
            editor-label="会议纪要"
            v-model="draft.summary_markdown"
            data-testid="meeting-summary-editor"
            target-type="meeting"
            :target-id="meeting.id"
            slot="meeting-summary-editor"
            :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, participants: meeting.participants.map((participant) => participant.user) }"
            @notice="error = $event"
          >
            <template #editor="{ disabled, registerEditor }">
              <MarkdownEditor ref="summaryEditor" v-model="draft.summary_markdown" label="会议纪要" placeholder="记录会议结论、行动项和后续安排…" :disabled="busy || disabled" :register-editor="registerEditor" />
            </template>
          </PluginEditorSlot>
        </section>
        <div class="meeting-tools workspace-section"><div><p class="eyebrow">Meeting tools</p><h2>材料与协作</h2><p class="muted">材料、评论都可以在会议进行中持续添加，不会离开当前议题。</p></div><div class="row-actions"><button class="button button-quiet" @click="materialsOpen = true">材料 ({{ materialItems.length }})</button><button class="button button-primary" @click="commentsOpen = true">评论</button></div></div>
        <ContextDrawer :open="preparationOpen" title="准备信息" @close="preparationOpen = false"><section class="meeting-preparation"><header class="section-heading"><div><p class="eyebrow">Preparation</p><h2>会议准备</h2></div><button class="button button-primary" :disabled="busy" @click="saveMeeting">保存会议信息</button></header><div class="meeting-prep-grid"><label>会议标题<input v-model="draft.title" /></label><label>开始时间<input v-model="draft.scheduled_start" type="datetime-local" /></label><label>结束时间<input v-model="draft.scheduled_end" type="datetime-local" /></label></div><label>会议目的<MarkdownEditor ref="purposeEditor" v-model="draft.purpose_markdown" label="会议目的" :disabled="busy" /></label><div class="participant-chips"><span v-for="participant in meeting.participants" :key="participant.user.id"><b>{{ participant.user.display_name }}</b> · {{ participant.participation_role }}</span><span v-if="!meeting.participants.length">尚未添加参与者</span></div></section></ContextDrawer>
        <ContextDrawer :open="materialsOpen" title="会议材料" @close="materialsOpen = false"><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="materialItems" @uploaded="addMaterial" @deleted="removeMaterial" /></ContextDrawer>
        <ContextDrawer :open="commentsOpen" title="评论" @close="commentsOpen = false"><MeetingCommentsPanel :meeting="meeting" /></ContextDrawer>
      </template>
    </template>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
