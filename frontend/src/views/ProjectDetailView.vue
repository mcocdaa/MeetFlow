<script setup lang="ts">
import { NButton, NDropdown, NInput, NTabPane, NTabs, useDialog } from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Page } from '../api/contracts'
import type { AttentionItem } from '../components/AttentionCard.vue'
import ContextDrawer from '../components/ContextDrawer.vue'
import PageHeader from '../components/PageHeader.vue'
import ProjectActivityTab from '../components/ProjectActivityTab.vue'
import ProjectCreatePanel from '../components/ProjectCreatePanel.vue'
import ProjectOverview from '../components/ProjectOverview.vue'
import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import type {
  ProjectActionSummary,
  ProjectDetail,
  ProjectHealth,
  ProjectStatus,
} from '../domain/projects'

type Tab = 'overview' | 'meetings' | 'actions' | 'decisions' | 'questions' | 'files' | 'activity'

const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const project = ref<ProjectDetail | null>(null)
const attention = ref<AttentionItem[]>([])
const openActions = ref<ProjectActionSummary[]>([])
const loading = ref(true)
const error = ref('')
const tab = ref<Tab>('overview')
const editing = ref(false)
const saving = ref(false)
const drawerKind = ref<'meeting' | 'series' | 'decision' | 'action' | ''>('')
const deleteTargetName = ref('')
const deleteError = ref('')
const edit = ref({
  name: '',
  summary: '',
  status: 'active' as ProjectStatus,
  health: 'unset' as ProjectHealth,
  target_date: '',
})

const projectId = computed(() => String(route.params.id))
const canManage = computed(() => project.value?.capabilities.can_manage ?? false)
const canContribute = computed(() => project.value?.capabilities.can_contribute ?? false)
const healthLabels: Record<ProjectHealth, string> = {
  on_track: '进展正常',
  at_risk: '存在风险',
  off_track: '偏离计划',
  unset: '未设置',
}
const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'overview', label: '概览' },
  { id: 'meetings', label: '会议' },
  { id: 'actions', label: '行动项' },
  { id: 'decisions', label: '决策' },
  { id: 'questions', label: '开放问题' },
  { id: 'files', label: '文件' },
  { id: 'activity', label: '动态' },
]
function menuOption(key: string, label: string) {
  return { key, label: () => h('button', { type: 'button', class: 'project-new-menu-item' }, label) }
}

const createOptions = [
  menuOption('meeting', '会议'),
  menuOption('series', '系列会议'),
  menuOption('decision', '决策'),
  menuOption('action', '行动项'),
  menuOption('activity', '进展'),
  menuOption('files', '文件'),
]

function tabA11y(id: Tab) {
  return { role: 'tab', 'aria-selected': tab.value === id }
}

function isTab(value: unknown): value is Tab {
  return typeof value === 'string' && tabs.some((item) => item.id === value)
}

const initialTab = route.query.tab
tab.value = isTab(initialTab) ? initialTab : 'overview'
watch(
  () => route.query.tab,
  (value) => {
    if (isTab(value) && value !== tab.value) tab.value = value
  },
)

function selectTab(value: string | number) {
  if (!isTab(value)) return
  tab.value = value
  if (route.query.tab !== value) void router.replace({ query: { ...route.query, tab: value } })
}

function syncEdit(value: ProjectDetail) {
  edit.value = {
    name: value.name,
    summary: value.summary,
    status: value.status,
    health: value.health,
    target_date: value.target_date ?? '',
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [value, attentionValue, actionValue] = await Promise.all([
      api<ProjectDetail>(`/api/projects/${projectId.value}`),
      api<{ items: AttentionItem[] }>('/api/attention'),
      api<Page<ProjectActionSummary>>(`/api/actions?project_id=${projectId.value}&status=open`),
    ])
    project.value = value
    attention.value = attentionValue.items
    openActions.value = Array.isArray(actionValue?.items) ? actionValue.items : []
    syncEdit(value)
  } catch (reason) {
    error.value = errorMessage(reason, '项目加载失败')
  } finally {
    loading.value = false
  }
}

