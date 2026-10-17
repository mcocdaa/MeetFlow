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
import { useI18n } from '../i18n'
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

const { tr } = useI18n()
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

const resetRules = computed<FormRules>(() => ({
  password: {
    required: true,
    min: 12,
    message: tr('新密码至少 12 位', 'New password must be at least 12 characters'),
    trigger: ['input', 'blur'],
  },
}))

function memberCell(user: User) {
  return h('div', { class: 'user-cell' }, [
    h(AppAvatar, { name: user.display_name, color: user.avatar_color ?? null, size: 30 }),
    h('div', { class: 'grow' }, [
      h('strong', user.display_name),
      h('span', { class: 'muted' }, `@${user.username} · ${user.role === 'admin' ? tr('管理员', 'Admin') : tr('成员', 'Member')}`),
    ]),
  ])
}

function statusCell(user: User) {
  return h(StatusPill, { status: user.status, kind: 'user' })
}

const activeColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: tr('成员', 'Member'), key: 'member', minWidth: 240, render: memberCell },
    { title: tr('状态', 'Status'), key: 'status', minWidth: 110, render: statusCell },
    {
      title: tr('操作', 'Actions'),
      key: 'actions',
      minWidth: 240,
      render: (user) => h('div', { class: 'row-actions' }, user.role === 'admin' ? [] : [
        h(NButton, {
          size: 'small',
          type: 'error',
          quaternary: true,
          disabled: busy,
          'aria-label': tr(`归档成员“${user.display_name}”`, `Archive member "${user.display_name}"`),
          onClick: () => confirmArchive(user),
        }, { default: () => tr('归档成员', 'Archive') }),
        h(NButton, {
          size: 'small',
          quaternary: true,
          disabled: busy,
          'aria-label': tr(`重置密码“${user.display_name}”`, `Reset password for "${user.display_name}"`),
          onClick: () => openReset(user),
        }, { default: () => tr('重置密码', 'Reset Password') }),
      ]),
    },
  ]
})

const applicationColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: tr('成员', 'Member'), key: 'member', minWidth: 240, render: memberCell },
    { title: tr('状态', 'Status'), key: 'status', minWidth: 110, render: statusCell },
    {
      title: tr('操作', 'Actions'),
      key: 'actions',
      minWidth: 220,
      render: (user) => h('div', { class: 'row-actions' }, user.status === 'pending' ? [
        h(NPopconfirm, {
          positiveText: tr('确认', 'Confirm'),
          negativeText: tr('取消', 'Cancel'),
          onPositiveClick: () => void transition(user.id, 'approve'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            type: 'primary',
            disabled: busy,
            'aria-label': tr(`批准“${user.display_name}”`, `Approve "${user.display_name}"`),
          }, { default: () => tr('批准', 'Approve') }),
          default: () => tr(`确定批准 ${user.display_name} 的账号申请吗？`, `Approve account request for ${user.display_name}?`),
        }),
        h(NPopconfirm, {
          positiveText: tr('确认', 'Confirm'),
          negativeText: tr('取消', 'Cancel'),
          onPositiveClick: () => void transition(user.id, 'reject'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            quaternary: true,
            disabled: busy,
            'aria-label': tr(`拒绝“${user.display_name}”`, `Reject "${user.display_name}"`),
          }, { default: () => tr('拒绝', 'Reject') }),
          default: () => tr(`确定拒绝 ${user.display_name} 的账号申请吗？`, `Reject account request for ${user.display_name}?`),
        }),
      ] : []),
    },
  ]
})

