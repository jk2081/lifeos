<template>
  <!-- desktop: a 480 px panel from the right, over the screen, which keeps its state underneath -->
  <Transition v-if="!phone" enter-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none" leave-active-class="transition-transform duration-200 ease-out motion-reduce:transition-none"
    enter-from-class="translate-x-full" leave-to-class="translate-x-full">
    <aside v-if="ask.open" class="fixed inset-y-0 right-0 z-50 flex w-[min(480px,100vw)] flex-col border-l border-outline-gray-2 bg-surface-base shadow-2xl" role="dialog"
      aria-label="Ask" data-ask-panel>
      <header class="flex flex-none items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h2 class="flex-1 text-lg-semibold text-ink-gray-9">Ask</h2>
        <Button variant="ghost" label="Expand" data-ask-expand @click="expand" />
        <Button icon="lucide-x" label="Close" tooltip="Close" data-ask-close @click="ask.open = false" />
      </header>
      <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <AskThread />
        <div v-if="!ask.messages.length && !ask.refusal" class="text-base text-ink-gray-6">Ask about your own records. Answers cite where they came from, and nothing changes until you click.</div>
      </div>
      <div class="flex-none px-4 pb-4"><AskComposer ref="composer" /></div>
    </aside>
  </Transition>
  <!-- phone: a bottom sheet -->
  <BottomSheet v-else :open="ask.open" @update:open="(v) => (ask.open = v)">
    <div class="flex h-[82dvh] flex-col" role="group" aria-label="Ask" data-ask-panel data-ask-sheet>
      <header class="flex flex-none items-center gap-2 px-4 pb-2">
        <h2 class="flex-1 text-lg-semibold text-ink-gray-9">Ask</h2>
        <Button variant="ghost" label="Full screen" data-ask-expand @click="expand" />
      </header>
      <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-4 py-2"><AskThread /></div>
      <div class="flex-none px-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"><AskComposer ref="composer" /></div>
    </div>
  </BottomSheet>
</template>
<script setup>
// Ask from any screen: the answer opens over the current screen. Expand opens the thread on the Ask page.
import { nextTick, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { BottomSheet, Button } from 'frappe-ui'
import AskThread from './AskThread.vue'
import AskComposer from './AskComposer.vue'
import { ask } from '@/lib/ask'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const scroller = ref(null)
const composer = ref(null)
function expand() {
  ask.open = false
  router.push({ path: '/ask', query: ask.thread ? { thread: ask.thread } : {} })
}
watch(() => ask.open, async (v) => { if (v) { await nextTick(); composer.value?.focus() } })
// keep the newest text in view while it is written
watch(() => [ask.messages.length, ask.messages[ask.messages.length - 1]?.text], async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})
</script>
