<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { api, ApiError } from '../api/client'
import type { AgendaDraft, AgendaItem, AgendaType, Meeting } from '../domain/meetings'
import MarkdownEditor from './MarkdownEditor.vue'
import OutcomeComposer from './OutcomeComposer.vue'
import VersionConflictDialog from './VersionConflictDialog.vue'

const props = defineProps<{ meeting: Meeting; item: AgendaItem }>()
const emit = defineEmits<{ changed: []; advance: [] }>()
function draftFor(item: AgendaItem): AgendaDraft {
  return { title: item.title, agenda_type: item.agenda_type, notes_markdown: item.notes_markdown, estimated_minutes: item.estimated_minutes }
}

const draft = reactive<AgendaDraft>(draftFor(props.item))
const accepted = ref<AgendaDraft>(draftFor(props.item))
const currentVersion = ref(props.item.version)
const dirty = computed(() => draft.title !== accepted.value.title
  || draft.agenda_type !== accepted.value.agenda_type
  || draft.notes_markdown !== accepted.value.notes_markdown
  || draft.estimated_minutes !== accepted.value.estimated_minutes)
const composer = ref<'decision' | 'action' | 'question' | null>(null)
const saving = ref(false)
const error = ref('')
const conflict = ref<{ version: number; server: string } | null>(null)

watch(() => props.item, (item) => {
  const next = draftFor(item)
  Object.assign(draft, next)
  accepted.value = next
  currentVersion.value = item.version
}, { deep: true })

async function persistIfDirty(expectedVersion = currentVersion.value): Promise<boolean> {
  if (!dirty.value) return false
  saving.value = true
  error.value = ''
  try {
    const saved = await api<AgendaItem>(`/api/agenda-items/${props.item.id}`, { method: 'PUT', body: JSON.stringify({ expected_version: expectedVersion, title: draft.title.trim(), agenda_type: draft.agenda_type, notes_markdown: draft.notes_markdown, estimated_minutes: draft.estimated_minutes }) })
    const next = draftFor(saved)
    Object.assign(draft, next)
    accepted.value = next
    currentVersion.value = saved.version
    conflict.value = null
    return true
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'version_conflict') {
      conflict.value = { version: Number(caught.details?.actual_version ?? currentVersion.value), server: props.item.notes_markdown }
    } else error.value = caught instanceof Error ? caught.message : '议题保存失败'
    throw caught
  } finally {
    saving.value = false
  }
}

async function flushIfDirty(): Promise<boolean> {
  return persistIfDirty()
}

async function save(expectedVersion = currentVersion.value) {
  try {
    if (await persistIfDirty(expectedVersion)) emit('changed')
  } catch {
    // The persistence helper keeps the error and conflict state local to this editor.
  }
}

defineExpose({ flushIfDirty })

async function flow(action: 'start' | 'skip' | 'complete') {
  saving.value = true
  error.value = ''
  try {
    await api(`/api/agenda-items/${props.item.id}/${action}`, { method: 'POST', body: JSON.stringify({ expected_version: currentVersion.value }) })
    if (action === 'complete' || action === 'skip') emit('advance')
    else emit('changed')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '议题状态更新失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="agenda-detail" data-testid="agenda-detail">
    <header class="agenda-detail-header"><div><p class="eyebrow">Current topic</p><input v-model="draft.title" class="agenda-title-input" aria-label="议题标题" /></div><span class="status-pill" :data-status="item.status">{{ item.status }}</span></header>
    <div class="agenda-meta-fields"><label>类型<select v-model="draft.agenda_type"><option value="information">信息同步</option><option value="discussion">讨论</option><option value="decision">决策</option></select></label><label>预计时长<input v-model.number="draft.estimated_minutes" type="number" min="1" max="480" /></label></div>
    <label class="agenda-notes">议题记录<MarkdownEditor v-model="draft.notes_markdown" label="议题记录" placeholder="记录讨论上下文、材料和过程…" /></label>
    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div class="agenda-save-row"><span class="muted">版本 {{ currentVersion }}</span><button class="button button-quiet" :disabled="saving || !draft.title.trim()" @click="save()">保存议题</button></div>

    <section class="agenda-outcomes"><header class="section-heading"><div><p class="eyebrow">Outcomes</p><h2>本议题产出</h2></div><div class="outcome-action-group" data-testid="outcome-actions"><button class="button button-small button-quiet" @click="composer = 'decision'">+ 决策</button><button class="button button-small button-quiet" @click="composer = 'action'">+ 行动</button><button class="button button-small button-quiet" @click="composer = 'question'">+ 开放问题</button></div></header>
      <OutcomeComposer v-if="composer" :mode="composer" :meeting="meeting" :item="item" @close="composer = null" @saved="emit('changed')" />
      <div class="outcome-list"><article v-for="decision in item.decisions" :key="decision.id"><span>决策</span><strong>{{ decision.title }}</strong></article><article v-for="action in item.actions" :key="action.id"><span>行动</span><strong>{{ action.content }}</strong></article><article v-for="question in item.open_questions" :key="question.id"><span>问题</span><strong>{{ question.question_markdown }}</strong></article><p v-if="!item.decisions.length && !item.actions.length && !item.open_questions.length" class="empty-inline">讨论结果会在这里形成可追踪的链条。</p></div>
    </section>

    <footer class="agenda-flow-actions" data-testid="flow-actions"><button v-if="item.status === 'planned'" class="button button-quiet" :disabled="saving" @click="flow('start')">开始此议题</button><button v-if="item.status === 'planned' || item.status === 'in_progress'" class="button button-quiet" :disabled="saving" @click="flow('skip')">跳过并进入下一项</button><button v-if="item.status === 'in_progress'" class="button button-primary" :disabled="saving" @click="flow('complete')">完成议题并进入下一项</button></footer>
    <VersionConflictDialog v-if="conflict" :local-markdown="draft.notes_markdown" :server-markdown="conflict.server" :actual-version="conflict.version" @close="conflict = null" @reload="emit('changed'); conflict = null" @overwrite="save" />
  </div>
</template>
