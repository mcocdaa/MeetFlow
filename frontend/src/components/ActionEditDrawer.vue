<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import type { ActionPriority, ActionStatus } from '../domain/outcomes'
import type { ProjectActionSummary } from '../domain/projects'
import { errorMessage } from '../utils/errors'
import { ACTION_STATUS_LABELS, PRIORITY_LABELS } from '../utils/labels'

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
const priorityOptions = (Object.keys(PRIORITY_LABELS) as ActionPriority[])
  .map((value) => ({ label: PRIORITY_LABELS[value], value }))
const statusOptions = (Object.keys(ACTION_STATUS_LABELS) as ActionStatus[])
  .map((value) => ({ label: ACTION_STATUS_LABELS[value], value }))

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
    error.value = errorMessage(reason, '行动项保存失败')
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
    <NDrawerContent title="编辑行动项" closable>
      <NForm label-placement="top" :show-require-mark="false">
        <NFormItem label="行动项内容">
          <NInput v-model:value="form.content" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '行动项内容' }" />
        </NFormItem>
        <NFormItem label="负责人">
          <NSelect
            v-model:value="form.owner_user_id"
            class="action-edit-owner"
            :options="memberOptions"
            :virtual-scroll="false"
            clearable
            placeholder="选择负责人"
          />
        </NFormItem>
        <NFormItem label="截止日期">
          <input v-model="form.due_date" class="native-date-input" type="date" aria-label="截止日期" />
        </NFormItem>
        <NFormItem label="优先级">
          <NSelect v-model:value="form.priority" class="action-edit-priority" :options="priorityOptions" :virtual-scroll="false" />
        </NFormItem>
        <NFormItem label="状态">
          <NSelect v-model:value="form.status" class="action-edit-status" :options="statusOptions" :virtual-scroll="false" />
        </NFormItem>
      </NForm>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">取消</NButton>
        <NButton
          type="primary"
          :loading="saving"
          :disabled="saving || !form.content.trim()"
          @click="save"
        >
          保存行动项
        </NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
