<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  summary?: string
}>()
</script>

<template>
  <header class="workspace-page-heading project-page-header">
    <div><p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p><h1>{{ title }}</h1><p v-if="summary">{{ summary }}</p><slot name="meta" /></div>
    <div class="page-header-actions"><slot name="actions" /></div>
  </header>
</template>
