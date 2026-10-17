<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, NTimeline, NTimelineItem } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '../api/client'
import type { ProjectActivityItem, ProjectActivityPage, ProjectDetail, ProjectUpdate } from '../domain/projects'
import { useI18n } from '../i18n'
import { activityLabel } from '../utils/activity'
import { errorMessage } from '../utils/errors'
import { useVersionedSave } from '../composables/useVersionedSave'
import { formatDateTime } from '../utils/time'
import MarkdownView from './MarkdownView.vue'
import MarkdownEditor from './MarkdownEditor.vue'
import PluginEditorSlot from './PluginEditorSlot.vue'
import ProjectUpdateComposer from './ProjectUpdateComposer.vue'
import VersionConflictDialog from './VersionConflictDialog.vue'

const { tr } = useI18n()

const props = defineProps<{ project: ProjectDetail; canContribute: boolean }>()
const emit = defineEmits<{ reload: [] }>()

const activityItems = ref<ProjectActivityItem[]>([])
const activityCursor = ref<number | null>(null)
const activityLoading = ref(false)
const activityError = ref('')

const updates = ref<ProjectUpdate[]>([])
const updatesOffset = ref(0)
const updatesHasMore = ref(false)
const updatesLoading = ref(false)

type Health = 'on_track' | 'at_risk' | 'off_track' | 'unset'
const healthLabels = computed<Record<Health, string>>(() => ({
  on_track: tr('进展正常', 'On Track'),
  at_risk: tr('存在风险', 'At Risk'),
  off_track: tr('偏离计划', 'Off Track'),
  unset: tr('未设置', 'Unset'),
}))
const healthOptions = computed(() => (['on_track', 'at_risk', 'off_track', 'unset'] as Health[])
  .map((value) => ({ label: healthLabels.value[value], value })))

const editTarget = ref<ProjectUpdate | null>(null)
const editForm = ref({ health: 'unset' as Health, content_markdown: '' })
const conflictServer = ref<ProjectUpdate | null>(null)

function actorName(item: ProjectActivityItem) {
  return item.actor?.display_name || item.actor?.username || tr('系统', 'System')
}

async function loadActivity(before?: number) {
  activityLoading.value = true
  activityError.value = ''
  try {
    const query = before === undefined ? '?limit=50' : `?limit=50&before=${before}`
    const page = await api<ProjectActivityPage>(`/api/projects/${props.project.id}/activity${query}`)
    const items = Array.isArray(page?.items) ? page.items : []
    activityItems.value = before === undefined ? items : [...activityItems.value, ...items]
    activityCursor.value = page?.next_cursor ?? null
  } catch (reason) {
    activityError.value = errorMessage(reason, tr('项目动态加载失败', 'Failed to load project activity'))
  } finally {
    activityLoading.value = false
  }
}

async function loadUpdates(append = false) {
  updatesLoading.value = true
  try {
    const offset = append ? updatesOffset.value : 0
    const value = await api<ProjectUpdate[]>(
      `/api/projects/${props.project.id}/updates?limit=50&offset=${offset}`,
    )
    const items = Array.isArray(value) ? value : []
    updates.value = append ? [...updates.value, ...items] : items
    updatesOffset.value = (append ? offset : 0) + items.length
    updatesHasMore.value = items.length === 50
  } catch (reason) {
    activityError.value = errorMessage(reason, tr('进展记录加载失败', 'Failed to load progress updates'))
  } finally {
    updatesLoading.value = false
  }
}

