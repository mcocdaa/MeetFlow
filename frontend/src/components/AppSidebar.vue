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
import { useI18n } from '../i18n'

type NavigationLink = { to: string; label: string; icon: Component }
type MenuOverrides = NonNullable<GlobalThemeOverrides['Menu']>

const { tr } = useI18n()

const workspaceLinks = computed<NavigationLink[]>(() => [
  { to: '/', label: tr('为你', 'For You'), icon: House },
  { to: '/projects', label: tr('项目', 'Projects'), icon: FolderKanban },
  { to: '/meetings', label: tr('会议', 'Meetings'), icon: CalendarDays },
  { to: '/actions', label: tr('行动项', 'Actions'), icon: SquareCheckBig },
  { to: '/decisions', label: tr('决策', 'Decisions'), icon: Gavel },
  { to: '/inbox', label: tr('收件箱', 'Inbox'), icon: Inbox },
  { to: '/ai-tasks', label: tr('AI 任务', 'AI Tasks'), icon: Bot },
])

const adminLinks = computed<NavigationLink[]>(() => [
  { to: '/admin/users', label: tr('用户', 'Users'), icon: UsersRound },
  { to: '/admin/plugins', label: tr('插件', 'Plugins'), icon: Puzzle },
  { to: '/account', label: tr('设置', 'Settings'), icon: Settings },
])

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
  const match = [...workspaceLinks.value, ...adminLinks.value].find(
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
  const link = [...workspaceLinks.value, ...adminLinks.value].find((item) => item.to === option.key)
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
  workspaceLinks.value.map((link) => ({ key: link.to, label: link.label })),
)

const adminOptions = computed<MenuOption[]>(() =>
  adminLinks.value.map((link) => ({ key: link.to, label: link.label })),
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
      <span><strong>MeetFlow</strong><small>{{ tr('团队会议工作区', 'Team Workspace') }}</small></span>
    </RouterLink>
    <nav class="sidebar-nav" :aria-label="tr('工作区导航', 'Workspace navigation')">
      <NMenu
        inverted
        :options="workspaceOptions"
        :value="activeKey"
        :theme-overrides="sidebarMenuTheme"
        :render-label="renderLabel"
      />
    </nav>
    <nav v-if="session.user?.role === 'admin'" class="sidebar-nav sidebar-admin" :aria-label="tr('管理员导航', 'Admin navigation')">
      <p>{{ tr('管理员', 'Admin') }}</p>
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

