<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import type { SessionUser } from '../auth/session'

const emit = defineEmits<{ loggedIn: [user: SessionUser] }>()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const registrationOpen = ref(false)

onMounted(async () => {
  try {
    const config = await api<{ allow_registration: boolean }>('/api/auth/config')
    registrationOpen.value = config.allow_registration
  } catch {
    registrationOpen.value = false
  }
})

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const user = await api<SessionUser>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    emit('loggedIn', user)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-layout">
    <section class="auth-intro">
      <p class="eyebrow">Shared meeting archive</p>
      <h1>让每次讨论<br />都有清晰的去向。</h1>
      <p>集中整理会议记录、关键结论、行动项与会后进展。</p>
    </section>
    <section class="auth-card" aria-labelledby="login-title">
      <div class="brand-mark">M</div>
      <p class="eyebrow">欢迎回来</p>
      <h2 id="login-title">登录 MeetFlow</h2>
      <form @submit.prevent="submit">
        <label>用户名<input v-model.trim="username" autocomplete="username" required /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <button class="button button-primary" type="submit" :disabled="submitting">
          {{ submitting ? '正在登录…' : '登录' }}
        </button>
      </form>
      <RouterLink v-if="registrationOpen" class="text-link" to="/register">申请账号</RouterLink>
    </section>
  </main>
</template>
