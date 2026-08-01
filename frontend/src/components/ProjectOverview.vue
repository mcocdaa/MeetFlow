<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { AttentionItem } from './AttentionCard.vue'
import type { ProjectActionSummary, ProjectDetail } from '../domain/projects'

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
const activityRows = computed(() => props.project.updates.slice(0, 5))

function attentionLink(item: AttentionItem) {
  return item.subject_type === 'meeting'
    ? `/meetings/${item.subject_id}`
    : `/${item.subject_type}s?highlight=${item.subject_id}`
}
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
        <time>{{ new Date(project.next_meeting.scheduled_start).toLocaleString('zh-CN') }}</time>
        <span>{{ project.next_meeting.status }} · 打开会议 →</span>
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
        <RouterLink v-for="item in actionRows" :key="item.id" class="compact-row" :to="item.meeting_id ? `/meetings/${item.meeting_id}` : `/actions?highlight=${item.id}`"><strong>{{ item.content }}</strong><span>{{ item.due_date ? `截止 ${item.due_date}` : '未设截止日期' }} · {{ item.priority }}</span></RouterLink>
      </div>
      <p v-else class="muted">没有未完成行动项。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>近期决策</h2><button class="text-link" @click="emit('openTab', 'decisions')">查看全部</button></div>
      <div v-if="decisionRows.length" class="project-dashboard-list">
        <RouterLink v-for="item in decisionRows" :key="item.id" class="compact-row" :to="`/decisions?highlight=${item.id}`"><strong>{{ item.title }}</strong><span>{{ item.status }}</span></RouterLink>
      </div>
      <p v-else class="muted">尚未形成项目决策。</p>
    </section>

    <section class="workspace-section project-dashboard-card">
      <div class="section-heading"><h2>最近动态</h2><button class="text-link" @click="emit('openTab', 'activity')">查看全部</button></div>
      <div v-if="activityRows.length" class="project-dashboard-list">
        <button v-for="item in activityRows" :key="item.id" class="compact-row compact-row-button" @click="emit('openTab', 'activity')"><strong>{{ item.content_markdown.slice(0, 52) }}</strong><span>{{ item.created_by.display_name }} · {{ new Date(item.created_at).toLocaleDateString('zh-CN') }}</span></button>
      </div>
      <p v-else class="muted">尚无项目动态。</p>
    </section>
  </div>
</template>
