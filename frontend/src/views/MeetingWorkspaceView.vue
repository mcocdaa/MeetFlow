<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api, ApiError } from '../api/client'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import CompletedMeetingChain from '../components/CompletedMeetingChain.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import type { Meeting } from '../domain/meetings'

const route = useRoute()
const meeting = ref<Meeting | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const unresolvedIds = ref<string[]>([])
const focusAgendaId = ref('')
const draft = ref({ title: '', purpose_markdown: '', raw_notes_markdown: '', summary_markdown: '', scheduled_start: '', scheduled_end: '' })
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
    await api(`/api/meetings/${meeting.value.id}`, { method: 'PUT', body: JSON.stringify({ expected_version: meeting.value.version, ...draft.value, scheduled_start: new Date(draft.value.scheduled_start).toISOString(), scheduled_end: new Date(draft.value.scheduled_end).toISOString() }) })
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '会议保存失败' }
  finally { saving.value = false }
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

onMounted(load)
</script>

<template>
  <main class="workspace-page meeting-workspace">
    <p v-if="loading" class="empty-state">正在打开会议工作区…</p>
    <template v-else-if="meeting">
      <PageHeader :eyebrow="meeting.project.name" :title="meeting.title" :summary="`${new Date(meeting.scheduled_start).toLocaleString('zh-CN')} · ${meeting.participants.length} 位参与者`">
        <template #meta><div class="project-context"><span class="status-pill" :data-status="meeting.status">{{ meeting.status === 'draft' ? '准备会议' : meeting.status === 'ready' ? '等待开始' : meeting.status === 'in_progress' ? '会议进行中' : '会议已完成' }}</span><span>主持：{{ meeting.host?.display_name ?? '未指定' }}</span><span>记录：{{ meeting.recorder?.display_name ?? '未指定' }}</span></div></template>
        <template #actions><button v-if="meeting.status === 'draft'" class="button button-primary" :disabled="saving" @click="lifecycle('ready')">准备完成</button><template v-else-if="meeting.status === 'ready'"><button class="button button-quiet" @click="lifecycle('draft')">返回准备</button><button class="button button-primary" @click="lifecycle('start')">开始会议</button></template><button v-else-if="meeting.status === 'in_progress'" class="button button-primary" :disabled="saving || unresolved.length > 0" :aria-disabled="unresolved.length > 0 ? 'true' : 'false'" @click="lifecycle('finish')">结束会议</button></template>
      </PageHeader>
      <p v-if="meeting.status === 'in_progress' && unresolved.length" class="meeting-unresolved">还有 {{ unresolved.length }} 个议题未处理</p>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

      <CompletedMeetingChain v-if="meeting.status === 'completed'" :meeting="meeting" @reload="load" />
      <template v-else>
        <section v-if="meeting.status === 'draft' || meeting.status === 'ready'" class="workspace-section meeting-preparation"><header class="section-heading"><div><p class="eyebrow">Preparation</p><h2>会议准备</h2></div><button class="button button-primary" :disabled="saving" @click="saveMeeting">保存会议信息</button></header><div class="meeting-prep-grid"><label>会议标题<input v-model="draft.title" /></label><label>开始时间<input v-model="draft.scheduled_start" type="datetime-local" /></label><label>结束时间<input v-model="draft.scheduled_end" type="datetime-local" /></label></div><label>会议目的<MarkdownEditor v-model="draft.purpose_markdown" label="会议目的" /></label><div class="participant-chips"><span v-for="participant in meeting.participants" :key="participant.user.id"><b>{{ participant.user.display_name }}</b> · {{ participant.participation_role }}</span><span v-if="!meeting.participants.length">尚未添加参与者</span></div></section>

        <AgendaWorkbench :meeting="meeting" :initial-selected-id="focusAgendaId" @reload="load" />
        <div class="meeting-support-grid"><section class="workspace-section"><h2>会议材料</h2><p>材料可以在准备和会议进行中持续添加。</p><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="meeting.attachments ?? []" @changed="load" /></section><section class="workspace-section comments-reserved"><h2>评论</h2><p class="empty-state">评论区已经预留；协作阶段会接入线程、@成员与解决状态。</p></section></div>
      </template>
    </template>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
