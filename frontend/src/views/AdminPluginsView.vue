<script setup lang="ts">
import { Puzzle } from '@lucide/vue'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NIcon,
  NInput,
  NInputNumber,
  NPopconfirm,
  NSwitch,
  NTag,
  type DataTableColumns,
} from 'naive-ui'
import { computed, h, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'

type ConfigField = { key: string; type: 'string' | 'number' | 'boolean' | 'secret'; required?: boolean; label?: string; description?: string }
type PluginInfo = {
  id: string; name: string; version: string; description?: string; enabled: boolean; effective_enabled?: boolean
  api_version?: number; loaded?: boolean
  capabilities?: { actions?: string[]; exporters?: string[]; event_subscriptions?: string[]; ui_slots?: string[]; context_scopes?: string[]; external_network?: boolean }
  load_error?: string | null; config_schema?: { fields?: ConfigField[]; secrets?: ConfigField[] }
  config?: Record<string, unknown>
}
type PluginEvent = { event_id: string; event_type: string; status: string; attempts: number; last_error?: string | null }
type PluginListResponse = {
  plugins: PluginInfo[]
  errors: Array<{ plugin_id: string; error_type: string; message: string }>
  events?: PluginEvent[]
}

const EVENT_LIMIT = 50

const plugins = ref<PluginInfo[]>([])
const pluginErrors = ref<PluginListResponse['errors']>([])
const drafts = reactive<Record<string, Record<string, string | number | boolean | null>>>({})
const saving = ref('')
const toggling = ref('')
const error = ref('')
const restartRequired = ref(false)
const retryingEvent = ref('')
const failedEvents = ref<PluginEvent[]>([])
const unmatchedErrors = computed(() => pluginErrors.value.filter(
  (item) => !plugins.value.some((plugin) => plugin.id === item.plugin_id),
))

function hydrate(plugin: PluginInfo) {
  const values: Record<string, string | number | boolean | null> = {}
  for (const field of plugin.config_schema?.fields ?? []) {
    const current = plugin.config?.[field.key]
    values[field.key] = typeof current === 'string' || typeof current === 'number' || typeof current === 'boolean' ? current : ''
  }
  for (const field of plugin.config_schema?.secrets ?? []) values[field.key] = ''
  drafts[plugin.id] = values
}

function draftValue(plugin: PluginInfo, key: string): string | number | boolean | null {
  return drafts[plugin.id]?.[key] ?? null
}

function stringDraft(plugin: PluginInfo, key: string): string | null {
  const value = draftValue(plugin, key)
  return typeof value === 'string' ? value : null
}

function numberDraft(plugin: PluginInfo, key: string): number | null {
  const value = draftValue(plugin, key)
  return typeof value === 'number' ? value : null
}

function setDraft(plugin: PluginInfo, key: string, value: string | number | boolean | null) {
  drafts[plugin.id][key] = value
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
      const events = await api<{ items: PluginEvent[] }>(`/api/admin/plugins/events?status=failed&limit=${EVENT_LIMIT}`)
      failedEvents.value = events.items ?? []
    } catch {
      // Keep failedEvents from /api/admin/plugins as the fallback.
    }
  } catch (reason) {
    error.value = errorMessage(reason, '插件列表加载失败')
  }
}

async function saveConfig(plugin: PluginInfo) {
  if (saving.value) return
  saving.value = plugin.id
  error.value = ''
  const payload: Record<string, unknown> = {}
  for (const field of plugin.config_schema?.fields ?? []) payload[field.key] = drafts[plugin.id][field.key]
  for (const field of plugin.config_schema?.secrets ?? []) {
    const value = drafts[plugin.id][field.key]
    if (value !== '') payload[field.key] = value
  }
  try {
    await api(`/api/admin/plugins/${plugin.id}/config`, { method: 'PUT', body: JSON.stringify(payload) })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, '插件配置保存失败')
  } finally {
    saving.value = ''
  }
}

async function clearSecret(plugin: PluginInfo, key: string) {
  error.value = ''
  try {
    await api(`/api/admin/plugins/${plugin.id}/config`, { method: 'PUT', body: JSON.stringify({ [key]: null }) })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, '敏感配置清除失败')
  }
}

