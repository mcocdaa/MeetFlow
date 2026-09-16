<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import StatusPill from './StatusPill.vue'
import { RouterLink } from 'vue-router'

import { api, ApiError } from '../api/client'
import type { Decision, OpenQuestion } from '../domain/outcomes'
import type { ProjectDetail } from '../domain/projects'
import { errorMessage } from '../utils/errors'

type MeetingOption = { id: string; title: string; scheduled_start: string; status: string; version?: number }

const props = defineProps<{ project: ProjectDetail; canContribute: boolean }>()
const emit = defineEmits<{ reload: [] }>()

const questions = ref<OpenQuestion[]>([])
const loading = ref(false)
const error = ref('')

const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editTarget = ref<OpenQuestion | null>(null)
const form = ref({ question_markdown: '', owner_user_id: null as string | null })
const formSaving = ref(false)
const formError = ref('')

const scheduleTarget = ref<OpenQuestion | null>(null)
const scheduleMeetingId = ref<string | null>(null)
const scheduleMeetings = ref<MeetingOption[]>([])
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)
const scheduleError = ref('')

const resolveTarget = ref<OpenQuestion | null>(null)
const resolveDecisionId = ref<string | null>(null)
const resolveDecisions = ref<Decision[]>([])
const resolveLoading = ref(false)
const resolveSaving = ref(false)
const resolveError = ref('')

const memberOptions = computed(() => props.project.memberships.map((row) => ({
  label: row.user.display_name || row.user.username,
  value: row.user.id,
})))
const scheduleOptions = computed(() => scheduleMeetings.value.map((meeting) => ({
  label: `${meeting.title} · ${meeting.scheduled_start.slice(0, 10)}`,
  value: meeting.id,
})))
const resolveDecisionOptions = computed(() => resolveDecisions.value.map((decision) => ({
  label: decision.title,
  value: decision.id,
})))

