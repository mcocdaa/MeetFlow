<script setup lang="ts">
import { NAvatar } from 'naive-ui'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    name: string
    color?: string | null
    size?: number
  }>(),
  { color: null, size: 30 },
)

const initial = computed(() => props.name.trim().slice(0, 1).toUpperCase() || '?')
</script>

<template>
  <n-avatar
    class="app-avatar"
    :size="size"
    :color="color ?? undefined"
    :style="color ? undefined : { background: 'var(--green-soft)', color: 'var(--green-dark)' }"
    :aria-label="name"
  >
    {{ initial }}
  </n-avatar>
</template>
