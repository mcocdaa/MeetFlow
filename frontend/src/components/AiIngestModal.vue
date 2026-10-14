<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NCheckbox, NForm, NFormItem, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import { fetchApiKey, ingestMeetingNotes, rotateApiKey } from '../api/meetings'
import type { Meeting } from '../domain/meetings'
import { errorMessage } from '../utils/errors'

const props = withDefaults(defineProps<{
  show: boolean
  meeting: Meeting
  canContribute?: boolean
}>(), {
  canContribute: true,
})

const emit = defineEmits<{
  'update:show': [value: boolean]
  ingested: [meeting: Meeting]
  reload: []
}>()

const activeTab = ref<'ingest' | 'api'>('ingest')
const agendaTitle = ref('AI 纪要导入')
const selectedAgendaId = ref<string | null>(null)
const notesMarkdown = ref('')
const autoCompleteAgenda = ref(false)
const submitting = ref(false)
const ingestError = ref('')

const apiKey = ref('')
const loadingKey = ref(false)
const rotatingKey = ref(false)
const keyError = ref('')
const copiedKey = ref(false)
const copiedCurl = ref(false)

const message = useMessage()

const isMutable = computed(() => (
  props.canContribute
  && (props.meeting.status === 'draft' || props.meeting.status === 'ready' || props.meeting.status === 'in_progress')
))

const agendaOptions = computed(() => [
  { label: '➕ 新建议题（或按标题匹配）', value: '' },
  ...props.meeting.agenda_items.map((item) => ({
    label: `${item.position + 1}. ${item.title}`,
    value: item.id,
  })),
])

const curlExample = computed(() => {
  const origin = typeof window !== 'undefined' && window.location.origin
    ? window.location.origin
    : 'http://localhost:8000'
  const token = apiKey.value || 'mf_<your_api_key>'
  return [
    `curl -X POST "${origin}/api/v1/meetings/${props.meeting.id}/ingest" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -H "X-API-Key: ${token}" \\`,
    `  -d '{`,
    `    "agenda_title": "AI 纪要总结",`,
    `    "notes_markdown": "### 讨论要点\\n@决策: 确定采用 Canonical API 统一架构\\n@行动:[todo] 完成端到端联调测试\\n@开放问题: 历史存量纪要是否需要批量重放？",`,
    `    "auto_complete_agenda": true`,
    `  }'`,
  ].join('\n')
})

async function loadApiKey() {
  loadingKey.value = true
  keyError.value = ''
  try {
    const res = await fetchApiKey()
    apiKey.value = res.api_key
  } catch (caught) {
    keyError.value = errorMessage(caught, 'API 密钥加载失败')
  } finally {
    loadingKey.value = false
  }
}

async function handleRotateKey() {
  if (rotatingKey.value) return
  rotatingKey.value = true
  keyError.value = ''
  try {
    const res = await rotateApiKey()
    apiKey.value = res.api_key
    message.success('API 密钥已轮换，旧密钥已立即失效')
  } catch (caught) {
    keyError.value = errorMessage(caught, '密钥轮换失败')
  } finally {
    rotatingKey.value = false
  }
}

watch(() => props.show, (shown) => {
  if (shown) {
    ingestError.value = ''
    if (!apiKey.value) {
      void loadApiKey()
    }
  }
}, { immediate: true })

function insertSampleTag(tag: string) {
  const prefix = notesMarkdown.value && !notesMarkdown.value.endsWith('\n') ? '\n' : ''
  notesMarkdown.value = `${notesMarkdown.value}${prefix}${tag}`
}

