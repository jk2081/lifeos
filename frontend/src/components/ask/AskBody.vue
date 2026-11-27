<template>
  <header class="flex flex-none items-center gap-1 border-b border-outline-gray-1 px-4 py-3">
    <Button v-if="stack.length > 1" variant="ghost" icon-left="lucide-arrow-left" label="Back" data-pane-back @click="popLayer" />
    <h2 class="min-w-0 flex-1 truncate text-lg-semibold text-ink-gray-9">{{ ask.view === 'history' ? 'History' : 'Chat' }}</h2>
    <Button v-if="ask.view === 'chat'" variant="ghost" icon-left="lucide-history" label="History" data-ask-history-open @click="ask.view = 'history'" />
    <Button v-else variant="ghost" icon-left="lucide-message-square" label="Back to chat" data-ask-history-close @click="ask.view = 'chat'" />
    <Button variant="ghost" icon="lucide-square-pen" label="New chat" tooltip="New chat" data-ask-new @click="newChat" />
    <Button v-if="!phone" variant="ghost" :label="drawer.wide ? 'Collapse' : 'Expand'" data-ask-expand @click="drawer.wide = !drawer.wide" />
    <Button icon="lucide-x" label="Close" tooltip="Close" variant="ghost" data-ask-close @click="closePane" />
  </header>
  <AskHistory v-if="ask.view === 'history'" class="min-h-0 flex-1 overflow-y-auto" />
  <template v-else>
    <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-4 py-4" :class="drawer.wide && !phone && 'mx-auto w-full max-w-3xl'">
      <h3 v-if="ask.channel" class="mb-3 text-base-medium text-ink-gray-9" data-ask-channel-title>{{ ask.title }}</h3>
      <AskThread />
      <div v-if="!ask.messages.length && !ask.refusal" class="text-base text-ink-gray-6" data-ask-empty>Ask about your own records, tell Life OS what to do, or drop a file here. Answers cite where they came from, and what Chat does is listed with Change.</div>
    </div>
    <div class="flex-none px-4 pb-4" :class="[phone && 'pb-[calc(1rem+env(safe-area-inset-bottom))]', drawer.wide && !phone && 'mx-auto w-full max-w-3xl']"><AskComposer ref="composer" /></div>
  </template>
</template>
<script setup>
// What the chat shows, on the laptop panel and the phone sheet: the header, then the conversation or History, then the message box.
import { nextTick, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import AskThread from './AskThread.vue'
import AskComposer from './AskComposer.vue'
import AskHistory from './AskHistory.vue'
import { ask, newChat } from '@/lib/ask'
import { drawer } from '@/lib/drawer'
import { closePane, popLayer, stack } from '@/lib/pane'

defineProps({ phone: { type: Boolean, default: false } })
const scroller = ref(null)
const composer = ref(null)
watch(() => ask.open, async (v) => { if (v) { await nextTick(); composer.value?.focus() } }, { immediate: true })
// keep the newest text in view while it is written
watch(() => [ask.messages.length, ask.messages[ask.messages.length - 1]?.text, ask.view], async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})
</script>
