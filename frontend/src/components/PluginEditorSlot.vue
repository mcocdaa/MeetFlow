<script setup lang="ts">
import { computed, ref } from 'vue'

import type { PluginBusyState, PluginEditorContext } from '../plugins/contracts'
import { assistantsForSlot } from '../plugins/registry'

type MarkdownWriter = (markdown: string) => void

const props = withDefaults(defineProps<{
  modelValue: string
  targetType: string
  targetId: string
  slot: string
  editorLabel: string
  metadata?: Record<string, unknown>
}>(), { metadata: () => ({}) })
const emit = defineEmits<{
  'update:modelValue': [value: string]
  notice: [message: string]
}>()

const busy = ref<PluginBusyState>({ active: false, label: '' })
const menuOpen = ref(false)
const editorWriter = ref<MarkdownWriter | null>(null)
const context = computed<PluginEditorContext>(() => ({
  targetType: props.targetType,
  targetId: props.targetId,
  metadata: props.metadata,
}))
const assistants = computed(() => assistantsForSlot(props.slot))

function updateBusy(state: PluginBusyState) {
  if (state.active) menuOpen.value = false
  busy.value = state
}

function registerEditor(writer: MarkdownWriter | null) {
  editorWriter.value = writer
}

function writeAssistantResult(markdown: string) {
  menuOpen.value = false
  if (!editorWriter.value) {
    emit('notice', '编辑器尚未就绪，请稍后重试')
    return
  }
  editorWriter.value(markdown)
}
</script>

<template>
  <section
    class="plugin-editor-slot"
    :data-busy="busy.active || undefined"
    :aria-busy="busy.active ? 'true' : undefined"
    @keydown.esc="menuOpen = false"
  >
    <div v-if="assistants.length" class="plugin-editor-chrome">
      <span class="plugin-editor-label">{{ editorLabel }}</span>
      <div class="plugin-editor-menu">
        <button
          type="button"
          class="editor-assistant-trigger"
          :class="{ 'is-active': menuOpen || busy.active }"
          :aria-label="busy.active ? 'AI 工具，正在处理' : 'AI 工具'"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :disabled="busy.active"
          @click="menuOpen = !menuOpen"
        >✦</button>
        <div
          v-if="menuOpen || busy.active"
          v-show="menuOpen"
          class="editor-assistant-menu"
          role="menu"
          aria-label="AI 操作"
          :aria-hidden="!menuOpen"
        >
          <component
            :is="assistant"
            v-for="(assistant, index) in assistants"
            :key="index"
            :model-value="modelValue"
            :context="context"
            :disabled="busy.active"
            @update:model-value="writeAssistantResult"
            @update:busy="updateBusy"
            @notice="emit('notice', $event)"
          />
        </div>
      </div>
    </div>
    <slot name="editor" :disabled="busy.active" :register-editor="registerEditor" />
    <div v-if="busy.active" class="plugin-editor-busy" role="status" aria-live="polite">
      <div class="plugin-editor-busy-stripes" aria-hidden="true"></div>
      <div class="plugin-editor-busy-activity">
        <span class="plugin-editor-busy-rail" aria-hidden="true"></span>
        <p>{{ busy.label }}</p>
        <span class="plugin-editor-busy-hint">请稍候</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.plugin-editor-slot { position: relative; }
.plugin-editor-chrome { align-items: center; display: flex; height: 34px; justify-content: space-between; padding: 0 .4rem 0 .65rem; border: 1px solid var(--line); border-bottom: 0; border-radius: 8px 8px 0 0; background: var(--paper); }
.plugin-editor-label { overflow: hidden; color: var(--muted); font-size: .76rem; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.plugin-editor-menu { position: relative; }
.editor-assistant-trigger { display: inline-grid; width: 27px; height: 27px; place-items: center; padding: 0; border: 0; border-radius: 8px; color: var(--green); background: #edf7f1; cursor: pointer; font-size: 1rem; line-height: 1; transition: background .16s ease, box-shadow .16s ease, color .16s ease; }
.editor-assistant-trigger:hover:not(:disabled), .editor-assistant-trigger:focus-visible { outline: 0; box-shadow: 0 0 0 3px rgba(11, 106, 88, .16); }
.editor-assistant-trigger.is-active { color: white; background: var(--green); box-shadow: 0 4px 10px rgba(11, 106, 88, .22); }
.editor-assistant-trigger:disabled { cursor: wait; opacity: 1; }
.editor-assistant-menu { position: absolute; z-index: 3; top: calc(100% + .35rem); right: 0; width: min(15.25rem, calc(100vw - 2rem)); padding: .5rem; border: 1px solid #cfded5; border-radius: 11px; background: var(--paper); box-shadow: 0 14px 32px rgba(18, 55, 36, .16); }
.editor-assistant-menu :deep(.ai-work-assistant-control) { display: grid; gap: .35rem; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-heading) { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .15rem .15rem .25rem; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-title) { color: var(--ink); font-size: .76rem; font-weight: 800; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-tag) { padding: .15rem .35rem; border-radius: 999px; color: var(--green-dark); background: var(--green-soft); font-size: .62rem; font-weight: 750; white-space: nowrap; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-action) { display: flex; width: 100%; min-height: 38px; align-items: center; gap: .45rem; padding: .45rem .55rem; border: 1px solid transparent; border-radius: 8px; color: var(--ink); background: transparent; cursor: pointer; font: inherit; font-size: .75rem; font-weight: 750; text-align: left; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-action.is-primary) { color: var(--green-dark); background: #eef8f2; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-action:hover:not(:disabled)), .editor-assistant-menu :deep(.ai-work-assistant-menu-action:focus-visible) { border-color: #b8d7c4; outline: 0; box-shadow: 0 0 0 3px rgba(11, 106, 88, .1); }
.editor-assistant-menu :deep(.ai-work-assistant-menu-action:disabled) { cursor: wait; opacity: .65; }
.editor-assistant-menu :deep(.ai-work-assistant-menu-spark) { color: var(--green); font-size: .9rem; }
.plugin-editor-busy { position: absolute; z-index: 2; inset: 34px 0 0; display: grid; align-items: end; overflow: hidden; background: rgba(246, 250, 247, .67); backdrop-filter: blur(2px); pointer-events: auto; }
.plugin-editor-busy-stripes { position: absolute; inset: -60%; opacity: .56; background: repeating-linear-gradient(135deg, transparent 0 22px, rgba(11, 106, 88, .16) 22px 25px, transparent 25px 49px); animation: plugin-editor-construction-scan 2.4s linear infinite; }
.plugin-editor-busy-activity { position: relative; display: flex; align-items: center; gap: .5rem; min-height: 38px; padding: .6rem .8rem; border-top: 1px solid rgba(11, 106, 88, .2); color: var(--green-dark); background: rgba(247, 252, 249, .56); font-size: .72rem; font-weight: 750; }
.plugin-editor-busy-activity p { margin: 0; line-height: 1.25; }
.plugin-editor-busy-hint { color: var(--muted); font-weight: 500; }
.plugin-editor-busy-rail { flex: 0 0 auto; width: 19px; height: 5px; border-radius: 999px; background: repeating-linear-gradient(135deg, var(--green) 0 4px, #cfe8d9 4px 8px); background-size: 14px 14px; animation: plugin-editor-construction-rail .65s linear infinite; }
@keyframes plugin-editor-construction-scan { to { transform: translate(49px, -49px); } }
@keyframes plugin-editor-construction-rail { to { background-position: 14px 0; } }
@media (prefers-reduced-motion: reduce) { .plugin-editor-busy-stripes, .plugin-editor-busy-rail { animation: none; } }
</style>
