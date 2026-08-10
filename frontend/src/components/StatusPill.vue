<script setup lang="ts">
import { computed } from 'vue'

import { statusLabel, type StatusKind } from '../utils/labels'

const props = withDefaults(defineProps<{
  status: string
  kind?: StatusKind
  label?: string
}>(), { kind: 'meeting' })

const text = computed(() => props.label ?? statusLabel(props.kind, props.status))
</script>

<template>
  <span class="status-pill" :data-status="status">{{ text }}</span>
</template>
