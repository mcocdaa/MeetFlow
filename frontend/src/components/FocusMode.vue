<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NProgress, NTag, useMessage } from 'naive-ui'
import { api, ApiError } from '../api/client'
import type { AgendaItem, Meeting } from '../domain/meetings'
import type { ActionItem, ActionStatus } from '../domain/outcomes'
import { errorMessage } from '../utils/errors'
import { parseUtcTimestamp } from '../utils/time'
import MarkdownEditor from './MarkdownEditor.vue'
import type { MarkdownEditorHandle } from './MarkdownEditor.vue'
import OutcomeComposer from './OutcomeComposer.vue'
import { Check, ChevronLeft, ChevronRight } from '@lucide/vue'

const props = defineProps<{
  show: boolean
  meeting: Meeting
  canContribute: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  reload: []
}>()

const message = useMessage()
const notesEditor = ref<MarkdownEditorHandle | null>(null)
const now = ref(Date.now())
const saving = ref(false)
const advancing = ref(false)
const composer = ref<'decision' | 'action' | 'question' | null>(null)
const hoveredOutcomeId = ref<string | null>(null)

// Current selected agenda item in Focus Mode
const selectedAgendaId = ref<string>('')

watch(() => props.meeting.agenda_items, (items) => {
  if (!items || items.length === 0) {
    selectedAgendaId.value = ''
    return
  }
  if (!items.some((item) => item.id === selectedAgendaId.value)) {
    const inProgress = items.find((item) => item.status === 'in_progress')
    selectedAgendaId.value = inProgress?.id ?? items[0].id
  }
}, { immediate: true })

watch(() => props.show, (shown) => {
  if (shown && props.meeting.agenda_items.length > 0) {
    const inProgress = props.meeting.agenda_items.find((item) => item.status === 'in_progress')
    selectedAgendaId.value = inProgress?.id ?? props.meeting.agenda_items[0].id
  }
})

const currentItem = computed<AgendaItem | null>(() => {
  return props.meeting.agenda_items.find((item) => item.id === selectedAgendaId.value) ?? props.meeting.agenda_items[0] ?? null
})

const currentIndex = computed(() => {
  if (!currentItem.value) return 0
  return props.meeting.agenda_items.findIndex((item) => item.id === currentItem.value!.id)
})

const totalItems = computed(() => props.meeting.agenda_items.length)

const progressPercent = computed(() => {
  if (totalItems.value === 0) return 0
  const completed = props.meeting.agenda_items.filter((item) => item.status === 'completed' || item.status === 'skipped').length
  return Math.round((completed / totalItems.value) * 100)
})

const liveElapsed = computed(() => {
  if (!props.meeting.started_at) return ''
  const elapsedSeconds = Math.max(0, Math.floor((now.value - parseUtcTimestamp(props.meeting.started_at).getTime()) / 1000))
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.floor((elapsedSeconds % 3600) / 60)
  const seconds = elapsedSeconds % 60
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(hours ? 2 : 1, '0')}:${String(seconds).padStart(2, '0')}`
})

// Local draft notes for current item
const localNotes = ref('')
const localVersion = ref(0)
const dirty = ref(false)

watch(() => currentItem.value, (item) => {
  if (item) {
    localNotes.value = item.notes_markdown
    localVersion.value = item.version
    dirty.value = false
  }
}, { immediate: true })

function onNotesInput(val: string) {
  localNotes.value = val
  dirty.value = true
}

function insertTag(tag: string) {
  if (!props.canContribute) return
  const prefix = localNotes.value && !localNotes.value.endsWith('\n') ? '\n' : ''
  localNotes.value = `${localNotes.value}${prefix}${tag}`
  dirty.value = true
}

// Clock handle
let clockHandle: number | undefined
onMounted(() => {
  clockHandle = window.setInterval(() => { now.value = Date.now() }, 1000)
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  if (clockHandle !== undefined) window.clearInterval(clockHandle)
  window.removeEventListener('keydown', handleKeydown)
})

function handleKeydown(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Escape') {
    exitFocus()
  } else if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault()
    if (currentItem.value?.status === 'in_progress') {
      void completeAndAdvance()
    }
  }
}

function exitFocus() {
  void persistCurrentNotes()
  emit('update:show', false)
}

async function persistCurrentNotes(): Promise<boolean> {
  if (!props.canContribute || !currentItem.value || !dirty.value) return false
  const markdown = typeof notesEditor.value?.flush === 'function' ? notesEditor.value.flush() : localNotes.value
  saving.value = true
  try {
    const saved = await api<AgendaItem>(`/api/agenda-items/${currentItem.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        expected_version: localVersion.value,
        title: currentItem.value.title,
        agenda_type: currentItem.value.agenda_type,
        notes_markdown: markdown,
        estimated_minutes: currentItem.value.estimated_minutes,
        proposer_user_id: currentItem.value.proposer?.id ?? null,
        presenter_user_id: currentItem.value.presenter?.id ?? null,
      }),
    })
    localVersion.value = saved.version
    dirty.value = false
    emit('reload')
    return true
  } catch (caught) {
    message.error(errorMessage(caught, '议题笔记保存失败'))
    return false
  } finally {
    saving.value = false
  }
}

