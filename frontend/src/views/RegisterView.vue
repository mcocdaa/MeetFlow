<script setup lang="ts">
import { ref } from 'vue'

import { api } from '../api/client'

const username = ref('')
const displayName = ref('')
const password = ref('')
const submitted = ref(false)
const submitting = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        username: username.value,
        display_name: displayName.value,
        password: password.value,
      }),
    })
    submitted.value = true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '注册失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-layout auth-layout-single">
    <section class="auth-card" aria-labelledby="register-title">
      <div class="brand-mark">M</div>
      <p class="eyebrow">加入共享工作区</p>
      <h1 id="register-title">申请 MeetFlow 账号</h1>
      <div v-if="submitted" class="success-state">
        <span class="success-icon">✓</span>
        <h2>申请已提交</h2>
        <p>申请已提交，请等待管理员批准。</p>
      </div>
      <form v-else @submit.prevent="submit">
        <label>用户名<input v-model.trim="username" autocomplete="username" minlength="3" required /></label>
        <label>显示名称<input v-model.trim="displayName" autocomplete="name" required /></label>
        <label>密码<input v-model="password" type="password" autocomplete="new-password" minlength="12" required /></label>
        <p class="field-hint">请使用至少 12 位密码。</p>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <button class="button button-primary" type="submit" :disabled="submitting">
          {{ submitting ? '正在提交…' : '提交申请' }}
        </button>
      </form>
      <RouterLink class="text-link" to="/login">返回登录</RouterLink>
    </section>
  </main>
</template>
