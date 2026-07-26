<script setup lang="ts">
import { computed, ref } from 'vue'

import type { PluginBusyState, PluginEditorContext } from '../plugins/contracts'
import { assistantsForSlot } from '../plugins/registry'

const props = withDefaults(defineProps<{
  modelValue: string
  targetType: string
  targetId: string
  slot: string
  metadata?: Record<string, unknown>
}>(), { metadata: () => ({}) })
const emit = defineEmits<{
  'update:modelValue': [value: string]
  notice: [message: string]
}>()

const busy = ref<PluginBusyState>({ active: false, label: '' })
const context = computed<PluginEditorContext>(() => ({
  targetType: props.targetType,
  targetId: props.targetId,
  metadata: props.metadata,
}))
const assistants = computed(() => assistantsForSlot(props.slot))

function updateBusy(state: PluginBusyState) {
  busy.value = state
}
</script>

<template>
  <section class="plugin-editor-slot" :data-busy="busy.active || undefined">
    <slot name="editor" :disabled="busy.active" />
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
    />
    <div v-if="busy.active" class="plugin-editor-busy" role="status" aria-live="polite">
      <p>{{ busy.label }}</p>
    </div>
  </section>
</template>

<style scoped>
.plugin-editor-slot { position: relative; }
.plugin-editor-busy { align-items: center; background: color-mix(in srgb, var(--surface, white) 84%, transparent); display: flex; inset: 0; justify-content: center; position: absolute; text-align: center; }
</style>
