<script setup lang="ts">
import { computed, ref } from 'vue'
import { X } from '@lucide/vue'

import { api } from '../api/client'
import type { AgendaItem, Meeting } from '../domain/meetings'
import type { ActionPriority } from '../domain/outcomes'
import { useI18n } from '../i18n'
import MarkdownEditor from './MarkdownEditor.vue'
import PluginEditorSlot from './PluginEditorSlot.vue'

type Mode = 'decision' | 'action' | 'question'
const props = defineProps<{ mode: Mode; meeting: Meeting; item: AgendaItem }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const { tr } = useI18n()
const title = ref('')
const content = ref('')
const ownerId = ref('')
const dueDate = ref('')
const priority = ref<ActionPriority>('normal')
const saving = ref(false)
const error = ref('')
const labels = computed(() => ({
  decision: tr('决策', 'Decision'),
  action: tr('行动项', 'Action Item'),
  question: tr('开放问题', 'Open Question'),
}[props.mode]))
const assistantSlot = computed(() => ({
  decision: 'decision-composer',
  action: 'action-composer',
  question: 'question-composer',
}[props.mode]))

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
    error.value = caught instanceof Error ? caught.message : tr(`${labels.value}保存失败`, `Failed to save ${labels.value}`)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="outcome-composer" @submit.prevent="save">
    <header class="section-heading"><h3>{{ tr(`添加${labels}`, `Add ${labels}`) }}</h3><button type="button" class="icon-button" :aria-label="tr('关闭', 'Close')" @click="emit('close')"><X :size="18" :stroke-width="2" aria-hidden="true" /></button></header>
    <label v-if="mode === 'decision'">{{ tr('标题', 'Title') }}<input v-model="title" required /></label>
    <PluginEditorSlot :editor-label="tr(`${labels}内容`, `${labels} content`)" v-model="content" :data-testid="assistantSlot" target-type="meeting" :target-id="meeting.id" :slot="assistantSlot" :metadata="{ projectId: meeting.project.id, meetingId: meeting.id, agendaId: item.id, participants: meeting.participants.map((participant) => participant.user) }" @notice="error = $event">
      <template #editor="{ disabled, registerEditor }"><MarkdownEditor v-model="content" :label="tr(`${labels}内容`, `${labels} content`)" :disabled="saving || disabled" :register-editor="registerEditor" /></template>
    </PluginEditorSlot>
    <div v-if="mode !== 'decision'" class="outcome-fields">
      <label>{{ tr('负责人', 'Owner') }}<select v-model="ownerId"><option value="">{{ tr('未指定', 'Unassigned') }}</option><option v-for="participant in meeting.participants" :key="participant.user.id" :value="participant.user.id">{{ participant.user.display_name }}</option></select></label>
      <label v-if="mode === 'action'">{{ tr('截止日期', 'Due Date') }}<input v-model="dueDate" type="date" /></label>
      <label v-if="mode === 'action'">{{ tr('优先级', 'Priority') }}<select v-model="priority"><option value="low">{{ tr('低', 'Low') }}</option><option value="normal">{{ tr('普通', 'Normal') }}</option><option value="high">{{ tr('高', 'High') }}</option><option value="urgent">{{ tr('紧急', 'Urgent') }}</option></select></label>
    </div>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div class="form-actions"><button type="button" class="button button-quiet" @click="emit('close')">{{ tr('取消', 'Cancel') }}</button><button class="button button-primary" :disabled="saving || !content.trim()">{{ saving ? tr('保存中…', 'Saving…') : tr(`保存${labels}`, `Save ${labels}`) }}</button></div>
  </form>
</template>
