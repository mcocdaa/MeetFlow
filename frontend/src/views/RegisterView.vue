<script setup lang="ts">
import { NAlert, NButton, NForm, NFormItem, NInput, type FormInst, type FormRules } from 'naive-ui'
import { reactive, ref } from 'vue'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'

const formRef = ref<FormInst | null>(null)
const form = reactive({ username: '', display_name: '', password: '' })
const rules: FormRules = {
  username: [
    { required: true, whitespace: true, message: '请输入用户名', trigger: ['input', 'blur'] },
    { min: 3, max: 80, message: '用户名需为 3-80 个字符', trigger: ['input', 'blur'] },
  ],
  display_name: [
    { required: true, whitespace: true, message: '请输入显示名称', trigger: ['input', 'blur'] },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: ['input', 'blur'] },
    { min: 12, max: 200, message: '密码至少 12 位', trigger: ['input', 'blur'] },
  ],
}
const submitted = ref(false)
const submitting = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        username: form.username.trim(),
        display_name: form.display_name.trim(),
        password: form.password,
      }),
    })
    submitted.value = true
  } catch (reason) {
    error.value = errorMessage(reason, '注册失败')
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
      <n-form
        v-else
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
        <n-form-item label="显示名称" path="display_name">
          <n-input
            v-model:value="form.display_name"
            :input-props="{ 'aria-label': '显示名称', autocomplete: 'name' }"
          />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': '密码', autocomplete: 'new-password' }"
          />
        </n-form-item>
        <p class="field-hint">请使用至少 12 位密码。</p>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" block attr-type="submit" :loading="submitting">
          {{ submitting ? '正在提交…' : '提交申请' }}
        </n-button>
      </n-form>
      <RouterLink class="text-link" to="/login">返回登录</RouterLink>
    </section>
  </main>
</template>
