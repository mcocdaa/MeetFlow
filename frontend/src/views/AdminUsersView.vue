<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/client'

type UserStatus = 'pending' | 'active' | 'rejected' | 'disabled'
type User = { id: string; username: string; display_name: string; role: 'admin' | 'member'; status: UserStatus; created_at?: string }

const users = ref<User[]>([])
const form = ref({ username: '', display_name: '', password: '' })
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const pendingCount = computed(() => users.value.filter((user) => user.status === 'pending').length)
const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const applicationUsers = computed(() => users.value.filter((user) => user.status === 'pending' || user.status === 'rejected'))
const archivedUsers = computed(() => users.value.filter((user) => user.status === 'disabled'))
const statusLabel: Record<UserStatus, string> = {
  pending: '待审批', active: '已启用', rejected: '已拒绝', disabled: '已归档',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    users.value = await api<User[]>('/api/admin/users')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '用户列表加载失败'
  } finally {
    loading.value = false
  }
}

async function transition(id: string, action: 'approve' | 'reject' | 'disable' | 'restore') {
  await api(`/api/admin/users/${id}/${action}`, { method: 'POST' })
  await load()
}

async function createFixedAccount() {
  saving.value = true
  error.value = ''
  try {
    await api('/api/admin/users', { method: 'POST', body: JSON.stringify(form.value) })
    form.value = { username: '', display_name: '', password: '' }
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '账号创建失败'
  } finally {
    saving.value = false
  }
}

async function resetPassword(user: User) {
  const password = window.prompt(`为 ${user.display_name} 设置至少 12 位的新密码`)
  if (!password || password.length < 12) return
  await api(`/api/admin/users/${user.id}/reset-password`, {
    method: 'POST', body: JSON.stringify({ password }),
  })
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="page-heading">
      <div><p class="eyebrow">Administration</p><h1>用户管理</h1><p>审批申请并管理共享工作区成员。</p></div>
      <span class="metric"><strong>{{ pendingCount }}</strong> 待审批</span>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <section class="panel split-panel">
      <div>
        <p class="eyebrow">Fixed account</p><h2>创建固定账号</h2>
        <p class="muted">账号创建后立即启用，适合作为演示或内部成员账号。</p>
      </div>
      <form class="compact-form" @submit.prevent="createFixedAccount">
        <label>用户名<input v-model.trim="form.username" aria-label="固定账号用户名" required /></label>
        <label>显示名称<input v-model.trim="form.display_name" required /></label>
        <label>初始密码<input v-model="form.password" type="password" minlength="12" required /></label>
        <button class="button button-primary" :disabled="saving">{{ saving ? '创建中…' : '创建固定账号' }}</button>
      </form>
    </section>
    <section class="panel">
      <div class="section-heading"><h2>当前成员</h2><button class="button button-quiet" @click="load">刷新</button></div>
      <p v-if="loading" class="empty-state">正在加载成员…</p>
      <p v-else-if="!activeUsers.length" class="empty-state">尚无已启用成员。</p>
      <div v-else class="table-list">
        <article v-for="user in activeUsers" :key="user.id" class="user-row">
          <div class="avatar">{{ user.display_name.slice(0, 1).toUpperCase() }}</div>
          <div class="grow"><strong>{{ user.display_name }}</strong><span class="muted">@{{ user.username }} · {{ user.role === 'admin' ? '管理员' : '成员' }}</span></div>
          <span class="status-pill" :data-status="user.status">{{ statusLabel[user.status] }}</span>
          <div class="row-actions">
            <button v-if="user.role !== 'admin'" class="button button-small button-danger" @click="transition(user.id, 'disable')">归档成员</button>
            <button v-if="user.role !== 'admin'" class="button button-small button-quiet" @click="resetPassword(user)">重置密码</button>
          </div>
        </article>
      </div>
    </section>
    <section v-if="applicationUsers.length" class="panel">
      <div class="section-heading"><h2>账号申请</h2><span class="muted">待审批和已拒绝的申请记录</span></div>
      <div class="table-list">
        <article v-for="user in applicationUsers" :key="user.id" class="user-row">
          <div class="avatar">{{ user.display_name.slice(0, 1).toUpperCase() }}</div>
          <div class="grow"><strong>{{ user.display_name }}</strong><span class="muted">@{{ user.username }} · 成员</span></div>
          <span class="status-pill" :data-status="user.status">{{ statusLabel[user.status] }}</span>
          <div class="row-actions">
            <button v-if="user.status === 'pending'" class="button button-small" @click="transition(user.id, 'approve')">批准</button>
            <button v-if="user.status === 'pending'" class="button button-small button-quiet" @click="transition(user.id, 'reject')">拒绝</button>
          </div>
        </article>
      </div>
    </section>
    <details v-if="archivedUsers.length" class="panel archive-section">
      <summary>已归档成员 ({{ archivedUsers.length }})</summary>
      <p class="muted">归档账号无法登录或执行操作；其历史记录和署名会被保留。</p>
      <div class="table-list">
        <article v-for="user in archivedUsers" :key="user.id" class="user-row">
          <div class="avatar">{{ user.display_name.slice(0, 1).toUpperCase() }}</div>
          <div class="grow"><strong>{{ user.display_name }}</strong><span class="muted">@{{ user.username }} · 成员</span></div>
          <span class="status-pill" :data-status="user.status">{{ statusLabel[user.status] }}</span>
          <div class="row-actions"><button class="button button-small" @click="transition(user.id, 'restore')">恢复成员</button></div>
        </article>
      </div>
    </details>
  </main>
</template>
