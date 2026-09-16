<script setup lang="ts">
import {
  NAlert,
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NPopconfirm,
  useDialog,
  type DataTableColumns,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import { api } from '../api/client'
import AppAvatar from '../components/AppAvatar.vue'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'

type UserStatus = 'pending' | 'active' | 'rejected' | 'disabled'
type User = {
  id: string
  username: string
  display_name: string
  role: 'admin' | 'member'
  status: UserStatus
  avatar_color?: string | null
  created_at?: string
}

const dialog = useDialog()
const users = ref<User[]>([])
const form = ref({ username: '', display_name: '', password: '' })
const loading = ref(true)
const saving = ref(false)
const busyId = ref('')
const error = ref('')
const resetTarget = ref<User | null>(null)
const resetFormRef = ref<FormInst | null>(null)
const resetForm = ref({ password: '' })
const resetSaving = ref(false)
const resetError = ref('')

const pendingCount = computed(() => users.value.filter((user) => user.status === 'pending').length)
const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const applicationUsers = computed(() => users.value.filter((user) => user.status === 'pending' || user.status === 'rejected'))
const archivedUsers = computed(() => users.value.filter((user) => user.status === 'disabled'))

const resetRules: FormRules = {
  password: {
    required: true,
    min: 12,
    message: '新密码至少 12 位',
    trigger: ['input', 'blur'],
  },
}

function memberCell(user: User) {
  return h('div', { class: 'user-cell' }, [
    h(AppAvatar, { name: user.display_name, color: user.avatar_color ?? null, size: 30 }),
    h('div', { class: 'grow' }, [
      h('strong', user.display_name),
      h('span', { class: 'muted' }, `@${user.username} · ${user.role === 'admin' ? '管理员' : '成员'}`),
    ]),
  ])
}

function statusCell(user: User) {
  return h(StatusPill, { status: user.status, kind: 'user' })
}

const activeColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: '成员', key: 'member', minWidth: 240, render: memberCell },
    { title: '状态', key: 'status', minWidth: 110, render: statusCell },
    {
      title: '操作',
      key: 'actions',
      minWidth: 240,
      render: (user) => h('div', { class: 'row-actions' }, user.role === 'admin' ? [] : [
        h(NButton, {
          size: 'small',
          type: 'error',
          quaternary: true,
          disabled: busy,
          'aria-label': `归档成员“${user.display_name}”`,
          onClick: () => confirmArchive(user),
        }, { default: () => '归档成员' }),
        h(NButton, {
          size: 'small',
          quaternary: true,
          disabled: busy,
          'aria-label': `重置密码“${user.display_name}”`,
          onClick: () => openReset(user),
        }, { default: () => '重置密码' }),
      ]),
    },
  ]
})

const applicationColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: '成员', key: 'member', minWidth: 240, render: memberCell },
    { title: '状态', key: 'status', minWidth: 110, render: statusCell },
    {
      title: '操作',
      key: 'actions',
      minWidth: 220,
      render: (user) => h('div', { class: 'row-actions' }, user.status === 'pending' ? [
        h(NPopconfirm, {
          positiveText: '确认',
          negativeText: '取消',
          onPositiveClick: () => void transition(user.id, 'approve'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            type: 'primary',
            disabled: busy,
            'aria-label': `批准“${user.display_name}”`,
          }, { default: () => '批准' }),
          default: () => `确定批准 ${user.display_name} 的账号申请吗？`,
        }),
        h(NPopconfirm, {
          positiveText: '确认',
          negativeText: '取消',
          onPositiveClick: () => void transition(user.id, 'reject'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            quaternary: true,
            disabled: busy,
            'aria-label': `拒绝“${user.display_name}”`,
          }, { default: () => '拒绝' }),
          default: () => `确定拒绝 ${user.display_name} 的账号申请吗？`,
        }),
      ] : []),
    },
  ]
})

const archivedColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: '成员', key: 'member', minWidth: 240, render: memberCell },
    { title: '状态', key: 'status', minWidth: 110, render: statusCell },
    {
      title: '操作',
      key: 'actions',
      minWidth: 160,
      render: (user) => h('div', { class: 'row-actions' }, [
        h(NPopconfirm, {
          positiveText: '确认',
          negativeText: '取消',
          onPositiveClick: () => void transition(user.id, 'restore'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            type: 'primary',
            disabled: busy,
            'aria-label': `恢复成员“${user.display_name}”`,
          }, { default: () => '恢复成员' }),
          default: () => `确定恢复 ${user.display_name} 的成员资格吗？`,
        }),
      ]),
    },
  ]
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    users.value = await api<User[]>('/api/admin/users')
  } catch (reason) {
    error.value = errorMessage(reason, '用户列表加载失败')
  } finally {
    loading.value = false
  }
}