async function toggle(plugin: PluginInfo, value: boolean) {
  if (toggling.value) return
  toggling.value = plugin.id
  const previous = plugin.enabled
  plugin.enabled = value
  error.value = ''
  try {
    await api(`/api/admin/plugins/${plugin.id}/enabled`, {
      method: 'PUT', body: JSON.stringify({ enabled: value }),
    })
    restartRequired.value = true
    await load()
  } catch (reason) {
    plugin.enabled = previous
    error.value = errorMessage(reason, '插件状态更新失败')
  } finally {
    toggling.value = ''
  }
}

async function retryEvent(eventId: string) {
  if (retryingEvent.value) return
  retryingEvent.value = eventId
  error.value = ''
  try {
    await api(`/api/admin/plugins/events/${encodeURIComponent(eventId)}/retry`, { method: 'POST' })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, '插件事件重试失败')
  } finally {
    retryingEvent.value = ''
  }
}

function secretConfigured(plugin: PluginInfo, key: string) {
  const value = plugin.config?.[key]
  return !!value && typeof value === 'object' && 'configured' in value && (value as { configured: boolean }).configured
}

const eventColumns = computed<DataTableColumns<PluginEvent>>(() => {
  const retrying = retryingEvent.value
  return [
    { title: '事件类型', key: 'event_type', minWidth: 200 },
    { title: '尝试次数', key: 'attempts', minWidth: 100 },
    { title: '最后错误', key: 'last_error', minWidth: 220, render: (event) => event.last_error || '—' },
    {
      title: '操作',
      key: 'actions',
      minWidth: 120,
      render: (event) => h(NButton, {
        size: 'small',
        disabled: retrying !== '',
        loading: retrying === event.event_id,
        onClick: () => retryEvent(event.event_id),
      }, { default: () => (retrying === event.event_id ? '重试中…' : '重试') }),
    },
  ]
})

onMounted(() => { void load() })
</script>

