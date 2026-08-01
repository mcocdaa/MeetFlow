import { computed, defineComponent, h, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { api } from '../api/client'
import type { PluginFrontendApi, PluginFrontendModule, PluginFrontendRegistration } from './contracts'
import { claimPluginModuleUrl, registerEditorAssistant, registerPluginSlot, registerTaskExtension } from './registry'

const pluginApi: PluginFrontendApi = {
  registerEditorAssistant,
  registerTaskExtension,
  registerPluginSlot,
  api,
  vue: { computed, defineComponent, h, onBeforeUnmount, onMounted, reactive, ref, watch },
}

export async function loadPluginFrontendModules() {
  let modules: PluginFrontendModule[]
  try {
    const response = await api<{ items: PluginFrontendModule[] }>('/api/plugins/frontend-modules')
    modules = response.items
  } catch (reason) {
    console.error('Unable to load plugin frontend modules.', reason)
    return
  }

  for (const module of modules) {
    if (!claimPluginModuleUrl(module.entry_url)) continue
    try {
      const loaded = await import(/* @vite-ignore */ module.entry_url) as PluginFrontendRegistration
      if (typeof loaded.register !== 'function') throw new Error('Plugin frontend module does not export register().')
      await loaded.register(pluginApi)
    } catch (reason) {
      console.error(`Unable to load plugin frontend module: ${module.entry_url}`, reason)
    }
  }
}
