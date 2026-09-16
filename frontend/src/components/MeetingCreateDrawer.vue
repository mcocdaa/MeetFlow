<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, type FormInst, type FormRules } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { ParticipationRole } from '../domain/meetings'
import { errorMessage } from '../utils/errors'
import MeetingParticipantEditor from './MeetingParticipantEditor.vue'

type ProjectOption = { id: string; name: string }
type ParticipantValue = { user_id: string; participation_role: ParticipationRole }

const props = defineProps<{
  show: boolean
  projects: ProjectOption[]
  memberOptions: UserRef[]
  defaultProjectId?: string
}>()

const emit = defineEmits<{
  close: []
  created: [meeting: { id: string }]
}>()

const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const error = ref('')
const form = ref({
  project_id: '',
  title: '',
  purpose_markdown: '',
  scheduled_start: '',
  scheduled_end: '',
  participants: [] as ParticipantValue[],
})

const projectOptions = computed(() => props.projects.map((project) => ({
  label: project.name,
  value: project.id,
})))

const rules = computed<FormRules>(() => ({
  project_id: { required: true, message: '请选择所属项目', trigger: ['change', 'blur'] },
  title: { required: true, message: '请输入会议标题', trigger: ['input', 'blur'] },
  scheduled_start: { required: true, message: '请选择开始时间', trigger: ['change', 'blur'] },
  scheduled_end: [
    { required: true, message: '请选择结束时间', trigger: ['change', 'blur'] },
    {
      validator: () => {
        if (!form.value.scheduled_start || !form.value.scheduled_end) return true
        return new Date(form.value.scheduled_end) > new Date(form.value.scheduled_start)
      },
      message: '结束时间必须晚于开始时间',
      trigger: ['change', 'blur'],
    },
  ],
}))

function resetForm() {
  form.value = {
    project_id: props.defaultProjectId ?? props.projects[0]?.id ?? '',
    title: '',
    purpose_markdown: '',
    scheduled_start: '',
    scheduled_end: '',
    participants: session.user
      ? [{ user_id: session.user.id, participation_role: 'host' }]
      : [],
  }
  error.value = ''
}

watch(() => props.show, (show) => {
  if (show) resetForm()
}, { immediate: true })

function close() {
  if (saving.value) return
  emit('close')
}

async function submit() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  try {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    if (!session.user) return
    const created = await api<{ id: string }>(`/api/projects/${form.value.project_id}/meetings`, {
      method: 'POST',
      body: JSON.stringify({
        title: form.value.title.trim(),
        purpose_markdown: form.value.purpose_markdown,
        scheduled_start: new Date(form.value.scheduled_start).toISOString(),
        scheduled_end: new Date(form.value.scheduled_end).toISOString(),
        host_user_id: session.user.id,
        recorder_user_id: session.user.id,
        summary_markdown: '',
        raw_notes_markdown: '',
        participants: form.value.participants.filter((row) => row.user_id),
      }),
    })
    emit('created', created)
  } catch (caught) {
    error.value = errorMessage(caught, '会议创建失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-drawer
    :show="show"
    placement="right"
    :width="'min(560px, 100vw)'"
    :mask-closable="!saving"
    @update:show="(value: boolean) => { if (!value) close() }"
  >
    <n-drawer-content title="新建会议" closable>
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" :show-require-mark="false">
        <n-form-item label="所属项目" path="project_id">
          <n-select
            v-model:value="form.project_id"
            :options="projectOptions"
            :virtual-scroll="false"
            placeholder="选择项目"
          />
        </n-form-item>
        <n-form-item label="会议标题" path="title">
          <n-input
            v-model:value="form.title"
            :input-props="{ 'aria-label': '会议标题' }"
            placeholder="例如：产品方案评审"
          />
        </n-form-item>
        <n-form-item label="开始时间" path="scheduled_start">
          <input v-model="form.scheduled_start" class="native-datetime-input" type="datetime-local" aria-label="开始时间" />
        </n-form-item>
        <n-form-item label="结束时间" path="scheduled_end">
          <input v-model="form.scheduled_end" class="native-datetime-input" type="datetime-local" aria-label="结束时间" />
        </n-form-item>
        <n-form-item label="会议目的" path="purpose_markdown">
          <n-input
            v-model:value="form.purpose_markdown"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :input-props="{ 'aria-label': '会议目的' }"
            placeholder="这次会议要解决什么问题？"
          />
        </n-form-item>
        <n-form-item label="参与人">
          <MeetingParticipantEditor v-model="form.participants" :member-options="memberOptions" />
        </n-form-item>
      </n-form>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <n-button quaternary :disabled="saving" @click="close">取消</n-button>
        <n-button type="primary" :loading="saving" :disabled="saving" @click="submit">创建会议</n-button>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
