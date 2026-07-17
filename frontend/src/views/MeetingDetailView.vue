<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import ActionItemEditor, { type ActionWrite } from '../components/ActionItemEditor.vue'
import AttachmentPanel from '../components/AttachmentPanel.vue'
import MarkdownView from '../components/MarkdownView.vue'
import PluginActionPanel from '../components/PluginActionPanel.vue'
import type { ActionItem, MeetingPackage, MeetingWrite } from '../meetings/types'

type Tab = 'overview' | 'notes' | 'actions' | 'attachments' | 'updates'
const route = useRoute()
const router = useRouter()
const meeting = ref<MeetingPackage | null>(null)
const draft = ref<MeetingWrite | null>(null)
const participantsInput = ref('')
const dateInput = ref('')
const tab = ref<Tab>('overview')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const updateDraft = ref('')
const editingAction = ref('')
const actionResetKey = ref(0)
const openActions = computed(() => meeting.value?.actions.filter((item) => item.status === 'open') ?? [])

function toLocalInput(value: string) {
  const date = new Date(value)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

async function load(refreshDraft = true) {
  if (refreshDraft) loading.value = true
  error.value = ''
  try {
    const value = await api<MeetingPackage>(`/api/meetings/${route.params.id}`)
    meeting.value = value
    if (refreshDraft) {
      draft.value = {
        title: value.title, project: value.project, meeting_type: value.meeting_type,
        meeting_date: value.meeting_date, participants: [...value.participants],
        raw_notes_markdown: value.raw_notes_markdown, conclusions_markdown: value.conclusions_markdown,
      }
      participantsInput.value = value.participants.join('、')
      dateInput.value = toLocalInput(value.meeting_date)
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '会议加载失败'
  } finally {
    if (refreshDraft) loading.value = false
  }
}

async function saveMeeting() {
  if (!draft.value || !meeting.value) return
  saving.value = true
  error.value = ''
  saved.value = false
  draft.value.participants = participantsInput.value.split(/[,，、]/).map((item) => item.trim()).filter(Boolean)
  draft.value.meeting_date = new Date(dateInput.value).toISOString()
  try {
    const value = await api<Omit<MeetingPackage, 'actions' | 'attachments' | 'updates'>>(`/api/meetings/${route.params.id}`, {
      method: 'PUT', body: JSON.stringify(draft.value),
    })
    meeting.value = { ...meeting.value, ...value }
    saved.value = true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '保存失败，草稿已保留'
  } finally {
    saving.value = false
  }
}

async function deleteMeeting() {
  if (!window.confirm('删除后将同时移除行动项和附件，确定继续？')) return
  await api(`/api/meetings/${route.params.id}`, { method: 'DELETE' })
  await router.push('/')
}

async function createAction(value: ActionWrite) {
  error.value = ''
  try {
    await api(`/api/meetings/${route.params.id}/actions`, { method: 'POST', body: JSON.stringify(value) })
    actionResetKey.value += 1
    await load(false)
    tab.value = 'actions'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '行动项创建失败，请重试'
  }
}

async function saveAction(item: ActionItem, value: ActionWrite) {
  await api(`/api/meetings/${route.params.id}/actions/${item.id}`, { method: 'PUT', body: JSON.stringify(value) })
  editingAction.value = ''
  await load(false)
  tab.value = 'actions'
}

async function removeAction(item: ActionItem) {
  if (!window.confirm('确定删除这个行动项吗？')) return
  await api(`/api/meetings/${route.params.id}/actions/${item.id}`, { method: 'DELETE' })
  await load(false)
  tab.value = 'actions'
}

async function addUpdate() {
  if (!updateDraft.value.trim()) return
  await api(`/api/meetings/${route.params.id}/updates`, {
    method: 'POST', body: JSON.stringify({ content_markdown: updateDraft.value }),
  })
  updateDraft.value = ''
  await load(false)
  tab.value = 'updates'
}

async function removeUpdate(id: string) {
  if (!window.confirm('确定删除这条会后补充吗？')) return
  await api(`/api/meetings/${route.params.id}/updates/${id}`, { method: 'DELETE' })
  await load(false)
  tab.value = 'updates'
}

function applyPluginPatch(patch: { conclusions_markdown?: string; raw_notes_markdown?: string }) {
  if (!draft.value) return
  Object.assign(draft.value, patch)
  tab.value = 'notes'
  saved.value = false
}

onMounted(load)
</script>

<template>
  <main class="page detail-page">
    <p v-if="loading" class="empty-state">正在打开会议档案…</p>
    <div v-else-if="meeting && draft">
      <RouterLink class="back-link" to="/">← 返回会议档案</RouterLink>
      <header class="detail-hero">
        <div class="grow"><div class="tag-row"><span v-if="draft.project" class="tag tag-project">{{ draft.project }}</span><span v-if="draft.meeting_type" class="tag">{{ draft.meeting_type }}</span></div><h1>{{ meeting.title }}</h1><p>{{ new Date(meeting.meeting_date).toLocaleString('zh-CN') }} · {{ meeting.participants.join('、') || '未填写参与人' }}</p></div>
        <div class="hero-actions"><button class="button button-danger" @click="deleteMeeting">删除会议</button></div>
      </header>
      <nav class="detail-tabs" aria-label="会议详情区域">
        <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
        <button :class="{ active: tab === 'notes' }" @click="tab = 'notes'">会议记录</button>
        <button :class="{ active: tab === 'actions' }" @click="tab = 'actions'">行动项 <span>{{ openActions.length }}</span></button>
        <button :class="{ active: tab === 'attachments' }" @click="tab = 'attachments'">附件 <span>{{ meeting.attachments.length }}</span></button>
        <button :class="{ active: tab === 'updates' }" @click="tab = 'updates'">后续补充 <span>{{ meeting.updates.length }}</span></button>
      </nav>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <p v-if="saved" class="notice notice-success">会议已保存</p>

      <section v-if="tab === 'overview'" class="tab-content overview-grid">
        <article class="panel span-2"><p class="eyebrow">Key conclusions</p><h2>关键结论</h2><MarkdownView :source="draft.conclusions_markdown" empty-text="还没有整理关键结论" /></article>
        <article class="panel"><p class="eyebrow">Open actions</p><h2>{{ openActions.length }} 项待完成</h2><div v-if="openActions.length" class="mini-list"><p v-for="item in openActions.slice(0, 4)" :key="item.id"><span>○</span>{{ item.content }}</p></div><p v-else class="empty-inline">当前没有未完成行动项</p></article>
        <article class="panel"><p class="eyebrow">Attachments</p><h2>{{ meeting.attachments.length }} 个附件</h2><div class="mini-list"><p v-for="item in meeting.attachments.slice(0, 4)" :key="item.id">↳ {{ item.original_name }}</p></div><p v-if="!meeting.attachments.length" class="empty-inline">还没有上传附件</p></article>
        <PluginActionPanel class="span-2" :meeting-id="meeting.id" @apply="applyPluginPatch" />
      </section>

      <section v-else-if="tab === 'notes'" class="tab-content">
        <div class="panel meeting-meta-form"><div class="form-grid"><label class="span-2">会议标题<input v-model="draft.title" required /></label><label>项目<input v-model="draft.project" /></label><label>会议类型<input v-model="draft.meeting_type" /></label><label>会议时间<input v-model="dateInput" type="datetime-local" required /></label><label>参与人<input v-model="participantsInput" placeholder="用逗号分隔" /></label></div></div>
        <div class="editor-grid"><article class="panel"><div class="section-heading"><h2>原始会议记录</h2><span class="tag">Markdown</span></div><label class="sr-only" for="raw-notes">原始会议记录</label><textarea id="raw-notes" v-model="draft.raw_notes_markdown" rows="18" placeholder="记录讨论过程…" /></article><article class="panel preview-panel"><p class="eyebrow">Preview</p><MarkdownView :source="draft.raw_notes_markdown" /></article></div>
        <div class="editor-grid"><article class="panel"><div class="section-heading"><h2>关键结论</h2><span class="tag">Markdown</span></div><label class="sr-only" for="conclusions">关键结论</label><textarea id="conclusions" v-model="draft.conclusions_markdown" rows="14" placeholder="提炼决定与共识…" /></article><article class="panel preview-panel"><p class="eyebrow">Preview</p><MarkdownView :source="draft.conclusions_markdown" /></article></div>
        <div class="sticky-save"><span>最后修改者：{{ meeting.updated_by.display_name }}</span><button class="button button-primary" :disabled="saving" @click="saveMeeting">{{ saving ? '保存中…' : '保存会议' }}</button></div>
      </section>

      <section v-else-if="tab === 'actions'" class="tab-content"><article class="panel"><div class="section-heading"><div><p class="eyebrow">Next steps</p><h2>行动项</h2></div></div><ActionItemEditor :reset-key="actionResetKey" @save="createAction" /><div class="action-list"><article v-for="item in meeting.actions" :key="item.id" class="action-item" :class="{ done: item.status === 'done' }"><template v-if="editingAction === item.id"><ActionItemEditor :item="item" @save="saveAction(item, $event)" @remove="removeAction(item)" /></template><template v-else><span class="action-check">{{ item.status === 'done' ? '✓' : '○' }}</span><div class="grow"><strong>{{ item.content }}</strong><p>{{ item.owner || '未指定负责人' }}<template v-if="item.due_date"> · 截止 {{ item.due_date }}</template></p></div><button class="button button-small button-quiet" @click="editingAction = item.id">编辑</button></template></article></div></article></section>

      <section v-else-if="tab === 'attachments'" class="tab-content panel"><div class="section-heading"><div><p class="eyebrow">Files & images</p><h2>附件</h2></div></div><AttachmentPanel :meeting-id="meeting.id" :attachments="meeting.attachments" @changed="load(false)" /></section>

      <section v-else class="tab-content updates-layout"><article class="panel"><p class="eyebrow">Append update</p><h2>添加会后进展</h2><textarea v-model="updateDraft" rows="8" placeholder="使用 Markdown 记录新进展…" /><button class="button button-primary" @click="addUpdate">发布补充</button></article><div class="update-timeline"><article v-for="update in meeting.updates" :key="update.id" class="panel update-card"><div class="section-heading"><span>{{ update.created_by.display_name }} · {{ new Date(update.created_at).toLocaleString('zh-CN') }}</span><button class="button button-small button-danger" @click="removeUpdate(update.id)">删除</button></div><MarkdownView :source="update.content_markdown" /></article><p v-if="!meeting.updates.length" class="empty-state">还没有会后补充</p></div></section>
    </div>
    <p v-else class="notice notice-error">{{ error || '会议不存在' }}</p>
  </main>
</template>