function ownerName(userId: string | null | undefined) {
  if (!userId) return '未指派'
  const row = props.project.memberships.find((item) => item.user.id === userId)
  return row?.user.display_name || row?.user.username || '未指派'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const value = await api<OpenQuestion[]>(`/api/projects/${props.project.id}/open-questions?limit=200`)
    questions.value = Array.isArray(value) ? value : []
  } catch (reason) {
    error.value = errorMessage(reason, '开放问题加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  if (!props.canContribute) return
  formMode.value = 'create'
  editTarget.value = null
  form.value = { question_markdown: '', owner_user_id: null }
  formError.value = ''
  formOpen.value = true
}

function openEdit(question: OpenQuestion) {
  if (!props.canContribute || question.is_derived) return
  formMode.value = 'edit'
  editTarget.value = question
  form.value = {
    question_markdown: question.question_markdown,
    owner_user_id: question.owner_user_id ?? null,
  }
  formError.value = ''
  formOpen.value = true
}

async function saveForm() {
  if (formSaving.value || !form.value.question_markdown.trim()) return
  formSaving.value = true
  formError.value = ''
  try {
    const body = {
      question_markdown: form.value.question_markdown.trim(),
      owner_user_id: form.value.owner_user_id || null,
    }
    if (formMode.value === 'create') {
      await api(`/api/projects/${props.project.id}/open-questions`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
    } else {
      const target = editTarget.value
      if (!target) return
      await api(`/api/open-questions/${target.id}`, {
        method: 'PUT',
        body: JSON.stringify({ ...body, expected_version: target.version }),
      })
    }
    formOpen.value = false
    await load()
    emit('reload')
  } catch (reason) {
    formError.value = errorMessage(reason, '开放问题保存失败')
  } finally {
    formSaving.value = false
  }
}

async function openSchedule(question: OpenQuestion) {
  if (!props.canContribute || question.is_derived) return
  scheduleTarget.value = question
  scheduleMeetingId.value = null
  scheduleError.value = ''
  scheduleLoading.value = true
  try {
    const page = await api<{ items: MeetingOption[] }>(`/api/meetings?project_id=${props.project.id}&limit=200`)
    const now = Date.now()
    scheduleMeetings.value = (page?.items ?? []).filter((meeting) => (
      meeting.status !== 'canceled' && new Date(meeting.scheduled_start).getTime() > now
    ))
  } catch (reason) {
    scheduleError.value = errorMessage(reason, '会议列表加载失败')
  } finally {
    scheduleLoading.value = false
  }
}

async function saveSchedule() {
  const target = scheduleTarget.value
  const meeting = scheduleMeetings.value.find((item) => item.id === scheduleMeetingId.value)
  if (!target || !meeting || scheduleSaving.value) return
  scheduleSaving.value = true
  scheduleError.value = ''
  try {
    let meetingVersion = meeting.version
    if (meetingVersion === undefined) {
      meetingVersion = (await api<{ version: number }>(`/api/meetings/${meeting.id}`)).version
    }
    await api(`/api/open-questions/${target.id}/schedule`, {
      method: 'POST',
      body: JSON.stringify({
        meeting_id: meeting.id,
        expected_version: target.version,
        expected_meeting_version: meetingVersion,
      }),
    })
    scheduleTarget.value = null
    await load()
    emit('reload')
  } catch (reason) {
    const message = errorMessage(reason, '排期失败')
    scheduleError.value = reason instanceof ApiError && reason.status === 409
      ? `${message}，请刷新后重试`
      : message
  } finally {
    scheduleSaving.value = false
  }
}

function canResolve(question: OpenQuestion) {
  return props.canContribute
    && !question.is_derived
    && question.status !== 'resolved'
    && question.status !== 'dropped'
}

async function openResolve(question: OpenQuestion) {
  if (!canResolve(question)) return
  resolveTarget.value = question
  resolveDecisionId.value = null
  resolveError.value = ''
  resolveLoading.value = true
  try {
    const page = await api<{ items: Decision[] }>(
      `/api/decisions?project_id=${props.project.id}&status=final&limit=200`,
    )
    resolveDecisions.value = page?.items ?? []
  } catch (reason) {
    resolveError.value = errorMessage(reason, '决策列表加载失败')
  } finally {
    resolveLoading.value = false
  }
}

async function saveResolve() {
  const target = resolveTarget.value
  if (!target || resolveSaving.value) return
  resolveSaving.value = true
  resolveError.value = ''
  try {
    await api(`/api/open-questions/${target.id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        decision_id: resolveDecisionId.value || null,
        expected_version: target.version,
      }),
    })
    resolveTarget.value = null
    await load()
    emit('reload')
  } catch (reason) {
    const message = errorMessage(reason, '解决失败')
    resolveError.value = reason instanceof ApiError && reason.status === 409
      ? `${message}，请刷新后重试`
      : message
  } finally {
    resolveSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="workspace-section project-questions-tab">
    <header class="section-heading">
      <h2>开放问题</h2>
      <NButton v-if="canContribute" type="primary" size="small" @click="openCreate">添加开放问题</NButton>
    </header>
    <p v-if="loading" class="muted">正在加载开放问题…</p>
    <div v-else-if="questions.length" class="project-record-list">
      <div v-for="item in questions" :key="item.id" class="project-record-row question-row">
        <div class="question-row-main">
          <strong>{{ item.question_markdown }}</strong>
          <span>
            <StatusPill :status="item.status" kind="question" />
            · {{ ownerName(item.owner_user_id) }}
            <template v-if="item.meeting_id"> · <RouterLink :to="`/meetings/${item.meeting_id}`">来源会议</RouterLink></template>
          </span>
          <span v-if="item.scheduled_meeting_id" class="muted">
            已排入会议 <RouterLink :to="`/meetings/${item.scheduled_meeting_id}`">{{ item.scheduled_meeting_id }}</RouterLink>
          </span>
          <span v-if="item.resolved_by_decision_id" class="muted">
            由决策解决 <RouterLink :to="`/decisions?highlight=${item.resolved_by_decision_id}`">{{ item.resolved_by_decision_id }}</RouterLink>
          </span>
          <span v-if="item.converted_from_agenda_item_id || item.source_agenda_item_id" class="muted">
            来源议程 {{ item.converted_from_agenda_item_id ?? item.source_agenda_item_id }}
          </span>
        </div>
        <div v-if="canContribute && !item.is_derived" class="row-actions">
          <button class="button button-quiet" type="button" :aria-label="`编辑开放问题“${item.question_markdown}”`" @click="openEdit(item)">编辑</button>
          <button
            v-if="item.status === 'open' && !item.scheduled_meeting_id"
            class="button button-primary"
            type="button"
            :aria-label="`排期开放问题“${item.question_markdown}”`"
            @click="openSchedule(item)"
          >
            排期
          </button>
          <button
            v-if="canResolve(item)"
            class="button button-quiet"
            type="button"
            :aria-label="`解决开放问题“${item.question_markdown}”`"
            @click="openResolve(item)"
          >
            解决
          </button>
        </div>
      </div>
    </div>
    <p v-else class="muted">当前没有开放问题。</p>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

    <NDrawer
      :show="formOpen"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!formSaving"
      @update:show="(value: boolean) => { if (!value) formOpen = false }"
    >
      <NDrawerContent :title="formMode === 'create' ? '添加开放问题' : '编辑开放问题'" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem label="问题内容">
            <NInput v-model:value="form.question_markdown" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '问题内容' }" />
          </NFormItem>
          <NFormItem label="负责人">
            <NSelect
              v-model:value="form.owner_user_id"
              class="question-owner-select"
              :options="memberOptions"
              :virtual-scroll="false"
              clearable
              placeholder="选择负责人"
            />
          </NFormItem>
        </NForm>
        <p v-if="formError" class="notice notice-error" role="alert">{{ formError }}</p>
        <template #footer>
          <NButton quaternary :disabled="formSaving" @click="formOpen = false">取消</NButton>
          <NButton
            type="primary"
            :loading="formSaving"
            :disabled="formSaving || !form.question_markdown.trim()"
            @click="saveForm"
          >
            {{ formMode === 'create' ? '提交' : '保存修改' }}
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NDrawer
      :show="Boolean(scheduleTarget)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!scheduleSaving"
      @update:show="(value: boolean) => { if (!value) scheduleTarget = null }"
    >
      <NDrawerContent title="排期开放问题" closable>
        <p class="form-hint">只能排入之后举行的同项目会议；排期会生成一个议题。</p>
        <p v-if="scheduleLoading" class="muted">正在加载可选会议…</p>
        <NSelect
          v-else
          v-model:value="scheduleMeetingId"
          class="question-schedule-meeting"
          :options="scheduleOptions"
          :virtual-scroll="false"
          placeholder="选择未来会议"
        />
        <p v-if="!scheduleLoading && !scheduleOptions.length" class="muted">没有可排期的未来会议。</p>
        <p v-if="scheduleError" class="notice notice-error" role="alert">{{ scheduleError }}</p>
        <template #footer>
          <NButton quaternary :disabled="scheduleSaving" @click="scheduleTarget = null">取消</NButton>
          <NButton
            type="primary"
            :loading="scheduleSaving"
            :disabled="scheduleSaving || !scheduleMeetingId"
            @click="saveSchedule"
          >
            确认排期
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NDrawer
      :show="Boolean(resolveTarget)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!resolveSaving"
      @update:show="(value: boolean) => { if (!value) resolveTarget = null }"
    >
      <NDrawerContent title="解决开放问题" closable>
        <p class="form-hint">可以关联一个同项目的最终决策，也可以不关联直接标记为已解决。</p>
        <p v-if="resolveLoading" class="muted">正在加载最终决策…</p>
        <NSelect
          v-else
          v-model:value="resolveDecisionId"
          class="question-resolve-decision"
          :options="resolveDecisionOptions"
          :virtual-scroll="false"
          clearable
          placeholder="关联最终决策（可选）"
        />
        <p v-if="resolveError" class="notice notice-error" role="alert">{{ resolveError }}</p>
        <template #footer>
          <NButton quaternary :disabled="resolveSaving" @click="resolveTarget = null">取消</NButton>
          <NButton type="primary" :loading="resolveSaving" :disabled="resolveSaving" @click="saveResolve">确认解决</NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>
