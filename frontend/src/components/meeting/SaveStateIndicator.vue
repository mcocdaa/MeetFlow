<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  state: 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
  role?: 'status' | 'note'
}>()

const label = computed(() => ({
  idle: '未修改',
  saving: '保存中…',
  saved: '已保存',
  error: '保存失败',
  conflict: '版本冲突',
}[props.state]))
</script>

<template>
  <span class="save-state-indicator" :role="props.role ?? 'status'" aria-live="polite">{{ label }}</span>
</template>
