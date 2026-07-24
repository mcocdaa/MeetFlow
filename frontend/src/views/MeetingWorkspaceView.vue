<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api, ApiError } from '../api/client'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import CompletedMeetingChain from '../components/CompletedMeetingChain.vue'
import ContextDrawer from '../components/ContextDrawer.vue'
import MeetingCommentsPanel from '../components/MeetingCommentsPanel.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import InlineAiDrafts from '../components/InlineAiDrafts.vue'
import PluginActionPanel from '../components/PluginActionPanel.vue'
import type { Attachment, Meeting } from '../domain/meetings'

const route = useRoute()
const meeting = ref<Meeting | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const unresolvedIds = ref<string[]>([])
const focusAgendaId = ref('')
const commentsOpen = ref(false)
const preparationOpen = ref(false)
const materialsOpen = ref(false)
const materialItems = ref<Attachment[]>([])
const draft = ref({ title: '', purpose_markdown: '', raw_notes_markdown: '', summary_markdown: '', scheduled_start: '', scheduled_end: '' })
const summaryDrafts = ref<{ reload: () => Promise<void> } | null>(null)
const actionDrafts = ref<{ reload: () => Promise<void> } | null>(null)
const unresolved = computed(() => meeting.value?.agenda_items.filter((item) => item.status === 'planned' || item.status === 'in_progress') ?? [])

function toLocalInput(value: string) {
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const value = await api<Meeting>(`/api/meetings/${route.params.id}`)
    meeting.value = value
    materialItems.value = value.attachments ?? []
    draft.value = { title: value.title, purpose_markdown: value.purpose_markdown, raw_notes_markdown: value.raw_notes_markdown, summary_markdown: value.summary_markdown, scheduled_start: toLocalInput(value.scheduled_start), scheduled_end: toLocalInput(value.scheduled_end) }
    unresolvedIds.value = []
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议加载失败' }
  finally { loading.value = false }
}

async function saveMeeting() {
  if (!meeting.value) return
  saving.value = true
  error.value = ''
  try {
    meeting.value = await api<Meeting>(`/api/meetings/${meeting.value.id}`, { method: 'PUT', body: JSON.stringify({ expected_version: meeting.value.version, ...draft.value, scheduled_start: new Date(draft.value.scheduled_start).toISOString(), scheduled_end: new Date(draft.value.scheduled_end).toISOString() }) })
    materialItems.value = meeting.value.attachments ?? materialItems.value
    preparationOpen.value = false
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议保存失败' }
  finally { saving.value = false }
}

function addMaterial(attachment: Attachment) {
  materialItems.value = [attachment, ...materialItems.value]
}

function removeMaterial(id: string) {
  materialItems.value = materialItems.value.filter((attachment) => attachment.id !== id)
}

async function lifecycle(action: 'ready' | 'draft' | 'start' | 'finish') {
  if (!meeting.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/meetings/${meeting.value.id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: meeting.value.version }) })
    await load()
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'meeting_has_unresolved_agenda') {
      unresolvedIds.value = Array.isArray(caught.details?.agenda_ids) ? caught.details.agenda_ids.map(String) : []
      focusAgendaId.value = unresolvedIds.value[0] ?? ''
      error.value = `还有 ${unresolvedIds.value.length} 个议题未处理`
    } else error.value = caught instanceof Error ? caught.message : '会议状态更新失败'
  } finally { saving.value = false }
}

async function refreshAgenda() {
  if (!meeting.value) return
  try {
    const value = await api<Meeting>(`/api/meetings/${meeting.value.id}`)
    meeting.value = value
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题刷新失败'
  }
}

function refreshInlineDrafts() {
  void summaryDrafts.value?.reload()
  void actionDrafts.value?.reload()
}

onMounted(load)
</script>

