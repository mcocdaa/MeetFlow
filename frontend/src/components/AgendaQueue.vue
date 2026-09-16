<script setup lang="ts">
import { ref, watch, h } from 'vue'
import { MoreHorizontal } from '@lucide/vue'
import { NButton, NDrawer, NDrawerContent, NDropdown, NIcon, NInputNumber, NPopconfirm, NSelect } from 'naive-ui'
import { statusLabel } from '../utils/labels'
import { errorMessage } from '../utils/errors'

import { api, ApiError } from '../api/client'
import type { Page } from '../api/contracts'
import type { AgendaItem, AgendaType, Meeting } from '../domain/meetings'

type MeetingOption = { id: string; title: string; version: number }

const props = defineProps<{
  meeting: Meeting
  canContribute: boolean
  selectedId?: string
  openingId?: string
  openError?: string
}>()
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
const skipTargetId = ref('')
const moveOpen = ref(false)
const moveTarget = ref<AgendaItem | null>(null)
const moveOptions = ref<MeetingOption[]>([])
const moveLoading = ref(false)
const moveSaving = ref(false)
const moveError = ref('')
const moveForm = ref<{ target_meeting_id: string | null; position: number | null }>({ target_meeting_id: null, position: null })

watch(() => props.meeting.agenda_items, (items) => {
  ordered.value = [...items].sort((a, b) => a.position - b.position)
}, { deep: true })

function startDrag(id: string) {
  if (props.canContribute && !saving.value) draggingId.value = id
}

async function dropOn(targetId: string) {
  if (!props.canContribute || saving.value || !draggingId.value || draggingId.value === targetId) return
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
    error.value = errorMessage(caught, '议题排序失败')
    emit('changed')
  } finally {
    saving.value = false
  }
}

async function addAgenda() {
  if (!props.canContribute || !title.value.trim() || saving.value) return
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
    error.value = errorMessage(caught, '议题添加失败')
  } finally {
    saving.value = false
  }
}

async function command(item: AgendaItem, action: 'cancel') {
  if (!props.canContribute) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/agenda-items/${item.id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: item.version }) })
    guardedId.value = ''
    emit('changed')
  } catch (caught) {
    error.value = errorMessage(caught, '议题操作失败')
  } finally {
    saving.value = false
  }
}

