<script setup lang="ts">
import { NTag } from 'naive-ui'
import { computed } from 'vue'

import { priorityTone, statusTone, type StatusTone } from '../theme/naive'
import { statusLabel, type StatusKind } from '../utils/labels'

type TagColor = { color?: string; borderColor?: string; textColor?: string }

const props = withDefaults(defineProps<{
  status: string
  kind?: StatusKind
  label?: string
}>(), { kind: 'meeting' })

const text = computed(() => props.label ?? statusLabel(props.kind, props.status))

const tone = computed<StatusTone>(() =>
  props.kind === 'priority' ? priorityTone(props.status) : statusTone(props.status),
)

const type = computed<'default' | 'success' | 'warning' | 'error'>(() => {
  if (props.kind === 'priority') return 'default'
  switch (tone.value) {
    case 'success': return 'success'
    case 'warning': return 'warning'
    case 'error': return 'error'
    default: return 'default'
  }
})

const COMPLETED_COLOR: TagColor = {
  color: 'var(--green-soft)',
  textColor: 'var(--green-dark)',
  borderColor: 'transparent',
}

const PRIORITY_COLORS: Record<StatusTone, TagColor> = {
  error: { color: '#f6deda', textColor: '#8d312a', borderColor: 'transparent' },
  warning: { color: '#f8e8c8', textColor: '#785318', borderColor: 'transparent' },
  muted: { color: '#e9e9e4', textColor: '#59615c', borderColor: 'transparent' },
  completed: { color: '#f1f3f5', textColor: '#66727f', borderColor: 'transparent' },
  success: { color: 'var(--green-soft)', textColor: 'var(--green-dark)', borderColor: 'transparent' },
}

const color = computed<TagColor | undefined>(() => {
  if (props.kind === 'priority') return PRIORITY_COLORS[tone.value]
  if (tone.value === 'completed') return COMPLETED_COLOR
  return undefined
})
</script>

<template>
  <n-tag
    class="status-pill"
    :data-status="status"
    :type="type"
    :color="color"
    :bordered="false"
    size="small"
  >
    {{ text }}
  </n-tag>
</template>
