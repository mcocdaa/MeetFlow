<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AgendaItem, Meeting } from '../domain/meetings'
import AgendaDetail from './AgendaDetail.vue'
import AgendaQueue from './AgendaQueue.vue'

const props = defineProps<{ meeting: Meeting; initialSelectedId?: string }>()
const emit = defineEmits<{ reload: []; selectNext: [itemId: string] }>()
const selectedId = ref(props.meeting.agenda_items.find((item) => item.status === 'in_progress')?.id ?? props.meeting.agenda_items[0]?.id ?? '')
const detail = ref<{ flushIfDirty: () => Promise<boolean> } | null>(null)

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

async function flushCurrentDraft(): Promise<boolean> {
  return detail.value?.flushIfDirty() ?? false
}

defineExpose({ flushCurrentDraft })
</script>

<template>
  <section class="workspace-section agenda-workbench" data-testid="meeting-workbench">
    <Transition name="agenda-detail" mode="out-in">
      <AgendaDetail v-if="selected" :key="selected.id" ref="detail" :meeting="meeting" :item="selected" @changed="emit('reload')" @advance="advance" />
      <div v-else class="agenda-empty-compact" data-testid="agenda-detail">
        <div><p class="eyebrow">Current topic</p><h2>还没有议题</h2><p>从右侧队列添加本次会议的第一个议题。</p></div>
      </div>
    </Transition>
    <AgendaQueue :meeting="meeting" :selected-id="selectedId" @select="selectedId = $event" @changed="emit('reload')" />
  </section>
</template>
