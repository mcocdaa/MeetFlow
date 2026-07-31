<script setup lang="ts">
import { ref, watch } from 'vue'

import { api, ApiError } from '../api/client'
import type { AgendaItem, AgendaType, Meeting } from '../domain/meetings'

const props = defineProps<{ meeting: Meeting; selectedId?: string; openingId?: string; openError?: string }>()
const emit = defineEmits<{ select: [id: string]; changed: [] }>()
const ordered = ref<AgendaItem[]>([...props.meeting.agenda_items].sort((a, b) => a.position - b.position))
const draggingId = ref('')
const saving = ref(false)
const adding = ref(false)
const title = ref('')
const agendaType = ref<AgendaType>('discussion')
const estimatedMinutes = ref(5)
const error = ref('')
const guardedId = ref('')
const menuId = ref('')

function openAdd() {
  adding.value = true
}

function statusLabel(status: AgendaItem['status']) {
  return { planned: '待开始', in_progress: '进行中', completed: '已完成', skipped: '已跳过', canceled: '已取消' }[status]
}

defineExpose({ openAdd })

watch(() => props.meeting.agenda_items, (items) => {
  ordered.value = [...items].sort((a, b) => a.position - b.position)
}, { deep: true })

function startDrag(id: string) {
  if (!saving.value) draggingId.value = id
}

async function dropOn(targetId: string) {
  if (saving.value || !draggingId.value || draggingId.value === targetId) return
  const previous = [...ordered.value]
  const source = previous.find((item) => item.id === draggingId.value)
  const targetIndex = previous.findIndex((item) => item.id === targetId)
  if (!source || targetIndex < 0) return
  ordered.value = previous.filter((item) => item.id !== source.id)
  ordered.value.splice(targetIndex, 0, source)
  draggingId.value = ''
  saving.value = true
  error.value = ''
  try {
    const result = await api<AgendaItem[]>(`/api/meetings/${props.meeting.id}/agenda-items/reorder`, {
      method: 'POST',
      body: JSON.stringify({ ids: ordered.value.map((item) => item.id), expected_meeting_version: props.meeting.version }),
    })
    if (Array.isArray(result) && result.length) ordered.value = result
    emit('changed')
  } catch (caught) {
    ordered.value = previous
    error.value = caught instanceof Error ? caught.message : '议题排序失败'
    emit('changed')
  } finally {
    saving.value = false
  }
}

async function addAgenda() {
  if (!title.value.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const item = await api<AgendaItem>(`/api/meetings/${props.meeting.id}/agenda-items?expected_meeting_version=${props.meeting.version}`, {
      method: 'POST',
      body: JSON.stringify({ title: title.value.trim(), agenda_type: agendaType.value, notes_markdown: '', position: ordered.value.length, estimated_minutes: estimatedMinutes.value }),
    })
    title.value = ''
    estimatedMinutes.value = 5
    adding.value = false
    emit('select', item.id)
    emit('changed')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题添加失败'
  } finally {
    saving.value = false
  }
}

async function command(item: AgendaItem, action: 'cancel') {
  saving.value = true
  error.value = ''
  try {
    await api(`/api/agenda-items/${item.id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: item.version }) })
    guardedId.value = ''
    emit('changed')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题操作失败'
  } finally {
    saving.value = false
  }
}

async function remove(item: AgendaItem) {
  saving.value = true
  error.value = ''
  guardedId.value = ''
  try {
    await api(`/api/agenda-items/${item.id}?expected_meeting_version=${props.meeting.version}`, {
      method: 'DELETE', body: JSON.stringify({ expected_version: item.version }),
    })
    emit('changed')
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'agenda_has_outcomes') {
      guardedId.value = item.id
      error.value = '议题已有产出，请先迁移产出，或将议题标记为取消。'
    } else error.value = caught instanceof Error ? caught.message : '议题删除失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <aside class="agenda-queue" data-testid="agenda-queue">
    <header class="section-heading"><div><p class="eyebrow">Agenda</p><h2>议题队列</h2></div><button class="button button-small button-primary" @click="adding = !adding">{{ adding ? '收起' : '+ 议题' }}</button></header>
    <form v-if="adding" class="agenda-add-form" @submit.prevent="addAgenda">
      <label>议题标题<input v-model="title" required /></label>
      <label>类型<select v-model="agendaType"><option value="information">信息同步</option><option value="discussion">讨论</option><option value="decision">决策</option></select></label>
      <label>预计时长（分钟）<input v-model.number="estimatedMinutes" type="number" min="1" max="480" required /></label>
      <button class="button button-small button-primary" :disabled="saving">插入队尾</button>
    </form>
    <p v-if="error || openError" class="notice notice-error">{{ error || openError }}</p>
    <div class="agenda-queue-list">
      <article v-for="(item, index) in ordered" :key="item.id" :data-testid="`agenda-row-${item.id}`" class="agenda-queue-row" :class="[{ selected: item.id === selectedId }, `agenda-status-${item.status}`]" draggable="true" @dragstart="startDrag(item.id)" @dragover.prevent @drop.prevent="dropOn(item.id)">
        <button class="agenda-select" :disabled="Boolean(openingId)" @click="emit('select', item.id)"><span class="agenda-index">{{ index + 1 }}</span><span><strong>{{ item.title }}</strong><small>{{ statusLabel(item.status) }} · {{ item.estimated_minutes ?? '—' }} 分钟</small></span></button>
        <div class="agenda-menu"><button class="agenda-menu-trigger" :aria-label="`议题“${item.title}”的更多操作`" :aria-expanded="menuId === item.id" @click="menuId = menuId === item.id ? '' : item.id">•••</button><div v-if="menuId === item.id"><button @click="emit('select', item.id); menuId = ''">编辑详情</button><button @click="command(item, 'cancel')">取消议题</button><button class="danger-link" @click="remove(item)">删除议题</button></div></div>
        <div v-if="guardedId === item.id" class="agenda-guard"><button class="button button-small button-danger" @click="command(item, 'cancel')">改为取消</button><span>产出迁移将在会议工作台中处理</span></div>
      </article>
    </div>
    <p v-if="!ordered.length" class="empty-inline">队列为空</p>
  </aside>
</template>
