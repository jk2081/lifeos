<template>
  <p v-if="ask.channel" class="rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 text-sm text-ink-gray-7" data-ask-readonly>This conversation is on {{ ask.channel }}. You reply there, not here.</p>
  <div v-else class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-base px-3 py-2.5 focus-within:border-outline-gray-4" data-ask-composer>
    <div v-if="ask.scope || ask.files.length" class="flex flex-wrap items-center gap-1.5">
      <!-- where the owner is: the record on the screen. Removing it makes the message about everything -->
      <Badge v-if="ask.scope" size="lg" theme="blue" data-ask-scope :data-scope-kind="ask.scope.kind">{{ ask.scope.label || 'Everything in this space' }}
        <template v-if="ask.scope.kind !== 'space'" #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" label="Remove the scope: chat about everything in this space"
          data-ask-scope-clear @click="clearScope" /></template></Badge>
      <Badge v-for="(f, i) in ask.files" :key="i" size="lg" data-ask-file>{{ f.name }} <span class="text-ink-gray-6">{{ fileSize(f.size) }}</span>
        <template #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove ' + f.name" @click="removeFile(i)" /></template></Badge>
    </div>
    <Textarea ref="box" v-model="ask.draft" variant="ghost" class="!px-0" :rows="2" :placeholder="placeholder" aria-label="Your message" data-ask-input
      @keydown.enter.exact.prevent="go" />
    <div class="flex flex-wrap items-center gap-1">
      <AttachMenu v-if="writable" />
      <MicButton @text="(t) => (ask.draft = (ask.draft ? ask.draft + ' ' : '') + t)" />
      <span class="ml-auto mr-2 text-sm text-ink-gray-6 max-md:hidden"><KeyboardShortcut combo="Mod+K" /> anywhere</span>
      <Button class="ml-auto md:ml-0" variant="solid" label="Send" :loading="ask.busy" :disabled="!ask.draft.trim() && !ask.files.length" data-ask-send @click="go" />
    </div>
  </div>
</template>
<script setup>
// The message box of the panel and the sheet: the chip, what is attached, the text, + and the mic, and Send.
import { computed, ref } from 'vue'
import { Badge, Button, KeyboardShortcut, Textarea } from 'frappe-ui'
import { ask, clearScope, removeFile, send } from '@/lib/ask'
import { canWrite } from '@/lib/store'
import { fileSize } from '@/lib/upload'
import AttachMenu from './AttachMenu.vue'
import MicButton from './MicButton.vue'

const props = defineProps({ placeholder: { type: String, default: '' } })
const box = ref(null)
const writable = computed(() => canWrite())
const placeholder = computed(() => props.placeholder || (ask.messages.length ? 'Write a follow-up…' : 'Ask, or tell Life OS what to do…'))
function go() { send(ask.draft) }
defineExpose({ focus: () => document.querySelector('[data-ask-panel] textarea')?.focus() })
</script>
