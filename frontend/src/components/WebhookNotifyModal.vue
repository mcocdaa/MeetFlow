<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NRadio, NRadioGroup, useMessage } from 'naive-ui'
import { api } from '../api/client'
import type { Meeting } from '../domain/meetings'
import { errorMessage } from '../utils/errors'

const props = defineProps<{
  show: boolean
  meeting: Meeting
}>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const platform = ref<'feishu' | 'dingtalk' | 'generic'>('feishu')
const webhookUrl = ref('')
const secret = ref('')
const sending = ref(false)
const error = ref('')
const message = useMessage()

async function sendNotification() {
  if (!webhookUrl.value.trim() || sending.value) return
  sending.value = true
  error.value = ''
  try {
    await api<{ status: string }>(`/api/meetings/${props.meeting.id}/webhook-notify`, {
      method: 'POST',
      body: JSON.stringify({
        platform: platform.value,
        webhook_url: webhookUrl.value.trim(),
        secret: secret.value.trim() || undefined,
      }),
    })
    message.success('会议纪要已成功推送至群聊卡片！')
    emit('update:show', false)
  } catch (caught) {
    error.value = errorMessage(caught, '推送失败，请检查 Webhook 地址与签名配置')
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <n-modal :show="props.show" preset="card" title="推送会议通知卡片" style="width: min(540px, 94vw);" :mask-closable="!sending" @update:show="(val: boolean) => emit('update:show', val)">
    <div class="webhook-modal-content">
      <p class="webhook-intro">
        将当前会议结论、决议与待办一键格式化为富文本卡片，推送到指定企业即时通讯群组机器人。
      </p>

      <n-form label-placement="top" :show-require-mark="false">
        <n-form-item label="目标平台">
          <n-radio-group v-model:value="platform">
            <n-radio value="feishu">飞书 (交互式卡片)</n-radio>
            <n-radio value="dingtalk">钉钉 (Markdown卡片)</n-radio>
            <n-radio value="generic">通用 Webhook</n-radio>
          </n-radio-group>
        </n-form-item>

        <n-form-item label="Webhook 机器人地址" required>
          <n-input
            v-model:value="webhookUrl"
            :placeholder="platform === 'feishu' ? 'https://open.feishu.cn/open-apis/bot/v2/hook/...' : 'https://oapi.dingtalk.com/robot/send?access_token=...'"
            :input-props="{ 'aria-label': 'Webhook 地址' }"
          />
        </n-form-item>

        <n-form-item :label="platform === 'dingtalk' ? '安全加签 Secret (推荐配置)' : '加签密钥 (可选)'">
          <n-input
            v-model:value="secret"
            type="password"
            show-password-on="click"
            placeholder="SEC..."
            :input-props="{ 'aria-label': '加签密钥' }"
          />
        </n-form-item>
      </n-form>

      <div class="card-preview-box">
        <span class="preview-tag">推送内容预览</span>
        <div class="preview-title">📋 会议纪要：{{ meeting.title }}</div>
        <div class="preview-meta">
          <span>状态：{{ meeting.status === 'completed' ? '已完成' : '进行中' }}</span> ·
          <span>议题数：{{ meeting.agenda_items.length }}</span>
        </div>
      </div>

      <p v-if="error" class="notice notice-error">{{ error }}</p>
    </div>

    <template #footer>
      <div class="row-actions">
        <n-button quaternary :disabled="sending" @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="sending" :disabled="!webhookUrl.trim() || sending" @click="sendNotification">
          立即推送
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.webhook-modal-content {
  display: grid;
  gap: 16px;
}
.webhook-intro {
  margin: 0;
  color: var(--muted, #64748b);
  font-size: 0.86rem;
  line-height: 1.5;
}
.card-preview-box {
  padding: 12px 14px;
  border-radius: 9px;
  background: var(--paper, #fafbfc);
  border: 1px solid var(--line, #e2e8f0);
  display: grid;
  gap: 4px;
}
.preview-tag {
  font-size: 0.72rem;
  font-weight: 750;
  color: var(--green, #0b6a58);
  text-transform: uppercase;
}
.preview-title {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--ink, #1e293b);
}
.preview-meta {
  font-size: 0.78rem;
  color: var(--muted, #64748b);
}
</style>
