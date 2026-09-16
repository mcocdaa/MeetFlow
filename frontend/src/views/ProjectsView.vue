<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NIcon, NInput } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import StatusPill from '../components/StatusPill.vue'
import { errorMessage } from '../utils/errors'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { session } from '../auth/session'
import type { Project, ProjectHealth, ProjectStatus } from '../domain/projects'

const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref('')
const status = ref<ProjectStatus | ''>('')
const health = ref<ProjectHealth | ''>('')
const createOpen = ref(false)
const creating = ref(false)
const slugTouched = ref(false)
const form = ref({ name: '', slug: '', summary: '' })

const healthLabels: Record<ProjectHealth, string> = { on_track: '进展正常', at_risk: '存在风险', off_track: '偏离计划', unset: '未设置' }
const filtered = computed(() => projects.value.filter((project) => (!status.value || project.status === status.value) && (!health.value || project.health === health.value)))

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

function updateName(value: string) {
  form.value.name = value
  if (!slugTouched.value) form.value.slug = slugify(value)
}

function updateSlug(value: string) {
  slugTouched.value = true
  form.value.slug = slugify(value)
}

function openCreate() {
  form.value = { name: '', slug: '', summary: '' }
  slugTouched.value = false
  error.value = ''
  createOpen.value = true
}

function closeCreate() {
  if (creating.value) return
  createOpen.value = false
}

async function load() {
  loading.value = true
  error.value = ''
  try { projects.value = await api<Project[]>('/api/projects') }
  catch (reason) { error.value = errorMessage(reason, '项目加载失败') }
  finally { loading.value = false }
}

async function createProject() {
  if (!session.user || creating.value || !form.value.name.trim() || !form.value.slug.trim()) return
  creating.value = true
  error.value = ''
  try {
    await api('/api/projects', {
      method: 'POST',
      body: JSON.stringify({
        name: form.value.name.trim(),
        slug: form.value.slug,
        summary: form.value.summary,
        status: 'active', health: 'unset', description_markdown: '',
        lead_user_id: session.user.id, member_ids: [session.user.id], target_date: null,
      }),
    })
    form.value = { name: '', slug: '', summary: '' }
    createOpen.value = false
    await load()
  } catch (reason) { error.value = errorMessage(reason, '项目创建失败') }
  finally { creating.value = false }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading"><div><p class="eyebrow">Projects</p><h1>项目</h1><p>从项目脉络进入会议、决策和后续行动。</p></div><button class="button button-primary" @click="openCreate">新建项目</button></header>
    <div class="project-filters"><label>项目状态<select v-model="status"><option value="">全部状态</option><option value="active">进行中</option><option value="planned">计划中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="canceled">已取消</option></select></label><label>健康度<select v-model="health"><option value="">全部健康度</option><option value="on_track">进展正常</option><option value="at_risk">存在风险</option><option value="off_track">偏离计划</option><option value="unset">未设置</option></select></label><span class="muted">筛选作用于已加载项目 · {{ filtered.length }} 个项目</span></div>
    <p v-if="error && !createOpen" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在加载项目…</p>
    <section v-else-if="filtered.length" class="project-grid">
      <RouterLink v-for="project in filtered" :key="project.id" class="project-card" :to="`/projects/${project.id}`">
        <div class="project-card-top"><span class="health-dot" :data-health="project.health"></span><span>{{ healthLabels[project.health] }}</span><StatusPill :status="project.status" kind="project" /></div>
        <h2>{{ project.name }}</h2><p>{{ project.summary || '尚未填写项目说明' }}</p>
        <dl><div><dt>负责人</dt><dd>{{ project.lead?.display_name ?? '未指定' }}</dd></div><div><dt>目标日期</dt><dd>{{ project.target_date ?? '未设置' }}</dd></div><div><dt>成员</dt><dd>{{ project.memberships.length }}</dd></div></dl>
        <span class="text-link">打开项目 <NIcon aria-hidden="true" :size="16"><ChevronRight /></NIcon></span>
      </RouterLink>
    </section>
    <div v-else class="empty-state"><strong>没有匹配的项目</strong><p>调整筛选条件，或建立一个新项目。</p></div>

    <NDrawer
      :show="createOpen"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!creating"
      @update:show="(value: boolean) => { if (!value) closeCreate() }"
    >
      <NDrawerContent title="新建项目" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem label="项目名称">
            <NInput
              :value="form.name"
              :input-props="{ 'aria-label': '项目名称' }"
              @update:value="updateName"
            />
          </NFormItem>
          <NFormItem label="项目标识">
            <NInput
              :value="form.slug"
              :input-props="{ 'aria-label': '项目标识' }"
              placeholder="meetflow"
              @update:value="updateSlug"
            />
          </NFormItem>
          <NFormItem label="一句话说明">
            <NInput
              :value="form.summary"
              :input-props="{ 'aria-label': '一句话说明' }"
              @update:value="(value: string) => { form.summary = value }"
            />
          </NFormItem>
        </NForm>
        <p class="form-hint">标识由名称自动生成，可手动修改；仅使用小写字母、数字和连字符。</p>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <template #footer>
          <NButton quaternary :disabled="creating" @click="closeCreate">取消</NButton>
          <NButton
            type="primary"
            :loading="creating"
            :disabled="creating || !form.name.trim() || !form.slug.trim()"
            @click="createProject"
          >
            创建项目
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </main>
</template>
