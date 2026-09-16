<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopconfirm, NSelect, NTag } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { Decision, DecisionReviewer } from '../domain/outcomes'
import { errorMessage } from '../utils/errors'
import { REVIEW_STATUS_LABELS } from '../utils/labels'
import { formatDateTime } from '../utils/time'
import MarkdownView from './MarkdownView.vue'
import StatusPill from './StatusPill.vue'

type SupersedeCandidate = { id: string; title: string; version: number }

const props = defineProps<{
  show: boolean
  decision: Decision | null
  members: UserRef[]
  userNames: Record<string, string>
  canContribute: boolean
}>()
const emit = defineEmits<{ close: []; saved: [] }>()

const saving = ref(false)
const error = ref('')
const editing = ref(false)
const reviewStatus = ref<'approved' | 'changes_requested'>('approved')
const reviewComment = ref('')
const supersedeTargetId = ref<string | null>(null)
const supersedeCandidates = ref<SupersedeCandidate[]>([])
const editForm = ref({
  title: '',
  decision_markdown: '',
  rationale_markdown: '',
  reviewer_ids: [] as string[],
})

const isDerived = computed(() => props.decision?.is_derived === true)
const isProposed = computed(() => props.decision?.status === 'proposed')
const canEdit = computed(() => props.canContribute && !isDerived.value && isProposed.value)
const pendingReviewer = computed(() => props.decision?.reviewers?.find(
  (row) => row.user_id === session.user?.id && row.status === 'pending',
) ?? null)
const canReview = computed(() => canEdit.value && pendingReviewer.value !== null)
const canSupersede = computed(() => (
  props.canContribute && !isDerived.value && props.decision?.status === 'final'
))
const showSupersede = computed(() => canSupersede.value && supersedeCandidates.value.length > 0)
const decidedByName = computed(() => {
  const decision = props.decision
  if (!decision) return '尚未定稿'
  if (decision.decided_by) return personName(decision.decided_by)
  if (decision.decided_by_user_id) return personName(decision.decided_by_user_id)
  return '尚未定稿'
})
const memberOptions = computed(() => props.members.map((member) => ({
  label: member.display_name || member.username,
  value: member.id,
})))
const candidateOptions = computed(() => supersedeCandidates.value.map((candidate) => ({
  label: candidate.title,
  value: candidate.id,
})))
const reviewStatusOptions = [
  { label: '同意', value: 'approved' },
  { label: '需修改', value: 'changes_requested' },
]

function personName(value: UserRef | string | null | undefined): string {
  if (value && typeof value === 'object') return value.display_name || value.username
  const id = typeof value === 'string' ? value : null
  if (!id) return '未指定'
  return props.userNames[id] ?? `用户·${id.slice(0, 8)}`
}

function reviewerName(reviewer: DecisionReviewer) {
  return personName(reviewer.user ?? reviewer.user_id)
}

async function loadCandidates() {
  supersedeCandidates.value = []
  const decision = props.decision
  if (!decision || !canSupersede.value) return
  try {
    const page = await api<{ items: Decision[] }>(
      `/api/decisions?project_id=${decision.project_id}&status=final&limit=200`,
    )
    supersedeCandidates.value = (page?.items ?? [])
      .filter((item) => (
        item.id !== decision.id && item.status === 'final' && !item.supersedes_decision_id
      ))
      .map((item) => ({ id: item.id, title: item.title, version: item.version }))
  } catch (reason) {
    error.value = errorMessage(reason, '替代候选加载失败')
  }
}

watch(() => [props.show, props.decision?.id], () => {
  const decision = props.decision
  if (!props.show || !decision) return
  error.value = ''
  editing.value = false
  reviewStatus.value = 'approved'
  reviewComment.value = ''
  supersedeTargetId.value = null
  editForm.value = {
    title: decision.title,
    decision_markdown: decision.decision_markdown,
    rationale_markdown: decision.rationale_markdown,
    reviewer_ids: (decision.reviewers ?? []).map((row) => row.user_id),
  }
  void loadCandidates()
}, { immediate: true })

function close() {
  if (saving.value) return
  emit('close')
}

function succeeded() {
  emit('saved')
}

async function finalizeDecision() {
  const decision = props.decision
  if (!decision || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/decisions/${decision.id}/finalize`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: decision.version }),
    })
    succeeded()
  } catch (reason) {
    error.value = errorMessage(reason, '决策定稿失败')
  } finally {
    saving.value = false
  }
}

async function withdrawDecision() {
  const decision = props.decision
  if (!decision || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/decisions/${decision.id}/withdraw`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: decision.version }),
    })
    succeeded()
  } catch (reason) {
    error.value = errorMessage(reason, '决策撤回失败')
  } finally {
    saving.value = false
  }
}

async function saveEdit() {
  const decision = props.decision
  if (!decision || saving.value || !editForm.value.title.trim()) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/decisions/${decision.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        title: editForm.value.title.trim(),
        decision_markdown: editForm.value.decision_markdown.trim() || editForm.value.title.trim(),
        rationale_markdown: editForm.value.rationale_markdown,
        reviewer_ids: editForm.value.reviewer_ids,
        expected_version: decision.version,
      }),
    })
    succeeded()
  } catch (reason) {
    error.value = errorMessage(reason, '决策保存失败')
  } finally {
    saving.value = false
  }
}

