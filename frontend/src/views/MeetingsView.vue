<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import MeetingCard from '../components/MeetingCard.vue'
import type { MeetingSummary, MeetingWrite } from '../meetings/types'

const router = useRouter()
const q = ref('')
const meetings = ref<MeetingSummary[]>([])
const loading = ref(true)
const error = ref('')
const createOpen = ref(false)
const creating = ref(false)
const form = ref({ title: '', project: '', meeting_type: '', meeting_date: '', participants: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    meetings.value = await api<MeetingSummary[]>(`/api/meetings?q=${encodeURIComponent(q.value)}`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '会议加载失败'
  } finally {
    loading.value = false
  }
}

async function createMeeting() {
  creating.value = true
  error.value = ''
  const payload: MeetingWrite = {
    title: form.value.title,
    project: form.value.project,
    meeting_type: form.value.meeting_type,
    meeting_date: new Date(form.value.meeting_date).toISOString(),
    participants: form.value.participants.split(/[,，、]/).map((item) => item.trim()).filter(Boolean),
    raw_notes_markdown: '',
    conclusions_markdown: '',
  }
  try {
    const created = await api<{ id: string }>('/api/meetings', { method: 'POST', body: JSON.stringify(payload) })
    await router.push(`/meetings/${created.id}`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '会议创建失败'
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <header class="workspace-hero">
      <div><p class="eyebrow">Meeting archive</p><h1>会议不是终点，<br /><em>行动才是。</em></h1><p>从讨论到结论，再到每一项后续进展。</p></div>
      <div class="hero-actions"><button class="button button-primary button-large" @click="createOpen = !createOpen">{{ createOpen ? '收起' : '新建会议' }}</button><RouterLink class="button button-quiet button-large" to="/actions">查看全部待办</RouterLink></div>
    </header>

    <form v-if="createOpen" class="panel create-meeting" @submit.prevent="createMeeting">
      <div class="section-heading"><div><p class="eyebrow">New meeting</p><h2>建立会议档案</h2></div><button type="button" class="icon-button" aria-label="关闭" @click="createOpen = false">×</button></div>
      <div class="form-grid">
        <label class="span-2">会议标题<input v-model.trim="form.title" required placeholder="例如：黑客松产品讨论" /></label>
        <label>项目<input v-model.trim="form.project" placeholder="可选" /></label>
        <label>会议类型<input v-model.trim="form.meeting_type" placeholder="例：方案评审" /></label>
        <label>会议时间<input v-model="form.meeting_date" type="datetime-local" required /></label>
        <label>参与人<input v-model="form.participants" placeholder="使用逗号分隔" /></label>
      </div>
      <div class="form-actions"><button type="button" class="button button-quiet" @click="createOpen = false">取消</button><button class="button button-primary" :disabled="creating">{{ creating ? '创建中…' : '创建并继续' }}</button></div>
    </form>

    <section class="timeline-section">
      <div class="section-heading archive-heading"><div><p class="eyebrow">Timeline</p><h2>会议档案</h2></div><form role="search" class="search-box" @submit.prevent="load"><span aria-hidden="true">⌕</span><input v-model.trim="q" aria-label="搜索会议" placeholder="搜索标题或项目" /><button class="sr-only">搜索</button></form></div>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <p v-if="loading" class="empty-state">正在整理会议时间线…</p>
      <div v-else-if="meetings.length" class="meeting-list"><MeetingCard v-for="meeting in meetings" :key="meeting.id" :meeting="meeting" /></div>
      <div v-else class="empty-state"><strong>{{ q ? '没有找到匹配的会议' : '这里还没有会议' }}</strong><p>{{ q ? '换一个标题或项目关键词试试。' : '创建第一场会议，开始积累团队档案。' }}</p></div>
    </section>
  </main>
</template>
