<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type Participant = { user: { id: string; username: string; display_name: string } }
const props = defineProps<{ modelValue: string; participants: Participant[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; 'update:mentionIds': [ids: string[]] }>()
const open = ref(false)
const active = ref(0)
const query = ref('')
const mentioned = ref<string[]>([])
const current = ref(props.modelValue)
const matches = computed(() => props.participants.filter((item) => `${item.user.display_name} ${item.user.username}`.toLowerCase().includes(query.value.toLowerCase())))

watch(() => props.modelValue, (value) => {
  if (value !== current.value) current.value = value
})

function input(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  current.value = value
  const match = value.match(/@([^\s@]*)$/)
  query.value = match?.[1] ?? ''
  open.value = Boolean(match)
  active.value = 0
  emit('update:modelValue', value)
}

function insert(participant: Participant) {
  const value = current.value.replace(/@([^\s@]*)$/, `@${participant.user.display_name} `)
  current.value = value
  mentioned.value = [...new Set([...mentioned.value, participant.user.id])]
  emit('update:modelValue', value)
  emit('update:mentionIds', mentioned.value)
  open.value = false
}

function keydown(event: KeyboardEvent) {
  if (!open.value || !matches.value.length) return
  if (event.key === 'ArrowDown') { event.preventDefault(); active.value = (active.value + 1) % matches.value.length }
  else if (event.key === 'ArrowUp') { event.preventDefault(); active.value = (active.value - 1 + matches.value.length) % matches.value.length }
  else if (event.key === 'Enter') { event.preventDefault(); insert(matches.value[active.value]) }
  else if (event.key === 'Escape') { event.preventDefault(); open.value = false }
}
</script>

<template>
  <div class="mention-textarea">
    <textarea role="combobox" :aria-label="label" aria-autocomplete="list" :aria-expanded="open && matches.length > 0" aria-controls="mention-listbox" :aria-activedescendant="open ? `mention-${active}` : undefined" :value="current" @input="input" @keydown="keydown" />
    <ul v-if="open && matches.length" id="mention-listbox" role="listbox" aria-label="会议参与者">
      <li v-for="(participant, index) in matches" :id="`mention-${index}`" :key="participant.user.id" role="option" :aria-selected="index === active" @mousedown.prevent="insert(participant)">{{ participant.user.display_name }} @{{ participant.user.username }}</li>
    </ul>
  </div>
</template>
