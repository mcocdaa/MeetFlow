<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { api } from './api/client'
import { clearSession, session, type SessionUser } from './auth/session'

const router = useRouter()

function onLoggedIn(user: SessionUser) {
  session.user = user
  session.loaded = true
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
  <div class="app-shell">
    <header v-if="session.user" class="site-header">
      <div class="site-header-inner">
        <RouterLink class="brand" to="/"><span class="brand-mark brand-mark-small">M</span><span>MeetFlow</span></RouterLink>
        <nav class="main-nav" aria-label="主导航">
          <RouterLink to="/">会议</RouterLink>
          <RouterLink to="/actions">待办</RouterLink>
          <template v-if="session.user.role === 'admin'"><span class="nav-divider"></span><RouterLink to="/admin/users">用户</RouterLink><RouterLink to="/admin/plugins">插件</RouterLink></template>
        </nav>
        <div class="account-menu"><RouterLink class="account-link" to="/account"><span class="avatar avatar-small">{{ session.user.display_name.slice(0, 1).toUpperCase() }}</span><span>{{ session.user.display_name }}</span></RouterLink><button class="button button-small button-quiet" aria-label="退出登录" @click="logout">退出</button></div>
      </div>
    </header>
    <RouterView @logged-in="onLoggedIn" />
  </div>
</template>
