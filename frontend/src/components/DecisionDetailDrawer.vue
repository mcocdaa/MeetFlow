<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopconfirm, NSelect, NTag } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { UserRef } from '../api/contracts'
import { session } from '../auth/session'
import type { Decision, DecisionReviewer } from '../domain/outcomes'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'
import { reviewStatusLabel } from '../utils/labels'
import { formatDateTime } from '../utils/time'
import MarkdownView from './MarkdownView.vue'
import StatusPill from './StatusPill.vue'

const { tr } = useI18n()

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
  if (!decision) return tr('尚未定稿', 'Not finalized')
  if (decision.decided_by) return personName(decision.decided_by)
  if (decision.decided_by_user_id) return personName(decision.decided_by_user_id)
  return tr('尚未定稿', 'Not finalized')
})
const memberOptions = computed(() => props.members.map((member) => ({
  label: member.display_name || member.username,
  value: member.id,
})))
const candidateOptions = computed(() => supersedeCandidates.value.map((candidate) => ({
  label: candidate.title,
  value: candidate.id,
})))
const reviewStatusOptions = computed(() => [
  { label: tr('同意', 'Approve'), value: 'approved' },
  { label: tr('需修改', 'Request Changes'), value: 'changes_requested' },
])

function personName(value: UserRef | string | null | undefined): string {
  if (value && typeof value === 'object') return value.display_name || value.username
  const id = typeof value === 'string' ? value : null
  if (!id) return tr('未指定', 'Unassigned')
  return props.userNames[id] ?? tr(`用户·${id.slice(0, 8)}`, `User·${id.slice(0, 8)}`)
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
    error.value = errorMessage(reason, tr('替代候选加载失败', 'Failed to load supersede candidates'))
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
    error.value = errorMessage(reason, tr('决策定稿失败', 'Failed to finalize decision'))
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
    error.value = errorMessage(reason, tr('决策撤回失败', 'Failed to withdraw decision'))
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
    error.value = errorMessage(reason, tr('决策保存失败', 'Failed to save decision'))
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
    error.value = errorMessage(reason, tr('决策评审失败', 'Failed to submit review'))
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
    error.value = errorMessage(reason, tr('决策替代失败', 'Failed to supersede decision'))
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
    <NDrawerContent :title="tr('决策详情', 'Decision Details')" closable>
      <div v-if="decision" class="decision-detail">
        <header class="decision-detail-meta">
          <StatusPill :status="decision.status" kind="decision" />
          <span>{{ tr('创建人：', 'Created by: ') }}{{ personName(decision.created_by) }}</span>
          <span>{{ tr('定稿人：', 'Finalized by: ') }}{{ decidedByName }}</span>
          <NTag v-if="decision.status === 'superseded'" size="small">{{ tr('已被替代', 'Superseded') }}</NTag>
        </header>
        <p v-if="decision.supersedes_decision_id" class="form-hint">{{ tr(`替代了决策 ${decision.supersedes_decision_id}`, `Supersedes decision ${decision.supersedes_decision_id}`) }}</p>

        <section class="decision-section">
          <h3>{{ tr('决策内容', 'Decision Statement') }}</h3>
          <MarkdownView :source="decision.decision_markdown" />
        </section>
        <section v-if="decision.rationale_markdown" class="decision-section">
          <h3>{{ tr('决策理由', 'Rationale') }}</h3>
          <MarkdownView :source="decision.rationale_markdown" />
        </section>

        <section class="decision-section">
          <h3>{{ tr('评审人', 'Reviewers') }}</h3>
          <div v-if="decision.reviewers?.length" class="reviewer-list">
            <div v-for="reviewer in decision.reviewers" :key="reviewer.user_id" class="reviewer-row">
              <strong>{{ reviewerName(reviewer) }}</strong>
              <NTag size="small">{{ reviewStatusLabel(reviewer.status) }}</NTag>
              <span v-if="reviewer.responded_at" class="muted">{{ formatDateTime(reviewer.responded_at) }}</span>
              <span v-if="reviewer.comment">{{ reviewer.comment }}</span>
            </div>
          </div>
          <p v-else class="muted">{{ tr('尚未指定评审人。', 'No reviewers assigned.') }}</p>
        </section>

        <div v-if="canEdit" class="row-actions decision-actions">
          <NButton size="small" quaternary :disabled="saving" @click="editing = !editing">{{ editing ? tr('收起编辑', 'Close Edit') : tr('编辑', 'Edit') }}</NButton>
          <NPopconfirm :positive-text="tr('确认', 'Confirm')" :negative-text="tr('取消', 'Cancel')" @positive-click="finalizeDecision">
            <template #trigger>
              <NButton size="small" type="primary" :disabled="saving">{{ tr('定稿', 'Finalize') }}</NButton>
            </template>
            {{ tr('定稿后决策将生效且不可再编辑，确定定稿吗？', 'Once finalized, the decision becomes final and cannot be edited. Finalize now?') }}
          </NPopconfirm>
          <NButton size="small" quaternary :disabled="saving" @click="withdrawDecision">{{ tr('撤回', 'Withdraw') }}</NButton>
        </div>

        <NForm v-if="editing && canEdit" label-placement="top" :show-require-mark="false" class="decision-edit-form">
          <NFormItem :label="tr('决策标题', 'Decision Title')">
            <NInput v-model:value="editForm.title" :input-props="{ 'aria-label': tr('决策标题', 'Decision Title') }" />
          </NFormItem>
          <NFormItem :label="tr('决策内容', 'Decision Statement')">
            <NInput v-model:value="editForm.decision_markdown" type="textarea" :autosize="{ minRows: 3 }" :input-props="{ 'aria-label': tr('决策内容', 'Decision Statement') }" />
          </NFormItem>
          <NFormItem :label="tr('决策理由', 'Rationale')">
            <NInput v-model:value="editForm.rationale_markdown" type="textarea" :autosize="{ minRows: 2 }" :input-props="{ 'aria-label': tr('决策理由', 'Rationale') }" />
          </NFormItem>
          <NFormItem :label="tr('评审人', 'Reviewers')">
            <NSelect
              v-model:value="editForm.reviewer_ids"
              class="decision-edit-reviewers"
              :options="memberOptions"
              :virtual-scroll="false"
              multiple
              :placeholder="tr('选择评审人', 'Select reviewers')"
            />
          </NFormItem>
          <NButton type="primary" :loading="saving" :disabled="saving || !editForm.title.trim()" @click="saveEdit">{{ tr('保存修改', 'Save Changes') }}</NButton>
        </NForm>

        <section v-if="canReview" class="decision-section decision-review">
          <h3>{{ tr('提交评审', 'Submit Review') }}</h3>
          <NForm label-placement="top" :show-require-mark="false">
            <NFormItem :label="tr('评审结论', 'Review Status')">
              <NSelect v-model:value="reviewStatus" class="decision-review-status" :options="reviewStatusOptions" :virtual-scroll="false" />
            </NFormItem>
            <NFormItem :label="tr('评审意见', 'Review Comment')">
              <NInput v-model:value="reviewComment" type="textarea" :autosize="{ minRows: 2 }" :input-props="{ 'aria-label': tr('评审意见', 'Review Comment') }" />
            </NFormItem>
          </NForm>
          <NButton type="primary" :loading="saving" :disabled="saving" @click="saveReview">{{ tr('提交评审', 'Submit Review') }}</NButton>
        </section>

        <section v-if="showSupersede" class="decision-section decision-supersede">
          <h3>{{ tr('替代决策', 'Supersede Decision') }}</h3>
          <p class="form-hint">{{ tr('替代后本决策标记为已替代，新决策记录替代来源。', 'This decision will be marked as superseded by the selected final decision.') }}</p>
          <NSelect
            v-model:value="supersedeTargetId"
            class="decision-supersede-select"
            :options="candidateOptions"
            :virtual-scroll="false"
            :placeholder="tr('选择同项目的最终决策', 'Select a final decision in this project')"
          />
          <NButton type="primary" :loading="saving" :disabled="saving || !supersedeTargetId" @click="saveSupersede">{{ tr('确认替代', 'Confirm Supersede') }}</NButton>
        </section>

        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      </div>
      <template #footer>
        <NButton quaternary @click="close">{{ tr('关闭', 'Close') }}</NButton>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.decision-detail-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  color: var(--muted, #66727f);
  font-size: 13px;
}

.reviewer-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