async function skip(item: AgendaItem) {
  if (!props.canContribute || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/api/agenda-items/${item.id}/skip`, { method: 'POST', body: JSON.stringify({ expected_version: item.version }) })
    skipTargetId.value = ''
    emit('changed')
  } catch (caught) {
    error.value = errorMessage(caught, '议题操作失败')
  } finally {
    saving.value = false
  }
}

async function remove(item: AgendaItem) {
  if (!props.canContribute) return
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
    } else error.value = errorMessage(caught, '议题删除失败')
  } finally {
    saving.value = false
  }
}

async function openMove(item: AgendaItem) {
  if (!props.canContribute || moveSaving.value) return
  moveTarget.value = item
  moveForm.value = { target_meeting_id: null, position: null }
  moveError.value = ''
  moveOpen.value = true
  moveLoading.value = true
  try {
    const page = await api<Page<MeetingOption>>(`/api/meetings?project_id=${props.meeting.project.id}&limit=200`)
    moveOptions.value = (page.items ?? []).filter((row) => row.id !== props.meeting.id)
  } catch (caught) {
    moveError.value = errorMessage(caught, '目标会议加载失败')
  } finally {
    moveLoading.value = false
  }
}

async function submitMove() {
  if (!moveTarget.value || moveSaving.value) return
  if (!moveForm.value.target_meeting_id) {
    moveError.value = '请选择目标会议'
    return
  }
  moveSaving.value = true
  moveError.value = ''
  try {
    let targetVersion = moveOptions.value.find((row) => row.id === moveForm.value.target_meeting_id)?.version
    if (targetVersion === undefined) {
      const target = await api<Meeting>(`/api/meetings/${moveForm.value.target_meeting_id}`)
      targetVersion = target.version
    }
    await api(`/api/agenda-items/${moveTarget.value.id}/move`, {
      method: 'POST',
      body: JSON.stringify({
        target_meeting_id: moveForm.value.target_meeting_id,
        position: moveForm.value.position ?? null,
        expected_version: moveTarget.value.version,
        expected_source_meeting_version: props.meeting.version,
        expected_target_meeting_version: targetVersion,
      }),
    })
    moveOpen.value = false
    moveTarget.value = null
    emit('changed')
  } catch (caught) {
    moveError.value = errorMessage(caught, '议题移动失败')
  } finally {
    moveSaving.value = false
  }
}

function menuOptions(item: AgendaItem) {
  const option = (key: string, label: string, danger = false) => ({
    key,
    label: () => h('button', {
      type: 'button',
      class: ['agenda-menu-item', danger && 'agenda-menu-item--danger'],
    }, label),
  })
  return [
    option('edit', '编辑详情'),
    option('skip', '跳过'),
    option('cancel', '取消议题'),
    option('move', '移动议题'),
    option('delete', '删除议题', true),
  ]
}

function onMenuShow(item: AgendaItem, value: boolean) {
  if (value) menuId.value = item.id
  else if (menuId.value === item.id) menuId.value = ''
}

function onMenuSelect(item: AgendaItem, key: string) {
  menuId.value = ''
  if (key === 'edit') emit('select', item.id)
  else if (key === 'skip') skipTargetId.value = item.id
  else if (key === 'cancel') void command(item, 'cancel')
  else if (key === 'move') void openMove(item)
  else if (key === 'delete') void remove(item)
}
</script>

<template>
  <aside class="agenda-queue" data-testid="agenda-queue">
    <header class="section-heading"><div><p class="eyebrow">Agenda</p><h2>议题队列</h2></div><button v-if="canContribute" class="button button-small button-primary" @click="adding = !adding">{{ adding ? '收起' : '+ 议题' }}</button></header>
    <form v-if="canContribute && adding" class="agenda-add-form" @submit.prevent="addAgenda">
      <label>议题标题<input v-model="title" required /></label>
      <label>类型<select v-model="agendaType"><option value="information">信息同步</option><option value="discussion">讨论</option><option value="decision">决策</option></select></label>
      <label>预计时长（分钟）<input v-model.number="estimatedMinutes" type="number" min="1" max="480" required /></label>
      <button class="button button-small button-primary" :disabled="saving">插入队尾</button>
    </form>
    <p v-if="error || openError" class="notice notice-error">{{ error || openError }}</p>
    <div class="agenda-queue-list">
      <article v-for="(item, index) in ordered" :key="item.id" :data-testid="`agenda-row-${item.id}`" class="agenda-queue-row" :class="[{ selected: item.id === selectedId }, `agenda-status-${item.status}`]" :draggable="canContribute" @dragstart="startDrag(item.id)" @dragover.prevent @drop.prevent="dropOn(item.id)">
        <button class="agenda-select" :disabled="Boolean(openingId)" @click="emit('select', item.id)"><span class="agenda-index">{{ index + 1 }}</span><span><strong>{{ item.title }}</strong><small>{{ statusLabel('agenda', item.status) }} · {{ item.estimated_minutes ?? '—' }} 分钟</small></span></button>
        <div v-if="canContribute" class="agenda-menu">
          <n-dropdown
            trigger="click"
            :options="menuOptions(item)"
            :show="menuId === item.id"
            @update:show="(value: boolean) => onMenuShow(item, value)"
            @select="(key: string | number) => onMenuSelect(item, String(key))"
          >
            <button class="agenda-menu-trigger" :aria-label="`议题“${item.title}”的更多操作`" :aria-expanded="menuId === item.id">
              <n-icon><MoreHorizontal :size="18" /></n-icon>
            </button>
          </n-dropdown>
          <n-popconfirm
            v-if="skipTargetId === item.id"
            :show="true"
            positive-text="确认"
            negative-text="取消"
            @positive-click="skip(item)"
            @negative-click="skipTargetId = ''"
          >
            <template #trigger><span class="agenda-menu-anchor" aria-hidden="true" /></template>
            确定跳过议题“{{ item.title }}”吗？
          </n-popconfirm>
        </div>
        <div v-if="canContribute && guardedId === item.id" class="agenda-guard"><button class="button button-small button-danger" @click="command(item, 'cancel')">改为取消</button><span>产出迁移将在会议工作台中处理</span></div>
      </article>
    </div>
    <p v-if="!ordered.length" class="empty-inline">队列为空</p>

    <n-drawer :show="moveOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!moveSaving" @update:show="(value: boolean) => { if (!value && !moveSaving) moveOpen = false }">
      <n-drawer-content title="移动议题" closable>
        <p class="muted">把“{{ moveTarget?.title ?? '' }}”移动到同项目的另一场会议。</p>
        <label class="move-field">目标会议
          <n-select
            v-model:value="moveForm.target_meeting_id"
            class="move-target-select"
            :options="moveOptions.map((option) => ({ label: `${option.title} · 版本 ${option.version}`, value: option.id }))"
            :loading="moveLoading"
            :disabled="moveSaving"
            :virtual-scroll="false"
            :input-props="{ 'aria-label': '目标会议' }"
            placeholder="选择目标会议"
          />
        </label>
        <label class="move-field">位置（可选，从 0 开始）
          <n-input-number v-model:value="moveForm.position" :min="0" :max="500" :disabled="moveSaving" :input-props="{ 'aria-label': '位置' }" placeholder="留空则排在队尾" />
        </label>
        <p v-if="moveError" class="notice notice-error" role="alert">{{ moveError }}</p>
        <template #footer>
          <n-button quaternary :disabled="moveSaving" @click="moveOpen = false">取消</n-button>
          <n-button type="primary" :loading="moveSaving" :disabled="moveSaving || moveLoading" @click="submitMove">确认移动</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </aside>
</template>
