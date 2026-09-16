<script setup lang="ts">
import { NButton, NDropdown, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, NTabPane, NTabs, NTag, useDialog } from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'
import { projectStatusLabel } from '../utils/labels'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Page } from '../api/contracts'
import type { AttentionItem } from '../components/AttentionCard.vue'
import MeetingCreateDrawer from '../components/MeetingCreateDrawer.vue'
import PageHeader from '../components/PageHeader.vue'
import ProjectActivityTab from '../components/ProjectActivityTab.vue'
import ProjectCreatePanel from '../components/ProjectCreatePanel.vue'
import ProjectOverview from '../components/ProjectOverview.vue'
import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import SeriesEditDrawer from '../components/SeriesEditDrawer.vue'
import VersionConflictDialog from '../components/VersionConflictDialog.vue'
import { useVersionedSave } from '../composables/useVersionedSave'
import type {
  ProjectActionSummary,
  ProjectDetail,
  ProjectHealth,
  ProjectMemberRole,
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
const drawerKind = ref<'meeting' | 'series' | 'decision' | 'action' | ''>('')
const deleteTargetName = ref('')
const deleteError = ref('')
const editOpen = ref(false)
const memberRoleLabels: Record<ProjectMemberRole, string> = { member: '成员', stakeholder: '干系人' }
const editForm = ref({
  name: '',
  summary: '',
  status: 'active' as ProjectStatus,
  health: 'unset' as ProjectHealth,
  target_date: '',
  lead_user_id: null as string | null,
  member_ids: [] as string[],
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
const statusOptions = (['planned', 'active', 'paused', 'completed', 'canceled'] as ProjectStatus[])
  .map((status) => ({ label: projectStatusLabel(status), value: status }))
const healthOptions = (['on_track', 'at_risk', 'off_track', 'unset'] as ProjectHealth[])
  .map((health) => ({ label: healthLabels[health], value: health }))
const memberOptions = computed(() => (project.value?.memberships ?? []).map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const panelKind = computed(() => (
  drawerKind.value === 'decision' || drawerKind.value === 'action' ? drawerKind.value : null
))
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

function syncEditForm() {
  const value = project.value
  if (!value) return
  editForm.value = {
    name: value.name,
    summary: value.summary,
    status: value.status,
    health: value.health,
    target_date: value.target_date ?? '',
    lead_user_id: value.lead?.id ?? null,
    member_ids: value.memberships.map((row) => row.user.id),
  }
}

function mergedMemberIds(): string[] {
  const ids = [...editForm.value.member_ids]
  const lead = editForm.value.lead_user_id
  if (lead && !ids.includes(lead)) ids.unshift(lead)
  return ids
}

const {
  conflict: projectConflict,
  saving: projectSaving,
  error: projectSaveError,
  submit: submitProjectSave,
  retryWith: retryProjectSave,
  reset: resetProjectSave,
} = useVersionedSave<ProjectDetail>(async (version) => {
  const value = await api<ProjectDetail>(`/api/projects/${projectId.value}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: editForm.value.name.trim(),
      summary: editForm.value.summary,
      status: editForm.value.status,
      health: editForm.value.health,
      target_date: editForm.value.target_date || null,
      lead_user_id: editForm.value.lead_user_id || null,
      member_ids: mergedMemberIds(),
      expected_version: version,
    }),
  })
  project.value = { ...project.value, ...value } as ProjectDetail
  editOpen.value = false
  return value
}, () => project.value?.version ?? 1)

const conflictServer = ref<ProjectDetail | null>(null)

watch(projectConflict, async (value) => {
  if (!value) {
    conflictServer.value = null
    return
  }
  try {
    conflictServer.value = await api<ProjectDetail>(`/api/projects/${projectId.value}`)
  } catch {
    conflictServer.value = project.value
  }
})

function displayName(userId: string | null): string {
  if (!userId) return '未指定'
  const row = project.value?.memberships.find((item) => item.user.id === userId)
  return row?.user.display_name || row?.user.username || userId
}

const conflictLocalText = computed(() => [
  `名称：${editForm.value.name}`,
  `摘要：${editForm.value.summary || '（空）'}`,
  `状态：${projectStatusLabel(editForm.value.status)}`,
  `健康度：${healthLabels[editForm.value.health]}`,
  `目标日期：${editForm.value.target_date || '未设置'}`,
  `负责人：${displayName(editForm.value.lead_user_id)}`,
  `成员：${editForm.value.member_ids.map((id) => displayName(id)).join('、') || '无'}`,
].join('\n'))

const conflictServerText = computed(() => {
  const value = conflictServer.value
  if (!value) return '（服务器版本加载中…）'
  return [
    `名称：${value.name}`,
    `摘要：${value.summary || '（空）'}`,
    `状态：${projectStatusLabel(value.status)}`,
    `健康度：${healthLabels[value.health]}`,
    `目标日期：${value.target_date ?? '未设置'}`,
    `负责人：${value.lead?.display_name ?? '未指定'}`,
    `成员：${value.memberships.map((row) => row.user.display_name || row.user.username).join('、') || '无'}`,
  ].join('\n')
})

function openEdit() {
  if (!project.value || !canManage.value) return
  syncEditForm()
  resetProjectSave()
  conflictServer.value = null
  editOpen.value = true
}

function closeEdit() {
  if (projectSaving.value) return
  editOpen.value = false
  resetProjectSave()
}

async function submitEdit() {
  if (projectSaving.value || !canManage.value || !editForm.value.name.trim()) return
  const value = await submitProjectSave()
  if (value) void load()
}

async function overwriteProject(version: number) {
  const value = await retryProjectSave(version)
  if (value) void load()
}

async function reloadProjectFromServer() {
  resetProjectSave()
  await load()
  syncEditForm()
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
  } catch (reason) {
    error.value = errorMessage(reason, '项目加载失败')
  } finally {
    loading.value = false
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
          <NButton v-if="canManage" quaternary @click="openEdit">编辑项目</NButton>
          <NButton v-if="canManage" quaternary type="error" @click="confirmDelete">删除项目</NButton>
        </template>
      </PageHeader>

      <NDrawer
        :show="editOpen"
        placement="right"
        :width="'min(560px, 100vw)'"
        :mask-closable="!projectSaving"
        @update:show="(value: boolean) => { if (!value) closeEdit() }"
      >
        <NDrawerContent title="编辑项目" closable>
          <NForm label-placement="top" :show-require-mark="false">
            <NFormItem label="名称">
              <NInput v-model:value="editForm.name" :input-props="{ 'aria-label': '名称' }" />
            </NFormItem>
            <NFormItem label="摘要">
              <NInput
                v-model:value="editForm.summary"
                type="textarea"
                :autosize="{ minRows: 3 }"
                :input-props="{ 'aria-label': '摘要' }"
              />
            </NFormItem>
            <NFormItem label="状态">
              <NSelect v-model:value="editForm.status" class="project-edit-status" :options="statusOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem label="健康度">
              <NSelect v-model:value="editForm.health" class="project-edit-health" :options="healthOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem label="目标日期">
              <input v-model="editForm.target_date" class="native-date-input" type="date" aria-label="目标日期" />
            </NFormItem>
            <NFormItem label="负责人">
              <NSelect
                v-model:value="editForm.lead_user_id"
                class="project-edit-lead-select"
                :options="memberOptions"
                :virtual-scroll="false"
                clearable
                placeholder="选择负责人"
              />
            </NFormItem>
            <NFormItem label="成员">
              <NSelect
                v-model:value="editForm.member_ids"
                class="project-edit-member-select"
                :options="memberOptions"
                :virtual-scroll="false"
                multiple
                placeholder="选择成员"
              />
            </NFormItem>
          </NForm>
          <p class="form-hint">移除成员会立即撤销其项目访问，但不会删除其历史记录。</p>
          <p class="form-hint">干系人可查看不可编辑；当前没有成员角色指引入口。</p>
          <div class="project-member-roles">
            <NTag v-for="row in project.memberships" :key="row.user.id" size="small">
              {{ row.user.display_name || row.user.username }} · {{ memberRoleLabels[row.role] }}
            </NTag>
          </div>
          <p v-if="projectSaveError" class="notice notice-error" role="alert">{{ projectSaveError }}</p>
          <template #footer>
            <NButton quaternary :disabled="projectSaving" @click="closeEdit">取消</NButton>
            <NButton
              type="primary"
              :loading="projectSaving"
              :disabled="projectSaving || !editForm.name.trim()"
              @click="submitEdit"
            >
              保存项目
            </NButton>
          </template>
        </NDrawerContent>
      </NDrawer>

      <VersionConflictDialog
        v-if="projectConflict"
        :local-markdown="conflictLocalText"
        :server-markdown="conflictServerText"
        :actual-version="projectConflict.actualVersion"
        @close="resetProjectSave"
        @reload="reloadProjectFromServer"
        @overwrite="overwriteProject"
      />

      <p v-if="error" class="notice notice-error">{{ error }}</p>
      <nav class="project-tabs" aria-label="项目内容">
        <NTabs :value="tab" type="line" @update:value="selectTab">
          <NTabPane name="overview" tab="概览" :tab-props="tabA11y('overview')">
            <ProjectOverview :project="project" :attention="attention" :open-actions="openActions" :can-contribute="canContribute" @schedule-meeting="openCreate('meeting')" @open-tab="selectTab" />
          </NTabPane>
          <NTabPane name="meetings" tab="会议" :tab-props="tabA11y('meetings')">
            <ProjectRecordTabs :project="project" tab="meetings" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" @changed="load" />
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

      <MeetingCreateDrawer
        :show="drawerKind === 'meeting'"
        :projects="[{ id: project.id, name: project.name }]"
        :member-options="project.memberships.map((row) => row.user)"
        :default-project-id="project.id"
        @close="drawerKind = ''"
        @created="created('meeting')"
      />
      <SeriesEditDrawer
        :show="drawerKind === 'series'"
        mode="create"
        :project-id="project.id"
        :members="project.memberships.map((row) => row.user)"
        @close="drawerKind = ''"
        @saved="created('series')"
      />
      <ProjectCreatePanel
        v-if="panelKind"
        :show="true"
        :kind="panelKind"
        :project="project"
        @close="drawerKind = ''"
        @created="created"
      />
    </template>
  </main>
</template>
