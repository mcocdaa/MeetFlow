<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { ProjectDetail } from '../domain/projects'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { priorityLabel } from '../utils/labels'

const { tr } = useI18n()

type Kind = 'decision' | 'action'
const props = defineProps<{ show: boolean; kind: Kind; project: ProjectDetail }>()
const emit = defineEmits<{ close: []; created: [kind: Kind, entity: Record<string, unknown>] }>()

const title = ref('')
const content = ref('')
const rationale = ref('')
const reviewerIds = ref<string[]>([])
const ownerUserId = ref<string | null>(null)
const dueDate = ref('')
const priority = ref('normal')
const saving = ref(false)
const error = ref('')

const drawerTitle = computed(() => (props.kind === 'decision' ? tr('添加决策', 'Add Decision') : tr('添加行动项', 'Add Action Item')))
const memberOptions = computed(() => props.project.memberships.map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const priorityOptions = computed(() => (['low', 'normal', 'high', 'urgent'] as const)
  .map((value) => ({ label: priorityLabel(value), value })))
const canSubmit = computed(() => (
  props.kind === 'action' ? Boolean(content.value.trim()) : Boolean(title.value.trim())
))
const label = computed(() => (props.kind === 'decision' ? tr('决策', 'Decision') : tr('行动项', 'Action item')))

function resetForm() {
  title.value = ''
  content.value = ''
  rationale.value = ''
  reviewerIds.value = []
  ownerUserId.value = null
  dueDate.value = ''
  priority.value = 'normal'
  error.value = ''
}

watch(() => [props.show, props.kind], () => {
  if (props.show) resetForm()
}, { immediate: true })

function close() {
  if (saving.value) return
  emit('close')
}

async function save() {
  if (saving.value || !canSubmit.value) return
  saving.value = true
  error.value = ''
  try {
    const base = `/api/projects/${props.project.id}`
    let entity: Record<string, unknown>
    if (props.kind === 'decision') {
      entity = await api(`${base}/decisions`, {
        method: 'POST',
        body: JSON.stringify({
          title: title.value.trim(),
          decision_markdown: content.value.trim() || title.value.trim(),
          rationale_markdown: rationale.value,
          reviewer_ids: reviewerIds.value,
        }),
      }) as Record<string, unknown>
    } else {
      entity = await api(`${base}/actions`, {
        method: 'POST',
        body: JSON.stringify({
          project_id: props.project.id,
          content: content.value.trim(),
          owner_user_id: ownerUserId.value || null,
          due_date: dueDate.value || null,
          priority: priority.value,
        }),
      }) as Record<string, unknown>
    }
    emit('created', props.kind, entity)
  } catch (reason) {
    error.value = errorMessage(reason, tr(`${label.value}创建失败`, `Failed to create ${label.value.toLowerCase()}`))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <NDrawer
    :show="show"
    placement="right"
    :width="'min(560px, 100vw)'"
    :mask-closable="!saving"
    @update:show="(value: boolean) => { if (!value) close() }"
  >
    <NDrawerContent :title="drawerTitle" closable>
      <NForm label-placement="top" :show-require-mark="false">
        <template v-if="kind === 'decision'">
          <NFormItem :label="tr('决策标题', 'Decision Title')">
            <NInput v-model:value="title" :input-props="{ 'aria-label': tr('决策标题', 'Decision Title') }" :placeholder="tr('例如：采用项目工作区方案', 'e.g., Adopt project workspace layout')" />
          </NFormItem>
          <NFormItem :label="tr('决策内容', 'Decision Statement')">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 4 }" :input-props="{ 'aria-label': tr('决策内容', 'Decision Statement') }" />
          </NFormItem>
          <p class="form-hint">{{ tr('内容为空时以标题作为决策内容。', 'Defaults to the title when left empty.') }}</p>
          <NFormItem :label="tr('决策理由', 'Rationale')">
            <NInput v-model:value="rationale" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': tr('决策理由', 'Rationale') }" />
          </NFormItem>
          <NFormItem :label="tr('评审人', 'Reviewers')">
            <NSelect
              v-model:value="reviewerIds"
              class="project-decision-reviewer-select"
              :options="memberOptions"
              :virtual-scroll="false"
              multiple
              :placeholder="tr('选择评审人', 'Select reviewers')"
            />
          </NFormItem>
        </template>
        <template v-else>
          <NFormItem :label="tr('行动项内容', 'Action Content')">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': tr('行动项内容', 'Action Content') }" :placeholder="tr('要完成什么？', 'What needs to be done?')" />
          </NFormItem>
          <NFormItem :label="tr('负责人', 'Owner')">
            <NSelect
              v-model:value="ownerUserId"
              class="project-action-owner-select"
              :options="memberOptions"
              :virtual-scroll="false"
              clearable
              :placeholder="tr('选择负责人', 'Select owner')"
            />
          </NFormItem>
          <NFormItem :label="tr('截止日期', 'Due Date')">
            <input v-model="dueDate" class="native-date-input" type="date" :aria-label="tr('截止日期', 'Due Date')" />
          </NFormItem>
          <NFormItem :label="tr('优先级', 'Priority')">
            <NSelect v-model:value="priority" class="project-action-priority-select" :options="priorityOptions" :virtual-scroll="false" />
          </NFormItem>
        </template>
      </NForm>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">{{ tr('取消', 'Cancel') }}</NButton>
        <NButton type="primary" :loading="saving" :disabled="saving || !canSubmit" @click="save">{{ drawerTitle }}</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
