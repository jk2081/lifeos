<template>
  <div class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-base px-3 py-2.5 focus-within:border-outline-gray-4" data-ask-composer>
    <Textarea ref="box" v-model="ask.draft" variant="ghost" class="!px-0" :rows="2" :placeholder="placeholder" aria-label="Your question" data-ask-input
      @keydown.enter.exact.prevent="go" />
    <div class="flex flex-wrap items-center gap-2">
      <Badge v-if="ask.scope" size="lg" theme="blue" data-ask-scope :data-scope-kind="ask.scope.kind">{{ ask.scope.label || 'Everything in this space' }}
        <template v-if="ask.scope.kind !== 'space'" #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" label="Remove the scope: ask about everything in this space"
          data-ask-scope-clear @click="clearScope" /></template></Badge>
      <span class="ml-auto text-sm text-ink-gray-6 max-md:hidden"><KeyboardShortcut combo="Mod+K" /> anywhere</span>
      <Button variant="solid" label="Ask" :loading="ask.busy" :disabled="!ask.draft.trim()" data-ask-send @click="go" />
    </div>
  </div>
</template>
<script setup>
// The question box of the panel, the sheet and the Ask page: the text, the scope chip (removable), and Ask.
import { computed, ref } from 'vue'
import { Badge, Button, KeyboardShortcut, Textarea } from 'frappe-ui'
import { ask, send } from '@/lib/ask'
const props = defineProps({ placeholder: { type: String, default: '' } })
const box = ref(null)
const placeholder = computed(() => props.placeholder || (ask.messages.length ? 'Ask a follow-up…' : 'Ask about anything in Life OS…'))
function go() { send(ask.draft) }
function clearScope() {
  ask.scope = { kind: 'space', label: 'Everything in this space' }
  ask.scopeChanged = true
}
const root = ref(null)
defineExpose({ focus: () => document.querySelector('[data-ask-panel] textarea, [data-ask-page] textarea')?.focus() })
</script>