async function submitIngest() {
  if (!notesMarkdown.value.trim() || submitting.value || !isMutable.value) return
  submitting.value = true
  ingestError.value = ''
  try {
    const res = await ingestMeetingNotes(props.meeting.id, {
      agenda_title: agendaTitle.value.trim() || 'AI 纪要导入',
      agenda_item_id: selectedAgendaId.value || undefined,
      notes_markdown: notesMarkdown.value,
      auto_complete_agenda: autoCompleteAgenda.value,
    })
    const decisions = res.decisions ?? res.extracted?.decisions ?? 0
    const actions = res.actions ?? res.extracted?.actions ?? 0
    const questions = res.questions ?? res.extracted?.questions ?? 0
    message.success(`纪要导入成功：提取 ${decisions} 项决策、${actions} 项行动、${questions} 项开放问题`)
    notesMarkdown.value = ''
    emit('ingested', res.meeting ?? res)
    emit('reload')
    emit('update:show', false)
  } catch (caught) {
    ingestError.value = errorMessage(caught, '纪要导入失败，请检查标签格式')
  } finally {
    submitting.value = false
  }
}

async function copyText(text: string, kind: 'key' | 'curl') {
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    if (kind === 'key') {
      copiedKey.value = true
      message.success('API 密钥已复制到剪贴板')
      setTimeout(() => { copiedKey.value = false }, 2000)
    } else {
      copiedCurl.value = true
      message.success('curl 命令已复制到剪贴板')
      setTimeout(() => { copiedCurl.value = false }, 2000)
    }
  } catch {
    message.warning('复制失败，请手动选择复制')
  }
}
</script>

