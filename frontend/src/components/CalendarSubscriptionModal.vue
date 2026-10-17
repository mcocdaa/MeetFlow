<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NInput, NModal, useMessage } from 'naive-ui'
import { api } from '../api/client'
import { useI18n } from '../i18n'
import { errorMessage } from '../utils/errors'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const { tr } = useI18n()

const loading = ref(false)
const error = ref('')
const feedUrl = ref('')
const copied = ref(false)
const message = useMessage()

async function loadFeedUrl() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<{ feed_url: string; full_feed_url: string }>('/api/calendar/feed-url')
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    feedUrl.value = data.full_feed_url || `${origin}${data.feed_url}`
  } catch (caught) {
    error.value = errorMessage(caught, tr('日历订阅链接获取失败', 'Failed to load calendar feed URL'))
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (val) => {
  if (val && !feedUrl.value) {
    void loadFeedUrl()
  }
}, { immediate: true })

async function copyUrl() {
  if (!feedUrl.value) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(feedUrl.value)
    } else {
      const input = document.createElement('input')
      input.value = feedUrl.value
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    copied.value = true
    message.success(tr('订阅链接已复制到剪贴板', 'Subscription URL copied to clipboard'))
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    message.warning(tr('复制失败，请手动选择复制', 'Copy failed, please select and copy manually'))
  }
}
</script>

<template>
  <n-modal :show="props.show" preset="card" :title="tr('订阅个人日程与待办 (iCal)', 'Subscribe to Personal Calendar & Tasks (iCal)')" style="width: min(580px, 94vw);" :mask-closable="true" @update:show="(val: boolean) => emit('update:show', val)">
    <div class="calendar-modal-content">
      <p class="calendar-modal-desc">
        {{ tr('通过标准 RFC 5545 iCalendar 订阅源，自动将您负责的待办行动项与参会日程单向同步至个人日历工具（支持 Apple 日历、Google Calendar、Outlook 等）。', 'Sync your assigned action items and meeting schedule to your personal calendar via a standard RFC 5545 iCalendar feed (Apple Calendar, Google Calendar, Outlook).') }}
      </p>

      <div v-if="loading" class="calendar-loading">{{ tr('正在生成专属订阅令牌…', 'Generating private subscription token…') }}</div>
      <div v-else-if="error" class="notice notice-error">{{ error }}</div>
      <div v-else class="calendar-feed-box">
        <label class="feed-label">{{ tr('您的私有订阅链接（请勿泄露）：', 'Your private feed URL (do not share):') }}</label>
        <div class="feed-input-group">
          <n-input :value="feedUrl" readonly :input-props="{ 'aria-label': tr('日历订阅链接', 'Calendar subscription URL') }" :placeholder="tr('订阅链接', 'Subscription URL')" />
          <n-button type="primary" :disabled="!feedUrl" @click="copyUrl">
            {{ copied ? tr('已复制', 'Copied') : tr('复制链接', 'Copy URL') }}
          </n-button>
        </div>
      </div>

      <div class="calendar-guide-section">
        <h4>{{ tr('快速配置指南', 'Quick Setup Guide') }}</h4>
        <div class="guide-item">
          <strong>🍎 {{ tr('Apple 日历 (Mac / iOS)', 'Apple Calendar (Mac / iOS)') }}</strong>
          <span>{{ tr('文件 ➔ 新建日历订阅 ➔ 粘贴上方链接 ➔ 自动刷新建议选择“每小时”。', 'File ➔ New Calendar Subscription ➔ Paste URL ➔ Set Auto-refresh to Every Hour.') }}</span>
        </div>
        <div class="guide-item">
          <strong>📅 Google Calendar</strong>
          <span>{{ tr('其他日历旁点击 “+” ➔ 通过网址添加 ➔ 粘贴链接 ➔ 添加日历。', 'Click "+" next to Other calendars ➔ From URL ➔ Paste URL ➔ Add calendar.') }}</span>
        </div>
        <div class="guide-item">
          <strong>📧 Microsoft Outlook</strong>
          <span>{{ tr('添加日历 ➔ 从 Web 订阅 ➔ 粘贴链接并保存。', 'Add calendar ➔ Subscribe from web ➔ Paste URL and save.') }}</span>
        </div>
      </div>
    </div>
    <template #footer>
      <div class="row-actions">
        <n-button quaternary @click="emit('update:show', false)">{{ tr('关闭', 'Close') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.calendar-modal-content {
  display: grid;
  gap: 16px;
}
.calendar-modal-desc {
  margin: 0;
  color: var(--ink);
  font-size: 0.88rem;
  line-height: 1.6;
}
.calendar-feed-box {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 10px;
  background: var(--paper, #fafbfc);
  border: 1px solid var(--line, #e2e8f0);
}
.feed-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--muted, #64748b);
}
.feed-input-group {
  display: flex;
  gap: 8px;
  align-items: center;
}
.calendar-guide-section {
  display: grid;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--line, #e2e8f0);
}
.calendar-guide-section h4 {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 750;
  color: var(--ink);
}
.guide-item {
  display: grid;
  gap: 3px;
  font-size: 0.8rem;
  color: var(--muted, #64748b);
}
.guide-item strong {
  color: var(--ink);
}
.calendar-loading {
  padding: 16px;
  text-align: center;
  color: var(--muted);
  font-size: 0.86rem;
}
</style>