const archivedColumns = computed<DataTableColumns<User>>(() => {
  const busy = Boolean(busyId.value)
  return [
    { title: tr('成员', 'Member'), key: 'member', minWidth: 240, render: memberCell },
    { title: tr('状态', 'Status'), key: 'status', minWidth: 110, render: statusCell },
    {
      title: tr('操作', 'Actions'),
      key: 'actions',
      minWidth: 160,
      render: (user) => h('div', { class: 'row-actions' }, [
        h(NPopconfirm, {
          positiveText: tr('确认', 'Confirm'),
          negativeText: tr('取消', 'Cancel'),
          onPositiveClick: () => void transition(user.id, 'restore'),
        }, {
          trigger: () => h(NButton, {
            size: 'small',
            type: 'primary',
            disabled: busy,
            'aria-label': tr(`恢复成员“${user.display_name}”`, `Restore member "${user.display_name}"`),
          }, { default: () => tr('恢复成员', 'Restore') }),
          default: () => tr(`确定恢复 ${user.display_name} 的成员资格吗？`, `Restore membership for ${user.display_name}?`),
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
    error.value = errorMessage(reason, tr('用户列表加载失败', 'Failed to load users'))
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
    error.value = errorMessage(reason, tr('状态变更失败', 'Failed to update status'))
  } finally {
    busyId.value = ''
  }
}

/** Archived accounts block sign-in, so `disable` needs the blocked n-dialog confirmation. */
function confirmArchive(user: User) {
  dialog.warning({
    title: tr('归档成员', 'Archive Member'),
    content: tr(
      `归档后 ${user.display_name} 将无法登录或执行操作；其历史记录和署名会被保留。确定归档吗？`,
      `Archiving ${user.display_name} will prevent sign-in while preserving historical attribution. Archive this member?`,
    ),
    positiveText: tr('确认归档', 'Archive'),
    negativeText: tr('取消', 'Cancel'),
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
    error.value = errorMessage(reason, tr('账号创建失败', 'Failed to create account'))
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
    resetError.value = errorMessage(reason, tr('密码重置失败', 'Failed to reset password'))
  } finally {
    resetSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="page-heading">
      <div><p class="eyebrow">Administration</p><h1>{{ tr('用户管理', 'User Management') }}</h1><p>{{ tr('审批申请并管理共享工作区成员。', 'Approve requests and manage workspace members.') }}</p></div>
      <span class="metric"><strong>{{ pendingCount }}</strong> {{ tr('待审批', 'Pending') }}</span>
    </header>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
    <section class="panel split-panel">
      <div>
        <p class="eyebrow">Fixed account</p><h2>{{ tr('创建固定账号', 'Create Fixed Account') }}</h2>
        <p class="muted">{{ tr('账号创建后立即启用，适合作为演示或内部成员账号。', 'Accounts are enabled immediately upon creation.') }}</p>
      </div>
      <form class="compact-form" @submit.prevent="createFixedAccount">
        <label>{{ tr('用户名', 'Username') }}<input v-model.trim="form.username" :aria-label="tr('固定账号用户名', 'Fixed account username')" required /></label>
        <label>{{ tr('显示名称', 'Display Name') }}<input v-model.trim="form.display_name" required /></label>
        <label>{{ tr('初始密码', 'Initial Password') }}<input v-model="form.password" type="password" minlength="12" required /></label>
        <button class="button button-primary" :disabled="saving">{{ saving ? tr('创建中…', 'Creating…') : tr('创建固定账号', 'Create Account') }}</button>
      </form>
    </section>
    <section class="panel">
      <div class="section-heading"><h2>{{ tr('当前成员', 'Active Members') }}</h2><n-button quaternary @click="load">{{ tr('刷新', 'Refresh') }}</n-button></div>
      <p v-if="loading" class="empty-state">{{ tr('正在加载成员…', 'Loading members…') }}</p>
      <p v-else-if="!activeUsers.length" class="empty-state">{{ tr('尚无已启用成员。', 'No active members yet.') }}</p>
      <n-data-table v-else :columns="activeColumns" :data="activeUsers" :bordered="false" size="small" :scroll-x="760" />
    </section>
    <section v-if="applicationUsers.length" class="panel">
      <div class="section-heading"><h2>{{ tr('账号申请', 'Account Requests') }}</h2><span class="muted">{{ tr('待审批和已拒绝的申请记录', 'Pending and rejected applications') }}</span></div>
      <n-data-table :columns="applicationColumns" :data="applicationUsers" :bordered="false" size="small" :scroll-x="760" />
    </section>
    <details v-if="archivedUsers.length" class="panel archive-section">
      <summary>{{ tr('已归档成员', 'Archived Members') }} ({{ archivedUsers.length }})</summary>
      <p class="muted">{{ tr('归档账号无法登录或执行操作；其历史记录和署名会被保留。', 'Archived accounts cannot sign in; historical attribution is preserved.') }}</p>
      <n-data-table :columns="archivedColumns" :data="archivedUsers" :bordered="false" size="small" :scroll-x="760" />
    </details>

    <n-drawer
      :show="Boolean(resetTarget)"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!resetSaving"
      @update:show="(value: boolean) => { if (!value) closeReset() }"
    >
      <n-drawer-content :title="tr('重置密码', 'Reset Password')" closable>
        <p class="muted">{{ tr(`为 ${resetTarget?.display_name ?? ''} 设置至少 12 位的新密码。`, `Set a new password (at least 12 characters) for ${resetTarget?.display_name ?? ''}.`) }}</p>
        <n-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-placement="top" :show-require-mark="false">
          <n-form-item :label="tr('新密码', 'New Password')" path="password">
            <n-input
              v-model:value="resetForm.password"
              type="password"
              show-password-on="click"
              :input-props="{ 'aria-label': tr('新密码', 'New Password') }"
              :placeholder="tr('至少 12 位', 'At least 12 characters')"
            />
          </n-form-item>
        </n-form>
        <p v-if="resetError" class="notice notice-error" role="alert">{{ resetError }}</p>
        <template #footer>
          <n-button quaternary :disabled="resetSaving" @click="closeReset">{{ tr('取消', 'Cancel') }}</n-button>
          <n-button type="primary" :loading="resetSaving" :disabled="resetSaving" @click="submitReset">{{ tr('确认重置', 'Reset Password') }}</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </main>
</template>