<template>
  <n-modal
    :show="props.show"
    preset="card"
    title="🤖 AI 纪要导入 / API 接入"
    style="width: min(640px, 95vw);"
    :mask-closable="!submitting"
    @update:show="(val: boolean) => emit('update:show', val)"
  >
    <div class="ai-ingest-modal" data-testid="ai-ingest-modal">
      <div class="ai-ingest-tabs" role="tablist" aria-label="AI 纪要导入与 API 接入标签页">
        <button
          type="button"
          role="tab"
          class="ai-tab-btn"
          :class="{ active: activeTab === 'ingest' }"
          :aria-selected="activeTab === 'ingest'"
          @click="activeTab = 'ingest'"
        >
          一键导入纪要
        </button>
        <button
          type="button"
          role="tab"
          class="ai-tab-btn"
          :class="{ active: activeTab === 'api' }"
          :aria-selected="activeTab === 'api'"
          @click="activeTab = 'api'"
        >
          AI API 密钥与调用示例
        </button>
      </div>

      <div v-if="activeTab === 'ingest'" class="ai-tab-panel" data-testid="ai-ingest-tab-panel">
        <p class="ai-modal-intro">
          支持人工粘贴或 AI 助手生成的结构化 Markdown 会议纪要，单次原子调用自动解析并落库所有
          <code>@决策:</code>、<code>@行动:</code> 与 <code>@开放问题:</code> 标签。
        </p>

        <n-form label-placement="top" :show-require-mark="false">
          <div class="ai-form-grid">
            <n-form-item label="目标议题（可选）">
              <n-select
                :value="selectedAgendaId ?? ''"
                :options="agendaOptions"
                :virtual-scroll="false"
                placeholder="新建议题（或按标题匹配）"
                @update:value="(val: string) => { selectedAgendaId = val || null }"
              />
            </n-form-item>

            <n-form-item label="议题标题">
              <n-input
                v-model:value="agendaTitle"
                placeholder="例如：AI 纪要导入"
                :input-props="{ 'aria-label': '导入议题标题' }"
              />
            </n-form-item>
          </div>

          <n-form-item label="纪要 Markdown 内容" required>
            <div class="ai-notes-wrapper">
              <div class="ai-tag-toolbar">
                <span class="toolbar-hint">快速插入标签：</span>
                <button type="button" class="tag-chip" @click="insertSampleTag('@决策: ')">+ @决策:</button>
                <button type="button" class="tag-chip" @click="insertSampleTag('@行动:[todo] ')">+ @行动:</button>
                <button type="button" class="tag-chip" @click="insertSampleTag('@开放问题: ')">+ @开放问题:</button>
              </div>
              <n-input
                v-model:value="notesMarkdown"
                type="textarea"
                :autosize="{ minRows: 6, maxRows: 12 }"
                placeholder="在此粘贴包含 @决策: / @行动: / @开放问题: 的会议纪要 Markdown…"
                :input-props="{ 'aria-label': 'AI 纪要 Markdown' }"
              />
            </div>
          </n-form-item>

          <n-checkbox v-model:checked="autoCompleteAgenda">
            导入后自动将该议题标记为“已完成”
          </n-checkbox>
        </n-form>

        <p v-if="!isMutable" class="notice">当前会议状态不可导入修改，您仍可切换至“AI API 密钥与调用示例”查看接入凭证。</p>
        <p v-if="ingestError" class="notice notice-error" role="alert">{{ ingestError }}</p>
      </div>

      <div v-else class="ai-tab-panel" data-testid="ai-api-key-tab-panel">
        <p class="ai-modal-intro">
          面向无头 AI 智能体（AutoFlow、KnowFlow、OpenClaw）提供免 Cookie 的个人访问令牌（PAT），与前端复用同一套单源 Canonical API。
        </p>

        <div class="api-key-box">
          <label class="box-label">您的专属 API Key（支持 <code>X-API-Key</code> 或 <code>Authorization: Bearer</code>）：</label>
          <div v-if="loadingKey" class="muted">正在加载 API 密钥…</div>
          <div v-else class="key-input-row">
            <n-input
              :value="apiKey"
              readonly
              placeholder="mf_..."
              :input-props="{ 'aria-label': 'AI API 密钥' }"
            />
            <n-button type="primary" :disabled="!apiKey" @click="copyText(apiKey, 'key')">
              {{ copiedKey ? '已复制' : '复制密钥' }}
            </n-button>
            <n-button quaternary :loading="rotatingKey" @click="handleRotateKey">
              轮换密钥
            </n-button>
          </div>
          <p v-if="keyError" class="notice notice-error" role="alert">{{ keyError }}</p>
        </div>

        <div class="curl-box">
          <div class="curl-header">
            <label class="box-label">AI 智能体单次原子导入示例 (<code>POST /api/v1/meetings/{{ meeting.id }}/ingest</code>)：</label>
            <n-button size="tiny" quaternary @click="copyText(curlExample, 'curl')">
              {{ copiedCurl ? '已复制命令' : '复制 curl 命令' }}
            </n-button>
          </div>
          <pre class="curl-code" data-testid="ai-curl-example"><code>{{ curlExample }}</code></pre>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="row-actions">
        <n-button quaternary :disabled="submitting" @click="emit('update:show', false)">关闭</n-button>
        <n-button
          v-if="activeTab === 'ingest'"
          type="primary"
          :loading="submitting"
          :disabled="!isMutable || !notesMarkdown.trim() || submitting"
          @click="submitIngest"
        >
          立即导入并提取
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.ai-ingest-modal {
  display: grid;
  gap: 16px;
}
.ai-ingest-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--line, #e2e8f0);
  padding-bottom: 8px;
}
.ai-tab-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted, #64748b);
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
}
.ai-tab-btn.active {
  background: var(--paper, #f1f5f9);
  border-color: var(--line, #cbd5e1);
  color: var(--ink, #0f172a);
}
.ai-tab-panel {
  display: grid;
  gap: 14px;
}
.ai-modal-intro {
  margin: 0;
  color: var(--muted, #64748b);
  font-size: 0.85rem;
  line-height: 1.55;
}
.ai-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.ai-notes-wrapper {
  width: 100%;
  display: grid;
  gap: 6px;
}
.ai-tag-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.toolbar-hint {
  font-size: 0.78rem;
  color: var(--muted, #64748b);
}
.tag-chip {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--line, #cbd5e1);
  background: var(--paper, #f8fafc);
  font-size: 0.76rem;
  cursor: pointer;
  color: var(--ink, #1e293b);
}
.api-key-box,
.curl-box {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 9px;
  background: var(--paper, #f8fafc);
  border: 1px solid var(--line, #e2e8f0);
}
.box-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--ink, #1e293b);
}
.key-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.curl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.curl-code {
  margin: 0;
  padding: 10px 12px;
  border-radius: 6px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 0.76rem;
  line-height: 1.45;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
