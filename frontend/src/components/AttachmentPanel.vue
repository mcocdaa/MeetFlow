<script setup lang="ts">
import { ref } from 'vue'
import { FileText } from '@lucide/vue'
import { NButton, NIcon, NPopconfirm, NUpload, useMessage, type UploadFileInfo } from 'naive-ui'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { Attachment } from '../domain/meetings'
import { useI18n } from '../i18n'

const props = withDefaults(defineProps<{
  targetType?: 'project' | 'meeting' | 'agenda_item'
  targetId?: string
  attachments: Attachment[]
  canContribute: boolean
}>(), { targetType: 'meeting' })
const emit = defineEmits<{ uploaded: [attachment: Attachment]; deleted: [id: string] }>()
const { tr } = useI18n()
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
    error.value = tr('单个附件不能超过 20 MB', 'Each attachment cannot exceed 20 MB')
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
    error.value = errorMessage(reason, tr('附件上传失败', 'Failed to upload attachment'))
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
    message.error(errorMessage(reason, tr('附件删除失败', 'Failed to delete attachment')))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="attachment-panel">
    <div v-if="canContribute" class="upload-box">
      <div><strong>{{ tr('添加图片或文件', 'Add images or files') }}</strong><p>{{ tr('单个附件不超过 20 MB', 'Max 20 MB per file') }}</p></div>
      <n-upload
        :show-file-list="false"
        :default-upload="false"
        :disabled="busy"
        :input-props="{ 'aria-label': tr('上传附件', 'Upload attachment') }"
        @change="pick"
      >
        <n-button quaternary :disabled="busy">{{ selected?.name ?? tr('选择文件', 'Choose File') }}</n-button>
      </n-upload>
      <n-button type="primary" :loading="busy" :disabled="!selected || busy" @click="upload">{{ tr('上传', 'Upload') }}</n-button>
    </div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="attachments.length" class="attachment-grid">
      <article v-for="attachment in attachments" :key="attachment.id" class="attachment-card">
        <img v-if="attachment.attachment_type === 'image'" :src="fileUrl(attachment)" :alt="attachment.original_name" />
        <div v-else class="file-glyph" aria-hidden="true"><n-icon :size="24"><FileText /></n-icon></div>
        <div class="attachment-meta"><strong :title="attachment.original_name">{{ attachment.original_name }}</strong><span>{{ formatSize(attachment.size) }} · {{ attachment.created_by.display_name }}</span></div>
        <div class="row-actions">
          <a class="button button-small button-quiet" :href="fileUrl(attachment)" download>{{ tr('下载', 'Download') }}</a>
          <n-popconfirm v-if="attachment.can_delete" :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="remove(attachment)">
            <template #trigger><n-button size="small" type="error" quaternary :disabled="busy">{{ tr('删除', 'Delete') }}</n-button></template>
            {{ tr(`确定删除附件“${attachment.original_name}”吗？`, `Delete attachment "${attachment.original_name}"?`) }}
          </n-popconfirm>
        </div>
      </article>
    </div>
    <p v-else class="empty-state">{{ tr('还没有附件', 'No attachments yet') }}</p>
  </div>
</template>
