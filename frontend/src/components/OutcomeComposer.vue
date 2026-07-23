<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api/client'
import type { AgendaItem, Meeting } from '../domain/meetings'
import type { ActionPriority } from '../domain/outcomes'
import MarkdownEditor from './MarkdownEditor.vue'

type Mode = 'decision' | 'action' | 'question'
const props = defineProps<{ mode: Mode; meeting: Meeting; item: AgendaItem }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const title = ref('')
const content = ref('')
const ownerId = ref('')
const dueDate = ref('')
const priority = ref<ActionPriority>('normal')
const saving = ref(false)
const error = ref('')
const labels = computed(() => ({ decision: '决策', action: '行动项', question: '开放问题' }[props.mode]))

async function save() {
  if (!content.value.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    if (props.mode === 'decision') {
      await api(`/api/projects/${props.meeting.project.id}/decisions`, { method: 'POST', body: JSON.stringify({ meeting_id: props.meeting.id, agenda_item_id: props.item.id, title: title.value.trim() || content.value.trim().slice(0, 80), decision_markdown: content.value, rationale_markdown: '', reviewer_ids: [] }) })
    } else if (props.mode === 'action') {
      await api(`/api/projects/${props.meeting.project.id}/actions`, { method: 'POST', body: JSON.stringify({ project_id: props.meeting.project.id, meeting_id: props.meeting.id, agenda_item_id: props.item.id, content: content.value.trim(), owner_user_id: ownerId.value || null, due_date: dueDate.value || null, priority: priority.value }) })
    } else {
      await api(`/api/projects/${props.meeting.project.id}/open-questions`, { method: 'POST', body: JSON.stringify({ meeting_id: props.meeting.id, agenda_item_id: props.item.id, question_markdown: content.value, owner_user_id: ownerId.value || null }) })
    }
    emit('saved')
    emit('close')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : `${labels.value}保存失败`
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="outcome-composer" @submit.prevent="save">
    <header class="section-heading"><h3>添加{{ labels }}</h3><button type="button" class="icon-button" aria-label="关闭" @click="emit('close')">×</button></header>
    <label v-if="mode === 'decision'">标题<input v-model="title" required /></label>
    <label>{{ mode === 'question' ? '问题' : mode === 'action' ? '行动内容' : '决策内容' }}<MarkdownEditor v-model="content" :label="`${labels}内容`" /></label>
    <div v-if="mode !== 'decision'" class="outcome-fields">
      <label>负责人<select v-model="ownerId"><option value="">未指定</option><option v-for="participant in meeting.participants" :key="participant.user.id" :value="participant.user.id">{{ participant.user.display_name }}</option></select></label>
      <label v-if="mode === 'action'">截止日期<input v-model="dueDate" type="date" /></label>
      <label v-if="mode === 'action'">优先级<select v-model="priority"><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
    </div>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div class="form-actions"><button type="button" class="button button-quiet" @click="emit('close')">取消</button><button class="button button-primary" :disabled="saving || !content.trim()">{{ saving ? '保存中…' : `保存${labels}` }}</button></div>
  </form>
</template>
