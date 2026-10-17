<script setup lang="ts">
import { NButton, NDropdown, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, NTabPane, NTabs, NTag, useDialog } from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import StatusPill from '../components/StatusPill.vue'
import { useI18n } from '../i18n'
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
import ProjectQuestionsTab from '../components/ProjectQuestionsTab.vue'
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

const { tr } = useI18n()
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
const memberRoleLabels = computed<Record<ProjectMemberRole, string>>(() => ({
  member: tr('成员', 'Member'),
  stakeholder: tr('干系人', 'Stakeholder'),
}))
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
const healthLabels = computed<Record<ProjectHealth, string>>(() => ({
  on_track: tr('进展正常', 'On Track'),
  at_risk: tr('存在风险', 'At Risk'),
  off_track: tr('偏离计划', 'Off Track'),
  unset: tr('未设置', 'Unset'),
}))
const statusOptions = computed(() => (['planned', 'active', 'paused', 'completed', 'canceled'] as ProjectStatus[])
  .map((status) => ({ label: projectStatusLabel(status), value: status })))
const healthOptions = computed(() => (['on_track', 'at_risk', 'off_track', 'unset'] as ProjectHealth[])
  .map((health) => ({ label: healthLabels.value[health], value: health })))
const memberOptions = computed(() => (project.value?.memberships ?? []).map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const panelKind = computed(() => (
  drawerKind.value === 'decision' || drawerKind.value === 'action' ? drawerKind.value : null
))
const tabs = computed<Array<{ id: Tab; label: string }>>(() => [
  { id: 'overview', label: tr('概览', 'Overview') },
  { id: 'meetings', label: tr('会议', 'Meetings') },
  { id: 'actions', label: tr('行动项', 'Actions') },
  { id: 'decisions', label: tr('决策', 'Decisions') },
  { id: 'questions', label: tr('开放问题', 'Questions') },
  { id: 'files', label: tr('文件', 'Files') },
  { id: 'activity', label: tr('动态', 'Activity') },
])
function menuOption(key: string, label: string) {
  return { key, label: () => h('button', { type: 'button', class: 'project-new-menu-item' }, label) }
}

const createOptions = computed(() => [
  menuOption('meeting', tr('会议', 'Meeting')),
  menuOption('series', tr('系列会议', 'Meeting Series')),
  menuOption('decision', tr('决策', 'Decision')),
  menuOption('action', tr('行动项', 'Action Item')),
  menuOption('activity', tr('进展', 'Update')),
  menuOption('files', tr('文件', 'File')),
])

function tabA11y(id: Tab) {
  return { role: 'tab', 'aria-selected': tab.value === id }
}

function isTab(value: unknown): value is Tab {
  return typeof value === 'string' && tabs.value.some((item) => item.id === value)
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
  if (!userId) return tr('未指定', 'Unassigned')
  const row = project.value?.memberships.find((item) => item.user.id === userId)
  return row?.user.display_name || row?.user.username || userId
}

const conflictLocalText = computed(() => [
  `${tr('名称：', 'Name: ')}${editForm.value.name}`,
  `${tr('摘要：', 'Summary: ')}${editForm.value.summary || tr('（空）', '(Empty)')}`,
  `${tr('状态：', 'Status: ')}${projectStatusLabel(editForm.value.status)}`,
  `${tr('健康度：', 'Health: ')}${healthLabels.value[editForm.value.health]}`,
  `${tr('目标日期：', 'Target Date: ')}${editForm.value.target_date || tr('未设置', 'Unset')}`,
  `${tr('负责人：', 'Lead: ')}${displayName(editForm.value.lead_user_id)}`,
  `${tr('成员：', 'Members: ')}${editForm.value.member_ids.map((id) => displayName(id)).join(tr('、', ', ')) || tr('无', 'None')}`,
].join('\n'))

const conflictServerText = computed(() => {
  const value = conflictServer.value
  if (!value) return tr('（服务器版本加载中…）', '(Loading server version…)')
  return [
    `${tr('名称：', 'Name: ')}${value.name}`,
    `${tr('摘要：', 'Summary: ')}${value.summary || tr('（空）', '(Empty)')}`,
    `${tr('状态：', 'Status: ')}${projectStatusLabel(value.status)}`,
    `${tr('健康度：', 'Health: ')}${healthLabels.value[value.health]}`,
    `${tr('目标日期：', 'Target Date: ')}${value.target_date ?? tr('未设置', 'Unset')}`,
    `${tr('负责人：', 'Lead: ')}${value.lead?.display_name ?? tr('未指定', 'Unassigned')}`,
    `${tr('成员：', 'Members: ')}${value.memberships.map((row) => row.user.display_name || row.user.username).join(tr('、', ', ')) || tr('无', 'None')}`,
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
    error.value = errorMessage(reason, tr('项目加载失败', 'Failed to load project'))
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
    title: tr('删除项目', 'Delete Project'),
    content: () => h('div', { class: 'project-delete-confirm' }, [
      h('p', tr('仅当项目下没有会议且没有项目附件时才能删除；删除不会级联清理项目下的记录，请先自行处理相关数据。', 'Projects can only be deleted when they have no meetings or attachments; deletion does not cascade-delete project records.')),
      h('p', tr(`请输入项目名称“${target.name}”以确认：`, `Type project name "${target.name}" to confirm:`)),
      h(NInput, {
        value: deleteTargetName.value,
        'onUpdate:value': (value: string) => { deleteTargetName.value = value },
        inputProps: { 'aria-label': tr('输入项目名称确认', 'Confirm project name') },
        placeholder: target.name,
      }),
      deleteError.value
        ? h('p', { class: 'notice notice-error', role: 'alert' }, deleteError.value)
        : null,
    ]),
    positiveText: tr('确认删除', 'Delete'),
    negativeText: tr('取消', 'Cancel'),
    onPositiveClick: async () => {
      if (deleteTargetName.value.trim() !== target.name) {
        deleteError.value = tr('请输入完整项目名称以确认删除', 'Please enter the exact project name to confirm deletion')
        return false
      }
      try {
        await api(`/api/projects/${target.id}`, { method: 'DELETE' })
        await router.push('/projects')
      } catch (reason) {
        deleteError.value = errorMessage(reason, tr('项目删除失败', 'Failed to delete project'))
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
    <p v-if="loading" class="empty-state">{{ tr('正在加载项目工作区…', 'Loading project workspace…') }}</p>
    <p v-else-if="error && !project" class="notice notice-error">{{ error }}</p>
    <template v-else-if="project">
      <PageHeader eyebrow="Project workspace" :title="project.name" :summary="project.summary">
        <template #meta>
          <div class="project-context">
            <StatusPill :status="project.status" kind="project" />
            <span><i class="health-dot" :data-health="project.health"></i>{{ healthLabels[project.health] }}</span>
            <span>{{ tr('负责人：', 'Lead: ') }}{{ project.lead?.display_name ?? tr('未指定', 'Unassigned') }}</span>
            <span>{{ tr('成员：', 'Members: ') }}{{ project.memberships.length }}</span>
            <span>{{ tr('目标：', 'Target: ') }}{{ project.target_date ?? tr('未设置', 'Unset') }}</span>
          </div>
        </template>
        <template #actions>
          <NDropdown v-if="canContribute" trigger="click" :options="createOptions" @select="onCreateSelect">
            <NButton type="primary">{{ tr('新建', 'New') }}</NButton>
          </NDropdown>
          <NButton v-if="canManage" quaternary @click="openEdit">{{ tr('编辑项目', 'Edit Project') }}</NButton>
          <NButton v-if="canManage" quaternary type="error" @click="confirmDelete">{{ tr('删除项目', 'Delete Project') }}</NButton>
        </template>
      </PageHeader>

      <NDrawer
        :show="editOpen"
        placement="right"
        :width="'min(560px, 100vw)'"
        :mask-closable="!projectSaving"
        @update:show="(value: boolean) => { if (!value) closeEdit() }"
      >
        <NDrawerContent :title="tr('编辑项目', 'Edit Project')" closable>
          <NForm label-placement="top" :show-require-mark="false">
            <NFormItem :label="tr('名称', 'Name')">
              <NInput v-model:value="editForm.name" :input-props="{ 'aria-label': tr('名称', 'Name') }" />
            </NFormItem>
            <NFormItem :label="tr('摘要', 'Summary')">
              <NInput
                v-model:value="editForm.summary"
                type="textarea"
                :autosize="{ minRows: 3 }"
                :input-props="{ 'aria-label': tr('摘要', 'Summary') }"
              />
            </NFormItem>
            <NFormItem :label="tr('状态', 'Status')">
              <NSelect v-model:value="editForm.status" class="project-edit-status" :options="statusOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem :label="tr('健康度', 'Health')">
              <NSelect v-model:value="editForm.health" class="project-edit-health" :options="healthOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem :label="tr('目标日期', 'Target Date')">
              <input v-model="editForm.target_date" class="native-date-input" type="date" :aria-label="tr('目标日期', 'Target Date')" />
            </NFormItem>
            <NFormItem :label="tr('负责人', 'Lead')">
              <NSelect
                v-model:value="editForm.lead_user_id"
                class="project-edit-lead-select"
                :options="memberOptions"
                :virtual-scroll="false"
                clearable
                :placeholder="tr('选择负责人', 'Select lead')"
              />
            </NFormItem>
            <NFormItem :label="tr('成员', 'Members')">
              <NSelect
                v-model:value="editForm.member_ids"
                class="project-edit-member-select"
                :options="memberOptions"
                :virtual-scroll="false"
                multiple
                :placeholder="tr('选择成员', 'Select members')"
              />
            </NFormItem>
          </NForm>
          <p class="form-hint">{{ tr('移除成员会立即撤销其项目访问，但不会删除其历史记录。', 'Removing a member immediately revokes their project access without deleting their history.') }}</p>
          <p class="form-hint">{{ tr('干系人可查看不可编辑；当前没有成员角色指引入口。', 'Stakeholders have view-only access.') }}</p>
          <div class="project-member-roles">
            <NTag v-for="row in project.memberships" :key="row.user.id" size="small">
              {{ row.user.display_name || row.user.username }} · {{ memberRoleLabels[row.role] }}
            </NTag>
          </div>
          <p v-if="projectSaveError" class="notice notice-error" role="alert">{{ projectSaveError }}</p>
          <template #footer>
            <NButton quaternary :disabled="projectSaving" @click="closeEdit">{{ tr('取消', 'Cancel') }}</NButton>
            <NButton
              type="primary"
              :loading="projectSaving"
              :disabled="projectSaving || !editForm.name.trim()"
              @click="submitEdit"
            >
              {{ tr('保存项目', 'Save Project') }}
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
      <nav class="project-tabs" :aria-label="tr('项目内容', 'Project tabs')">
        <NTabs :value="tab" type="line" @update:value="selectTab">
          <NTabPane name="overview" :tab="tr('概览', 'Overview')" :tab-props="tabA11y('overview')">
            <ProjectOverview :project="project" :attention="attention" :open-actions="openActions" :can-contribute="canContribute" @schedule-meeting="openCreate('meeting')" @open-tab="selectTab" />
          </NTabPane>
          <NTabPane name="meetings" :tab="tr('会议', 'Meetings')" :tab-props="tabA11y('meetings')">
            <ProjectRecordTabs :project="project" tab="meetings" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" @changed="load" />
          </NTabPane>
          <NTabPane name="actions" :tab="tr('行动项', 'Actions')" :tab-props="tabA11y('actions')">
            <ProjectRecordTabs :project="project" tab="actions" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" @changed="load" />
          </NTabPane>
          <NTabPane name="decisions" :tab="tr('决策', 'Decisions')" :tab-props="tabA11y('decisions')">
            <ProjectRecordTabs :project="project" tab="decisions" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" @changed="load" />
          </NTabPane>
          <NTabPane name="questions" :tab="tr('开放问题', 'Questions')" :tab-props="tabA11y('questions')">
            <ProjectQuestionsTab :project="project" :can-contribute="canContribute" @reload="load" />
          </NTabPane>
          <NTabPane name="files" :tab="tr('文件', 'Files')" :tab-props="tabA11y('files')">
            <ProjectRecordTabs :project="project" tab="files" :can-contribute="canContribute" @create="openCreate" @uploaded="addAttachment" @deleted="removeAttachment" />
          </NTabPane>
          <NTabPane name="activity" :tab="tr('动态', 'Activity')" :tab-props="tabA11y('activity')">
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