async function transition(id: string, action: 'approve' | 'reject' | 'disable' | 'restore') {
  if (busyId.value) return
  busyId.value = id
  error.value = ''
  try {
    await api(`/api/admin/users/${id}/${action}`, { method: 'POST' })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, '状态变更失败')
  } finally {
    busyId.value = ''
  }
}

/** Archived accounts block sign-in, so `disable` needs the blocked n-dialog confirmation. */
function confirmArchive(user: User) {
  dialog.warning({
    title: '归档成员',
    content: `归档后 ${user.display_name} 将无法登录或执行操作；其历史记录和署名会被保留。确定归档吗？`,
    positiveText: '确认归档',
    negativeText: '取消',
    onPositiveClick: () => { void transition(user.id, 'disable') },
  })
}

async function createFixedAccount() {
  saving.value = true
  error.value = ''
  try {
    await api('/api/admin/users', { method: 'POST', body: JSON.stringify(form.value) })
    form.value = { username: '', display_name: '', password: '' }
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, '账号创建失败')
  } finally {
    saving.value = false
  }
}

function openReset(user: User) {
  resetTarget.value = user
  resetForm.value = { password: '' }
  resetError.value = ''
}

function closeReset() {
  if (resetSaving.value) return
  resetTarget.value = null
}

async function submitReset() {
  if (resetSaving.value || !resetTarget.value) return
  resetSaving.value = true
  resetError.value = ''
  try {
    try {
      await resetFormRef.value?.validate()
    } catch {
      return
    }
    await api(`/api/admin/users/${resetTarget.value.id}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password: resetForm.value.password }),
    })
    resetTarget.value = null
    resetForm.value = { password: '' }
  } catch (reason) {
    resetError.value = errorMessage(reason, '密码重置失败')
  } finally {
    resetSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="page-heading">
      <div><p class="eyebrow">Administration</p><h1>用户管理</h1><p>审批申请并管理共享工作区成员。</p></div>
      <span class="metric"><strong>{{ pendingCount }}</strong> 待审批</span>
    </header>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
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
      <div class="section-heading"><h2>当前成员</h2><n-button quaternary @click="load">刷新</n-button></div>
      <p v-if="loading" class="empty-state">正在加载成员…</p>
      <p v-else-if="!activeUsers.length" class="empty-state">尚无已启用成员。</p>
      <n-data-table v-else :columns="activeColumns" :data="activeUsers" :bordered="false" size="small" :scroll-x="760" />
    </section>
    <section v-if="applicationUsers.length" class="panel">
      <div class="section-heading"><h2>账号申请</h2><span class="muted">待审批和已拒绝的申请记录</span></div>
        <n-data-table :columns="applicationColumns" :data="applicationUsers" :bordered="false" size="small" :scroll-x="760" />
    </section>
    <details v-if="archivedUsers.length" class="panel archive-section">
      <summary>已归档成员 ({{ archivedUsers.length }})</summary>
      <p class="muted">归档账号无法登录或执行操作；其历史记录和署名会被保留。</p>
      <n-data-table :columns="archivedColumns" :data="archivedUsers" :bordered="false" size="small" :scroll-x="760" />
    </details>

    <n-drawer
      :show="Boolean(resetTarget)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!resetSaving"
      @update:show="(value: boolean) => { if (!value) closeReset() }"
    >
      <n-drawer-content title="重置密码" closable>
        <p class="muted">为 {{ resetTarget?.display_name ?? '' }} 设置至少 12 位的新密码。</p>
        <n-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-placement="top" :show-require-mark="false">
          <n-form-item label="新密码" path="password">
            <n-input
              v-model:value="resetForm.password"
              type="password"
              show-password-on="click"
              :input-props="{ 'aria-label': '新密码' }"
              placeholder="至少 12 位"
            />
          </n-form-item>
        </n-form>
        <p v-if="resetError" class="notice notice-error" role="alert">{{ resetError }}</p>
        <template #footer>
          <n-button quaternary :disabled="resetSaving" @click="closeReset">取消</n-button>
          <n-button type="primary" :loading="resetSaving" :disabled="resetSaving" @click="submitReset">确认重置</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </main>
</template>
