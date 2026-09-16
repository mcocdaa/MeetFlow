<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { ProjectDetail } from '../domain/projects'
import { errorMessage } from '../utils/errors'
import { priorityLabel } from '../utils/labels'

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

const drawerTitle = computed(() => ({ decision: '添加决策', action: '添加行动项' }[props.kind]))
const memberOptions = computed(() => props.project.memberships.map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const priorityOptions = (['low', 'normal', 'high', 'urgent'] as const)
  .map((value) => ({ label: priorityLabel(value), value }))
const canSubmit = computed(() => (
  props.kind === 'action' ? Boolean(content.value.trim()) : Boolean(title.value.trim())
))
const label = computed(() => ({ decision: '决策', action: '行动项' }[props.kind]))

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
    error.value = errorMessage(reason, `${label.value}创建失败`)
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
          <NFormItem label="决策标题">
            <NInput v-model:value="title" :input-props="{ 'aria-label': '决策标题' }" placeholder="例如：采用项目工作区方案" />
          </NFormItem>
          <NFormItem label="决策内容">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 4 }" :input-props="{ 'aria-label': '决策内容' }" />
          </NFormItem>
          <p class="form-hint">内容为空时以标题作为决策内容。</p>
          <NFormItem label="决策理由">
            <NInput v-model:value="rationale" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '决策理由' }" />
          </NFormItem>
          <NFormItem label="评审人">
            <NSelect
              v-model:value="reviewerIds"
              class="project-decision-reviewer-select"
              :options="memberOptions"
              :virtual-scroll="false"
              multiple
              placeholder="选择评审人"
            />
          </NFormItem>
        </template>
        <template v-else>
          <NFormItem label="行动项内容">
            <NInput v-model:value="content" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '行动项内容' }" placeholder="要完成什么？" />
          </NFormItem>
          <NFormItem label="负责人">
            <NSelect
              v-model:value="ownerUserId"
              class="project-action-owner-select"
              :options="memberOptions"
              :virtual-scroll="false"
              clearable
              placeholder="选择负责人"
            />
          </NFormItem>
          <NFormItem label="截止日期">
            <input v-model="dueDate" class="native-date-input" type="date" aria-label="截止日期" />
          </NFormItem>
          <NFormItem label="优先级">
            <NSelect v-model:value="priority" class="project-action-priority-select" :options="priorityOptions" :virtual-scroll="false" />
          </NFormItem>
        </template>
      </NForm>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <NButton quaternary :disabled="saving" @click="close">取消</NButton>
        <NButton type="primary" :loading="saving" :disabled="saving || !canSubmit" @click="save">{{ drawerTitle }}</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
