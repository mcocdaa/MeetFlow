<script setup lang="ts">
import { X } from '@lucide/vue'
import { NButton, NIcon, NModal } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from '../i18n'

const { tr } = useI18n()

const props = defineProps<{ localMarkdown: string; serverMarkdown: string; actualVersion: number }>()
const emit = defineEmits<{ close: []; reload: []; overwrite: [version: number] }>()
const copied = ref(false)

async function copyLocal() {
  await navigator.clipboard?.writeText(props.localMarkdown)
  copied.value = true
}
</script>

<template>
  <NModal
    :show="true"
    preset="card"
    :title="tr('内容已被其他成员更新', 'Content Updated by Another Member')"
    :mask-closable="false"
    :auto-focus="false"
    :closable="false"
    class="conflict-modal"
    style="width: min(900px, 100%)"
    @update:show="emit('close')"
  >
    <template #header-extra>
      <NButton quaternary :aria-label="tr('关闭', 'Close')" @click="emit('close')">
        <template #icon><NIcon><X /></NIcon></template>
      </NButton>
    </template>
    <p>{{ tr('你的草稿仍然保留。比较两个版本后，再明确选择载入服务器内容或覆盖。', 'Your draft is preserved. Compare the two versions before choosing whether to load the server version or overwrite it.') }}</p>
    <div class="conflict-columns"><article><h3>{{ tr('本地草稿', 'Local Draft') }}</h3><pre>{{ localMarkdown }}</pre></article><article><h3>{{ tr('服务器版本', 'Server Version') }}</h3><pre>{{ serverMarkdown }}</pre></article></div>
    <footer><NButton quaternary @click="copyLocal">{{ copied ? tr('已复制', 'Copied') : tr('复制本地草稿', 'Copy Local Draft') }}</NButton><span class="grow"></span><NButton quaternary @click="emit('reload')">{{ tr('载入服务器版本', 'Load Server Version') }}</NButton><NButton type="error" @click="emit('overwrite', actualVersion)">{{ tr('用本地草稿覆盖', 'Overwrite with Local Draft') }}</NButton></footer>
  </NModal>
</template>
