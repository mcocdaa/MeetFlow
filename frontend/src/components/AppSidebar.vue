<script setup lang="ts">
import type { Component, VNodeChild } from 'vue'
import { computed, h } from 'vue'
import {
  Bot, CalendarDays, FolderKanban, Gavel, House, Inbox,
  Puzzle, Settings, SquareCheckBig, UsersRound,
} from '@lucide/vue'
import { NBadge, NIcon, NLayoutSider, NMenu, type GlobalThemeOverrides, type MenuOption } from 'naive-ui'
import { RouterLink, useRoute } from 'vue-router'

import { session } from '../auth/session'
import { unreadCount } from '../composables/useInboxUnread'

type NavigationLink = { to: string; label: string; icon: Component }
type MenuOverrides = NonNullable<GlobalThemeOverrides['Menu']>

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

// NMenu paints its own inline theme variables, so the dark sidebar needs its own overrides
// instead of the CSS variable cascade (brand colours stay in styles.css).
const sidebarMenuTheme: MenuOverrides = {
  itemColorHoverInverted: '#1d2940',
  itemColorActiveInverted: '#25324a',
  itemColorActiveHoverInverted: '#25324a',
  itemTextColorInverted: '#b7c2d3',
  itemTextColorHoverInverted: '#ffffff',
  itemTextColorActiveInverted: '#ffffff',
  itemIconColorInverted: '#8fa0b9',
  itemIconColorHoverInverted: '#ffffff',
  itemIconColorActiveInverted: '#ffffff',
  itemHeight: '40px',
  borderRadius: '9px',
}

const route = useRoute()

const activeKey = computed(() => {
  const path = route.path
  if (path === '/') return '/'
  const match = [...workspaceLinks, ...adminLinks].find(
    (link) => link.to !== '/' && (path === link.to || path.startsWith(`${link.to}/`)),
  )
  return match?.to ?? null
})

function renderNavIcon(icon: Component): VNodeChild {
  return h(NIcon, { class: 'sidebar-nav-icon' }, {
    default: () => h(icon, { size: 18, 'stroke-width': 1.8, 'aria-hidden': 'true' }),
  })
}

function renderLabel(option: MenuOption): VNodeChild {
  const link = [...workspaceLinks, ...adminLinks].find((item) => item.to === option.key)
  if (!link) return typeof option.label === 'string' ? option.label : null
  // The icon lives inside the anchor so the whole item is one link target (the existing tests
  // assert every navigation link contains its svg).
  const content: VNodeChild[] = [renderNavIcon(link.icon), link.label]
  if (link.to === '/inbox') {
    // The badge stays inside the link but the explicit aria-label keeps the numeric badge out
    // of the link's accessible name.
    content.push(h(NBadge, {
      value: unreadCount.value,
      show: unreadCount.value > 0,
      'aria-hidden': 'true',
    }))
  }
  return h(RouterLink, { to: link.to, 'aria-label': link.label }, { default: () => content })
}

const workspaceOptions = computed<MenuOption[]>(() =>
  workspaceLinks.map((link) => ({ key: link.to, label: link.label })),
)

const adminOptions = computed<MenuOption[]>(() =>
  adminLinks.map((link) => ({ key: link.to, label: link.label })),
)
</script>

<template>
  <NLayoutSider
    class="workspace-sidebar"
    :width="232"
    :native-scrollbar="false"
    content-class="sidebar-body"
  >
    <RouterLink class="workspace-brand" to="/">
      <span class="brand-mark brand-mark-small">M</span>
      <span><strong>MeetFlow</strong><small>团队会议工作区</small></span>
    </RouterLink>
    <nav class="sidebar-nav" aria-label="工作区导航">
      <NMenu
        inverted
        :options="workspaceOptions"
        :value="activeKey"
        :theme-overrides="sidebarMenuTheme"
        :render-label="renderLabel"
      />
    </nav>
    <nav v-if="session.user?.role === 'admin'" class="sidebar-nav sidebar-admin" aria-label="管理员导航">
      <p>管理员</p>
      <NMenu
        inverted
        :options="adminOptions"
        :value="activeKey"
        :theme-overrides="sidebarMenuTheme"
        :render-label="renderLabel"
      />
    </nav>
  </NLayoutSider>
</template>
