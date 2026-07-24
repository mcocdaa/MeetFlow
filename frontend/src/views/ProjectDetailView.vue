<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../api/client'
import type { Page } from '../api/contracts'
import type { AttentionItem } from '../components/AttentionCard.vue'
import ContextDrawer from '../components/ContextDrawer.vue'
import PageHeader from '../components/PageHeader.vue'
import ProjectActivityTab from '../components/ProjectActivityTab.vue'
import ProjectCreatePanel from '../components/ProjectCreatePanel.vue'
import ProjectOverview from '../components/ProjectOverview.vue'
import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import type { ProjectActionSummary, ProjectDetail, ProjectHealth, ProjectStatus } from '../domain/projects'

type Tab = 'overview' | 'meetings' | 'actions' | 'decisions' | 'files' | 'activity'
const route = useRoute()
const project = ref<ProjectDetail | null>(null)
const attention = ref<AttentionItem[]>([])
const openActions = ref<ProjectActionSummary[]>([])
const loading = ref(true)
const error = ref('')
const tab = ref<Tab>('overview')
const editing = ref(false)
const saving = ref(false)
const newMenuOpen = ref(false)
const drawerKind = ref<'meeting' | 'series' | 'decision' | 'action' | ''>('')
const edit = ref({ name: '', summary: '', status: 'active' as ProjectStatus, health: 'unset' as ProjectHealth, target_date: '' })
const projectId = computed(() => String(route.params.id))
const healthLabels: Record<ProjectHealth, string> = { on_track: '进展正常', at_risk: '存在风险', off_track: '偏离计划', unset: '未设置' }
const statusLabels: Record<ProjectStatus, string> = { planned: '计划中', active: '进行中', paused: '已暂停', completed: '已完成', canceled: '已取消' }
const tabs: Array<{ id: Tab; label: string }> = [{ id: 'overview', label: '概览' }, { id: 'meetings', label: '会议' }, { id: 'actions', label: '行动项' }, { id: 'decisions', label: '决策' }, { id: 'files', label: '文件' }, { id: 'activity', label: '动态' }]
function syncEdit(value: ProjectDetail) { edit.value = { name: value.name, summary: value.summary, status: value.status, health: value.health, target_date: value.target_date ?? '' } }
async function load() { loading.value = true; error.value = ''; try { const [value, attentionValue, actionValue] = await Promise.all([api<ProjectDetail>(`/api/projects/${projectId.value}`), api<{ items: AttentionItem[] }>('/api/attention'), api<Page<ProjectActionSummary>>(`/api/actions?project_id=${projectId.value}&status=open`)]); project.value = value; attention.value = attentionValue.items; openActions.value = Array.isArray(actionValue?.items) ? actionValue.items : []; syncEdit(value) } catch (reason) { error.value = reason instanceof Error ? reason.message : '项目加载失败' } finally { loading.value = false } }
async function saveProject() { if (!project.value) return; saving.value = true; try { const value = await api<ProjectDetail>(`/api/projects/${projectId.value}`, { method: 'PUT', body: JSON.stringify({ ...edit.value, target_date: edit.value.target_date || null, expected_version: project.value.version }) }); project.value = { ...project.value, ...value }; syncEdit(project.value); editing.value = false } catch (reason) { error.value = reason instanceof Error ? reason.message : '项目保存失败' } finally { saving.value = false } }
function openCreate(kind: 'meeting' | 'series' | 'decision' | 'action') { drawerKind.value = kind; newMenuOpen.value = false }
function created(kind: 'meeting' | 'series' | 'decision' | 'action') { drawerKind.value = ''; void load(); if (kind === 'meeting') tab.value = 'meetings' }
function addAttachment(attachment: ProjectDetail['attachments'][number]) { project.value?.attachments.unshift(attachment) }
function removeAttachment(id: string) { if (project.value) project.value.attachments = project.value.attachments.filter((item) => item.id !== id) }
onMounted(load)
</script>

<template><main class="workspace-page project-workspace"><p v-if="loading" class="empty-state">正在加载项目工作区…</p><p v-else-if="error && !project" class="notice notice-error">{{ error }}</p><template v-else-if="project"><PageHeader eyebrow="Project workspace" :title="project.name" :summary="project.summary"><template #meta><div class="project-context"><span class="status-pill">{{ statusLabels[project.status] }}</span><span><i class="health-dot" :data-health="project.health"></i>{{ healthLabels[project.health] }}</span><span>负责人：{{ project.lead?.display_name ?? '未指定' }}</span><span>成员：{{ project.memberships.length }}</span><span>目标：{{ project.target_date ?? '未设置' }}</span></div></template><template #actions><div class="project-header-new"><button class="button button-primary" aria-haspopup="menu" :aria-expanded="newMenuOpen" @click="newMenuOpen = !newMenuOpen">新建</button><div v-if="newMenuOpen" role="menu" class="project-new-menu"><button role="menuitem" @click="openCreate('meeting')">会议</button><button role="menuitem" @click="openCreate('series')">系列会议</button><button role="menuitem" @click="openCreate('decision')">决策</button><button role="menuitem" @click="openCreate('action')">行动项</button><button role="menuitem" @click="tab = 'activity'; newMenuOpen = false">进展</button><button role="menuitem" @click="tab = 'files'; newMenuOpen = false">文件</button></div></div><button class="button button-quiet" @click="editing = !editing">{{ editing ? '取消编辑' : '编辑项目' }}</button></template></PageHeader><form v-if="editing" class="panel project-edit-form" @submit.prevent="saveProject"><label>名称<input v-model.trim="edit.name" required /></label><label>状态<select v-model="edit.status"><option value="planned">计划中</option><option value="active">进行中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label><label>健康度<select v-model="edit.health"><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label><label>目标日期<input v-model="edit.target_date" type="date" /></label><label class="span-2">摘要<input v-model.trim="edit.summary" /></label><div class="form-actions span-2"><button class="button button-primary" :disabled="saving">{{ saving ? '保存中…' : '保存项目' }}</button></div></form><p v-if="error" class="notice notice-error">{{ error }}</p><nav class="workspace-tabs" aria-label="项目内容"><button v-for="item in tabs" :key="item.id" role="tab" :aria-selected="tab === item.id" @click="tab = item.id">{{ item.label }}</button></nav><ProjectOverview v-if="tab === 'overview'" :project="project" :attention="attention" :open-actions="openActions" @schedule-meeting="openCreate('meeting')" @open-tab="tab = $event" /><ProjectActivityTab v-else-if="tab === 'activity'" :project="project" @reload="load" /><ProjectRecordTabs v-else :project="project" :tab="tab" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" /><ContextDrawer :open="Boolean(drawerKind)" :title="({ meeting: '添加会议', series: '添加系列', decision: '添加决策', action: '添加行动项' } as Record<string, string>)[drawerKind] ?? ''" @close="drawerKind = ''"><ProjectCreatePanel v-if="drawerKind" :kind="drawerKind" :project="project" @close="drawerKind = ''" @created="created" /></ContextDrawer></template></main></template>
