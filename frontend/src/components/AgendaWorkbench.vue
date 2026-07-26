<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AgendaItem, Meeting } from '../domain/meetings'
import AgendaDetail from './AgendaDetail.vue'
import AgendaQueue from './AgendaQueue.vue'

const props = defineProps<{ meeting: Meeting; initialSelectedId?: string }>()
const emit = defineEmits<{ reload: []; selectNext: [itemId: string] }>()
const selectedId = ref(props.meeting.agenda_items.find((item) => item.status === 'in_progress')?.id ?? props.meeting.agenda_items[0]?.id ?? '')
const queue = ref<{ openAdd: () => void } | null>(null)

watch(() => props.initialSelectedId, (value) => { if (value) selectedId.value = value })

watch(() => props.meeting.agenda_items, (items) => {
  if (!items.some((item) => item.id === selectedId.value)) selectedId.value = items[0]?.id ?? ''
})

const selected = computed<AgendaItem | null>(() => props.meeting.agenda_items.find((item) => item.id === selectedId.value) ?? null)

function advance() {
  const index = props.meeting.agenda_items.findIndex((item) => item.id === selectedId.value)
  const next = props.meeting.agenda_items.slice(index + 1).find((item) => item.status === 'planned')
  if (next) {
    selectedId.value = next.id
    emit('selectNext', next.id)
  }
  emit('reload')
}

function requestAdd() {
  queue.value?.openAdd()
}
</script>

<template>
  <section class="workspace-section agenda-workbench" data-testid="meeting-workbench">
    <AgendaDetail v-if="selected" :meeting="meeting" :item="selected" @changed="emit('reload')" @advance="advance" />
    <div v-else class="agenda-empty-compact" data-testid="agenda-detail">
      <div><p class="eyebrow">Agenda</p><h2>还没有议题</h2><p>从右侧队列添加本次会议的第一个议题。</p></div>
      <button class="button button-primary" @click="requestAdd">添加议题</button>
    </div>
    <AgendaQueue ref="queue" :meeting="meeting" :selected-id="selectedId" @select="selectedId = $event" @changed="emit('reload')" />
  </section>
</template>
