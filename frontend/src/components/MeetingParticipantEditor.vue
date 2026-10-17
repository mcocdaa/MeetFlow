<script setup lang="ts">
import { Plus, X } from '@lucide/vue'
import { NButton, NIcon, NSelect } from 'naive-ui'
import { computed } from 'vue'

import type { UserRef } from '../api/contracts'
import type { ParticipationRole } from '../domain/meetings'
import { useI18n } from '../i18n'
import { PARTICIPATION_ROLE_LABELS, participationRoleLabel } from '../utils/labels'

const { tr } = useI18n()

export type ParticipantValue = {
  user_id: string
  participation_role: ParticipationRole
}

const props = withDefaults(defineProps<{
  modelValue: ParticipantValue[]
  memberOptions: UserRef[]
  disabled?: boolean
}>(), { disabled: false })

const emit = defineEmits<{ 'update:modelValue': [value: ParticipantValue[]] }>()

const roleOptions = computed(() => (Object.keys(PARTICIPATION_ROLE_LABELS) as ParticipationRole[]).map((role) => ({
  label: participationRoleLabel(role),
  value: role,
})))

/** Options for one row: deduplicated members, excluding selections owned by other rows. */
function optionsFor(index: number) {
  const usedByOtherRows = new Set(
    props.modelValue.filter((_, rowIndex) => rowIndex !== index).map((row) => row.user_id),
  )
  const seen = new Set<string>()
  const options: Array<{ label: string; value: string }> = []
  for (const member of props.memberOptions) {
    if (usedByOtherRows.has(member.id) || seen.has(member.id)) continue
    seen.add(member.id)
    options.push({ label: member.display_name, value: member.id })
  }
  const currentUserId = props.modelValue[index]?.user_id
  if (currentUserId && !seen.has(currentUserId)) {
    const current = props.memberOptions.find((member) => member.id === currentUserId)
    options.unshift({ label: current?.display_name ?? currentUserId, value: currentUserId })
  }
  return options
}

function updateRow(index: number, patch: Partial<ParticipantValue>) {
  emit('update:modelValue', props.modelValue.map((row, rowIndex) => (
    rowIndex === index ? { ...row, ...patch } : row
  )))
}

function addRow() {
  emit('update:modelValue', [...props.modelValue, { user_id: '', participation_role: 'attendee' }])
}

function removeRow(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, rowIndex) => rowIndex !== index))
}
</script>

<template>
  <div class="participant-editor">
    <div v-for="(row, index) in modelValue" :key="index" class="participant-editor-row">
      <n-select
        class="participant-member-select"
        :value="row.user_id || null"
        :options="optionsFor(index)"
        :placeholder="tr('选择成员', 'Select member')"
        :disabled="disabled"
        :virtual-scroll="false"
        filterable
        @update:value="(value: string | null) => updateRow(index, { user_id: value ?? '' })"
      />
      <n-select
        class="participant-role-select"
        :value="row.participation_role"
        :options="roleOptions"
        :disabled="disabled"
        :virtual-scroll="false"
        @update:value="(value: ParticipationRole) => updateRow(index, { participation_role: value })"
      />
      <n-button v-if="!disabled" quaternary :aria-label="tr('移除参与人', 'Remove participant')" @click="removeRow(index)">
        <template #icon><n-icon><X :size="16" /></n-icon></template>
      </n-button>
    </div>
    <n-button v-if="!disabled" quaternary @click="addRow">
      <template #icon><n-icon><Plus :size="16" /></n-icon></template>
      {{ tr('添加参与人', 'Add Participant') }}
    </n-button>
  </div>
</template>
