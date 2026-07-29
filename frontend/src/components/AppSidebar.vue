<script setup lang="ts">
import type { Component } from 'vue'
import {
  Bot, CalendarDays, FolderKanban, Gavel, House, Inbox,
  Puzzle, Settings, SquareCheckBig, UsersRound,
} from '@lucide/vue'
import { RouterLink } from 'vue-router'

import { session } from '../auth/session'

type NavigationLink = { to: string; label: string; icon: Component }

const workspaceLinks: NavigationLink[] = [
  { to: '/', label: '为你', icon: House },
  { to: '/projects', label: '项目', icon: FolderKanban },
  { to: '/meetings', label: '会议', icon: CalendarDays },
  { to: '/actions', label: '行动项', icon: SquareCheckBig },
  { to: '/decisions', label: '决策', icon: Gavel },
  { to: '/inbox', label: '收件箱', icon: Inbox },
  { to: '/ai-tasks', label: 'AI 任务', icon: Bot },
]

const adminLinks: NavigationLink[] = [
  { to: '/admin/users', label: '用户', icon: UsersRound },
  { to: '/admin/plugins', label: '插件', icon: Puzzle },
  { to: '/account', label: '设置', icon: Settings },
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
        <component :is="link.icon" class="sidebar-nav-icon" :size="18" :stroke-width="1.8" aria-hidden="true" />{{ link.label }}
      </RouterLink>
    </nav>
    <nav v-if="session.user?.role === 'admin'" class="sidebar-nav sidebar-admin" aria-label="管理员导航">
      <p>管理员</p>
      <RouterLink v-for="link in adminLinks" :key="link.to" :to="link.to"><component :is="link.icon" class="sidebar-nav-icon" :size="18" :stroke-width="1.8" aria-hidden="true" />{{ link.label }}</RouterLink>
    </nav>
  </aside>
</template>
