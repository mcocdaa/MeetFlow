<script setup lang="ts">
import MarkdownView from './MarkdownView.vue'
import ProjectUpdateComposer from './ProjectUpdateComposer.vue'
import type { ProjectDetail } from '../domain/projects'

defineProps<{ project: ProjectDetail; canContribute: boolean }>()
const emit = defineEmits<{ reload: [] }>()
</script>

<template>
  <section class="workspace-section project-activity-tab"><header class="section-heading"><div><p class="eyebrow">Activity</p><h2>项目动态</h2></div></header><ProjectUpdateComposer v-if="canContribute" :project-id="project.id" :health="project.health" @saved="emit('reload')" /><div class="project-activity-list"><article v-for="item in project.updates" :key="item.id" class="latest-update"><MarkdownView :source="item.content_markdown" /><p class="attribution">{{ item.created_by.display_name }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</p></article><p v-if="!project.updates.length" class="muted">尚无项目动态。</p></div></section>
</template>
