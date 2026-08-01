<script setup lang="ts">
import { computed, defineComponent, h, onErrorCaptured, ref } from 'vue'

import type { PluginSlotContext } from '../plugins/contracts'
import { componentsForPluginSlot } from '../plugins/registry'

const props = withDefaults(defineProps<{
  slot: string
  targetType: string
  targetId: string
  metadata?: Record<string, unknown>
}>(), { metadata: () => ({}) })

const components = computed(() => componentsForPluginSlot(props.slot))
const context = computed<PluginSlotContext>(() => ({
  slot: props.slot,
  targetType: props.targetType,
  targetId: props.targetId,
  metadata: props.metadata,
}))

const SlotBoundary = defineComponent({
  setup(_, { slots }) {
    const failed = ref(false)
    onErrorCaptured(() => {
      failed.value = true
      return false
    })
    return () => failed.value ? null : h('div', { class: 'plugin-slot-item' }, slots.default?.())
  },
})
</script>

<template>
  <section v-if="components.length" class="plugin-slot" :data-slot="slot">
    <SlotBoundary v-for="(component, index) in components" :key="`${slot}:${index}`">
      <component :is="component" :context="context" />
    </SlotBoundary>
  </section>
</template>