<template>
  <main class="workspace-page meeting-workspace">
    <p v-if="loading" class="empty-state">正在打开会议工作区…</p>
    <template v-else-if="meeting">
      <PageHeader :eyebrow="meeting.project.name" :title="meeting.title" :summary="`${new Date(meeting.scheduled_start).toLocaleString('zh-CN')} · ${meeting.participants.length} 位参与者`">
        <template #meta><div class="project-context"><span class="status-pill" :data-status="meeting.status">{{ meeting.status === 'draft' ? '准备会议' : meeting.status === 'ready' ? '等待开始' : meeting.status === 'in_progress' ? '会议进行中' : '会议已完成' }}</span><span>主持：{{ meeting.host?.display_name ?? '未指定' }}</span><span>记录：{{ meeting.recorder?.display_name ?? '未指定' }}</span></div></template>
        <template #actions><button v-if="meeting.status === 'draft' || meeting.status === 'ready'" class="button button-quiet" @click="preparationOpen = true">准备信息</button><button v-if="meeting.status === 'draft'" class="button button-primary" :disabled="saving" @click="lifecycle('ready')">准备完成</button><template v-else-if="meeting.status === 'ready'"><button class="button button-quiet" @click="lifecycle('draft')">返回准备</button><button class="button button-primary" @click="lifecycle('start')">开始会议</button></template><button v-else-if="meeting.status === 'in_progress'" class="button button-primary" :disabled="saving || unresolved.length > 0" :aria-disabled="unresolved.length > 0 ? 'true' : 'false'" @click="lifecycle('finish')">结束会议</button></template>
      </PageHeader>
      <p v-if="meeting.status === 'in_progress' && unresolved.length" class="meeting-unresolved">还有 {{ unresolved.length }} 个议题未处理</p>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

      <CompletedMeetingChain v-if="meeting.status === 'completed'" :meeting="meeting" @reload="load" />
      <template v-else>
        <AgendaWorkbench :meeting="meeting" :initial-selected-id="focusAgendaId" @reload="refreshAgenda" />
        <section data-testid="meeting-inline-summary"><InlineAiDrafts ref="summaryDrafts" target-type="meeting" :target-id="meeting.id" mode="summary" @applied="load" /></section>
        <section data-testid="meeting-inline-actions"><InlineAiDrafts ref="actionDrafts" target-type="meeting" :target-id="meeting.id" mode="actions" :participants="meeting.participants.map((participant) => participant.user)" @applied="refreshAgenda" /></section>
        <div class="meeting-tools workspace-section"><div><p class="eyebrow">Meeting tools</p><h2>材料与协作</h2><p class="muted">材料、评论都可以在会议进行中持续添加，不会离开当前议题。</p></div><div class="row-actions"><button class="button button-quiet" @click="materialsOpen = true">材料 ({{ materialItems.length }})</button><button class="button button-primary" @click="commentsOpen = true">评论</button></div></div>
        <PluginActionPanel :target-type="'meeting'" :target-id="meeting.id" @submitted="refreshInlineDrafts" />
        <ContextDrawer :open="preparationOpen" title="准备信息" @close="preparationOpen = false"><section class="meeting-preparation"><header class="section-heading"><div><p class="eyebrow">Preparation</p><h2>会议准备</h2></div><button class="button button-primary" :disabled="saving" @click="saveMeeting">保存会议信息</button></header><div class="meeting-prep-grid"><label>会议标题<input v-model="draft.title" /></label><label>开始时间<input v-model="draft.scheduled_start" type="datetime-local" /></label><label>结束时间<input v-model="draft.scheduled_end" type="datetime-local" /></label></div><label>会议目的<MarkdownEditor v-model="draft.purpose_markdown" label="会议目的" /></label><div class="participant-chips"><span v-for="participant in meeting.participants" :key="participant.user.id"><b>{{ participant.user.display_name }}</b> · {{ participant.participation_role }}</span><span v-if="!meeting.participants.length">尚未添加参与者</span></div></section></ContextDrawer>
        <ContextDrawer :open="materialsOpen" title="会议材料" @close="materialsOpen = false"><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="materialItems" @uploaded="addMaterial" @deleted="removeMaterial" /></ContextDrawer>
        <ContextDrawer :open="commentsOpen" title="评论" @close="commentsOpen = false"><MeetingCommentsPanel :meeting="meeting" /></ContextDrawer>
      </template>
    </template>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
