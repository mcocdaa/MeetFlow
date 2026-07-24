<script setup lang="ts">
import { ref } from 'vue'

import InlineAiDrafts from './InlineAiDrafts.vue'
import MarkdownView from './MarkdownView.vue'
import PluginActionPanel from './PluginActionPanel.vue'
import ProjectUpdateComposer from './ProjectUpdateComposer.vue'
import type { ProjectDetail } from '../domain/projects'

const props = defineProps<{ project: ProjectDetail }>()
const emit = defineEmits<{ reload: [] }>()
const progressDrafts = ref<{ reload: () => Promise<void> } | null>(null)
function refreshProgressDrafts() { void progressDrafts.value?.reload() }
</script>

<template>
  <section class="workspace-section project-activity-tab"><header class="section-heading"><div><p class="eyebrow">Activity</p><h2>项目动态</h2></div></header><ProjectUpdateComposer :project-id="project.id" :health="project.health" @saved="emit('reload')" /><section data-testid="project-inline-progress"><InlineAiDrafts ref="progressDrafts" target-type="project" :target-id="project.id" mode="progress" @applied="emit('reload')" /></section><PluginActionPanel :target-type="'project'" :target-id="project.id" @submitted="refreshProgressDrafts" /><div class="project-activity-list"><article v-for="item in project.updates" :key="item.id" class="latest-update"><MarkdownView :source="item.content_markdown" /><p class="attribution">{{ item.created_by.display_name }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</p></article><p v-if="!project.updates.length" class="muted">尚无项目动态。</p></div></section>
</template>
