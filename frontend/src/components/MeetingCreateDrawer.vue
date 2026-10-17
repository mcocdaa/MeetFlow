<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, type FormInst, type FormRules } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { ParticipationRole } from '../domain/meetings'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import MeetingParticipantEditor from './MeetingParticipantEditor.vue'

const { tr } = useI18n()

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
  project_id: { required: true, message: tr('请选择所属项目', 'Please select a project'), trigger: ['change', 'blur'] },
  title: {
    required: true,
    message: tr('请输入会议标题', 'Please enter a meeting title'),
    transform: (value: string) => value.trim(),
    trigger: ['input', 'blur'],
  },
  scheduled_start: { required: true, message: tr('请选择开始时间', 'Please select a start time'), trigger: ['change', 'blur'] },
  scheduled_end: [
    { required: true, message: tr('请选择结束时间', 'Please select an end time'), trigger: ['change', 'blur'] },
    {
      validator: () => {
        if (!form.value.scheduled_start || !form.value.scheduled_end) return true
        return new Date(form.value.scheduled_end) > new Date(form.value.scheduled_start)
      },
      message: tr('结束时间必须晚于开始时间', 'End time must be after start time'),
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
    error.value = errorMessage(caught, tr('会议创建失败', 'Failed to create meeting'))
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
    <n-drawer-content :title="tr('新建会议', 'New Meeting')" closable>
      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" :show-require-mark="false">
        <n-form-item :label="tr('所属项目', 'Project')" path="project_id">
          <n-select
            v-model:value="form.project_id"
            :options="projectOptions"
            :virtual-scroll="false"
            :placeholder="tr('选择项目', 'Select project')"
          />
        </n-form-item>
        <n-form-item :label="tr('会议标题', 'Meeting Title')" path="title">
          <n-input
            v-model:value="form.title"
            :input-props="{ 'aria-label': tr('会议标题', 'Meeting Title') }"
            :placeholder="tr('例如：产品方案评审', 'e.g., Product Design Review')"
          />
        </n-form-item>
        <n-form-item :label="tr('开始时间', 'Start Time')" path="scheduled_start">
          <input v-model="form.scheduled_start" class="native-datetime-input" type="datetime-local" :aria-label="tr('开始时间', 'Start Time')" />
        </n-form-item>
        <n-form-item :label="tr('结束时间', 'End Time')" path="scheduled_end">
          <input v-model="form.scheduled_end" class="native-datetime-input" type="datetime-local" :aria-label="tr('结束时间', 'End Time')" />
        </n-form-item>
        <n-form-item :label="tr('会议目的', 'Meeting Purpose')" path="purpose_markdown">
          <n-input
            v-model:value="form.purpose_markdown"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :input-props="{ 'aria-label': tr('会议目的', 'Meeting Purpose') }"
            :placeholder="tr('这次会议要解决什么问题？', 'What should this meeting resolve?')"
          />
        </n-form-item>
        <n-form-item :label="tr('参与人', 'Participants')">
          <MeetingParticipantEditor v-model="form.participants" :member-options="memberOptions" />
        </n-form-item>
      </n-form>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <template #footer>
        <n-button quaternary :disabled="saving" @click="close">{{ tr('取消', 'Cancel') }}</n-button>
        <n-button type="primary" :loading="saving" :disabled="saving" @click="submit">{{ tr('创建会议', 'Create Meeting') }}</n-button>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
