<template>
  <div class="flex flex-col" data-md-field>
    <div v-if="!readonly" class="mb-1 text-right text-sm text-ink-gray-6" data-save-state aria-live="polite">{{ state }}</div>
    <LiveEditor v-model="text" compact :space="space" :links="links" :readonly="readonly" :doctype="doctype" :docname="docname" :images="images"
      :label="label" :placeholder="placeholder" @update:model-value="queue" @blur="flush" />
  </div>
</template>
<script setup>
// A Markdown field that saves by itself: the transcript of a journal page or an inbox item. It is the same editor as notes
// (formatted as you type, no Edit or Done) and calls `save(text)` a moment after typing stops and when it loses focus.
import { onBeforeUnmount, ref, watch } from 'vue'
import LiveEditor from './LiveEditor.vue'

const props = defineProps({ modelValue: String, save: { type: Function, required: true }, space: String, links: { type: Array, default: () => [] },
  doctype: String, docname: String, images: { type: Boolean, default: false }, readonly: Boolean, label: { type: String, default: 'Text' },
  placeholder: { type: String, default: 'Type here.' } })
const emit = defineEmits(['update:modelValue'])
const text = ref(props.modelValue || '')
const state = ref('Saved')
let timer = null
let dirty = false
watch(() => props.modelValue, (v) => { if (!dirty && (v || '') !== text.value) text.value = v || '' })
function queue() {
  dirty = true
  state.value = 'Typing…'
  clearTimeout(timer)
  timer = setTimeout(flush, 1500)
}
async function flush() {
  clearTimeout(timer)
  if (!dirty) return
  dirty = false
  state.value = 'Saving…'
  const value = text.value
  try {
    await props.save(value)
    emit('update:modelValue', value)
    state.value = 'Saved'
  } catch (e) {
    dirty = true
    state.value = 'Not saved'
  }
}
onBeforeUnmount(flush)
</script>
