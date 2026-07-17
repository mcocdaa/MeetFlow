<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = withDefaults(defineProps<{ source?: string; emptyText?: string }>(), {
  source: '', emptyText: '暂时还没有内容',
})

const html = computed(() => DOMPurify.sanitize(marked.parse(props.source, { async: false }) as string))
</script>

<template>
  <div v-if="source" class="markdown" v-html="html" />
  <p v-else class="empty-inline">{{ emptyText }}</p>
</template>
