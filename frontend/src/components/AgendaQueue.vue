<script setup lang="ts">
import { computed, ref, watch, h } from 'vue'
import { MoreHorizontal } from '@lucide/vue'
import { NButton, NDrawer, NDrawerContent, NDropdown, NIcon, NInputNumber, NPopconfirm, NSelect } from 'naive-ui'
import { statusLabel } from '../utils/labels'
import { errorMessage } from '../utils/errors'

import { api, ApiError } from '../api/client'
import type { Page } from '../api/contracts'
import type { AgendaItem, AgendaType, Meeting } from '../domain/meetings'
import { useI18n } from '../i18n'

const { tr } = useI18n()

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
  if (props.canContribute && !meetingLocked.value && !saving.value) draggingId.value = id
}

async function dropOn(targetId: string) {
  if (!props.canContribute || meetingLocked.value || saving.value || !draggingId.value || draggingId.value === targetId) return
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
    error.value = errorMessage(caught, tr('议题排序失败', 'Failed to reorder agenda items'))
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
    error.value = errorMessage(caught, tr('议题添加失败', 'Failed to add agenda item'))
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
    error.value = errorMessage(caught, tr('议题操作失败', 'Agenda action failed'))
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
    error.value = errorMessage(caught, tr('议题操作失败', 'Agenda action failed'))
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
      error.value = tr('议题已有产出，请先迁移产出，或将议题标记为取消。', 'This agenda item already has outcomes. Please migrate its outcomes or cancel the item first.')
    } else error.value = errorMessage(caught, tr('议题删除失败', 'Failed to delete agenda item'))
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
    moveError.value = errorMessage(caught, tr('目标会议加载失败', 'Failed to load target meetings'))
  } finally {
    moveLoading.value = false
  }
}

async function submitMove() {
  if (!moveTarget.value || moveSaving.value) return
  if (!moveForm.value.target_meeting_id) {
    moveError.value = tr('请选择目标会议', 'Please select a target meeting')
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
    moveError.value = errorMessage(caught, tr('议题移动失败', 'Failed to move agenda item'))
  } finally {
    moveSaving.value = false
  }
}

const meetingLocked = computed(() => props.meeting.status === 'completed' || props.meeting.status === 'canceled')

/** Skip/cancel/move are only accepted by the backend for planned or in-progress items. */
function canRunFlowCommand(item: AgendaItem) {
  return item.status === 'planned' || item.status === 'in_progress'
}

