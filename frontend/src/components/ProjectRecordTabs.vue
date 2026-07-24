<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import AttachmentPanel from './AttachmentPanel.vue'
import type { ProjectActionSummary, ProjectDetail } from '../domain/projects'

type Tab = 'meetings' | 'actions' | 'decisions' | 'files'
type Page<T> = { items: T[] }
type MeetingRow = { id: string; title: string; scheduled_start: string; status: string }
type DecisionRow = { id: string; title: string; status: string; meeting_id: string | null }
const props = defineProps<{ project: ProjectDetail; tab: Tab }>()
const emit = defineEmits<{ create: [kind: 'meeting' | 'series' | 'decision' | 'action']; uploaded: [attachment: ProjectDetail['attachments'][number]]; deleted: [id: string] }>()
const rows = ref<Array<MeetingRow | ProjectActionSummary | DecisionRow>>([])
const loading = ref(false)

function endpoint() { if (props.tab === 'meetings') return `/api/meetings?project_id=${props.project.id}`; if (props.tab === 'actions') return `/api/actions?project_id=${props.project.id}&status=open`; return `/api/decisions?project_id=${props.project.id}` }
async function load() { if (props.tab === 'files') return; loading.value = true; try { const value = await api<Page<typeof rows.value[number]>>(endpoint()); rows.value = Array.isArray(value?.items) ? value.items : [] } finally { loading.value = false } }
watch(() => props.tab, () => void load())
onMounted(load)
</script>

<template>
  <section class="workspace-section tab-content project-record-tabs">
    <template v-if="tab === 'meetings'"><header class="section-heading"><h2>会议与系列</h2><div class="row-actions"><button class="button button-primary" @click="emit('create', 'meeting')">添加会议</button><button class="button button-quiet" @click="emit('create', 'series')">添加系列</button></div></header><div v-if="project.series_summaries.length" class="project-dashboard-list"><RouterLink v-for="series in project.series_summaries" :key="series.id" class="compact-row" :to="`/meetings?series_id=${series.id}`"><strong>{{ series.title }}</strong><span>{{ series.recurrence_description || series.status }}</span></RouterLink></div><p v-if="loading" class="muted">正在加载会议…</p><div class="project-record-list"><RouterLink v-for="item in rows as MeetingRow[]" :key="item.id" class="project-record-row" :to="`/meetings/${item.id}`"><strong>{{ item.title }}</strong><span>{{ new Date(item.scheduled_start).toLocaleString('zh-CN') }} · {{ item.status }}</span></RouterLink></div></template>
    <template v-else-if="tab === 'actions'"><header class="section-heading"><h2>项目行动项</h2><button class="button button-primary" @click="emit('create', 'action')">添加行动项</button></header><p v-if="loading" class="muted">正在加载行动项…</p><div class="project-record-list"><RouterLink v-for="item in rows as ProjectActionSummary[]" :key="item.id" class="project-record-row" :to="item.meeting_id ? `/meetings/${item.meeting_id}` : `/actions?highlight=${item.id}`"><strong>{{ item.content }}</strong><span>{{ item.status }} · {{ item.due_date ?? '未设期限' }} · {{ item.priority }}</span></RouterLink></div><p v-if="!loading && !rows.length" class="muted">当前没有未完成行动项。</p></template>
    <template v-else-if="tab === 'decisions'"><header class="section-heading"><h2>项目决策</h2><button class="button button-primary" @click="emit('create', 'decision')">添加决策</button></header><p v-if="loading" class="muted">正在加载决策…</p><div class="project-record-list"><RouterLink v-for="item in rows as DecisionRow[]" :key="item.id" class="project-record-row" :to="item.meeting_id ? `/meetings/${item.meeting_id}` : `/decisions?highlight=${item.id}`"><strong>{{ item.title }}</strong><span>{{ item.status }}</span></RouterLink></div><p v-if="!loading && !rows.length" class="muted">尚未形成项目决策。</p></template>
    <template v-else><header class="section-heading"><h2>项目文件</h2></header><AttachmentPanel target-type="project" :target-id="project.id" :attachments="project.attachments" @uploaded="emit('uploaded', $event)" @deleted="emit('deleted', $event)" /></template>
  </section>
</template>
