<script setup lang="ts">
import { NAlert, NButton, NForm, NFormItem, NInput, type FormInst, type FormRules } from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { SessionUser } from '../auth/session'

const emit = defineEmits<{ loggedIn: [user: SessionUser] }>()
const formRef = ref<FormInst | null>(null)
const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: { required: true, whitespace: true, message: '请输入用户名', trigger: ['input', 'blur'] },
  password: { required: true, message: '请输入密码', trigger: ['input', 'blur'] },
}
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
  if (submitting.value) return
  error.value = ''
  submitting.value = true
  try {
    await formRef.value?.validate()
  } catch {
    submitting.value = false
    return
  }
  try {
    const user = await api<SessionUser>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: form.username.trim(), password: form.password }),
    })
    emit('loggedIn', user)
  } catch (reason) {
    error.value = errorMessage(reason, '登录失败')
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
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        :show-require-mark="false"
        @submit.prevent="submit"
      >
        <n-form-item label="用户名" path="username">
          <n-input
            v-model:value="form.username"
            :input-props="{ 'aria-label': '用户名', autocomplete: 'username' }"
          />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': '密码', autocomplete: 'current-password' }"
          />
        </n-form-item>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" block attr-type="submit" :loading="submitting" :disabled="submitting">
          {{ submitting ? '正在登录…' : '登录' }}
        </n-button>
      </n-form>
      <RouterLink v-if="registrationOpen" class="text-link" to="/register">申请账号</RouterLink>
    </section>
  </main>
</template>
