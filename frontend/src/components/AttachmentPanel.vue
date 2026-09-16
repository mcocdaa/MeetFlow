<script setup lang="ts">
import { ref } from 'vue'
import { FileText } from '@lucide/vue'
import { NButton, NIcon, NPopconfirm, NUpload, useMessage, type UploadFileInfo } from 'naive-ui'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { Attachment } from '../domain/meetings'

const props = withDefaults(defineProps<{
  targetType?: 'project' | 'meeting' | 'agenda_item'
  targetId?: string
  attachments: Attachment[]
  canContribute: boolean
}>(), { targetType: 'meeting' })
const emit = defineEmits<{ uploaded: [attachment: Attachment]; deleted: [id: string] }>()
const message = useMessage()
const selected = ref<File | null>(null)
const busy = ref(false)
const error = ref('')
const maxBytes = 20 * 1024 * 1024

function pick(data: { file: UploadFileInfo }) {
  selected.value = data.file.file ?? null
  error.value = ''
}

const targetId = () => props.targetId ?? ''
function fileUrl(attachment: Attachment) { return attachment.download_url || `/api/attachments/${props.targetType}/${targetId()}/${attachment.id}` }

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function upload() {
  if (!props.canContribute || !selected.value || busy.value) return
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
  } catch (reason) {
    error.value = errorMessage(reason, '附件上传失败')
  } finally {
    busy.value = false
  }
}

async function remove(attachment: Attachment) {
  if (!props.canContribute || !attachment.can_delete || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/attachments/${attachment.target_type}/${attachment.target_id}/${attachment.id}`, { method: 'DELETE' })
    emit('deleted', attachment.id)
  } catch (reason) {
    message.error(errorMessage(reason, '附件删除失败'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="attachment-panel">
    <div v-if="canContribute" class="upload-box">
      <div><strong>添加图片或文件</strong><p>单个附件不超过 20 MB</p></div>
      <n-upload
        :show-file-list="false"
        :default-upload="false"
        :disabled="busy"
        :input-props="{ 'aria-label': '上传附件' }"
        @change="pick"
      >
        <n-button quaternary :disabled="busy">{{ selected?.name ?? '选择文件' }}</n-button>
      </n-upload>
      <n-button type="primary" :loading="busy" :disabled="!selected || busy" @click="upload">上传</n-button>
    </div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="attachments.length" class="attachment-grid">
      <article v-for="attachment in attachments" :key="attachment.id" class="attachment-card">
        <img v-if="attachment.attachment_type === 'image'" :src="fileUrl(attachment)" :alt="attachment.original_name" />
        <div v-else class="file-glyph" aria-hidden="true"><n-icon :size="24"><FileText /></n-icon></div>
        <div class="attachment-meta"><strong :title="attachment.original_name">{{ attachment.original_name }}</strong><span>{{ formatSize(attachment.size) }} · {{ attachment.created_by.display_name }}</span></div>
        <div class="row-actions">
          <a class="button button-small button-quiet" :href="fileUrl(attachment)" download>下载</a>
          <n-popconfirm v-if="attachment.can_delete" positive-text="确认" negative-text="取消" @positive-click="remove(attachment)">
            <template #trigger><n-button size="small" type="error" quaternary :disabled="busy">删除</n-button></template>
            确定删除附件“{{ attachment.original_name }}”吗？
          </n-popconfirm>
        </div>
      </article>
    </div>
    <p v-else class="empty-state">还没有附件</p>
  </div>
</template>
