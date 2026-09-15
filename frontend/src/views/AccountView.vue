<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import { nextTick, reactive, ref } from 'vue'
import { errorMessage } from '../utils/errors'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { clearSession } from '../auth/session'

const router = useRouter()
const message = useMessage()
const formRef = ref<FormInst | null>(null)
const form = reactive({ current_password: '', new_password: '' })
const rules: FormRules = {
  current_password: [
    { required: true, message: '请输入当前密码', trigger: ['input', 'blur'] },
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: ['input', 'blur'] },
    { min: 12, max: 200, message: '新密码至少 12 位', trigger: ['input', 'blur'] },
  ],
}
const error = ref('')
const saving = ref(false)

async function changePassword() {
  error.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await api('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: form.current_password,
        new_password: form.new_password,
      }),
    })
    message.success('密码已修改，请重新登录')
    // Let the message render before the session clears and this view unmounts.
    await nextTick()
    clearSession()
    await router.push('/login')
  } catch (reason) {
    error.value = errorMessage(reason, '修改失败')
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
    <n-card title="修改密码">
      <p class="muted">修改后，其他设备上的旧会话也会立即失效。</p>
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        :show-require-mark="false"
        @submit.prevent="changePassword"
      >
        <n-form-item label="当前密码" path="current_password">
          <n-input
            v-model:value="form.current_password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': '当前密码', autocomplete: 'current-password' }"
          />
        </n-form-item>
        <n-form-item label="新密码" path="new_password">
          <n-input
            v-model:value="form.new_password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': '新密码', autocomplete: 'new-password' }"
          />
        </n-form-item>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" attr-type="submit" :loading="saving">
          {{ saving ? '正在修改…' : '修改密码' }}
        </n-button>
      </n-form>
    </n-card>
  </main>
</template>
