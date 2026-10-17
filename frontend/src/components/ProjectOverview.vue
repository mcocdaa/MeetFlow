<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { NButton, NIcon } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import StatusPill from './StatusPill.vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { AttentionItem } from './AttentionCard.vue'
import type { ProjectActionSummary, ProjectActivityItem, ProjectActivityPage, ProjectDetail } from '../domain/projects'
import { useI18n } from '../i18n'
import { activityLabel } from '../utils/activity'
import { subjectHref } from '../utils/links'
import { priorityLabel } from '../utils/labels'
import { formatDate, formatDateTime } from '../utils/time'

const { tr } = useI18n()

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
  return item.actor?.display_name || item.actor?.username || tr('系统', 'System')
}

function reasonLabel(reason: string): string {
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
          <h2>{{ tr('项目状态', 'Project State') }}</h2>
        </div>
      </div>
      <p class="project-state-summary">{{ project.summary || tr('尚未填写项目摘要。', 'No project summary provided yet.') }}</p>
      <dl class="project-state-metrics">
        <div>
          <dt>{{ tr('健康度', 'Health') }}</dt>
          <dd>
            {{
              project.health === 'on_track'
                ? tr('进展正常', 'On Track')
                : project.health === 'at_risk'
                  ? tr('存在风险', 'At Risk')
                  : project.health === 'off_track'
                    ? tr('偏离计划', 'Off Track')
                    : tr('未设置', 'Unset')
            }}
          </dd>
        </div>
        <div><dt>{{ tr('目标日期', 'Target Date') }}</dt><dd>{{ project.target_date ?? tr('未设置', 'Unset') }}</dd></div>
        <div><dt>{{ tr('负责人', 'Lead') }}</dt><dd>{{ project.lead?.display_name ?? tr('未指定', 'Unassigned') }}</dd></div>
      </dl>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading">
        <h2>{{ tr('下一次会议', 'Next Meeting') }}</h2>
        <button v-if="canContribute && !project.next_meeting" class="button button-small button-primary" @click="emit('scheduleMeeting')">{{ tr('安排会议', 'Schedule Meeting') }}</button>
      </div>
      <RouterLink v-if="project.next_meeting" class="next-meeting-card" :to="`/meetings/${project.next_meeting.id}`">
        <strong>{{ project.next_meeting.title }}</strong>
        <time>{{ formatDateTime(project.next_meeting.scheduled_start) }}</time>
        <span><StatusPill :status="project.next_meeting.status" kind="meeting" /> · {{ tr('打开会议', 'Open Meeting') }} <NIcon aria-hidden="true" :size="16"><ChevronRight /></NIcon></span>
      </RouterLink>
      <p v-else class="muted">{{ tr('暂未安排下一次会议。', 'No upcoming meeting scheduled.') }}</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>{{ tr('需要处理', 'Needs Attention') }}</h2><span class="metric"><strong>{{ attentionRows.length }}</strong> {{ tr('项', 'items') }}</span></div>
      <div v-if="attentionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in attentionRows" :key="`${item.subject_type}-${item.subject_id}`" class="compact-row" :to="attentionLink(item)"><strong>{{ item.title }}</strong><span>{{ item.reasons.map(reasonLabel).join(' · ') }}</span></RouterLink>
      </div>
      <p v-else class="muted">{{ tr('当前没有需要立即处理的事项。', 'No items require immediate attention.') }}</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>{{ tr('近期行动项', 'Recent Actions') }}</h2><n-button size="small" quaternary round @click="emit('openTab', 'actions')">{{ tr('查看全部', 'View All') }}</n-button></div>
      <div v-if="actionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in actionRows" :key="item.id" class="compact-row" :to="item.meeting_id ? `/meetings/${item.meeting_id}` : `/actions?highlight=${item.id}`"><strong>{{ item.content }}</strong><span>{{ item.due_date ? tr(`截止 ${item.due_date}`, `Due ${item.due_date}`) : tr('未设截止日期', 'No due date') }} · {{ priorityLabel(item.priority) }}</span></RouterLink>
      </div>
      <p v-else class="muted">{{ tr('没有未完成行动项。', 'No open action items.') }}</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>{{ tr('近期决策', 'Recent Decisions') }}</h2><n-button size="small" quaternary round @click="emit('openTab', 'decisions')">{{ tr('查看全部', 'View All') }}</n-button></div>
      <div v-if="decisionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in decisionRows" :key="item.id" class="compact-row" :to="`/decisions?highlight=${item.id}`"><strong>{{ item.title }}</strong><span><StatusPill :status="item.status" kind="decision" /></span></RouterLink>
      </div>
      <p v-else class="muted">{{ tr('尚未形成项目决策。', 'No project decisions recorded yet.') }}</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>{{ tr('最近动态', 'Recent Activity') }}</h2><n-button size="small" quaternary round @click="emit('openTab', 'activity')">{{ tr('查看全部', 'View All') }}</n-button></div>
      <div v-if="activityRows.length" class="project-dashboard-list">
        <button v-for="item in activityRows" :key="item.id" class="compact-row compact-row-button" @click="emit('openTab', 'activity')"><strong>{{ activityLabel(item.event_type, item.payload) }}</strong><span>{{ actorName(item) }} · {{ formatDate(item.created_at) }}</span></button>
      </div>
      <p v-else class="muted">{{ tr('尚无项目动态。', 'No project activity yet.') }}</p>
    </section>
  </div>
</template>
