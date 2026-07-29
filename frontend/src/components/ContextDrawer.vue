<script setup lang="ts">
import { X } from '@lucide/vue'

defineProps<{ open: boolean; title: string }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="context-drawer-backdrop" @click.self="$emit('close')">
      <aside class="context-drawer" role="dialog" :aria-label="title" aria-modal="true">
        <header class="section-heading"><h2>{{ title }}</h2><button class="icon-button" aria-label="关闭" @click="$emit('close')"><X :size="18" :stroke-width="2" aria-hidden="true" /></button></header>
        <slot />
      </aside>
    </div>
  </Teleport>
</template>
