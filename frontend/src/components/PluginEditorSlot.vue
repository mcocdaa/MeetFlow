<script setup lang="ts">
import { computed, ref } from 'vue'

import type { PluginBusyState, PluginEditorContext } from '../plugins/contracts'
import { assistantsForSlot } from '../plugins/registry'
import MarkdownEditor from './MarkdownEditor.vue'

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
const pendingDraft = ref<string | null>(null)
const context = computed<PluginEditorContext>(() => ({
  targetType: props.targetType,
  targetId: props.targetId,
  metadata: props.metadata,
}))
const assistants = computed(() => assistantsForSlot(props.slot))

function updateBusy(state: PluginBusyState) {
  busy.value = state
}

function receiveDraft(markdown: string) {
  pendingDraft.value = markdown
  menuOpen.value = false
}

function applyDraft() {
  if (pendingDraft.value === null) return
  emit('update:modelValue', pendingDraft.value)
  pendingDraft.value = null
}

function discardDraft() {
  pendingDraft.value = null
}
</script>

<template>
  <section class="plugin-editor-slot" :data-busy="busy.active || undefined" @keydown.esc="menuOpen = false">
    <div v-if="assistants.length" class="plugin-editor-chrome">
      <span class="plugin-editor-label">{{ editorLabel }}</span>
      <div class="plugin-editor-menu">
        <button
          type="button"
          class="editor-assistant-trigger"
          aria-label="AI 工具"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :disabled="busy.active"
          @click="menuOpen = !menuOpen"
        >✦</button>
        <div v-if="menuOpen" class="editor-assistant-menu" role="menu" aria-label="AI 操作">
          <component
            :is="assistant"
            v-for="(assistant, index) in assistants"
            :key="index"
            :model-value="modelValue"
            :context="context"
            :disabled="busy.active"
            @update:model-value="emit('update:modelValue', $event)"
            @update:busy="updateBusy"
            @notice="emit('notice', $event)"
            @draft="receiveDraft"
          />
        </div>
      </div>
    </div>
    <slot name="editor" :disabled="busy.active || pendingDraft !== null" />
    <section v-if="pendingDraft !== null" class="plugin-editor-draft-review">
      <header><span>AI 草稿</span><button type="button" class="button button-small button-quiet" @click="discardDraft">放弃</button></header>
      <MarkdownEditor v-model="pendingDraft" label="AI 草稿" placeholder="检查并编辑 AI 草稿…" />
      <footer><button type="button" class="button button-primary" @click="applyDraft">应用草稿</button></footer>
    </section>
    <div v-if="busy.active" class="plugin-editor-busy" role="status" aria-live="polite">
      <p>{{ busy.label }}</p>
    </div>
  </section>
</template>

<style scoped>
.plugin-editor-slot { position: relative; }
.plugin-editor-chrome { align-items: center; background: var(--surface, #fff); border: 1px solid var(--line, #d8dde5); border-bottom: 0; border-radius: 6px 6px 0 0; display: flex; height: 32px; justify-content: space-between; padding: 0 .375rem 0 .625rem; }
.plugin-editor-label { color: var(--muted, #64748b); font-size: .8125rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plugin-editor-menu { position: relative; }
.editor-assistant-trigger { align-items: center; background: transparent; border: 0; border-radius: 4px; color: var(--text, #1f2937); cursor: pointer; display: inline-flex; font-size: 1rem; height: 26px; justify-content: center; padding: 0; width: 26px; }
.editor-assistant-trigger:hover:not(:disabled), .editor-assistant-trigger:focus-visible { background: var(--surface-soft, #f1f5f9); outline: none; }
.editor-assistant-trigger:disabled { cursor: wait; opacity: .6; }
.editor-assistant-menu { background: var(--surface, #fff); border: 1px solid var(--line, #d8dde5); border-radius: 6px; box-shadow: 0 8px 18px rgb(15 23 42 / 14%); display: grid; gap: .375rem; min-width: 180px; padding: .5rem; position: absolute; right: 0; top: calc(100% + .25rem); z-index: 2; }
.plugin-editor-draft-review { background: var(--surface-soft, #f8fafc); border-top: 1px solid var(--line, #d8dde5); display: grid; gap: .625rem; margin-top: .75rem; padding: .75rem; }
.plugin-editor-draft-review > header, .plugin-editor-draft-review > footer { align-items: center; display: flex; justify-content: space-between; }
.plugin-editor-draft-review > header > span { color: var(--muted, #64748b); font-size: .8125rem; font-weight: 600; }
.plugin-editor-draft-review > footer { justify-content: flex-end; }
.plugin-editor-busy { align-items: center; background: color-mix(in srgb, var(--surface, white) 84%, transparent); display: flex; inset: 0; justify-content: center; position: absolute; text-align: center; }
</style>
