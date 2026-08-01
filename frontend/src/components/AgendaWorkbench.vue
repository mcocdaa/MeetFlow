<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '../api/client'
import type { AgendaItem, Meeting } from '../domain/meetings'
import AgendaDetail from './AgendaDetail.vue'
import AgendaQueue from './AgendaQueue.vue'

const props = defineProps<{
  meeting: Meeting
  canContribute: boolean
  initialSelectedId?: string
}>()
const emit = defineEmits<{ reload: [] }>()
const selectedId = ref(props.meeting.agenda_items.find((item) => item.status === 'in_progress')?.id ?? props.meeting.agenda_items[0]?.id ?? '')
const detail = ref<{ flushIfDirty: () => Promise<boolean> } | null>(null)
const openingId = ref('')
const openError = ref('')

watch(() => props.initialSelectedId, (value) => { if (value) selectedId.value = value })

watch(() => props.meeting.status, (status, previousStatus) => {
  if (status !== 'in_progress' || previousStatus === 'in_progress') return
  selectedId.value = props.meeting.agenda_items.find((item) => item.status === 'in_progress')?.id ?? props.meeting.agenda_items[0]?.id ?? ''
})

watch(() => props.meeting.agenda_items, (items) => {
  if (!items.some((item) => item.id === selectedId.value)) selectedId.value = items[0]?.id ?? ''
})

const selected = computed<AgendaItem | null>(() => props.meeting.agenda_items.find((item) => item.id === selectedId.value) ?? null)

async function openAgenda(itemId: string) {
  const item = props.meeting.agenda_items.find((row) => row.id === itemId)
  if (!item || openingId.value) return
  openError.value = ''
  if (!props.canContribute || props.meeting.status !== 'in_progress' || item.status !== 'planned') {
    selectedId.value = itemId
    return
  }
  openingId.value = itemId
  try {
    await api(`/api/agenda-items/${item.id}/start`, {
      method: 'POST', body: JSON.stringify({ expected_version: item.version }),
    })
    selectedId.value = itemId
    emit('reload')
  } catch (caught) {
    openError.value = caught instanceof Error ? caught.message : '议题开始失败'
  } finally {
    openingId.value = ''
  }
}

function advance(nextId: string | null) {
  if (nextId) selectedId.value = nextId
  emit('reload')
}

async function flushCurrentDraft(): Promise<boolean> {
  return detail.value?.flushIfDirty() ?? false
}

defineExpose({ flushCurrentDraft })
</script>

<template>
  <section class="workspace-section agenda-workbench" data-testid="meeting-workbench">
    <Transition name="agenda-detail" mode="out-in">
      <AgendaDetail v-if="selected" :key="selected.id" ref="detail" :meeting="meeting" :item="selected" :can-contribute="canContribute" @changed="emit('reload')" @advance="advance" />
      <div v-else class="agenda-empty-compact" data-testid="agenda-detail">
        <div><p class="eyebrow">Current topic</p><h2>还没有议题</h2><p>从右侧队列添加本次会议的第一个议题。</p></div>
      </div>
    </Transition>
    <AgendaQueue :meeting="meeting" :can-contribute="canContribute" :selected-id="selectedId" :opening-id="openingId" :open-error="openError" @select="openAgenda" @changed="emit('reload')" />
  </section>
</template>