function menuOptions(item: AgendaItem) {
  const option = (key: string, label: string, danger = false) => ({
    key,
    label: () => h('button', {
      type: 'button',
      class: ['agenda-menu-item', danger && 'agenda-menu-item--danger'],
    }, label),
  })
  const options = [option('edit', tr('编辑详情', 'Edit Details'))]
  if (canRunFlowCommand(item)) {
    options.push(
      option('skip', tr('跳过', 'Skip')),
      option('cancel', tr('取消议题', 'Cancel Agenda')),
      option('move', tr('移动议题', 'Move Agenda')),
    )
  }
  options.push(option('delete', tr('删除议题', 'Delete Agenda'), true))
  return options
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
    <header class="section-heading"><div><p class="eyebrow">{{ tr('议程编排', 'Agenda') }}</p><h2>{{ tr('议题队列', 'Agenda Queue') }}</h2></div><button v-if="canContribute" class="button button-small button-primary" @click="adding = !adding">{{ adding ? tr('收起', 'Close') : tr('+ 议题', '+ Agenda') }}</button></header>
    <form v-if="canContribute && adding" class="agenda-add-form" @submit.prevent="addAgenda">
      <label>{{ tr('议题标题', 'Agenda Title') }}<input v-model="title" required /></label>
      <label>{{ tr('类型', 'Type') }}<select v-model="agendaType"><option value="information">{{ tr('信息同步', 'Info Sync') }}</option><option value="discussion">{{ tr('讨论', 'Discussion') }}</option><option value="decision">{{ tr('决策', 'Decision') }}</option></select></label>
      <label>{{ tr('预计时长（分钟）', 'Duration (min)') }}<input v-model.number="estimatedMinutes" type="number" min="1" max="480" required /></label>
      <button class="button button-small button-primary" :disabled="saving">{{ tr('插入队尾', 'Add to Queue') }}</button>
    </form>
    <p v-if="error || openError" class="notice notice-error">{{ error || openError }}</p>
    <div class="agenda-queue-list">
      <article v-for="(item, index) in ordered" :key="item.id" :data-testid="`agenda-row-${item.id}`" class="agenda-queue-row" :class="[{ selected: item.id === selectedId }, `agenda-status-${item.status}`]" :draggable="canContribute && !meetingLocked" @dragstart="startDrag(item.id)" @dragover.prevent @drop.prevent="dropOn(item.id)">
        <button class="agenda-select" :disabled="Boolean(openingId)" @click="emit('select', item.id)"><span class="agenda-index">{{ index + 1 }}</span><span><strong>{{ item.title }}</strong><small>{{ statusLabel('agenda', item.status) }} · {{ item.estimated_minutes ?? '—' }} {{ tr('分钟', 'min') }}</small></span></button>
        <div v-if="canContribute && !meetingLocked" class="agenda-menu">
          <n-dropdown
            trigger="click"
            :options="menuOptions(item)"
            :show="menuId === item.id"
            @update:show="(value: boolean) => onMenuShow(item, value)"
            @select="(key: string | number) => onMenuSelect(item, String(key))"
          >
            <button class="agenda-menu-trigger" :aria-label="tr(`议题“${item.title}”的更多操作`, `More actions for ${item.title}`)" :aria-expanded="menuId === item.id">
              <n-icon><MoreHorizontal :size="18" /></n-icon>
            </button>
          </n-dropdown>
          <n-popconfirm
            v-if="skipTargetId === item.id"
            :show="true"
            :positive-text="tr('确认', 'Confirm')"
            :negative-text="tr('取消', 'Cancel')"
            @positive-click="skip(item)"
            @negative-click="skipTargetId = ''"
          >
            <template #trigger><span class="agenda-menu-anchor" aria-hidden="true" /></template>
            {{ tr(`确定跳过议题“${item.title}”吗？`, `Skip agenda item "${item.title}"?`) }}
          </n-popconfirm>
        </div>
        <div v-if="canContribute && guardedId === item.id" class="agenda-guard"><button class="button button-small button-danger" @click="command(item, 'cancel')">{{ tr('改为取消', 'Cancel Instead') }}</button><span>{{ tr('产出迁移将在会议工作台中处理', 'Outcome migration is handled in the workbench') }}</span></div>
      </article>
    </div>
    <p v-if="!ordered.length" class="empty-inline">{{ tr('队列为空', 'Queue is empty') }}</p>

    <n-drawer :show="moveOpen" placement="right" :width="'min(560px, 100vw)'" :mask-closable="!moveSaving" @update:show="(value: boolean) => { if (!value && !moveSaving) moveOpen = false }">
      <n-drawer-content :title="tr('移动议题', 'Move Agenda')" closable>
        <p class="muted">{{ tr(`把“${moveTarget?.title ?? ''}”移动到同项目的另一场会议。`, `Move "${moveTarget?.title ?? ''}" to another meeting in this project.`) }}</p>
        <label class="move-field">{{ tr('目标会议', 'Target Meeting') }}
          <n-select
            v-model:value="moveForm.target_meeting_id"
            class="move-target-select"
            :options="moveOptions.map((option) => ({ label: option.title, value: option.id }))"
            :loading="moveLoading"
            :disabled="moveSaving"
            :virtual-scroll="false"
            :input-props="{ 'aria-label': tr('目标会议', 'Target Meeting') }"
            :placeholder="tr('选择目标会议', 'Select target meeting')"
          />
        </label>
        <label class="move-field">{{ tr('位置（可选，从 0 开始）', 'Position (optional, 0-based)') }}
          <n-input-number v-model:value="moveForm.position" :min="0" :max="500" :disabled="moveSaving" :input-props="{ 'aria-label': tr('位置', 'Position') }" :placeholder="tr('留空则排在队尾', 'Leave empty to append')" />
        </label>
        <p v-if="moveError" class="notice notice-error" role="alert">{{ moveError }}</p>
        <template #footer>
          <n-button quaternary :disabled="moveSaving" @click="moveOpen = false">{{ tr('取消', 'Cancel') }}</n-button>
          <n-button type="primary" :loading="moveSaving" :disabled="moveSaving || moveLoading" @click="submitMove">{{ tr('确认移动', 'Confirm Move') }}</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </aside>
</template>
