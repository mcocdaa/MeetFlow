<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { AttentionItem } from '../components/AttentionCard.vue'
import MarkdownView from '../components/MarkdownView.vue'
import PageHeader from '../components/PageHeader.vue'
import ProjectUpdateComposer from '../components/ProjectUpdateComposer.vue'
import type { ProjectDetail, ProjectHealth, ProjectStatus } from '../domain/projects'

const route = useRoute()
const project = ref<ProjectDetail | null>(null)
const attention = ref<AttentionItem[]>([])
const loading = ref(true)
const error = ref('')
const tab = ref('overview')
const editing = ref(false)
const saving = ref(false)
const edit = ref({ name: '', summary: '', status: 'active' as ProjectStatus, health: 'unset' as ProjectHealth, target_date: '' })

const projectId = computed(() => String(route.params.id))
const projectAttention = computed(() => attention.value.filter((item) => item.project.id === projectId.value))
const latestUpdate = computed(() => project.value?.updates[0] ?? null)
const healthLabels: Record<ProjectHealth, string> = { on_track: '进展正常', at_risk: '存在风险', off_track: '偏离计划', unset: '未设置' }
const statusLabels: Record<ProjectStatus, string> = { planned: '计划中', active: '进行中', paused: '已暂停', completed: '已完成', canceled: '已取消' }
const tabs = [{ id: 'overview', label: '概览' }, { id: 'meetings', label: '会议' }, { id: 'decisions', label: '决策' }, { id: 'actions', label: '行动项' }, { id: 'files', label: '文件' }, { id: 'activity', label: '动态' }]

function syncEdit(value: ProjectDetail) {
  edit.value = { name: value.name, summary: value.summary, status: value.status, health: value.health, target_date: value.target_date ?? '' }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [value, attentionValue] = await Promise.all([
      api<ProjectDetail>(`/api/projects/${projectId.value}`),
      api<{ items: AttentionItem[] }>('/api/attention'),
    ])
    project.value = value
    attention.value = attentionValue.items
    syncEdit(value)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '项目加载失败' }
  finally { loading.value = false }
}

