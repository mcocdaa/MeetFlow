<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'

type ConfigField = { key: string; type: 'string' | 'number' | 'boolean' | 'secret'; required?: boolean; label?: string; description?: string }
type PluginInfo = {
  id: string; name: string; version: string; description?: string; enabled: boolean; effective_enabled?: boolean
  api_version?: number; loaded?: boolean
  capabilities?: { actions?: string[]; exporters?: string[]; event_subscriptions?: string[]; ui_slots?: string[]; context_scopes?: string[]; external_network?: boolean }
  load_error?: string | null; config_schema?: { fields?: ConfigField[]; secrets?: ConfigField[] }
  config?: Record<string, unknown>
}
type PluginListResponse = {
  plugins: PluginInfo[]
  errors: Array<{ plugin_id: string; error_type: string; message: string }>
  events?: Array<{ event_id: string; event_type: string; status: string; attempts: number; last_error?: string | null }>
}

const plugins = ref<PluginInfo[]>([])
const pluginErrors = ref<PluginListResponse['errors']>([])
const drafts = reactive<Record<string, Record<string, string | number | boolean | null>>>({})
const saving = ref('')
const error = ref('')
const restartRequired = ref(false)
const unmatchedErrors = computed(() => pluginErrors.value.filter(
  (item) => !plugins.value.some((plugin) => plugin.id === item.plugin_id),
))
const failedEvents = ref<NonNullable<PluginListResponse['events']>>([])

function hydrate(plugin: PluginInfo) {
  const values: Record<string, string | number | boolean | null> = {}
  for (const field of plugin.config_schema?.fields ?? []) {
    const current = plugin.config?.[field.key]
    values[field.key] = typeof current === 'string' || typeof current === 'number' || typeof current === 'boolean' ? current : ''
  }
  for (const field of plugin.config_schema?.secrets ?? []) values[field.key] = ''
  drafts[plugin.id] = values
}

