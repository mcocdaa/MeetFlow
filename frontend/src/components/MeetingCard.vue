<script setup lang="ts">
import { computed } from 'vue'

import type { MeetingSummary } from '../meetings/types'

const props = defineProps<{ meeting: MeetingSummary }>()
const dateParts = computed(() => {
  const value = new Date(props.meeting.meeting_date)
  return {
    day: new Intl.DateTimeFormat('zh-CN', { day: '2-digit' }).format(value),
    month: new Intl.DateTimeFormat('zh-CN', { month: 'short' }).format(value),
    full: new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(value),
  }
})
</script>

<template>
  <RouterLink class="meeting-card" :to="`/meetings/${meeting.id}`">
    <div class="date-tile" :title="dateParts.full"><strong>{{ dateParts.day }}</strong><span>{{ dateParts.month }}</span></div>
    <div class="meeting-card-main">
      <div class="meeting-card-heading">
        <div>
          <div class="tag-row"><span v-if="meeting.project" class="tag tag-project">{{ meeting.project }}</span><span v-if="meeting.meeting_type" class="tag">{{ meeting.meeting_type }}</span></div>
          <h2>{{ meeting.title }}</h2>
        </div>
        <span class="arrow-link" aria-hidden="true">↗</span>
      </div>
      <p class="participant-line">{{ meeting.participants.length ? meeting.participants.join('、') : '未填写参与人' }}</p>
      <div class="meeting-stats">
        <span><strong>{{ meeting.conclusion_count }}</strong> 条结论</span>
        <span v-if="meeting.action_count !== undefined"><strong>{{ meeting.open_action_count }}</strong> / {{ meeting.action_count }} 待办</span>
        <span v-else>{{ meeting.open_action_count }} 项待办</span>
        <span><strong>{{ meeting.attachment_count }}</strong> 个附件</span>
      </div>
      <p class="attribution">由 {{ meeting.created_by.display_name }} 创建 · {{ meeting.updated_by.display_name }} 最近修改</p>
    </div>
  </RouterLink>
</template>
