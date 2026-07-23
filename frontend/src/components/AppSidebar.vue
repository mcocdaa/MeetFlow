<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { session } from '../auth/session'

const workspaceLinks = [
  { to: '/', label: '为你', mark: '⌂' },
  { to: '/projects', label: '项目', mark: '◇' },
  { to: '/meetings', label: '会议', mark: '▣' },
  { to: '/actions', label: '行动项', mark: '✓' },
  { to: '/decisions', label: '决策', mark: '◆' },
  { to: '/inbox', label: '收件箱', mark: '↙' },
  { to: '/ai-tasks', label: 'AI 任务', mark: '✦' },
]

const adminLinks = [
  { to: '/admin/users', label: '用户' },
  { to: '/admin/plugins', label: '插件' },
  { to: '/account', label: '设置' },
]
</script>

<template>
  <aside class="workspace-sidebar">
    <RouterLink class="workspace-brand" to="/">
      <span class="brand-mark brand-mark-small">M</span>
      <span><strong>MeetFlow</strong><small>团队会议工作区</small></span>
    </RouterLink>
    <nav class="sidebar-nav" aria-label="工作区导航">
      <RouterLink v-for="link in workspaceLinks" :key="link.to" :to="link.to">
        <span aria-hidden="true">{{ link.mark }}</span>{{ link.label }}
      </RouterLink>
    </nav>
    <nav v-if="session.user?.role === 'admin'" class="sidebar-nav sidebar-admin" aria-label="管理员导航">
      <p>管理员</p>
      <RouterLink v-for="link in adminLinks" :key="link.to" :to="link.to">{{ link.label }}</RouterLink>
    </nav>
  </aside>
</template>