async function load() {
  error.value = ''
  try {
    const response = await api<PluginListResponse>('/api/admin/plugins')
    pluginErrors.value = response.errors
    failedEvents.value = (response.events ?? []).filter((event) => event.status === 'failed')
    plugins.value = response.plugins.map((plugin) => ({
      ...plugin,
      load_error: response.errors.find((item) => item.plugin_id === plugin.id)?.message ?? null,
    }))
    for (const plugin of plugins.value) hydrate(plugin)
    try {
      const events = await api<{ items: NonNullable<PluginListResponse['events']> }>('/api/admin/plugins/events?status=failed')
      failedEvents.value = events.items ?? []
    } catch {
      failedEvents.value = []
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '插件列表加载失败'
  }
}

async function saveConfig(plugin: PluginInfo) {
  saving.value = plugin.id
  const payload: Record<string, unknown> = {}
  for (const field of plugin.config_schema?.fields ?? []) payload[field.key] = drafts[plugin.id][field.key]
  for (const field of plugin.config_schema?.secrets ?? []) {
    const value = drafts[plugin.id][field.key]
    if (value !== '') payload[field.key] = value
  }
  try {
    await api(`/api/admin/plugins/${plugin.id}/config`, { method: 'PUT', body: JSON.stringify(payload) })
    await load()
  } finally {
    saving.value = ''
  }
}

async function clearSecret(plugin: PluginInfo, key: string) {
  if (!window.confirm('确定清除已保存的敏感配置吗？')) return
  await api(`/api/admin/plugins/${plugin.id}/config`, { method: 'PUT', body: JSON.stringify({ [key]: null }) })
  await load()
}

async function toggle(plugin: PluginInfo) {
  plugin.enabled = !plugin.enabled
  try {
    await api(`/api/admin/plugins/${plugin.id}/enabled`, {
      method: 'PUT', body: JSON.stringify({ enabled: plugin.enabled }),
    })
    restartRequired.value = true
    await load()
  } catch (reason) {
    plugin.enabled = !plugin.enabled
    error.value = reason instanceof Error ? reason.message : '插件状态更新失败'
  }
}

function secretConfigured(plugin: PluginInfo, key: string) {
  const value = plugin.config?.[key]
  return !!value && typeof value === 'object' && 'configured' in value && (value as { configured: boolean }).configured
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="page-heading"><div><p class="eyebrow">Extensions</p><h1>插件管理</h1><p>配置由服务器管理员安装的可信扩展。代码变更与启停需要重启。</p></div><span class="metric"><strong>{{ plugins.length }}</strong> 已发现</span></header>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <p v-if="restartRequired" class="notice notice-warning">插件启用状态已保存，重启后生效。</p>
    <div v-if="plugins.length" class="plugin-grid">
      <article v-for="plugin in plugins" :key="plugin.id" class="panel plugin-card">
        <div class="plugin-card-heading"><div class="plugin-icon">⌁</div><div class="grow"><div class="tag-row"><span class="tag">v{{ plugin.version }}</span><span v-if="plugin.load_error" class="status-pill" data-status="rejected">加载失败</span></div><h2>{{ plugin.name }}</h2><p>{{ plugin.description || plugin.id }}</p></div><label class="switch"><input :checked="plugin.enabled" type="checkbox" :aria-label="`启用 ${plugin.name}`" @change="toggle(plugin)" /><span></span></label></div>
        <p v-if="plugin.load_error" class="notice notice-error">{{ plugin.load_error }}</p>
        <div v-if="plugin.capabilities" class="plugin-capabilities" aria-label="插件能力">
          <span class="tag">API v{{ plugin.api_version ?? 1 }}</span>
          <span v-if="plugin.loaded" class="tag">已加载</span>
          <span v-for="capability in [...(plugin.capabilities.exporters ?? []), ...(plugin.capabilities.event_subscriptions ?? []), ...(plugin.capabilities.ui_slots ?? [])]" :key="capability" class="tag">{{ capability }}</span>
        </div>
        <p class="restart-note">状态变更：<span>重启后生效</span></p>
        <form v-if="plugin.config_schema" class="plugin-config" @submit.prevent="saveConfig(plugin)">
          <label v-for="field in plugin.config_schema.fields ?? []" :key="field.key">
            {{ field.label || field.key }}
            <input v-if="field.type === 'boolean'" v-model="drafts[plugin.id][field.key]" type="checkbox" />
            <input v-else-if="field.type === 'number'" v-model.number="drafts[plugin.id][field.key]" type="number" :required="field.required" />
            <input v-else v-model="drafts[plugin.id][field.key]" type="text" :required="field.required" />
            <small v-if="field.description">{{ field.description }}</small>
          </label>
          <div v-for="field in plugin.config_schema.secrets ?? []" :key="field.key" class="secret-field"><label>{{ field.label || field.key }}<input v-model="drafts[plugin.id][field.key]" type="password" autocomplete="new-password" :placeholder="secretConfigured(plugin, field.key) ? '留空则保持不变' : '尚未配置'" /></label><div class="secret-state"><span v-if="secretConfigured(plugin, field.key)" class="status-pill" data-status="active">已配置</span><button v-if="secretConfigured(plugin, field.key)" type="button" class="button button-small button-danger" @click="clearSecret(plugin, field.key)">清除</button></div></div>
          <button class="button button-primary" :disabled="saving === plugin.id">{{ saving === plugin.id ? '保存中…' : '保存配置' }}</button>
        </form>
      </article>
    </div>
    <div v-if="unmatchedErrors.length" class="plugin-errors"><p v-for="item in unmatchedErrors" :key="`${item.plugin_id}-${item.error_type}`" class="notice notice-error">{{ item.plugin_id }} · {{ item.message }}</p></div>
    <section v-if="failedEvents.length" class="plugin-errors" aria-labelledby="plugin-event-errors-title"><h2 id="plugin-event-errors-title">事件失败</h2><p v-for="event in failedEvents" :key="event.event_id" class="notice notice-error">{{ event.event_type }} · 已重试 {{ event.attempts }} 次<span v-if="event.last_error"> · {{ event.last_error }}</span></p></section>
    <div v-if="!plugins.length" class="empty-state"><strong>没有发现插件</strong><p>将插件挂载到服务器插件目录并重启后，它们会显示在这里。</p></div>
  </main>
</template>
