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
import { computed, nextTick, reactive, ref } from 'vue'
import { errorMessage } from '../utils/errors'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { fetchApiKey, rotateApiKey } from '../api/meetings'
import { clearSession } from '../auth/session'
import { useI18n } from '../i18n'

const router = useRouter()
const { tr } = useI18n()
const message = useMessage()
const formRef = ref<FormInst | null>(null)
const form = reactive({ current_password: '', new_password: '' })
const rules = computed<FormRules>(() => ({
  current_password: [
    { required: true, message: tr('请输入当前密码', 'Please enter current password'), trigger: ['input', 'blur'] },
  ],
  new_password: [
    { required: true, message: tr('请输入新密码', 'Please enter new password'), trigger: ['input', 'blur'] },
    { min: 12, message: tr('新密码至少 12 位', 'New password must be at least 12 characters'), trigger: ['input', 'blur'] },
    { max: 200, message: tr('新密码不能超过 200 个字符', 'New password cannot exceed 200 characters'), trigger: ['input', 'blur'] },
  ],
}))
const error = ref('')
const saving = ref(false)
const apiKey = ref('')
const loadingKey = ref(false)
const rotatingKey = ref(false)
const keyError = ref('')

async function loadToken() {
  if (loadingKey.value) return
  loadingKey.value = true
  keyError.value = ''
  try {
    const res = await fetchApiKey()
    apiKey.value = res.api_key
  } catch (caught) {
    keyError.value = errorMessage(caught, tr('访问令牌加载失败', 'Failed to load access token'))
  } finally {
    loadingKey.value = false
  }
}

async function rotateToken() {
  if (rotatingKey.value) return
  rotatingKey.value = true
  keyError.value = ''
  try {
    const res = await rotateApiKey()
    apiKey.value = res.api_key
    message.success(tr('访问令牌已轮换，旧令牌已失效', 'Access token rotated; previous token is now invalid'))
  } catch (caught) {
    keyError.value = errorMessage(caught, tr('令牌轮换失败', 'Failed to rotate token'))
  } finally {
    rotatingKey.value = false
  }
}

async function changePassword() {
  if (saving.value) return
  error.value = ''
  saving.value = true
  try {
    await formRef.value?.validate()
  } catch {
    saving.value = false
    return
  }
  try {
    await api('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: form.current_password,
        new_password: form.new_password,
      }),
    })
    message.success(tr('密码已修改，请重新登录', 'Password changed, please sign in again'))
    // Let the message render before the session clears and this view unmounts.
    await nextTick()
    clearSession()
    await router.push('/login')
  } catch (reason) {
    error.value = errorMessage(reason, tr('修改失败', 'Failed to change password'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="page page-narrow account-page">
    <header class="page-heading">
      <div><p class="eyebrow">Account</p><h1>{{ tr('账号设置', 'Account Settings') }}</h1></div>
    </header>
    <n-card :title="tr('修改密码', 'Change Password')">
      <p class="muted">{{ tr('修改后，其他设备上的旧会话也会立即失效。', 'Updating your password immediately invalidates existing sessions on other devices.') }}</p>
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        :show-require-mark="false"
        @submit.prevent="changePassword"
      >
        <n-form-item :label="tr('当前密码', 'Current Password')" path="current_password">
          <n-input
            v-model:value="form.current_password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': tr('当前密码', 'Current Password'), autocomplete: 'current-password' }"
          />
        </n-form-item>
        <n-form-item :label="tr('新密码', 'New Password')" path="new_password">
          <n-input
            v-model:value="form.new_password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': tr('新密码', 'New Password'), autocomplete: 'new-password' }"
          />
        </n-form-item>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" attr-type="submit" :loading="saving" :disabled="saving">
          {{ saving ? tr('正在修改…', 'Updating…') : tr('修改密码', 'Update Password') }}
        </n-button>
      </n-form>
    </n-card>

    <n-card :title="tr('个人访问令牌', 'Personal Access Token')" style="margin-top: 20px;">
      <p class="muted">{{ tr('用于自动化脚本或外部工具授权访问，轮换后旧令牌立即失效。', 'Use for automation scripts or external tool authorization. Rotating immediately revokes the previous token.') }}</p>
      <div v-if="!apiKey" class="row-actions" style="justify-content: flex-start;">
        <n-button quaternary :loading="loadingKey" @click="loadToken">{{ tr('查看访问令牌', 'Reveal Access Token') }}</n-button>
      </div>
      <div v-else class="token-row" style="display: flex; gap: 8px; align-items: center;">
        <n-input
          :value="apiKey"
          readonly
          :input-props="{ 'aria-label': tr('个人访问令牌', 'Personal Access Token') }"
        />
        <n-button quaternary :loading="rotatingKey" @click="rotateToken">{{ tr('轮换令牌', 'Rotate Token') }}</n-button>
      </div>
      <n-alert v-if="keyError" type="error" style="margin-top: 10px;">{{ keyError }}</n-alert>
    </n-card>
  </main>
</template>
