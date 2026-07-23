<script setup lang="ts">
defineProps<{ open: boolean; title: string }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="context-drawer-backdrop" @click.self="$emit('close')">
      <aside class="context-drawer" role="dialog" :aria-label="title" aria-modal="true">
        <header class="section-heading"><h2>{{ title }}</h2><button class="icon-button" aria-label="关闭" @click="$emit('close')">×</button></header>
        <slot />
      </aside>
    </div>
  </Teleport>
</template>
