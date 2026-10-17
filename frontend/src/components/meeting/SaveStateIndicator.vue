<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '../../i18n'

const props = defineProps<{
  state: 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
  role?: 'status' | 'note'
}>()

const { tr } = useI18n()
const label = computed(() => ({
  idle: tr('未修改', 'Unchanged'),
  saving: tr('保存中…', 'Saving…'),
  saved: tr('已保存', 'Saved'),
  error: tr('保存失败', 'Save failed'),
  conflict: tr('版本冲突', 'Version conflict'),
}[props.state]))
</script>

<template>
  <span class="save-state-indicator" :role="props.role ?? 'status'" aria-live="polite">{{ label }}</span>
</template>
