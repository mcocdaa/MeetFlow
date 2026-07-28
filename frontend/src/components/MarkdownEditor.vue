<script setup lang="ts">
import { Crepe } from '@milkdown/crepe'
import { replaceAll } from '@milkdown/kit/utils'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'

const props = withDefaults(defineProps<{
  modelValue: string
  disabled?: boolean
  placeholder?: string
  label?: string
  registerEditor?: (writer: ((markdown: string) => void) | null) => void
}>(), { disabled: false, placeholder: '输入 Markdown…', label: 'Markdown 编辑器' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const root = ref<HTMLElement | null>(null)
const failed = ref(false)
let editor: Crepe | null = null
let ready = false
let latestMarkdown = props.modelValue

function applyMarkdown(markdown: string) {
  if (!ready || !editor) return
  latestMarkdown = markdown
  editor.editor.action(replaceAll(markdown))
  emit('update:modelValue', markdown)
}

onMounted(async () => {
  await nextTick()
  if (!root.value) return
  editor = new Crepe({
    root: root.value,
    defaultValue: props.modelValue,
    features: {
      [Crepe.Feature.ImageBlock]: false,
      [Crepe.Feature.Latex]: false,
    },
    featureConfigs: {
      [Crepe.Feature.Placeholder]: { text: props.placeholder, mode: 'block' },
    },
  })
  editor.on((listener) => {
    listener.markdownUpdated((_ctx, markdown) => {
      latestMarkdown = markdown
      emit('update:modelValue', markdown)
    })
  })
  try {
    await editor.create()
    ready = true
    editor.setReadonly(props.disabled)
    props.registerEditor?.(applyMarkdown)
  } catch {
    failed.value = true
  }
})

watch(() => props.disabled, (value) => {
  if (ready) editor?.setReadonly(value)
})

watch(() => props.modelValue, (value) => {
  if (!ready || !editor || value === latestMarkdown) return
  latestMarkdown = value
  editor.editor.action(replaceAll(value))
})

onBeforeUnmount(() => {
  props.registerEditor?.(null)
  ready = false
  void editor?.destroy()
  editor = null
})
</script>

<template>
  <div class="markdown-editor" :data-disabled="disabled || undefined">
    <div ref="root" class="markdown-editor-root markdown-editor-top-aligned" role="textbox" :aria-label="label" :aria-readonly="disabled" />
    <textarea v-if="failed" :value="modelValue" :disabled="disabled" :aria-label="label" rows="8" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" />
  </div>
</template>