async function saveProject() {
  if (!project.value) return
  saving.value = true
  error.value = ''
  try {
    const value = await api<ProjectDetail>(`/api/projects/${projectId.value}`, {
      method: 'PUT', body: JSON.stringify({ ...edit.value, target_date: edit.value.target_date || null, expected_version: project.value.version }),
    })
    project.value = { ...project.value, ...value }
    syncEdit(project.value)
    editing.value = false
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '项目保存失败' }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page project-workspace">
    <p v-if="loading" class="empty-state">正在加载项目工作区…</p>
    <p v-else-if="error && !project" class="notice notice-error" role="alert">{{ error }}</p>
    <template v-else-if="project">
      <PageHeader eyebrow="Project workspace" :title="project.name" :summary="project.summary">
        <template #meta><div class="project-context"><span class="status-pill">{{ statusLabels[project.status] }}</span><span><i class="health-dot" :data-health="project.health"></i>{{ healthLabels[project.health] }}</span><span>负责人：{{ project.lead?.display_name ?? '未指定' }}</span><span>成员：{{ project.memberships.map((item) => item.user.display_name).join('、') || '暂无' }}</span><span>目标：{{ project.target_date ?? '未设置' }}</span></div></template>
        <template #actions><RouterLink class="button button-quiet" :to="`/meetings?project_id=${project.id}`">查看会议</RouterLink><button class="button button-primary" @click="editing = !editing">{{ editing ? '取消编辑' : '编辑项目' }}</button></template>
      </PageHeader>
      <form v-if="editing" class="panel project-edit-form" @submit.prevent="saveProject"><label>名称<input v-model.trim="edit.name" required /></label><label>状态<select v-model="edit.status"><option value="planned">计划中</option><option value="active">进行中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label><label>健康度<select v-model="edit.health"><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label><label>目标日期<input v-model="edit.target_date" type="date" /></label><label class="span-2">摘要<input v-model.trim="edit.summary" /></label><div class="form-actions span-2"><button class="button button-primary" :disabled="saving">{{ saving ? '保存中…' : '保存项目' }}</button></div></form>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <nav class="workspace-tabs" aria-label="项目内容"><button v-for="item in tabs" :key="item.id" role="tab" :aria-selected="tab === item.id" @click="tab = item.id">{{ item.label }}</button></nav>

      <div v-if="tab === 'overview'" class="project-overview-grid">
        <section class="workspace-section project-update-section"><div class="section-heading"><div><p class="eyebrow">Latest progress</p><h2>最近进展</h2></div></div><article v-if="latestUpdate" class="latest-update"><MarkdownView :source="latestUpdate.content_markdown" /><p class="attribution">{{ latestUpdate.created_by.display_name }} · {{ new Date(latestUpdate.created_at).toLocaleString('zh-CN') }}</p></article><p v-else class="muted">尚未发布项目进展。</p><ProjectUpdateComposer :project-id="project.id" :health="project.health" @saved="load" /></section>
        <section class="workspace-section"><div class="section-heading"><h2>需要关注</h2><span class="metric"><strong>{{ projectAttention.length }}</strong> 项</span></div><RouterLink v-for="item in projectAttention.slice(0, 5)" :key="item.subject_id" class="compact-row" :to="item.subject_type === 'meeting' ? `/meetings/${item.subject_id}` : `/${item.subject_type}s?highlight=${item.subject_id}`"><strong>{{ item.title }}</strong><span>{{ item.reasons.join(' · ') }}</span></RouterLink><p v-if="!projectAttention.length" class="muted">当前项目没有需要你立即处理的事项。</p></section>
        <section class="workspace-section"><div class="section-heading"><h2>下一次会议</h2></div><RouterLink v-if="project.next_meeting" class="next-meeting-card" :to="`/meetings/${project.next_meeting.id}`"><strong>{{ project.next_meeting.title }}</strong><time>{{ new Date(project.next_meeting.scheduled_start).toLocaleString('zh-CN') }}</time><span>进入会议 →</span></RouterLink><p v-else class="muted">暂未安排下一次会议。</p></section>
        <section class="workspace-section"><div class="section-heading"><h2>最近决策</h2><RouterLink class="text-link" :to="`/decisions?project_id=${project.id}`">全部</RouterLink></div><RouterLink v-for="decision in project.recent_decisions.slice(0, 5)" :key="decision.id" class="compact-row" :to="`/decisions?highlight=${decision.id}`"><strong>{{ decision.title }}</strong><span>{{ decision.status }}</span></RouterLink><p v-if="!project.recent_decisions.length" class="muted">尚未形成项目决策。</p></section>
        <section class="project-metrics"><div><strong>{{ project.meeting_count }}</strong><span>会议</span></div><div><strong>{{ project.decision_count }}</strong><span>决策</span></div><div><strong>{{ project.open_action_count }}</strong><span>未完成行动</span></div><div><strong>{{ project.attachments.length }}</strong><span>文件</span></div></section>
      </div>
      <section v-else class="workspace-section tab-content">
        <template v-if="tab === 'meetings'"><h2>会议与系列</h2><RouterLink v-for="series in project.series_summaries" :key="series.id" class="compact-row" :to="`/meetings?series_id=${series.id}`"><strong>{{ series.title }}</strong><span>{{ series.recurrence_description || series.status }}</span></RouterLink><RouterLink class="button button-primary" :to="`/meetings?project_id=${project.id}`">查看项目会议</RouterLink></template>
        <template v-else-if="tab === 'decisions'"><h2>项目决策</h2><RouterLink class="button button-primary" :to="`/decisions?project_id=${project.id}`">打开决策日志</RouterLink></template>
        <template v-else-if="tab === 'actions'"><h2>项目行动项</h2><RouterLink class="button button-primary" :to="`/actions?project_id=${project.id}`">查看行动项</RouterLink></template>
        <template v-else-if="tab === 'files'"><h2>项目文件</h2><a v-for="file in project.attachments" :key="file.id" class="compact-row" :href="file.download_url"><strong>{{ file.original_name }}</strong><span>{{ Math.ceil(file.size / 1024) }} KB</span></a><p v-if="!project.attachments.length" class="muted">尚未上传项目文件。</p></template>
        <template v-else><h2>项目动态</h2><p class="muted">动态记录已由后端保存；协作面板将在下一阶段接入分页时间线。</p></template>
      </section>
    </template>
  </main>
</template>