async function completeAndAdvance() {
  if (!props.canContribute || !currentItem.value || advancing.value) return
  advancing.value = true
  try {
    await persistCurrentNotes()
    const result = await api<{ next_agenda_item_id: string | null }>(`/api/agenda-items/${currentItem.value.id}/complete-and-advance`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: localVersion.value }),
    })
    message.success(`议题「${currentItem.value.title}」已完成`)
    emit('reload')
    if (result.next_agenda_item_id) {
      selectedAgendaId.value = result.next_agenda_item_id
    }
  } catch (caught) {
    message.error(errorMessage(caught, '完成议题失败'))
  } finally {
    advancing.value = false
  }
}

function selectAgenda(id: string) {
  if (dirty.value) {
    void persistCurrentNotes()
  }
  selectedAgendaId.value = id
}

// Action Status Cycling and Checkbox Toggle
async function toggleActionStatus(action: ActionItem, targetStatus?: ActionStatus) {
  if (!props.canContribute) return
  let nextStatus: ActionStatus
  if (targetStatus) {
    nextStatus = targetStatus
  } else {
    // Checkbox click toggle: done <-> open/in_progress
    if (action.status === 'done') {
      nextStatus = 'open'
    } else {
      nextStatus = 'done'
    }
  }

  try {
    const updated = await api<ActionItem>(`/api/actions/${action.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        status: nextStatus,
        expected_version: action.version,
      }),
    })
    action.status = updated.status
    action.version = updated.version
    message.success(`行动项状态更新为: ${actionStatusLabel(nextStatus)}`)
    emit('reload')
  } catch (caught) {
    message.error(errorMessage(caught, '更新行动项失败'))
  }
}

function cycleActionStatus(action: ActionItem) {
  if (!props.canContribute) return
  const cycleMap: Record<ActionStatus, ActionStatus> = {
    open: 'in_progress',
    in_progress: 'done',
    done: 'open',
    canceled: 'open',
  }
  const next = cycleMap[action.status] || 'open'
  void toggleActionStatus(action, next)
}

function actionStatusLabel(status: ActionStatus): string {
  const map: Record<ActionStatus, string> = {
    open: '待办',
    in_progress: '进行中',
    done: '已完成',
    canceled: '已取消',
  }
  return map[status] || status
}

const noteActionTags = computed(() => {
  const regex = /@行动:(\[[^\]]*\])*\s*([^\n\r]+)/g
  const matches: string[] = []
  let match: RegExpExecArray | null
  while ((match = regex.exec(localNotes.value)) !== null) {
    matches.push(match[2].trim())
  }
  return matches
})
</script>

<template>
  <div v-if="props.show" class="focus-mode-container" data-testid="focus-mode-view">
    <!-- Top Floating Header Bar -->
    <header class="focus-topbar">
      <div class="focus-bar-left">
        <div class="focus-live-badge" v-if="meeting.status === 'in_progress'">
          <span class="live-dot-pulse"></span>
          <span class="live-time-text">{{ liveElapsed || '进行中' }}</span>
        </div>
        <div class="focus-meeting-title">
          <span class="project-pill">{{ meeting.project.name }}</span>
          <strong>{{ meeting.title }}</strong>
        </div>
      </div>

      <div class="focus-bar-center" v-if="currentItem">
        <div class="focus-topic-pill">
          <span class="topic-index">{{ currentIndex + 1 }}/{{ totalItems }}</span>
          <span class="topic-title">{{ currentItem.title }}</span>
          <n-tag v-if="currentItem.presenter" size="small" :bordered="false" class="presenter-tag">
            主讲: {{ currentItem.presenter.display_name }}
          </n-tag>
        </div>
        <div class="focus-progress-wrapper">
          <n-progress
            type="line"
            :percentage="progressPercent"
            :show-indicator="false"
            :height="4"
            status="success"
          />
        </div>
      </div>

      <div class="focus-bar-right">
        <div class="focus-nav-arrows">
          <button
            type="button"
            class="icon-nav-btn"
            :disabled="currentIndex <= 0"
            title="上一议题"
            @click="selectAgenda(meeting.agenda_items[currentIndex - 1].id)"
          >
            <ChevronLeft :size="14" />
          </button>
          <button
            type="button"
            class="icon-nav-btn"
            :disabled="currentIndex >= totalItems - 1"
            title="下一议题"
            @click="selectAgenda(meeting.agenda_items[currentIndex + 1].id)"
          >
            <ChevronRight :size="14" />
          </button>
        </div>

        <button
          v-if="canContribute && currentItem?.status === 'in_progress'"
          type="button"
          class="button button-primary focus-flow-btn"
          :disabled="advancing"
          @click="completeAndAdvance"
        >
          <span>完成并下一项</span>
          <kbd class="shortcut-key">⌘↵</kbd>
        </button>

        <button
          v-if="canContribute && dirty"
          type="button"
          class="button button-quiet"
          :disabled="saving"
          @click="persistCurrentNotes"
        >
          {{ saving ? '保存中…' : '保存笔记' }}
        </button>

        <button type="button" class="focus-exit-btn" @click="exitFocus" title="退出专注模式 (Esc)">
          退出专注 <kbd>Esc</kbd>
        </button>
      </div>
    </header>

    <!-- Main Split Body -->
    <div class="focus-body">
      <!-- Left Pane: Distraction-free Note Editor -->
      <section class="focus-editor-pane">
        <div class="pane-header">
          <div class="agenda-title-row" v-if="currentItem">
            <h1 class="focus-agenda-title">{{ currentItem.title }}</h1>
            <span class="focus-agenda-type">
              {{ currentItem.agenda_type === 'decision' ? '决策议题' : currentItem.agenda_type === 'discussion' ? '讨论议题' : '信息同步' }}
            </span>
          </div>
          <p class="syntax-guide-pill">
            💡 支持在手记中直接输入 <code>@决策: 结论</code>、<code>@行动:[待办][@成员][日期] 事项</code>、<code>@问题: 待确认</code> 自动双向流转产出。
          </p>
          <div class="quick-tag-toolbar" v-if="canContribute">
            <span class="quick-tag-label">快捷标签:</span>
            <button type="button" class="tag-insert-btn tag-btn-decision" @click="insertTag('@决策: ')">+ 决策</button>
            <button type="button" class="tag-insert-btn tag-btn-action" @click="insertTag('@行动:[open] ')">+ 待办行动</button>
            <button type="button" class="tag-insert-btn tag-btn-question" @click="insertTag('@问题: ')">+ 开放问题</button>
          </div>
        </div>

        <div class="editor-content-area" v-if="currentItem">
          <MarkdownEditor
            ref="notesEditor"
            :model-value="localNotes"
            label="议题笔记"
            placeholder="专注于此项议题的核心讨论、事实依据与快速手记…"
            :disabled="!canContribute || saving"
            @update:model-value="onNotesInput"
          />
        </div>
        <div v-else class="empty-state">
          <strong>会议暂无议题</strong>
          <p>请在退出专注模式后添加议题。</p>
        </div>
      </section>

      <!-- Right Pane: Real-time Outcomes & Action State Machine -->
      <aside class="focus-outcomes-pane" v-if="currentItem">
        <div class="outcomes-header">
          <div class="outcomes-title-area">
            <h3>实时决议与待办</h3>
            <span class="outcomes-count">
              {{ currentItem.decisions.length + currentItem.actions.length + currentItem.open_questions.length }} 项产出
            </span>
          </div>
          <div v-if="canContribute" class="quick-composer-btns">
            <button type="button" class="tiny-btn" @click="composer = 'decision'">+ 决策</button>
            <button type="button" class="tiny-btn" @click="composer = 'action'">+ 行动</button>
            <button type="button" class="tiny-btn" @click="composer = 'question'">+ 问题</button>
          </div>
        </div>

        <!-- Inline Composer when triggered -->
        <OutcomeComposer
          v-if="canContribute && composer"
          :mode="composer"
          :meeting="meeting"
          :item="currentItem"
          @close="composer = null"
          @saved="emit('reload')"
        />

        <div class="outcomes-cards-list">
          <!-- Decisions -->
          <div
            v-for="decision in currentItem.decisions"
            :key="decision.id"
            class="outcome-card decision-card"
            :class="{ 'linked-glow': hoveredOutcomeId === decision.id }"
            @mouseenter="hoveredOutcomeId = decision.id"
            @mouseleave="hoveredOutcomeId = null"
          >
            <div class="card-badge-row">
              <span class="card-badge badge-decision">决策</span>
              <span v-if="decision.is_derived" class="derived-badge">来自手记</span>
            </div>
            <div class="card-title">{{ decision.title }}</div>
          </div>

          <!-- Actions with one-click checkbox & status cycle -->
          <div
            v-for="action in currentItem.actions"
            :key="action.id"
            class="outcome-card action-card"
            :class="{
              'action-card--done': action.status === 'done',
              'linked-glow': hoveredOutcomeId === action.id || noteActionTags.includes(action.content)
            }"
            @mouseenter="hoveredOutcomeId = action.id"
            @mouseleave="hoveredOutcomeId = null"
          >
            <div class="action-card-header">
              <div class="action-card-left">
                <!-- Checkbox toggle with micro-bounce animation -->
                <button
                  type="button"
                  class="action-checkbox-toggle"
                  :class="[`status-${action.status}`]"
                  :disabled="!canContribute"
                  title="点击切换完成状态"
                  @click="toggleActionStatus(action)"
                >
                  <span v-if="action.status === 'done'" class="check-mark-animated"><Check :size="12" :stroke-width="3" /></span>
                  <span v-else-if="action.status === 'in_progress'" class="progress-dot"></span>
                </button>
                <div class="action-text" :class="{ 'done-strikethrough': action.status === 'done' }">
                  {{ action.content }}
                </div>
              </div>

              <!-- Status badge pill (clickable to cycle status) -->
              <button
                type="button"
                class="status-cycle-pill"
                :class="[`pill-${action.status}`]"
                :disabled="!canContribute"
                title="点击循环状态 (待办 -> 进行中 -> 已完成)"
                @click="cycleActionStatus(action)"
              >
                {{ actionStatusLabel(action.status) }}
              </button>
            </div>

            <div class="action-card-meta">
              <span v-if="action.owner" class="meta-tag owner-tag">@{{ action.owner.display_name }}</span>
              <span v-if="action.due_date" class="meta-tag due-tag">截止 {{ action.due_date }}</span>
              <span v-if="action.is_derived" class="derived-badge">手记双向映射</span>
            </div>
          </div>

          <!-- Questions -->
          <div
            v-for="question in currentItem.open_questions"
            :key="question.id"
            class="outcome-card question-card"
            :class="{ 'linked-glow': hoveredOutcomeId === question.id }"
            @mouseenter="hoveredOutcomeId = question.id"
            @mouseleave="hoveredOutcomeId = null"
          >
            <div class="card-badge-row">
              <span class="card-badge badge-question">开放问题</span>
              <span v-if="question.is_derived" class="derived-badge">来自手记</span>
            </div>
            <div class="card-title">{{ question.question_markdown }}</div>
          </div>

          <div
            v-if="!currentItem.decisions.length && !currentItem.actions.length && !currentItem.open_questions.length"
            class="empty-outcomes-note"
          >
            <p>在左侧记录输入 <code>@行动: 事项内容</code>，或点击右上角按钮添加结构化决议与待办。</p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.focus-mode-container {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  color: #1e293b;
  font-family: inherit;
  overflow: hidden;
}

/* Top Floating Header Bar */
.focus-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #e2e8f0;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
  flex-shrink: 0;
}

.focus-bar-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.focus-live-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #e6f4ea;
  color: #137333;
  font-size: 0.8rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.live-dot-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1e8e3e;
  box-shadow: 0 0 0 0 rgba(30, 142, 62, 0.6);
  animation: live-pulse-animation 1.8s infinite;
}

@keyframes live-pulse-animation {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(30, 142, 62, 0.6); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(30, 142, 62, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(30, 142, 62, 0); }
}

.focus-meeting-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.95rem;
}

.project-pill {
  padding: 2px 8px;
  border-radius: 6px;
  background: #f1f5f9;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 700;
}

.focus-bar-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}

.focus-topic-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.88rem;
}

.topic-index {
  padding: 1px 7px;
  border-radius: 6px;
  background: #0b6a58;
  color: white;
  font-size: 0.72rem;
  font-weight: 800;
}

.topic-title {
  font-weight: 700;
  color: #0f172a;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.presenter-tag {
  font-size: 0.72rem;
}

.focus-progress-wrapper {
  width: 180px;
}

.focus-bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.focus-nav-arrows {
  display: flex;
  gap: 4px;
}

.icon-nav-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: white;
  color: #475569;
  display: grid;
  place-items: center;
  cursor: pointer;
  font-size: 0.75rem;
  transition: all 0.15s;
}

.icon-nav-btn:hover:not(:disabled) {
  background: #f1f5f9;
  color: #0f172a;
}

.icon-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.focus-flow-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.shortcut-key {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.25);
  font-size: 0.7rem;
  font-family: inherit;
}

.focus-exit-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: white;
  color: #334155;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.focus-exit-btn:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
}

.focus-exit-btn kbd {
  padding: 1px 5px;
  border-radius: 4px;
  background: #e2e8f0;
  font-size: 0.7rem;
  font-family: inherit;
}

/* Split Body */
.focus-body {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.85fr);
  gap: 0;
  overflow: hidden;
}

/* Left Editor Pane */
.focus-editor-pane {
  display: flex;
  flex-direction: column;
  padding: 24px 32px;
  overflow-y: auto;
  border-right: 1px solid #e2e8f0;
  background: white;
}

.pane-header {
  margin-bottom: 18px;
}

.agenda-title-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}

.focus-agenda-title {
  margin: 0;
  font-size: 1.65rem;
  font-weight: 800;
  color: #0f172a;
}

.focus-agenda-type {
  font-size: 0.78rem;
  color: #64748b;
  font-weight: 600;
}

.syntax-guide-pill {
  margin: 0;
  font-size: 0.78rem;
  color: #475569;
  background: #f8fafc;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #f1f5f9;
}

.syntax-guide-pill code {
  background: #e2e8f0;
  padding: 2px 4px;
  border-radius: 4px;
  font-family: monospace;
}

.quick-tag-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.quick-tag-label {
  font-size: 0.76rem;
  color: #64748b;
  font-weight: 500;
}

.tag-insert-btn {
  border: 1px solid transparent;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 0.76rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.tag-btn-decision {
  background: #eff6ff;
  color: #1d4ed8;
  border-color: #bfdbfe;
}
.tag-btn-decision:hover {
  background: #dbeafe;
}

.tag-btn-action {
  background: #f0fdf4;
  color: #15803d;
  border-color: #bbf7d0;
}
.tag-btn-action:hover {
  background: #dcfce7;
}

.tag-btn-question {
  background: #fffbeb;
  color: #b45309;
  border-color: #fde68a;
}
.tag-btn-question:hover {
  background: #fef3c7;
}

.editor-content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* Right Outcomes Pane */
.focus-outcomes-pane {
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  background: #f8fafc;
  overflow-y: auto;
}

.outcomes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.outcomes-title-area h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 750;
  color: #0f172a;
}

.outcomes-count {
  font-size: 0.75rem;
  color: #64748b;
}

.quick-composer-btns {
  display: flex;
  gap: 6px;
}

.tiny-btn {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: white;
  color: #1e293b;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.tiny-btn:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
}

.outcomes-cards-list {
  display: grid;
  gap: 10px;
}

.outcome-card {
  padding: 12px 14px;
  border-radius: 10px;
  background: white;
  border: 1px solid #e2e8f0;
  transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.outcome-card.linked-glow {
  border-color: #0b6a58;
  box-shadow: 0 0 0 2px rgba(11, 106, 88, 0.18), 0 4px 12px rgba(0, 0, 0, 0.05);
  background: #fcfdfc;
}

.card-badge-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.card-badge {
  font-size: 0.68rem;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
}

.badge-decision {
  background: #e0f2fe;
  color: #0369a1;
}

.badge-question {
  background: #fef3c7;
  color: #b45309;
}

.derived-badge {
  font-size: 0.68rem;
  color: #64748b;
  font-style: italic;
}

.card-title {
  font-size: 0.88rem;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.5;
}

/* Action Card & Checkbox Micro-Interaction */
.action-card {
  display: grid;
  gap: 8px;
}

.action-card--done {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.action-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.action-card-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
}

.action-checkbox-toggle {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 2px solid #94a3b8;
  background: white;
  display: grid;
  place-items: center;
  cursor: pointer;
  margin-top: 1px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 0;
}

.action-checkbox-toggle:hover {
  border-color: #0b6a58;
}

.action-checkbox-toggle.status-in_progress {
  border-color: #eab308;
  background: #fefce8;
}

.action-checkbox-toggle.status-done {
  border-color: #0b6a58;
  background: #0b6a58;
}

.check-mark-animated {
  color: white;
  font-size: 0.75rem;
  font-weight: 900;
  animation: check-bounce 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes check-bounce {
  0% { transform: scale(0.4); opacity: 0; }
  60% { transform: scale(1.25); }
  100% { transform: scale(1); opacity: 1; }
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #eab308;
}

.action-text {
  font-size: 0.88rem;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.45;
  transition: all 0.2s ease;
}

.action-text.done-strikethrough {
  text-decoration: line-through;
  color: #94a3b8;
}

.status-cycle-pill {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
}

.pill-open {
  background: #f1f5f9;
  color: #475569;
  border-color: #e2e8f0;
}

.pill-in_progress {
  background: #fef9c3;
  color: #854d0e;
  border-color: #fef08a;
}

.pill-done {
  background: #dcfce7;
  color: #166534;
  border-color: #bbf7d0;
}

.pill-canceled {
  background: #fee2e2;
  color: #991b1b;
  border-color: #fecaca;
}

.action-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 30px;
}

.meta-tag {
  font-size: 0.72rem;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
}

.empty-outcomes-note {
  padding: 28px 16px;
  text-align: center;
  color: #94a3b8;
  font-size: 0.82rem;
  line-height: 1.6;
}

.empty-outcomes-note code {
  background: #e2e8f0;
  padding: 2px 4px;
  border-radius: 4px;
}

@media (max-width: 900px) {
  .focus-body {
    grid-template-columns: 1fr;
  }
  .focus-editor-pane {
    border-right: none;
    border-bottom: 1px solid #e2e8f0;
  }
}
</style>
