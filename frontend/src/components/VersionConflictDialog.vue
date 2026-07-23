<script setup lang="ts">
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
  <div class="dialog-backdrop" role="presentation">
    <section class="conflict-dialog" role="dialog" aria-modal="true" aria-labelledby="conflict-title">
      <header><div><p class="eyebrow">Version conflict</p><h2 id="conflict-title">内容已被其他成员更新</h2></div><button class="icon-button" aria-label="关闭" @click="emit('close')">×</button></header>
      <p>你的草稿仍然保留。比较两个版本后，再明确选择载入服务器内容或覆盖。</p>
      <div class="conflict-columns"><article><h3>本地草稿</h3><pre>{{ localMarkdown }}</pre></article><article><h3>服务器版本</h3><pre>{{ serverMarkdown }}</pre></article></div>
      <footer><button class="button button-quiet" @click="copyLocal">{{ copied ? '已复制' : '复制本地草稿' }}</button><span class="grow"></span><button class="button button-quiet" @click="emit('reload')">载入服务器版本</button><button class="button button-danger" @click="emit('overwrite', actualVersion)">用本地草稿覆盖</button></footer>
    </section>
  </div>
</template>
