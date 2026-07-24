<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'

type SchemaProperty = { title?: string; type?: string; enum?: Array<string | number>; default?: unknown }
type PluginAction = {
  action_id: string
  label: string
  description: string
  input_schema: { properties?: Record<string, SchemaProperty>; required?: string[] }
  target_types?: string[]
}

const props = defineProps<{ targetType: 'meeting' | 'project'; targetId: string }>()
const emit = defineEmits<{ submitted: [] }>()
const actions = ref<PluginAction[]>([])
const inputs = reactive<Record<string, Record<string, unknown>>>({})
const running = ref('')
const error = ref('')
const notice = ref('')

const visibleActions = computed(() => actions.value.filter((action) =>
  (action.target_types ?? ['meeting']).includes(props.targetType),
))

onMounted(async () => {
  try {
    const response = await api<PluginAction[]>('/api/plugins/actions')
    actions.value = Array.isArray(response) ? response : []
    for (const action of actions.value) {
      inputs[action.action_id] = {}
      for (const [key, schema] of Object.entries(action.input_schema?.properties ?? {})) {
        inputs[action.action_id][key] = schema.default ?? (schema.type === 'boolean' ? false : schema.enum?.[0] ?? '')
      }
    }
  } catch { actions.value = [] }
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
  notice.value = ''
  const payload = buildPayload(action)
  if (!payload) return
  running.value = action.action_id
  try {
    await api('/api/plugin-jobs', {
      method: 'POST',
      body: JSON.stringify({
        action_id: action.action_id,
        target_type: props.targetType,
        target_id: props.targetId,
        input: payload,
      }),
    })
    notice.value = 'AI 正在生成草稿；完成后会显示在当前页面。'
    emit('submitted')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'AI 任务创建失败'
  } finally {
    running.value = ''
  }
}
</script>

<template>
  <section v-if="visibleActions.length" class="plugin-action-panel">
    <div class="section-heading"><div><p class="eyebrow">AI assistance</p><h2>AI 工作助手</h2></div></div>
    <div class="plugin-actions">
      <article v-for="action in visibleActions" :key="action.action_id" class="plugin-action-card">
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
        <button class="button button-quiet" :disabled="!!running" @click="run(action)">{{ running === action.action_id ? '加入任务中…' : action.label }}</button>
      </article>
    </div>
    <p v-if="notice" class="notice">{{ notice }}</p>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
  </section>
</template>
