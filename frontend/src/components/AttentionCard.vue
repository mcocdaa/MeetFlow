<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { NIcon, NThing } from 'naive-ui'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { useI18n } from '../i18n'
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
const { tr } = useI18n()

const reasonLabel = (reason: string) => {
  const map: Record<string, string> = {
    action_overdue: tr('已逾期', 'Overdue'),
    action_due_soon: tr('即将到期', 'Due soon'),
    action_assigned: tr('分配给我', 'Assigned to me'),
    decision_review_pending: tr('等待我的评审', 'Awaiting my review'),
    decision_review_requested: tr('请求我评审', 'Review requested'),
    comment_mention: tr('提到了我', 'Mentioned me'),
    comment_reply: tr('有新回复', 'New reply'),
    meeting_needs_preparation: tr('需要准备', 'Needs prep'),
    meeting_upcoming: tr('即将开始', 'Upcoming'),
  }
  return map[reason] ?? reason
}

const href = computed(() => subjectHref(props.item.subject_type, props.item.subject_id))

const kindLabel = computed(() =>
  props.item.subject_type === 'meeting' ? tr('会议', 'Meeting') : props.item.subject_type === 'decision' ? tr('决策', 'Decision') : tr('行动', 'Action'),
)

const reasonText = computed(() =>
  props.item.reasons.map((reason) => reasonLabel(reason)).join(' · '),
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
