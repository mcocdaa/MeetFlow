<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { ProjectHealth } from '../domain/projects'
import MarkdownEditor from './MarkdownEditor.vue'
import PluginEditorSlot from './PluginEditorSlot.vue'

const { tr } = useI18n()

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
    error.value = errorMessage(reason, tr('进展发布失败', 'Failed to post update'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="project-update-composer" @submit.prevent="submit">
    <div class="composer-heading">
      <div><p class="eyebrow">{{ tr('进展更新', 'Progress update') }}</p><h3>{{ tr('追加项目进展', 'Post Project Update') }}</h3></div>
      <label>{{ tr('健康度', 'Health') }}<select v-model="health"><option value="on_track">{{ tr('进展正常', 'On Track') }}</option><option value="at_risk">{{ tr('存在风险', 'At Risk') }}</option><option value="off_track">{{ tr('偏离计划', 'Off Track') }}</option><option value="unset">{{ tr('未设置', 'Unset') }}</option></select></label>
    </div>
    <PluginEditorSlot :editor-label="tr('进展记录', 'Progress Update')" v-model="content" data-testid="project-update-editor" target-type="project" :target-id="projectId" slot="project-update-editor" :metadata="{ projectId }" @notice="error = $event">
      <template #editor="{ disabled, registerEditor }"><MarkdownEditor v-model="content" :label="tr('进展记录', 'Progress Update')" :placeholder="tr('用 Markdown 记录本次进展、风险或下一步…', 'Record progress, risks, or next steps in Markdown…')" :disabled="saving || disabled" :register-editor="registerEditor" /></template>
    </PluginEditorSlot>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div class="form-actions"><span class="muted">{{ tr('发布后形成一条独立历史记录', 'Creates an independent history entry when posted') }}</span><button class="button button-primary" :disabled="saving || !content.trim()">{{ saving ? tr('发布中…', 'Posting…') : tr('发布进展', 'Post Update') }}</button></div>
  </form>
</template>
