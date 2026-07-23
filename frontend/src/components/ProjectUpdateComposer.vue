<script setup lang="ts">
import { ref } from 'vue'

import { api } from '../api/client'
import type { ProjectHealth } from '../domain/projects'

const props = defineProps<{ projectId: string; health: ProjectHealth }>()
const emit = defineEmits<{ saved: [] }>()
const content = ref('')
const health = ref<ProjectHealth>(props.health)
const saving = ref(false)
const error = ref('')

async function submit() {
  if (!content.value.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/projects/${props.projectId}/updates`, {
      method: 'POST',
      body: JSON.stringify({ health: health.value, content_markdown: content.value, source: 'human' }),
    })
    content.value = ''
    emit('saved')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '进展发布失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="project-update-composer" @submit.prevent="submit">
    <div class="composer-heading"><div><p class="eyebrow">Progress update</p><h3>追加项目进展</h3></div><label>健康度<select v-model="health"><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label></div>
    <label class="sr-only" for="project-progress">进展记录</label>
    <textarea id="project-progress" v-model="content" aria-label="进展记录" rows="4" placeholder="用 Markdown 记录本次进展、风险或下一步…"></textarea>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div class="form-actions"><span class="muted">发布后形成一条独立历史记录</span><button class="button button-primary" :disabled="saving || !content.trim()">{{ saving ? '发布中…' : '发布进展' }}</button></div>
  </form>
</template>
