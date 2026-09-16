<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { NIcon, NThing } from 'naive-ui'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { subjectHref } from '../utils/links'

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

const href = computed(() => subjectHref(props.item.subject_type, props.item.subject_id))

const kindLabel = computed(() =>
  props.item.subject_type === 'meeting' ? '会议' : props.item.subject_type === 'decision' ? '决策' : '行动',
)

const reasonText = computed(() =>
  props.item.reasons.map((reason) => reasonLabels[reason] ?? reason).join(' · '),
)
</script>

<template>
  <RouterLink class="attention-card" :to="href">
    <span class="attention-kind" :data-kind="item.subject_type">{{ kindLabel }}</span>
    <n-thing class="grow attention-subject" :title="item.title">
      <template #description>
        <p class="attention-project">{{ item.project.name }}</p>
        <p class="attention-reasons">{{ reasonText }}</p>
      </template>
    </n-thing>
    <n-icon class="attention-arrow" aria-hidden="true"><ChevronRight :size="18" /></n-icon>
  </RouterLink>
</template>
