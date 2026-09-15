<script setup lang="ts">
import { NConfigProvider, NDialogProvider, NMessageProvider, dateZhCN, zhCN } from 'naive-ui'
import { onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { api } from './api/client'
import { clearSession, session, type SessionUser } from './auth/session'
import AppAvatar from './components/AppAvatar.vue'
import AppSidebar from './components/AppSidebar.vue'
import { loadPluginFrontendModules } from './plugins/runtime'
import { naiveThemeOverrides } from './theme/naive'

const router = useRouter()

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

function handleAuthExpired() {
  clearSession()
  router.push('/login')
}

onMounted(() => window.addEventListener('meetflow:auth-expired', handleAuthExpired))
onBeforeUnmount(() => window.removeEventListener('meetflow:auth-expired', handleAuthExpired))
</script>

<template>
  <NConfigProvider :theme-overrides="naiveThemeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <div class="app-shell">
          <template v-if="session.user">
            <AppSidebar />
            <section class="workspace-main">
              <header class="workspace-topbar">
                <span class="workspace-label">共享工作区</span>
                <div class="account-menu"><RouterLink class="account-link" to="/account"><AppAvatar :name="session.user.display_name" :color="session.user.avatar_color" :size="30" /><span>{{ session.user.display_name }}</span></RouterLink><button class="button button-small button-quiet" aria-label="退出登录" @click="logout">退出</button></div>
              </header>
              <RouterView @logged-in="onLoggedIn" />
            </section>
          </template>
          <RouterView v-else @logged-in="onLoggedIn" />
        </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