const {
  conflict: updateConflict,
  saving: updateSaving,
  error: updateError,
  submit: submitUpdate,
  retryWith: retryUpdate,
  reset: resetUpdate,
} = useVersionedSave<ProjectUpdate>(async (version) => {
  const target = editTarget.value
  if (!target) throw new Error(tr('未选择进展记录', 'No progress update selected'))
  const saved = await api<ProjectUpdate>(`/api/project-updates/${target.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      health: editForm.value.health,
      content_markdown: editForm.value.content_markdown,
      source: target.source,
      expected_version: version,
    }),
  })
  editTarget.value = null
  return saved
}, () => editTarget.value?.version ?? 1)

async function findUpdate(id: string): Promise<ProjectUpdate | undefined> {
  let found = updates.value.find((update) => update.id === id)
  // The ledger can reference updates outside the loaded history page; walk forward
  // without resetting already-loaded pages, bounded so a very old update cannot
  // trigger an unbounded request chain (the backend has no GET-by-id endpoint).
  const walkLimit = 10
  for (let page = 0; !found && updatesHasMore.value && page < walkLimit; page += 1) {
    await loadUpdates(true)
    found = updates.value.find((update) => update.id === id)
  }
  return found
}

watch(updateConflict, async (value) => {
  if (!value) {
    conflictServer.value = null
    return
  }
  const id = editTarget.value?.id
  if (!id) {
    conflictServer.value = null
    return
  }
  try {
    await loadUpdates()
    conflictServer.value = (await findUpdate(id)) ?? null
  } catch {
    conflictServer.value = null
  }
})

const conflictLocalText = computed(() => (
  `${tr('健康度：', 'Health: ')}${healthLabels.value[editForm.value.health]}\n${editForm.value.content_markdown}`
))
const conflictServerText = computed(() => {
  const server = conflictServer.value
  if (!server) return tr('（服务器版本加载中…）', '(Loading server version…)')
  return `${tr('健康度：', 'Health: ')}${healthLabels.value[server.health as Health]}\n${server.content_markdown}`
})

function syncEditForm(target: ProjectUpdate) {
  editForm.value = { health: target.health as Health, content_markdown: target.content_markdown }
}

async function openUpdateEdit(item: ProjectActivityItem) {
  if (!props.canContribute) return
  const target = await findUpdate(item.subject.id)
  if (!target) {
    activityError.value = tr('该进展记录较早，请在“进展记录”中加载更多后重试', 'This update is older; load more in Progress History and try again')
    return
  }
  resetUpdate()
  conflictServer.value = null
  editTarget.value = target
  syncEditForm(target)
}

function closeUpdateEdit() {
  if (updateSaving.value) return
  editTarget.value = null
  resetUpdate()
}

async function submitUpdateEdit() {
  if (updateSaving.value || !editForm.value.content_markdown.trim()) return
  const saved = await submitUpdate()
  if (saved) {
    await Promise.all([loadActivity(), loadUpdates()])
    emit('reload')
  }
}

async function overwriteUpdate(version: number) {
  const saved = await retryUpdate(version)
  if (saved) {
    await Promise.all([loadActivity(), loadUpdates()])
    emit('reload')
  }
}

async function reloadUpdateFromServer() {
  resetUpdate()
  await loadUpdates()
  const target = await findUpdate(editTarget.value?.id ?? '')
  if (target) {
    editTarget.value = target
    syncEditForm(target)
  }
}

async function onComposerSaved() {
  await Promise.all([loadActivity(), loadUpdates()])
  emit('reload')
}

onMounted(() => {
  void loadActivity()
  void loadUpdates()
})
</script>

<template>
  <section class="workspace-section project-activity-tab">
    <header class="section-heading"><div><p class="eyebrow">{{ tr('动态流', 'Activity') }}</p><h2>{{ tr('项目动态', 'Project Activity') }}</h2></div></header>

    <ProjectUpdateComposer v-if="canContribute" :project-id="project.id" :health="project.health" @saved="onComposerSaved" />

    <p v-if="activityError" class="notice notice-error" role="alert">{{ activityError }}</p>

    <NTimeline v-if="activityItems.length" class="project-activity-timeline">
      <NTimelineItem v-for="item in activityItems" :key="item.id" :time="formatDateTime(item.created_at)">
        <p class="activity-entry">
          <strong>{{ actorName(item) }}</strong>
          <span>{{ activityLabel(item.event_type, item.payload) }}</span>
        </p>
        <div v-if="canContribute && item.subject.type === 'project_update'" class="row-actions">
          <button class="button button-quiet" type="button" :aria-label="tr(`编辑进展 ${item.subject.id}`, `Edit update ${item.subject.id}`)" @click="openUpdateEdit(item)">{{ tr('编辑', 'Edit') }}</button>
        </div>
      </NTimelineItem>
    </NTimeline>
    <p v-else-if="!activityLoading" class="muted">{{ tr('尚无项目动态。', 'No project activity yet.') }}</p>

    <div v-if="activityCursor !== null" class="row-actions">
      <button class="button button-quiet" type="button" :disabled="activityLoading" @click="loadActivity(activityCursor)">{{ tr('加载更多', 'Load More') }}</button>
    </div>

    <section class="project-updates-history">
      <header class="section-heading"><h3>{{ tr('进展记录', 'Progress History') }}</h3></header>
      <div v-if="updates.length" class="project-activity-list">
        <article v-for="item in updates" :key="item.id" class="latest-update">
          <MarkdownView :source="item.content_markdown" />
          <p class="attribution">
            {{ item.created_by?.display_name || item.created_by?.username || tr('系统', 'System') }} · {{ formatDateTime(item.created_at) }}
            <template v-if="item.source === 'ai_draft_applied'"> · {{ tr('AI 草稿', 'AI Draft') }}</template>
          </p>
        </article>
      </div>
      <p v-else-if="!updatesLoading" class="muted">{{ tr('尚无项目进展记录。', 'No progress updates recorded yet.') }}</p>
      <div v-if="updatesHasMore" class="row-actions">
        <button class="button button-quiet" type="button" :disabled="updatesLoading" @click="loadUpdates(true)">{{ tr('加载更多', 'Load More') }}</button>
      </div>
    </section>

    <NDrawer
      :show="Boolean(editTarget)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!updateSaving"
      @update:show="(value: boolean) => { if (!value) closeUpdateEdit() }"
    >
      <NDrawerContent :title="tr('编辑项目进展', 'Edit Progress Update')" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem :label="tr('健康度', 'Health')">
            <NSelect v-model:value="editForm.health" class="update-edit-health" :options="healthOptions" :virtual-scroll="false" />
          </NFormItem>
          <NFormItem :label="tr('进展内容', 'Update Content')">
            <PluginEditorSlot
              v-model="editForm.content_markdown"
              :editor-label="tr('进展内容', 'Update Content')"
              data-testid="project-update-edit-editor"
              target-type="project"
              :target-id="project.id"
              slot="project-update-editor"
              :metadata="{ projectId: project.id }"
              @notice="activityError = $event"
            >
              <template #editor="{ disabled, registerEditor }">
                <MarkdownEditor v-model="editForm.content_markdown" :label="tr('进展内容', 'Update Content')" :disabled="updateSaving || disabled" :register-editor="registerEditor" />
              </template>
            </PluginEditorSlot>
          </NFormItem>
        </NForm>
        <p v-if="updateError" class="notice notice-error" role="alert">{{ updateError }}</p>
        <template #footer>
          <NButton quaternary :disabled="updateSaving" @click="closeUpdateEdit">{{ tr('取消', 'Cancel') }}</NButton>
          <NButton
            type="primary"
            :loading="updateSaving"
            :disabled="updateSaving || !editForm.content_markdown.trim()"
            @click="submitUpdateEdit"
          >
            {{ tr('保存进展', 'Save Update') }}
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>

    <VersionConflictDialog
      v-if="updateConflict"
      :local-markdown="conflictLocalText"
      :server-markdown="conflictServerText"
      :actual-version="updateConflict.actualVersion"
      @close="resetUpdate"
      @reload="reloadUpdateFromServer"
      @overwrite="overwriteUpdate"
    />
  </section>
</template>
