<script setup lang="ts">
import { ref, watch } from 'vue'

import type { ActionItem, ActionStatus } from '../meetings/types'

export type ActionWrite = { content: string; owner: string; due_date: string | null; status: ActionStatus }
const props = withDefaults(defineProps<{ item?: ActionItem; resetKey?: number }>(), { resetKey: 0 })
const emit = defineEmits<{ save: [draft: ActionWrite]; remove: [] }>()
const draft = ref<ActionWrite>({ content: '', owner: '', due_date: null, status: 'open' })

watch(() => props.item, (item) => {
  draft.value = item
    ? { content: item.content, owner: item.owner, due_date: item.due_date, status: item.status }
    : { content: '', owner: '', due_date: null, status: 'open' }
}, { immediate: true })

watch(() => props.resetKey, () => {
  if (!props.item) draft.value = { content: '', owner: '', due_date: null, status: 'open' }
})

function submit() {
  emit('save', { ...draft.value, due_date: draft.value.due_date || null })
}
</script>

<template>
  <form class="action-editor" @submit.prevent="submit">
    <label class="grow">行动内容<input v-model.trim="draft.content" required placeholder="下一步需要完成什么？" /></label>
    <label>负责人<input v-model.trim="draft.owner" placeholder="可选" /></label>
    <label>截止日期<input v-model="draft.due_date" type="date" /></label>
    <label v-if="item">状态<select v-model="draft.status"><option value="open">进行中</option><option value="done">已完成</option></select></label>
    <div class="row-actions action-editor-buttons">
      <button class="button button-small button-primary">{{ item ? '保存' : '添加行动项' }}</button>
      <button v-if="item" type="button" class="button button-small button-danger" @click="emit('remove')">删除</button>
    </div>
  </form>
</template>