<template>
  <main class="page">
    <header class="page-heading"><div><p class="eyebrow">Extensions</p><h1>插件管理</h1><p>配置由服务器管理员安装的可信扩展。代码变更与启停需要重启。</p></div><span class="metric"><strong>{{ plugins.length }}</strong> 已发现</span></header>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <n-alert v-if="restartRequired" type="warning" class="restart-notice">插件启用状态已保存，重启后生效。</n-alert>
    <n-grid v-if="plugins.length" class="plugin-grid" :cols="2" :x-gap="16" :y-gap="16">
      <n-grid-item v-for="plugin in plugins" :key="plugin.id">
        <n-card class="plugin-card" size="small">
          <div class="plugin-card-heading">
            <div class="plugin-icon" aria-hidden="true"><n-icon :size="20"><Puzzle /></n-icon></div>
            <div class="grow">
              <div class="tag-row"><n-tag size="small" :bordered="false">v{{ plugin.version }}</n-tag><StatusPill v-if="plugin.load_error" status="rejected" label="加载失败" /></div>
              <h2>{{ plugin.name }}</h2>
              <p>{{ plugin.description || plugin.id }}</p>
            </div>
            <n-switch
              :value="plugin.enabled"
              :disabled="Boolean(toggling)"
              :aria-label="`启用 ${plugin.name}`"
              @update:value="(value: boolean) => toggle(plugin, value)"
            />
          </div>
          <p v-if="plugin.load_error" class="notice notice-error">{{ plugin.load_error }}</p>
          <div v-if="plugin.capabilities" class="plugin-capabilities" aria-label="插件能力">
            <n-tag size="small" :bordered="false">API v{{ plugin.api_version ?? 1 }}</n-tag>
            <n-tag v-if="plugin.loaded" size="small" :bordered="false">已加载</n-tag>
            <n-tag v-for="scope in plugin.capabilities.context_scopes ?? []" :key="`scope-${scope}`" size="small" :bordered="false">上下文范围：{{ scope }}</n-tag>
            <n-tag v-if="plugin.capabilities.external_network" class="capability-warning" size="small" type="warning" :bordered="false">可访问外部网络</n-tag>
            <n-tag v-for="capability in [...(plugin.capabilities.exporters ?? []), ...(plugin.capabilities.event_subscriptions ?? []), ...(plugin.capabilities.ui_slots ?? [])]" :key="capability" size="small" :bordered="false">{{ capability }}</n-tag>
          </div>
          <p class="restart-note">状态变更：<span>重启后生效</span></p>
          <n-form v-if="plugin.config_schema" class="plugin-config" label-placement="top" :show-require-mark="false" @submit.prevent>
            <n-form-item v-for="field in plugin.config_schema.fields ?? []" :key="field.key" :label="field.label || field.key">
              <n-switch
                v-if="field.type === 'boolean'"
                :value="Boolean(draftValue(plugin, field.key))"
                :aria-label="field.label || field.key"
                @update:value="(value: boolean) => setDraft(plugin, field.key, value)"
              />
              <n-input-number
                v-else-if="field.type === 'number'"
                :value="numberDraft(plugin, field.key)"
                :input-props="{ 'aria-label': field.label || field.key, required: field.required }"
                @update:value="(value: number | null) => setDraft(plugin, field.key, value)"
              />
              <n-input
                v-else
                :value="stringDraft(plugin, field.key)"
                :input-props="{ 'aria-label': field.label || field.key, required: field.required }"
                @update:value="(value: string) => setDraft(plugin, field.key, value)"
              />
              <template #feedback><span v-if="field.description">{{ field.description }}</span></template>
            </n-form-item>
            <n-form-item v-for="field in plugin.config_schema.secrets ?? []" :key="field.key" :label="field.label || field.key">
              <n-input
                type="password"
                show-password-on="click"
                autocomplete="new-password"
                :value="stringDraft(plugin, field.key)"
                :input-props="{ 'aria-label': field.label || field.key, autocomplete: 'new-password' }"
                :placeholder="secretConfigured(plugin, field.key) ? '留空则保持不变' : '尚未配置'"
                @update:value="(value: string) => setDraft(plugin, field.key, value)"
              />
              <template #feedback>
                <span v-if="secretConfigured(plugin, field.key)" class="secret-state">
                  <StatusPill status="active" label="已配置" />
                  <n-popconfirm positive-text="确认清除" negative-text="取消" @positive-click="clearSecret(plugin, field.key)">
                    <template #trigger>
                      <n-button size="small" type="error" quaternary :aria-label="`清除 ${field.label || field.key}`">清除</n-button>
                    </template>
                    确定清除已保存的敏感配置吗？
                  </n-popconfirm>
                </span>
              </template>
            </n-form-item>
            <n-button type="primary" :loading="saving === plugin.id" :disabled="Boolean(saving)" @click="saveConfig(plugin)">{{ saving === plugin.id ? '保存中…' : '保存配置' }}</n-button>
          </n-form>
        </n-card>
      </n-grid-item>
    </n-grid>
    <div v-if="unmatchedErrors.length" class="plugin-errors"><p v-for="item in unmatchedErrors" :key="`${item.plugin_id}-${item.error_type}`" class="notice notice-error">{{ item.plugin_id }} · {{ item.message }}</p></div>
    <section v-if="failedEvents.length" class="plugin-errors" aria-labelledby="plugin-event-errors-title">
      <h2 id="plugin-event-errors-title">事件失败</h2>
      <n-data-table :columns="eventColumns" :data="failedEvents" :bordered="false" size="small" />
      <p class="plugin-events-note">最多显示 {{ EVENT_LIMIT }} 条，可用状态筛选</p>
    </section>
    <div v-if="!plugins.length" class="empty-state"><strong>没有发现插件</strong><p>将插件挂载到服务器插件目录并重启后，它们会显示在这里。</p></div>
  </main>
</template>

<style scoped>
.plugin-card-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.plugin-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--green-soft, #d9efe8);
  color: var(--green-dark, #075044);
}

.plugin-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}

.secret-state {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.plugin-events-note {
  margin: 8px 0 0;
  color: var(--muted, #66727f);
  font-size: 13px;
}
</style>
