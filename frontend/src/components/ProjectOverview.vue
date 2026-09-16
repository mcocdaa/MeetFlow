<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { NIcon } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import StatusPill from './StatusPill.vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { AttentionItem } from './AttentionCard.vue'
import type { ProjectActionSummary, ProjectActivityItem, ProjectActivityPage, ProjectDetail } from '../domain/projects'
import { activityLabel } from '../utils/activity'
import { subjectHref } from '../utils/links'
import { priorityLabel } from '../utils/labels'
import { formatDate, formatDateTime } from '../utils/time'

const props = defineProps<{
  project: ProjectDetail
  attention: AttentionItem[]
  openActions: ProjectActionSummary[]
  canContribute: boolean
}>()
const emit = defineEmits<{
  scheduleMeeting: []
  openTab: [tab: 'meetings' | 'actions' | 'decisions' | 'activity']
}>()

const attentionRows = computed(() => props.attention.slice(0, 5))
const actionRows = computed(() => props.openActions.slice(0, 5))
const decisionRows = computed(() => props.project.recent_decisions.slice(0, 3))
const activityRows = ref<ProjectActivityItem[]>([])

const attentionLink = (item: AttentionItem) => subjectHref(item.subject_type, item.subject_id)

function actorName(item: ProjectActivityItem) {
  return item.actor?.display_name || item.actor?.username || '系统'
}

onMounted(async () => {
  try {
    const page = await api<ProjectActivityPage>(`/api/projects/${props.project.id}/activity?limit=5`)
    activityRows.value = (page?.items ?? []).slice(0, 5)
  } catch {
    activityRows.value = []
  }
})
</script>

<template>
  <div class="project-overview-grid">
    <section class="workspace-section project-dashboard-card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Project state</p>
          <h2>项目状态</h2>
        </div>
      </div>
      <p class="project-state-summary">{{ project.summary || '尚未填写项目摘要。' }}</p>
      <dl class="project-state-metrics">
        <div><dt>健康度</dt><dd>{{ project.health === 'on_track' ? '进展正常' : project.health === 'at_risk' ? '存在风险' : project.health === 'off_track' ? '偏离计划' : '未设置' }}</dd></div>
        <div><dt>目标日期</dt><dd>{{ project.target_date ?? '未设置' }}</dd></div>
        <div><dt>负责人</dt><dd>{{ project.lead?.display_name ?? '未指定' }}</dd></div>
      </dl>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading">
        <h2>下一次会议</h2>
        <button v-if="canContribute && !project.next_meeting" class="button button-small button-primary" @click="emit('scheduleMeeting')">安排会议</button>
      </div>
      <RouterLink v-if="project.next_meeting" class="next-meeting-card" :to="`/meetings/${project.next_meeting.id}`">
        <strong>{{ project.next_meeting.title }}</strong>
        <time>{{ formatDateTime(project.next_meeting.scheduled_start) }}</time>
        <span><StatusPill :status="project.next_meeting.status" kind="meeting" /> · 打开会议 <NIcon aria-hidden="true" :size="16"><ChevronRight /></NIcon></span>
      </RouterLink>
      <p v-else class="muted">暂未安排下一次会议。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>需要处理</h2><span class="metric"><strong>{{ attentionRows.length }}</strong> 项</span></div>
      <div v-if="attentionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in attentionRows" :key="`${item.subject_type}-${item.subject_id}`" class="compact-row" :to="attentionLink(item)"><strong>{{ item.title }}</strong><span>{{ item.reasons.join(' · ') }}</span></RouterLink>
      </div>
      <p v-else class="muted">当前没有需要立即处理的事项。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>近期行动项</h2><button class="text-link" @click="emit('openTab', 'actions')">查看全部</button></div>
      <div v-if="actionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in actionRows" :key="item.id" class="compact-row" :to="item.meeting_id ? `/meetings/${item.meeting_id}` : `/actions?highlight=${item.id}`"><strong>{{ item.content }}</strong><span>{{ item.due_date ? `截止 ${item.due_date}` : '未设截止日期' }} · {{ priorityLabel(item.priority) }}</span></RouterLink>
      </div>
      <p v-else class="muted">没有未完成行动项。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>近期决策</h2><button class="text-link" @click="emit('openTab', 'decisions')">查看全部</button></div>
      <div v-if="decisionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in decisionRows" :key="item.id" class="compact-row" :to="`/decisions?highlight=${item.id}`"><strong>{{ item.title }}</strong><span><StatusPill :status="item.status" kind="decision" /></span></RouterLink>
      </div>
      <p v-else class="muted">尚未形成项目决策。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>最近动态</h2><button class="text-link" @click="emit('openTab', 'activity')">查看全部</button></div>
      <div v-if="activityRows.length" class="project-dashboard-list">
        <button v-for="item in activityRows" :key="item.id" class="compact-row compact-row-button" @click="emit('openTab', 'activity')"><strong>{{ activityLabel(item.event_type, item.payload) }}</strong><span>{{ actorName(item) }} · {{ formatDate(item.created_at) }}</span></button>
      </div>
      <p v-else class="muted">尚无项目动态。</p>
    </section>
  </div>
</template>
