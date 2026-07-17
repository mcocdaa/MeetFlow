<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'

type SchemaProperty = { title?: string; type?: string; enum?: Array<string | number>; default?: unknown }
type PluginAction = { action_id: string; label: string; description: string; input_schema: { properties?: Record<string, SchemaProperty>; required?: string[] } }
type PluginResult = { markdown?: string; suggested_patch?: { conclusions_markdown?: string; raw_notes_markdown?: string }; data?: unknown }
const props = defineProps<{ meetingId: string }>()
const emit = defineEmits<{ apply: [patch: { conclusions_markdown?: string; raw_notes_markdown?: string }] }>()
const actions = ref<PluginAction[]>([])
const inputs = reactive<Record<string, Record<string, unknown>>>({})
const running = ref('')
const error = ref('')
const result = ref<PluginResult | null>(null)
const editableMarkdown = ref('')
const editablePatch = ref<{ conclusions_markdown?: string; raw_notes_markdown?: string }>({})

onMounted(async () => {
  try {
    actions.value = (await api<PluginAction[]>('/api/plugins/actions')) ?? []
    for (const action of actions.value) {
      inputs[action.action_id] = {}
      for (const [key, schema] of Object.entries(action.input_schema?.properties ?? {})) {
        inputs[action.action_id][key] = schema.default ?? (schema.type === 'boolean' ? false : schema.enum?.[0] ?? '')
      }
    }
  }
  catch { actions.value = [] }
})

function buildPayload(action: PluginAction): Record<string, unknown> | null {
  const payload: Record<string, unknown> = {}
  const required = new Set(action.input_schema?.required ?? [])
  for (const [key, schema] of Object.entries(action.input_schema?.properties ?? {})) {
    const value = inputs[action.action_id]?.[key]
    const blank = value === null || value === undefined || (typeof value === 'string' && !value.trim())
    if (blank) {
      if (required.has(key)) {
        error.value = `请填写${schema.title ?? key}`
        return null
      }
      continue
    }
    payload[key] = value
  }
  return payload
}

async function run(action: PluginAction) {
  error.value = ''
  const payload = buildPayload(action)
  if (!payload) return
  running.value = action.action_id
  result.value = null
  try {
    const response = await api<PluginResult>(`/api/meetings/${props.meetingId}/plugin-actions/${action.action_id}`, {
      method: 'POST', body: JSON.stringify(payload),
    })
    result.value = response
    editableMarkdown.value = response.markdown ?? ''
    editablePatch.value = { ...(response.suggested_patch ?? {}) }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '插件动作执行失败'
  } finally {
    running.value = ''
  }
}

function applyDraft() {
  emit('apply', { ...editablePatch.value })
}
</script>

<template>
  <section v-if="actions.length || result" class="plugin-action-panel">
    <div class="section-heading"><div><p class="eyebrow">Extensions</p><h2>会议工具</h2></div></div>
    <div class="plugin-actions">
      <article v-for="action in actions" :key="action.action_id" class="plugin-action-card">
        <div><strong>{{ action.label }}</strong><p>{{ action.description }}</p></div>
        <div v-if="action.input_schema?.properties" class="mini-fields">
          <label v-for="(schema, key) in action.input_schema.properties" :key="key">
            {{ schema.title ?? key }}
            <input v-if="schema.type === 'boolean'" v-model="inputs[action.action_id][key]" type="checkbox" />
            <select v-else-if="schema.enum" v-model="inputs[action.action_id][key]" :required="action.input_schema.required?.includes(String(key))"><option v-for="choice in schema.enum" :key="choice" :value="choice">{{ choice }}</option></select>
            <input v-else-if="schema.type === 'number' || schema.type === 'integer'" v-model.number="inputs[action.action_id][key]" type="number" :step="schema.type === 'integer' ? 1 : 'any'" :required="action.input_schema.required?.includes(String(key))" />
            <input v-else v-model="inputs[action.action_id][key]" :required="action.input_schema.required?.includes(String(key))" />
          </label>
        </div>
        <button class="button button-quiet" :disabled="!!running" @click="run(action)">{{ running === action.action_id ? '运行中…' : action.label }}</button>
      </article>
    </div>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div v-if="result" class="draft-panel">
      <div><span class="status-pill" data-status="pending">草稿 · 尚未保存</span><h3>插件生成结果</h3></div>
      <label v-if="editableMarkdown">Markdown 结果<textarea v-model="editableMarkdown" rows="8" /></label>
      <label v-if="'conclusions_markdown' in editablePatch">建议关键结论<textarea v-model="editablePatch.conclusions_markdown" rows="8" /></label>
      <label v-if="'raw_notes_markdown' in editablePatch">建议会议记录<textarea v-model="editablePatch.raw_notes_markdown" rows="8" /></label>
      <button v-if="Object.keys(editablePatch).length" class="button button-primary" @click="applyDraft">应用到会议草稿</button>
    </div>
  </section>
</template>
