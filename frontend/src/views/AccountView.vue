<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { clearSession } from '../auth/session'

const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const error = ref('')
const saving = ref(false)

async function changePassword() {
  saving.value = true
  error.value = ''
  try {
    await api('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }),
    })
    clearSession()
    await router.push('/login')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '修改失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="page page-narrow">
    <header class="page-heading">
      <div><p class="eyebrow">Account</p><h1>账号设置</h1></div>
    </header>
    <section class="panel">
      <h2>修改密码</h2>
      <p class="muted">修改后，其他设备上的旧会话也会立即失效。</p>
      <form @submit.prevent="changePassword">
        <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
        <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" required /></label>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <button class="button button-primary" :disabled="saving">{{ saving ? '正在修改…' : '修改密码' }}</button>
      </form>
    </section>
  </main>
</template>
