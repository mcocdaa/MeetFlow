<script setup lang="ts">
import { computed } from 'vue'

import type { PluginJob } from '../domain/plugin-jobs'
import { taskExtensionFor } from '../plugins/registry'

const props = defineProps<{ job: PluginJob }>()
const extension = computed(() => props.job.plugin_id ? taskExtensionFor(props.job.plugin_id) : undefined)
</script>

<template>
  <component :is="extension" v-if="extension" :job="job" />
</template>
