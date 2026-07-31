import { markRaw, reactive } from 'vue'
import type { Component } from 'vue'

const editorAssistants = reactive(new Map<string, Component[]>())
const taskExtensions = reactive(new Map<string, Component>())
const pluginSlots = reactive(new Map<string, Component[]>())
const moduleUrls = new Set<string>()

export function registerEditorAssistant(slot: string, component: Component) {
  editorAssistants.set(slot, [...(editorAssistants.get(slot) ?? []), markRaw(component)])
}

export function registerTaskExtension(pluginId: string, component: Component) {
  taskExtensions.set(pluginId, markRaw(component))
}

export function registerPluginSlot(slot: string, component: Component) {
  pluginSlots.set(slot, [...(pluginSlots.get(slot) ?? []), markRaw(component)])
}

export function assistantsForSlot(slot: string) {
  return editorAssistants.get(slot) ?? []
}

export function taskExtensionFor(pluginId: string) {
  return taskExtensions.get(pluginId)
}

export function componentsForPluginSlot(slot: string) {
  return pluginSlots.get(slot) ?? []
}

export function claimPluginModuleUrl(url: string) {
  if (moduleUrls.has(url)) return false
  moduleUrls.add(url)
  return true
}
