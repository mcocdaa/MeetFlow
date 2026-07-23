<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

export type AttentionItem = {
  subject_type: 'action' | 'decision' | 'meeting' | string
  subject_id: string
  project: { id: string; name: string; slug: string }
  title: string
  reasons: string[]
  due_date?: string | null
  scheduled_start?: string | null
  status?: string
}

const props = defineProps<{ item: AttentionItem }>()

const reasonLabels: Record<string, string> = {
  action_overdue: '已逾期',
  action_due_soon: '即将到期',
  action_assigned: '分配给我',
  decision_review_pending: '等待我的评审',
  decision_review_requested: '请求我评审',
  comment_mention: '提到了我',
  comment_reply: '有新回复',
  meeting_needs_preparation: '需要准备',
  meeting_upcoming: '即将开始',
}

const href = computed(() => {
  if (props.item.subject_type === 'meeting') return `/meetings/${props.item.subject_id}`
  if (props.item.subject_type === 'decision') return `/decisions?highlight=${props.item.subject_id}`
  return `/actions?highlight=${props.item.subject_id}`
})
</script>

<template>
  <RouterLink class="attention-card" :to="href">
    <span class="attention-kind" :data-kind="item.subject_type">{{ item.subject_type === 'meeting' ? '会议' : item.subject_type === 'decision' ? '决策' : '行动' }}</span>
    <div class="grow">
      <p class="attention-project">{{ item.project.name }}</p>
      <h3>{{ item.title }}</h3>
      <p class="attention-reasons">{{ item.reasons.map((reason) => reasonLabels[reason] ?? reason).join(' · ') }}</p>
    </div>
    <span class="arrow-link" aria-hidden="true">→</span>
  </RouterLink>
</template>
