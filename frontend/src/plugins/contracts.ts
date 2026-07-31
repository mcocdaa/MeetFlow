import type { Component } from 'vue'

export type PluginEditorContext = {
  targetType: string
  targetId: string
  metadata: Record<string, unknown>
}

export type PluginSlotContext = PluginEditorContext & { slot: string }

export type PluginBusyState = {
  active: boolean
  label: string
}

export type PluginFrontendModule = {
  plugin_id: string
  entry_url: string
}

export type PluginFrontendApi = {
  registerEditorAssistant: (slot: string, component: Component) => void
  registerTaskExtension: (pluginId: string, component: Component) => void
  registerPluginSlot: (slot: string, component: Component) => void
  api: typeof import('../api/client').api
  vue: Pick<typeof import('vue'), 'computed' | 'defineComponent' | 'h' | 'onBeforeUnmount' | 'onMounted' | 'reactive' | 'ref' | 'watch'>
}

export type PluginFrontendRegistration = {
  register: (api: PluginFrontendApi) => void | Promise<void>
}
