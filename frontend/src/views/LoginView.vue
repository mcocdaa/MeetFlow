<script setup lang="ts">
import { NAlert, NButton, NForm, NFormItem, NInput, type FormInst, type FormRules } from 'naive-ui'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'

import { api } from '../api/client'
import type { SessionUser } from '../auth/session'

const { t, tr, toggleLocale } = useI18n()
const emit = defineEmits<{ loggedIn: [user: SessionUser] }>()
const formRef = ref<FormInst | null>(null)
const form = reactive({ username: '', password: '' })
const rules = computed<FormRules>(() => ({
  username: { required: true, whitespace: true, message: tr('请输入用户名', 'Please enter username'), trigger: ['input', 'blur'] },
  password: { required: true, message: tr('请输入密码', 'Please enter password'), trigger: ['input', 'blur'] },
}))
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
    error.value = errorMessage(reason, tr('登录失败', 'Sign in failed'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-layout">
    <section class="auth-intro">
      <p class="eyebrow">{{ tr('共享会议档案', 'Shared meeting archive') }}</p>
      <h1 v-if="tr('zh', 'en') === 'zh'">让每次讨论<br />都有清晰的去向。</h1>
      <h1 v-else>Turn every discussion<br />into clear next steps.</h1>
      <p>{{ tr('集中整理会议记录、关键结论、行动项与会后进展。', 'Organize meeting notes, key decisions, action items, and follow-up progress in one place.') }}</p>
    </section>
    <section class="auth-card" aria-labelledby="login-title">
      <div class="auth-card-top">
        <div class="brand-mark">M</div>
        <button type="button" class="lang-toggle-btn" @click="toggleLocale">{{ t('app.langToggle') }}</button>
      </div>
      <p class="eyebrow">{{ tr('欢迎回来', 'Welcome back') }}</p>
      <h2 id="login-title">{{ tr('登录 MeetFlow', 'Sign in to MeetFlow') }}</h2>
      <n-form
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
        <n-form-item :label="tr('密码', 'Password')" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :input-props="{ 'aria-label': tr('密码', 'Password'), autocomplete: 'current-password' }"
          />
        </n-form-item>
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
        <n-button type="primary" block attr-type="submit" :loading="submitting" :disabled="submitting">
          {{ submitting ? tr('正在登录…', 'Signing in…') : tr('登录', 'Sign In') }}
        </n-button>
      </n-form>
      <RouterLink v-if="registrationOpen" class="text-link" to="/register">{{ tr('申请账号', 'Request Account') }}</RouterLink>
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
