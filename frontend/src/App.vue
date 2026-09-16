<script setup lang="ts">
import { Bell } from '@lucide/vue'
import {
  NBadge, NConfigProvider, NDialogProvider, NDropdown, NIcon, NLayout, NLayoutContent,
  NMessageProvider, dateZhCN, zhCN,
} from 'naive-ui'
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { api } from './api/client'
import { clearSession, session, type SessionUser } from './auth/session'
import AppAvatar from './components/AppAvatar.vue'
import AppSidebar from './components/AppSidebar.vue'
import { resetUnread, startUnreadPolling, unreadCount } from './composables/useInboxUnread'
import { resetUserNames } from './composables/useUserNameMap'
import { loadPluginFrontendModules } from './plugins/runtime'
import { naiveThemeOverrides } from './theme/naive'

const router = useRouter()

const accountOptions = [
  { key: 'account', label: '账号设置' },
  { key: 'logout', label: '退出登录' },
]

function onLoggedIn(user: SessionUser) {
  session.user = user
  session.loaded = true
  void loadPluginFrontendModules()
  router.push('/')
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }) }
  finally {
    clearSession()
    await router.push('/login')
  }
}

async function onAccountSelect(key: string | number) {
  if (key === 'logout') {
    await logout()
    return
  }
  if (key === 'account') await router.push('/account')
}

function handleAuthExpired() {
  clearSession()
  router.push('/login')
}

// The shell owns the only unread poller: it starts with a session and stops (plus resets the
// badge) on logout or session expiry. Views refresh through `refreshUnread()` instead.
let stopUnreadPolling: (() => void) | null = null

watch(
  () => session.user,
  (user) => {
    stopUnreadPolling?.()
    stopUnreadPolling = null
    if (user) stopUnreadPolling = startUnreadPolling(router)
    else {
      resetUnread()
      resetUserNames()
    }
  },
  { immediate: true },
)

onMounted(() => window.addEventListener('meetflow:auth-expired', handleAuthExpired))
onBeforeUnmount(() => {
  window.removeEventListener('meetflow:auth-expired', handleAuthExpired)
  stopUnreadPolling?.()
  stopUnreadPolling = null
})
</script>

<template>
  <NConfigProvider :theme-overrides="naiveThemeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <div class="app-shell">
          <template v-if="session.user">
            <NLayout has-sider class="shell-layout">
              <AppSidebar />
              <NLayoutContent class="workspace-main">
                <header class="workspace-topbar">
                  <span class="workspace-label">共享工作区</span>
                  <div class="topbar-actions">
                    <NBadge :value="unreadCount" :show="unreadCount > 0">
                      <button type="button" class="icon-button" aria-label="收件箱" @click="router.push('/inbox')">
                        <NIcon :size="18"><Bell :size="18" aria-hidden="true" /></NIcon>
                      </button>
                    </NBadge>
                    <NDropdown :options="accountOptions" trigger="click" @select="onAccountSelect">
                      <button type="button" class="account-menu-trigger" aria-label="账户菜单">
                        <AppAvatar :name="session.user.display_name" :color="session.user.avatar_color" :size="30" />
                        <span>{{ session.user.display_name }}</span>
                      </button>
                    </NDropdown>
                  </div>
                </header>
                <RouterView @logged-in="onLoggedIn" />
              </NLayoutContent>
            </NLayout>
          </template>
          <RouterView v-else @logged-in="onLoggedIn" />
        </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
