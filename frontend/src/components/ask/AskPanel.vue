<template>
  <!-- On a laptop the chat is a layer of the Drawer (ItemView hosts it). On a phone it is a bottom sheet over the screen, opened from the chat bar; a record opened from an answer is
       the next layer, full screen, and Back brings the sheet and its thread back. -->
  <BottomSheet v-if="phone" :open="chatOnTop" @update:open="(v) => !v && popLayer()">
    <div class="flex h-[82dvh] flex-col" role="group" aria-label="Chat" data-ask-panel data-ask-sheet><AskBody phone /></div>
  </BottomSheet>
  <!-- a file dragged over any screen: drop it to add it to the chat -->
  <div v-if="dragging && !phone" class="pointer-events-none fixed inset-0 z-[60] grid place-items-center bg-surface-gray-3/80" data-ask-drop>
    <div class="rounded-5 border border-dashed border-outline-gray-5 bg-surface-base px-6 py-4 text-lg-semibold text-ink-gray-9 shadow-2xl">Drop to add to the chat</div>
  </div>
</template>
<script setup>
// Chat on every screen (issue 120). It lives in the shell, so it keeps its messages while the owner goes from Today to the Library to a goal. The chat layer's thread is in the URL
// (`?open=ask:<thread>`, `ask:new` for a conversation not started): this keeps the two the same, and rebuilds the conversation on a reload.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { BottomSheet } from 'frappe-ui'
import AskBody from './AskBody.vue'
import { addFiles, ask, ensureLoaded, followRoute } from '@/lib/ask'
import { current, popLayer, swapTop } from '@/lib/pane'
import { isPhone as phone } from '@/lib/drawer'

const dragging = ref(false)
const chatOnTop = computed(() => current.value?.type === 'ask')
watch(() => current.value?.ref, (ref) => { if (ref && current.value.type === 'ask') ensureLoaded(current.value.name === 'new' ? '' : current.value.name) }, { immediate: true })
watch(() => ask.thread, (t) => { if (current.value?.type === 'ask' && current.value.name !== (t || 'new')) swapTop(`ask:${t || 'new'}`) })
followRoute()

// files dropped anywhere on the screen (laptop); a drop another part of the page took for itself is left to it
let depth = 0
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files')
const enter = (e) => { if (hasFiles(e)) { depth++; dragging.value = true } }
const over = (e) => { if (hasFiles(e)) e.preventDefault() }
const leave = (e) => { if (hasFiles(e) && --depth <= 0) { depth = 0; dragging.value = false } }
function drop(e) {
  depth = 0
  dragging.value = false
  if (!hasFiles(e) || e.defaultPrevented && e.target.closest?.('[data-dropzone]')) return
  e.preventDefault()
  addFiles([...e.dataTransfer.files])
}
onMounted(() => { for (const [n, f] of [['dragenter', enter], ['dragover', over], ['dragleave', leave], ['drop', drop]]) window.addEventListener(n, f) })
onUnmounted(() => { for (const [n, f] of [['dragenter', enter], ['dragover', over], ['dragleave', leave], ['drop', drop]]) window.removeEventListener(n, f) })
</script>
