<script setup lang="ts">
import { X } from '@lucide/vue'
import { NButton, NIcon, NModal } from 'naive-ui'
import { ref } from 'vue'

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
    title="内容已被其他成员更新"
    :mask-closable="false"
    :auto-focus="false"
    :closable="false"
    class="conflict-modal"
    style="width: min(900px, 100%)"
    @update:show="emit('close')"
  >
    <template #header-extra>
      <NButton quaternary aria-label="关闭" @click="emit('close')">
        <template #icon><NIcon><X /></NIcon></template>
      </NButton>
    </template>
    <p>你的草稿仍然保留。比较两个版本后，再明确选择载入服务器内容或覆盖。</p>
    <div class="conflict-columns"><article><h3>本地草稿</h3><pre>{{ localMarkdown }}</pre></article><article><h3>服务器版本</h3><pre>{{ serverMarkdown }}</pre></article></div>
    <footer><NButton quaternary @click="copyLocal">{{ copied ? '已复制' : '复制本地草稿' }}</NButton><span class="grow"></span><NButton quaternary @click="emit('reload')">载入服务器版本</NButton><NButton type="error" @click="emit('overwrite', actualVersion)">用本地草稿覆盖</NButton></footer>
  </NModal>
</template>
