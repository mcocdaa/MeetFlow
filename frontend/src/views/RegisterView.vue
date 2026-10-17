<script setup lang="ts">
import { CheckCircle2 } from '@lucide/vue'
import { NAlert, NButton, NForm, NFormItem, NIcon, NInput, type FormInst, type FormRules } from 'naive-ui'
import { computed, reactive, ref } from 'vue'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'

const { t, tr, toggleLocale } = useI18n()
const formRef = ref<FormInst | null>(null)
const form = reactive({ username: '', display_name: '', password: '' })
const rules = computed<FormRules>(() => ({
  username: [
    { required: true, whitespace: true, message: tr('请输入用户名', 'Please enter username'), trigger: ['input', 'blur'] },
    { min: 3, max: 80, transform: (value: string) => value.trim(), message: tr('用户名需为 3-80 个字符', 'Username must be 3-80 characters'), trigger: ['input', 'blur'] },
  ],
  display_name: [
    { required: true, whitespace: true, message: tr('请输入显示名称', 'Please enter display name'), trigger: ['input', 'blur'] },
  ],
  password: [
    { required: true, message: tr('请输入密码', 'Please enter password'), trigger: ['input', 'blur'] },
    { min: 12, message: tr('密码至少 12 位', 'Password must be at least 12 characters'), trigger: ['input', 'blur'] },
    { max: 200, message: tr('密码不能超过 200 个字符', 'Password cannot exceed 200 characters'), trigger: ['input', 'blur'] },
  ],
}))
const submitted = ref(false)
const submitting = ref(false)
const error = ref('')

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
    error.value = errorMessage(reason, tr('注册失败', 'Registration failed'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-layout auth-layout-single">
    <section class="auth-card" aria-labelledby="register-title">
      <div class="auth-card-top">
        <div class="brand-mark">M</div>
        <button type="button" class="lang-toggle-btn" @click="toggleLocale">{{ t('app.langToggle') }}</button>
      </div>
      <p class="eyebrow">{{ tr('加入共享工作区', 'Join shared workspace') }}</p>
      <h1 id="register-title">{{ tr('申请 MeetFlow 账号', 'Request MeetFlow Account') }}</h1>
      <div v-if="submitted" class="success-state">
        <NIcon class="success-icon" :size="56" aria-hidden="true"><CheckCircle2 /></NIcon>
        <h2>{{ tr('申请已提交', 'Request Submitted') }}</h2>
        <p>{{ tr('申请已提交，请等待管理员批准。', 'Your account request has been submitted and is awaiting administrator approval.') }}</p>
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
        <n-form-item :label="tr('用户名', 'Username')" path="username">
          <n-input
            v-model:value="form.username"
            :input-props="{ 'aria-label': tr('用户名', 'Username'), autocomplete: 'username' }"
          />
        </n-form-item>
        <n-form-item :label="tr('显示名称', 'Display Name')" path="display_name">
          <n-input
            v-model:value="form.display_name"
            :input-props="{ 'aria-label': tr('显示名称', 'Display Name'), autocomplete: 'name' }"
          />
        </n-form-item>
        <n-form-item :label="tr('密码', 'Password')" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': tr('密码', 'Password'), autocomplete: 'new-password' }"
          />
        </n-form-item>
        <p class="field-hint">{{ tr('请使用至少 12 位密码。', 'Use at least 12 characters.') }}</p>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" block attr-type="submit" :loading="submitting" :disabled="submitting">
          {{ submitting ? tr('正在提交…', 'Submitting…') : tr('提交申请', 'Submit Request') }}
        </n-button>
      </n-form>
      <RouterLink class="text-link" to="/login">{{ tr('返回登录', 'Back to Sign In') }}</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.auth-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
