<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '../api/client'
import { session } from '../auth/session'
import type { ProjectDetail } from '../domain/projects'

type Kind = 'meeting' | 'series' | 'decision' | 'action'
const props = defineProps<{ kind: Kind; project: ProjectDetail }>()
const emit = defineEmits<{ close: []; created: [kind: Kind, entity: Record<string, unknown>] }>()
const title = ref('')
const content = ref('')
const start = ref('')
const end = ref('')
const recurrence = ref('')
const saving = ref(false)
const error = ref('')
const label = computed(() => ({ meeting: '添加会议', series: '添加系列', decision: '添加决策', action: '添加行动项' }[props.kind]))

async function save() {
  if (saving.value || !title.value.trim() || (props.kind === 'meeting' && (!start.value || !end.value)) || (props.kind === 'action' && !content.value.trim())) return
  saving.value = true; error.value = ''
  try {
    let entity: Record<string, unknown>
    if (props.kind === 'meeting') {
      entity = await api(`/api/projects/${props.project.id}/meetings`, { method: 'POST', body: JSON.stringify({ title: title.value.trim(), purpose_markdown: content.value, scheduled_start: new Date(start.value).toISOString(), scheduled_end: new Date(end.value).toISOString(), host_user_id: session.user?.id ?? null, recorder_user_id: session.user?.id ?? null, summary_markdown: '', raw_notes_markdown: '', participants: session.user ? [{ user_id: session.user.id, participation_role: 'host' }] : [] }) }) as Record<string, unknown>
    } else if (props.kind === 'series') {
      entity = await api(`/api/projects/${props.project.id}/meeting-series`, { method: 'POST', body: JSON.stringify({ title: title.value.trim(), purpose_markdown: content.value, recurrence_description: recurrence.value, default_duration_minutes: 60, default_host_user_id: session.user?.id ?? null, default_recorder_user_id: session.user?.id ?? null, participants: [] }) }) as Record<string, unknown>
    } else if (props.kind === 'decision') {
      entity = await api(`/api/projects/${props.project.id}/decisions`, { method: 'POST', body: JSON.stringify({ title: title.value.trim(), decision_markdown: content.value || title.value.trim(), rationale_markdown: '', reviewer_ids: [] }) }) as Record<string, unknown>
    } else {
      entity = await api(`/api/projects/${props.project.id}/actions`, { method: 'POST', body: JSON.stringify({ project_id: props.project.id, content: content.value.trim(), owner_user_id: null, due_date: null, priority: 'normal' }) }) as Record<string, unknown>
    }
    emit('created', props.kind, entity)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : `${label.value}失败` }
  finally { saving.value = false }
}
</script>

<template>
  <form class="project-create-panel" @submit.prevent="save">
    <label v-if="kind !== 'action'">{{ kind === 'decision' ? '决策标题' : kind === 'series' ? '系列标题' : '会议标题' }}<input v-model.trim="title" required /></label>
    <label v-if="kind === 'meeting'">开始时间<input v-model="start" type="datetime-local" required /></label>
    <label v-if="kind === 'meeting'">结束时间<input v-model="end" type="datetime-local" required /></label>
    <label v-if="kind === 'series'">重复说明<input v-model.trim="recurrence" placeholder="例如：每周一 10:00" /></label>
    <label>{{ kind === 'action' ? '行动项内容' : kind === 'decision' ? '决策内容' : '说明' }}<textarea v-model="content" rows="5" :required="kind === 'action'" /></label>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div class="form-actions"><button type="button" class="button button-quiet" @click="emit('close')">取消</button><button class="button button-primary" :disabled="saving">{{ saving ? '保存中…' : label }}</button></div>
  </form>
</template>