async function saveReview() {
  const decision = props.decision
  if (!decision || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/decisions/${decision.id}/review`, {
      method: 'POST',
      body: JSON.stringify({
        status: reviewStatus.value,
        comment: reviewComment.value,
        expected_version: decision.version,
      }),
    })
    succeeded()
  } catch (reason) {
    error.value = errorMessage(reason, '决策评审失败')
  } finally {
    saving.value = false
  }
}

async function saveSupersede() {
  const decision = props.decision
  const target = supersedeCandidates.value.find((item) => item.id === supersedeTargetId.value)
  if (!decision || !target || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/decisions/${decision.id}/supersede`, {
      method: 'POST',
      body: JSON.stringify({
        new_decision_id: target.id,
        expected_version: decision.version,
        expected_new_version: target.version,
      }),
    })
    succeeded()
  } catch (reason) {
    error.value = errorMessage(reason, '决策替代失败')
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
    <NDrawerContent title="决策详情" closable>
      <div v-if="decision" class="decision-detail">
        <header class="decision-detail-meta">
          <StatusPill :status="decision.status" kind="decision" />
          <span>创建人：{{ personName(decision.created_by) }}</span>
          <span>定稿人：{{ decidedByName }}</span>
          <NTag v-if="decision.status === 'superseded'" size="small">已被替代</NTag>
        </header>
        <p v-if="decision.supersedes_decision_id" class="form-hint">替代了决策 {{ decision.supersedes_decision_id }}</p>

        <section class="decision-section">
          <h3>决策内容</h3>
          <MarkdownView :source="decision.decision_markdown" />
        </section>
        <section v-if="decision.rationale_markdown" class="decision-section">
          <h3>决策理由</h3>
          <MarkdownView :source="decision.rationale_markdown" />
        </section>

        <section class="decision-section">
          <h3>评审人</h3>
          <div v-if="decision.reviewers?.length" class="reviewer-list">
            <div v-for="reviewer in decision.reviewers" :key="reviewer.user_id" class="reviewer-row">
              <strong>{{ reviewerName(reviewer) }}</strong>
              <NTag size="small">{{ REVIEW_STATUS_LABELS[reviewer.status] }}</NTag>
              <span v-if="reviewer.responded_at" class="muted">{{ formatDateTime(reviewer.responded_at) }}</span>
              <span v-if="reviewer.comment">{{ reviewer.comment }}</span>
            </div>
          </div>
          <p v-else class="muted">尚未指定评审人。</p>
        </section>

        <div v-if="canEdit" class="row-actions decision-actions">
          <NButton size="small" quaternary :disabled="saving" @click="editing = !editing">{{ editing ? '收起编辑' : '编辑' }}</NButton>
          <NPopconfirm positive-text="确认" negative-text="取消" @positive-click="finalizeDecision">
            <template #trigger>
              <NButton size="small" type="primary" :disabled="saving">定稿</NButton>
            </template>
            定稿后决策将生效且不可再编辑，确定定稿吗？
          </NPopconfirm>
          <NButton size="small" quaternary :disabled="saving" @click="withdrawDecision">撤回</NButton>
        </div>

        <NForm v-if="editing && canEdit" label-placement="top" :show-require-mark="false" class="decision-edit-form">
          <NFormItem label="决策标题">
            <NInput v-model:value="editForm.title" :input-props="{ 'aria-label': '决策标题' }" />
          </NFormItem>
          <NFormItem label="决策内容">
            <NInput v-model:value="editForm.decision_markdown" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': '决策内容' }" />
          </NFormItem>
          <NFormItem label="决策理由">
            <NInput v-model:value="editForm.rationale_markdown" type="textarea" :autosize="{ minRows: 2 }" :input-props="{ 'aria-label': '决策理由' }" />
          </NFormItem>
          <NFormItem label="评审人">
            <NSelect
              v-model:value="editForm.reviewer_ids"
              class="decision-edit-reviewers"
              :options="memberOptions"
              :virtual-scroll="false"
              multiple
              placeholder="选择评审人"
            />
          </NFormItem>
          <NButton type="primary" :loading="saving" :disabled="saving || !editForm.title.trim()" @click="saveEdit">保存修改</NButton>
        </NForm>

        <section v-if="canReview" class="decision-section decision-review">
          <h3>提交评审</h3>
          <NForm label-placement="top" :show-require-mark="false">
            <NFormItem label="评审结论">
              <NSelect v-model:value="reviewStatus" class="decision-review-status" :options="reviewStatusOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem label="评审意见">
              <NInput v-model:value="reviewComment" type="textarea" :autosize="{ minRows: 2 }" :input-props="{ 'aria-label': '评审意见' }" />
            </NFormItem>
          </NForm>
          <NButton type="primary" :loading="saving" :disabled="saving" @click="saveReview">提交评审</NButton>
        </section>

        <section v-if="showSupersede" class="decision-section decision-supersede">
          <h3>替代决策</h3>
          <p class="form-hint">替代后本决策标记为已替代，新决策记录替代来源。</p>
          <NSelect
            v-model:value="supersedeTargetId"
            class="decision-supersede-select"
            :options="candidateOptions"
            :virtual-scroll="false"
            placeholder="选择同项目的最终决策"
          />
          <NButton type="primary" :loading="saving" :disabled="saving || !supersedeTargetId" @click="saveSupersede">确认替代</NButton>
        </section>

        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      </div>
      <template #footer>
        <NButton quaternary @click="close">关闭</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
