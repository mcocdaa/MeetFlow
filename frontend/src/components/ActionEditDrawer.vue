<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import type { ActionPriority, ActionStatus } from '../domain/outcomes'
import type { ProjectActionSummary } from '../domain/projects'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { ACTION_STATUS_LABELS, PRIORITY_LABELS, actionStatusLabel, priorityLabel } from '../utils/labels'

const { tr } = useI18n()

const props = defineProps<{
  show: boolean
  action: ProjectActionSummary | null
  members: UserRef[]
}>()
const emit = defineEmits<{ close: []; saved: [action: Record<string, unknown>] }>()

const saving = ref(false)
const error = ref('')
const form = ref({
  content: '',
  owner_user_id: null as string | null,
  due_date: '',
  priority: 'normal' as ActionPriority,
  status: 'open' as ActionStatus,
})

const memberOptions = computed(() => props.members.map((member) => ({
  label: member.display_name || member.username,
  value: member.id,
})))
const priorityOptions = computed(() => (Object.keys(PRIORITY_LABELS) as ActionPriority[])
  .map((value) => ({ label: priorityLabel(value), value })))
const statusOptions = computed(() => (Object.keys(ACTION_STATUS_LABELS) as ActionStatus[])
  .map((value) => ({ label: actionStatusLabel(value), value })))

watch(() => [props.show, props.action?.id], () => {
  const action = props.action
  if (!props.show || !action) return
  form.value = {
    content: action.content,
    owner_user_id: action.owner_user_id,
    due_date: action.due_date ?? '',
    priority: action.priority as ActionPriority,
    status: action.status as ActionStatus,
  }
  error.value = ''
}, { immediate: true })

function close() {
  if (saving.value) return
  emit('close')
}

async function save() {
  const action = props.action
  if (saving.value || !action || !form.value.content.trim()) return
  saving.value = true
  error.value = ''
  try {
    const saved = await api<Record<string, unknown>>(`/api/actions/${action.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        content: form.value.content.trim(),
        owner_user_id: form.value.owner_user_id || null,
        due_date: form.value.due_date || null,
        priority: form.value.priority,
        status: form.value.status,
        expected_version: action.version ?? 1,
      }),
    })
    emit('saved', saved)
  } catch (reason) {
    error.value = errorMessage(reason, tr('行动项保存失败', 'Failed to save action item'))
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
    <NDrawerContent :title="tr('编辑行动项', 'Edit Action Item')" closable>
      <NForm label-placement="top" :show-require-mark="false">
        <NFormItem :label="tr('行动项内容', 'Action Content')">
          <NInput v-model:value="form.content" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': tr('行动项内容', 'Action Content') }" />
        </NFormItem>
        <NFormItem :label="tr('负责人', 'Owner')">
          <NSelect
            v-model:value="form.owner_user_id"
            class="action-edit-owner"
            :options="memberOptions"
            :virtual-scroll="false"
            clearable
            :placeholder="tr('选择负责人', 'Select owner')"
          />
        </NFormItem>
        <NFormItem :label="tr('截止日期', 'Due Date')">
          <input v-model="form.due_date" class="native-date-input" type="date" :aria-label="tr('截止日期', 'Due Date')" />
        </NFormItem>
        <NFormItem :label="tr('优先级', 'Priority')">
          <NSelect v-model:value="form.priority" class="action-edit-priority" :options="priorityOptions" :virtual-scroll="false" />
        </NFormItem>
        <NFormItem :label="tr('状态', 'Status')">
          <NSelect v-model:value="form.status" class="action-edit-status" :options="statusOptions" :virtual-scroll="false" />
        </NFormItem>
      </NForm>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">{{ tr('取消', 'Cancel') }}</NButton>
        <NButton
          type="primary"
          :loading="saving"
          :disabled="saving || !form.content.trim()"
          @click="save"
        >
          {{ tr('保存行动项', 'Save Action Item') }}
        </NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