async function saveProject() {
  if (!project.value || !canManage.value) return
  saving.value = true
  try {
    const value = await api<ProjectDetail>(`/api/projects/${projectId.value}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...edit.value,
        target_date: edit.value.target_date || null,
        expected_version: project.value.version,
      }),
    })
    project.value = { ...project.value, ...value }
    syncEdit(project.value)
    editing.value = false
  } catch (reason) {
    error.value = errorMessage(reason, '项目保存失败')
  } finally {
    saving.value = false
  }
}

function openCreate(kind: 'meeting' | 'series' | 'decision' | 'action') {
  if (!canContribute.value) return
  drawerKind.value = kind
}

function onCreateSelect(key: string) {
  if (key === 'activity' || key === 'files') {
    selectTab(key)
    return
  }
  openCreate(key as 'meeting' | 'series' | 'decision' | 'action')
}

function confirmDelete() {
  const target = project.value
  if (!target || !canManage.value) return
  deleteTargetName.value = ''
  deleteError.value = ''
  dialog.warning({
    title: '删除项目',
    content: () => h('div', { class: 'project-delete-confirm' }, [
      h('p', '仅当项目下没有会议且没有项目附件时才能删除；删除不会级联清理项目下的记录，请先自行处理相关数据。'),
      h('p', `请输入项目名称“${target.name}”以确认：`),
      h(NInput, {
        value: deleteTargetName.value,
        'onUpdate:value': (value: string) => { deleteTargetName.value = value },
        inputProps: { 'aria-label': '输入项目名称确认' },
        placeholder: target.name,
      }),
      deleteError.value
        ? h('p', { class: 'notice notice-error', role: 'alert' }, deleteError.value)
        : null,
    ]),
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (deleteTargetName.value.trim() !== target.name) {
        deleteError.value = '请输入完整项目名称以确认删除'
        return false
      }
      try {
        await api(`/api/projects/${target.id}`, { method: 'DELETE' })
        await router.push('/projects')
      } catch (reason) {
        deleteError.value = errorMessage(reason, '项目删除失败')
        return false
      }
      return true
    },
  })
}

function created(kind: 'meeting' | 'series' | 'decision' | 'action') {
  drawerKind.value = ''
  void load()
  if (kind === 'meeting') selectTab('meetings')
}

function addAttachment(attachment: ProjectDetail['attachments'][number]) {
  project.value?.attachments.unshift(attachment)
}

function removeAttachment(id: string) {
  if (project.value) {
    project.value.attachments = project.value.attachments.filter(
      (item) => item.id !== id,
    )
  }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page project-workspace">
    <p v-if="loading" class="empty-state">正在加载项目工作区…</p>
    <p v-else-if="error && !project" class="notice notice-error">{{ error }}</p>
    <template v-else-if="project">
      <PageHeader eyebrow="Project workspace" :title="project.name" :summary="project.summary">
        <template #meta>
          <div class="project-context">
            <StatusPill :status="project.status" kind="project" />
            <span><i class="health-dot" :data-health="project.health"></i>{{ healthLabels[project.health] }}</span>
            <span>负责人：{{ project.lead?.display_name ?? '未指定' }}</span>
            <span>成员：{{ project.memberships.length }}</span>
            <span>目标：{{ project.target_date ?? '未设置' }}</span>
          </div>
        </template>
        <template #actions>
          <NDropdown v-if="canContribute" trigger="click" :options="createOptions" @select="onCreateSelect">
            <NButton type="primary">新建</NButton>
          </NDropdown>
          <NButton v-if="canManage" quaternary @click="editing = !editing">{{ editing ? '取消编辑' : '编辑项目' }}</NButton>
          <NButton v-if="canManage" quaternary type="error" @click="confirmDelete">删除项目</NButton>
        </template>
      </PageHeader>

      <form v-if="editing && canManage" class="panel project-edit-form" @submit.prevent="saveProject">
        <label>名称<input v-model.trim="edit.name" required /></label>
        <label>状态<select v-model="edit.status"><option value="planned">计划中</option><option value="active">进行中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label>
        <label>健康度<select v-model="edit.health"><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label>
        <label>目标日期<input v-model="edit.target_date" type="date" /></label>
        <label class="span-2">摘要<input v-model.trim="edit.summary" /></label>
        <div class="form-actions span-2"><button class="button button-primary" :disabled="saving">{{ saving ? '保存中…' : '保存项目' }}</button></div>
      </form>

      <p v-if="error" class="notice notice-error">{{ error }}</p>
      <nav class="project-tabs" aria-label="项目内容">
        <NTabs :value="tab" type="line" @update:value="selectTab">
          <NTabPane name="overview" tab="概览" :tab-props="tabA11y('overview')">
            <ProjectOverview :project="project" :attention="attention" :open-actions="openActions" :can-contribute="canContribute" @schedule-meeting="openCreate('meeting')" @open-tab="selectTab" />
          </NTabPane>
          <NTabPane name="meetings" tab="会议" :tab-props="tabA11y('meetings')">
            <ProjectRecordTabs :project="project" tab="meetings" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" />
          </NTabPane>
          <NTabPane name="actions" tab="行动项" :tab-props="tabA11y('actions')">
            <ProjectRecordTabs :project="project" tab="actions" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" />
          </NTabPane>
          <NTabPane name="decisions" tab="决策" :tab-props="tabA11y('decisions')">
            <ProjectRecordTabs :project="project" tab="decisions" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" />
          </NTabPane>
          <NTabPane name="questions" tab="开放问题" :tab-props="tabA11y('questions')">
            <p class="muted">开放问题列表将在后续任务中接入。</p>
          </NTabPane>
          <NTabPane name="files" tab="文件" :tab-props="tabA11y('files')">
            <ProjectRecordTabs :project="project" tab="files" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" />
          </NTabPane>
          <NTabPane name="activity" tab="动态" :tab-props="tabA11y('activity')">
            <ProjectActivityTab :project="project" :can-contribute="canContribute" @reload="load" />
          </NTabPane>
        </NTabs>
      </nav>

      <ContextDrawer :open="Boolean(drawerKind)" :title="({ meeting: '添加会议', series: '添加系列', decision: '添加决策', action: '添加行动项' } as Record<string, string>)[drawerKind] ?? ''" @close="drawerKind = ''">
        <ProjectCreatePanel v-if="drawerKind" :kind="drawerKind" :project="project" @close="drawerKind = ''" @created="created" />
      </ContextDrawer>
    </template>
  </main>
</template>
