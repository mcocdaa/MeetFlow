<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api/client'
import type { Meeting } from '../domain/meetings'
import AttachmentPanel from './AttachmentPanel.vue'
import MarkdownEditor from './MarkdownEditor.vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps<{ meeting: Meeting }>()
const emit = defineEmits<{ reload: [] }>()
const amendmentOpen = ref(false)
const reason = ref('')
const content = ref('')
const saving = ref(false)
const error = ref('')
const snapshot = computed(() => props.meeting.current_snapshot?.snapshot_json ?? props.meeting.current_snapshot?.snapshot ?? {})
const snapshotMeeting = computed(() => (snapshot.value.meeting ?? {}) as Record<string, any>)
const snapshotAgenda = computed(() => (snapshot.value.agenda_items ?? []) as Array<Record<string, any>>)

async function addAmendment() {
  if (!reason.value.trim() || !content.value.trim()) return
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
    <section class="workspace-section completed-summary"><header class="section-heading"><div><p class="eyebrow">Trusted record</p><h2>会议完成链条</h2></div><div class="page-header-actions"><button class="button button-quiet" @click="amendmentOpen = !amendmentOpen">添加更正</button><button class="button button-danger" :disabled="saving" @click="reopen">重新打开会议</button></div></header><p class="snapshot-meta">快照 #{{ meeting.current_snapshot?.completion_number ?? '—' }} · 原始记录保持只读</p><MarkdownView :source="String(snapshotMeeting.summary_markdown ?? meeting.summary_markdown)" empty-text="本次会议未填写摘要" /></section>

    <form v-if="amendmentOpen" class="workspace-section amendment-form" @submit.prevent="addAmendment"><h2>添加更正</h2><p>更正会作为独立历史记录追加，不会修改完成快照。</p><label>更正原因<input v-model="reason" required /></label><label>更正内容<MarkdownEditor v-model="content" label="更正内容" /></label><div class="form-actions"><button type="button" class="button button-quiet" @click="amendmentOpen = false">取消</button><button class="button button-primary" :disabled="saving || !reason.trim() || !content.trim()">保存更正</button></div></form>
    <p v-if="error" class="notice notice-error">{{ error }}</p>

    <section class="workspace-section"><h2>议题与产出</h2><div class="completed-agenda-list"><article v-for="item in snapshotAgenda" :key="item.id"><div><span class="status-pill">{{ item.status }}</span><strong>{{ item.title }}</strong></div><p>{{ item.decisions?.length ?? 0 }} 个决策 · {{ item.actions?.length ?? 0 }} 个行动 · {{ item.open_questions?.length ?? 0 }} 个开放问题</p></article><p v-if="!snapshotAgenda.length" class="empty-inline">快照中没有议题</p></div></section>
    <section class="workspace-section"><h2>材料</h2><AttachmentPanel target-type="meeting" :target-id="meeting.id" :attachments="meeting.attachments ?? []" @changed="emit('reload')" /></section>
    <section class="workspace-section"><h2>更正历史</h2><article v-for="item in meeting.amendments ?? []" :key="item.id" class="amendment-item"><strong>{{ item.reason }}</strong><MarkdownView :source="item.content_markdown" /><small>{{ item.created_by.display_name }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></article><p v-if="!meeting.amendments?.length" class="empty-inline">尚未添加更正</p></section>
  </div>
</template>
