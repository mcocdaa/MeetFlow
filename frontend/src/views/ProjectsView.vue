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
import { useI18n } from '../i18n'

const { tr } = useI18n()
const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref('')
const status = ref<ProjectStatus | ''>('')
const health = ref<ProjectHealth | ''>('')
const createOpen = ref(false)
const creating = ref(false)
const slugTouched = ref(false)
const form = ref({ name: '', slug: '', summary: '' })

const healthLabels = computed<Record<ProjectHealth, string>>(() => ({
  on_track: tr('进展正常', 'On Track'),
  at_risk: tr('存在风险', 'At Risk'),
  off_track: tr('偏离计划', 'Off Track'),
  unset: tr('未设置', 'Unset'),
}))
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
  catch (reason) { error.value = errorMessage(reason, tr('项目加载失败', 'Failed to load projects')) }
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
  } catch (reason) { error.value = errorMessage(reason, tr('项目创建失败', 'Failed to create project')) }
  finally { creating.value = false }
}

onMounted(load)
</script>

<template>
  <main class="workspace-page">
    <header class="workspace-page-heading"><div><p class="eyebrow">Projects</p><h1>{{ tr('项目', 'Projects') }}</h1><p>{{ tr('从项目脉络进入会议、决策和后续行动。', 'Navigate meetings, decisions, and follow-up actions by project.') }}</p></div><button class="button button-primary" @click="openCreate">{{ tr('新建项目', 'New Project') }}</button></header>
    <div class="project-filters"><label>{{ tr('项目状态', 'Status') }}<select v-model="status"><option value="">{{ tr('全部状态', 'All Statuses') }}</option><option value="active">{{ tr('进行中', 'Active') }}</option><option value="planned">{{ tr('计划中', 'Planned') }}</option><option value="paused">{{ tr('已暂停', 'Paused') }}</option><option value="completed">{{ tr('已完成', 'Completed') }}</option><option value="canceled">{{ tr('已取消', 'Canceled') }}</option></select></label><label>{{ tr('健康度', 'Health') }}<select v-model="health"><option value="">{{ tr('全部健康度', 'All Health') }}</option><option value="on_track">{{ tr('进展正常', 'On Track') }}</option><option value="at_risk">{{ tr('存在风险', 'At Risk') }}</option><option value="off_track">{{ tr('偏离计划', 'Off Track') }}</option><option value="unset">{{ tr('未设置', 'Unset') }}</option></select></label><span class="muted">{{ tr(`筛选作用于已加载项目 · ${filtered.length} 个项目`, `Filters apply to loaded projects · ${filtered.length} projects`) }}</span></div>
    <p v-if="error && !createOpen" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state">{{ tr('正在加载项目…', 'Loading projects…') }}</p>
    <section v-else-if="filtered.length" class="project-grid">
      <RouterLink v-for="project in filtered" :key="project.id" class="project-card" :to="`/projects/${project.id}`">
        <div class="project-card-top"><span class="health-dot" :data-health="project.health"></span><span>{{ healthLabels[project.health] }}</span><StatusPill :status="project.status" kind="project" /></div>
        <h2>{{ project.name }}</h2><p>{{ project.summary || tr('尚未填写项目说明', 'No project summary provided') }}</p>
        <dl><div><dt>{{ tr('负责人', 'Lead') }}</dt><dd>{{ project.lead?.display_name ?? tr('未指定', 'Unassigned') }}</dd></div><div><dt>{{ tr('目标日期', 'Target Date') }}</dt><dd>{{ project.target_date ?? tr('未设置', 'Unset') }}</dd></div><div><dt>{{ tr('成员', 'Members') }}</dt><dd>{{ project.memberships.length }}</dd></div></dl>
        <span class="text-link">{{ tr('打开项目', 'Open Project') }} <NIcon aria-hidden="true" :size="16"><ChevronRight /></NIcon></span>
      </RouterLink>
    </section>
    <div v-else class="empty-state"><strong>{{ tr('没有匹配的项目', 'No matching projects') }}</strong><p>{{ tr('调整筛选条件，或建立一个新项目。', 'Adjust your filters or create a new project.') }}</p></div>

    <NDrawer
      :show="createOpen"
      placement="right"
      :width="'min(560px, 100vw)'"
      :mask-closable="!creating"
      @update:show="(value: boolean) => { if (!value) closeCreate() }"
    >
      <NDrawerContent :title="tr('新建项目', 'New Project')" closable>
        <NForm label-placement="top" :show-require-mark="false">
          <NFormItem :label="tr('项目名称', 'Project Name')">
            <NInput
              :value="form.name"
              :input-props="{ 'aria-label': tr('项目名称', 'Project Name') }"
              @update:value="updateName"
            />
          </NFormItem>
          <NFormItem :label="tr('项目标识', 'Project Slug')">
            <NInput
              :value="form.slug"
              :input-props="{ 'aria-label': tr('项目标识', 'Project Slug') }"
              placeholder="meetflow"
              @update:value="updateSlug"
            />
          </NFormItem>
          <NFormItem :label="tr('一句话说明', 'One-line Summary')">
            <NInput
              :value="form.summary"
              :input-props="{ 'aria-label': tr('一句话说明', 'One-line Summary') }"
              @update:value="(value: string) => { form.summary = value }"
            />
          </NFormItem>
        </NForm>
        <p class="form-hint">{{ tr('标识由名称自动生成，可手动修改；仅使用小写字母、数字和连字符。', 'Slug is auto-generated from name; lowercase letters, numbers, and hyphens only.') }}</p>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <template #footer>
          <NButton quaternary :disabled="creating" @click="closeCreate">{{ tr('取消', 'Cancel') }}</NButton>
          <NButton
            type="primary"
            :loading="creating"
            :disabled="creating || !form.name.trim() || !form.slug.trim()"
            @click="createProject"
          >
            {{ tr('创建项目', 'Create Project') }}
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>
  </main>
</template>
