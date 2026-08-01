<script setup lang="ts">
import { ref } from 'vue'

import { api } from '../api/client'
import type { Attachment } from '../domain/meetings'

const props = withDefaults(defineProps<{
  targetType?: 'project' | 'meeting' | 'agenda_item'
  targetId?: string
  meetingId?: string
  attachments: Attachment[]
  canContribute: boolean
}>(), { targetType: 'meeting' })
const emit = defineEmits<{ changed: []; uploaded: [attachment: Attachment]; deleted: [id: string] }>()
const selected = ref<File | null>(null)
const busy = ref(false)
const error = ref('')
const maxBytes = 20 * 1024 * 1024

function pick(event: Event) {
  selected.value = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
}

const targetId = () => props.targetId ?? props.meetingId ?? ''
function fileUrl(attachment: Attachment) { return attachment.download_url || `/api/attachments/${props.targetType}/${targetId()}/${attachment.id}` }

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function upload() {
  if (!props.canContribute || !selected.value) return
  if (selected.value.size > maxBytes) {
    error.value = '单个附件不能超过 20 MB'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', selected.value)
    const attachment = await api<Attachment>(`/api/attachments/${props.targetType}/${targetId()}`, { method: 'POST', body })
    selected.value = null
    emit('uploaded', attachment)
    emit('changed')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '附件上传失败'
  } finally {
    busy.value = false
  }
}

async function remove(attachment: Attachment) {
  if (!props.canContribute || !attachment.can_delete) return
  if (!window.confirm(`确定删除附件“${attachment.original_name}”吗？`)) return
    await api(`/api/attachments/${attachment.target_type}/${attachment.target_id}/${attachment.id}`, { method: 'DELETE' })
  emit('deleted', attachment.id)
  emit('changed')
}
</script>

<template>
  <div class="attachment-panel">
    <div v-if="canContribute" class="upload-box">
      <div><strong>添加图片或文件</strong><p>单个附件不超过 20 MB</p></div>
      <input id="attachment-upload" class="file-input" type="file" aria-label="上传附件" @change="pick" />
      <label for="attachment-upload" class="button button-quiet">{{ selected?.name ?? '选择文件' }}</label>
      <button class="button button-primary" :disabled="!selected || busy" @click="upload">{{ busy ? '上传中…' : '上传' }}</button>
    </div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="attachments.length" class="attachment-grid">
      <article v-for="attachment in attachments" :key="attachment.id" class="attachment-card">
        <img v-if="attachment.attachment_type === 'image'" :src="fileUrl(attachment)" :alt="attachment.original_name" />
        <div v-else class="file-glyph" aria-hidden="true">DOC</div>
        <div class="attachment-meta"><strong :title="attachment.original_name">{{ attachment.original_name }}</strong><span>{{ formatSize(attachment.size) }} · {{ attachment.created_by.display_name }}</span></div>
        <div class="row-actions"><a class="button button-small button-quiet" :href="fileUrl(attachment)" download>下载</a><button v-if="attachment.can_delete" class="button button-small button-danger" @click="remove(attachment)">删除</button></div>
      </article>
    </div>
    <p v-else class="empty-state">还没有附件</p>
  </div>
</template>
