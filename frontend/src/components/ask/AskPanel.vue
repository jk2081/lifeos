<template>
  <!-- laptop: a panel on the right that stays open while the owner moves between screens; Expand takes the whole width.
       Docked (the page makes room) only from 1440 px; on a narrower laptop it floats over the page's right side, so the page keeps its width (26 Nov: "when flow opens everything gets squeezed"). -->
  <aside v-if="!phone && ask.open" class="flex h-screen min-w-0 flex-col border-l border-outline-gray-2 bg-surface-base"
    :class="ask.wide ? 'sticky top-0 flex-1' : docked ? 'sticky top-0 w-[420px] shrink-0 xl:w-[460px]' : 'fixed inset-y-0 right-0 z-40 w-[420px] max-w-[90vw] shadow-2xl'"
    role="complementary" aria-label="Chat" data-ask-panel :data-wide="ask.wide ? 1 : 0" :data-docked="docked ? 1 : 0">
    <AskBody />
  </aside>
  <!-- phone: a bottom sheet over the screen, opened from the chat bar -->
  <BottomSheet v-else-if="phone" :open="ask.open" @update:open="(v) => (ask.open = v)">
    <div class="flex h-[82dvh] flex-col" role="group" aria-label="Chat" data-ask-panel data-ask-sheet><AskBody phone /></div>
  </BottomSheet>
  <!-- a file dragged over any screen: drop it to add it to the chat -->
  <div v-if="dragging && !phone" class="pointer-events-none fixed inset-0 z-[60] grid place-items-center bg-surface-gray-3/80" data-ask-drop>
    <div class="rounded-5 border border-dashed border-outline-gray-5 bg-surface-base px-6 py-4 text-lg-semibold text-ink-gray-9 shadow-2xl">Drop to add to the chat</div>
  </div>
</template>
<script setup>
// Chat on every screen (issue 120). It lives in the shell, so it keeps its messages while the owner goes from Today to the Library to a goal.
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { BottomSheet } from 'frappe-ui'
import AskBody from './AskBody.vue'
import { addFiles, ask, followRoute } from '@/lib/ask'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const docked = useMediaQuery('(min-width: 1440px)') // narrower: the panel floats over the page instead of squeezing it
const dragging = ref(false)
// phone: a citation closed the sheet to show its record; closing the record brings the thread back (lib/ask.js openCite)
watch(() => router.currentRoute.value.fullPath, () => {
  const r = router.currentRoute.value
  if (!ask.returnTo || r.query.open) return
  const back = r.path === ask.returnTo
  ask.returnTo = null
  if (back) ask.open = true
})
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
