<template>
  <div class="flex flex-col gap-4" data-ask-thread>
    <template v-for="(m, i) in ask.messages" :key="i">
      <div v-if="m.role === 'user'" class="max-w-[85%] self-end rounded-5 bg-surface-gray-2 px-3.5 py-2 text-base text-ink-gray-9" data-ask-question>{{ m.text }}</div>
      <div v-else class="flex flex-col gap-3" data-ask-answer :data-status="m.status">
        <div v-if="m.status === 'Error'"><Alert theme="red" :title="m.error || 'The answer could not be written.'" /></div>
        <template v-else>
          <Md v-if="m.text" :text="m.text" :cites="m.cited || []" @cite="(n) => openCite(m, n)" />
          <div v-if="m.status === 'Working'" class="flex items-center gap-2 text-sm text-ink-gray-6" aria-live="polite" data-ask-working>
            <LoadingIndicator class="size-3.5" />{{ m.text ? 'Writing…' : 'Reading your records…' }}</div>
          <div v-if="m.actions && m.actions.length" class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5" data-ask-actions>
            <div class="text-sm text-ink-gray-6">Suggested</div>
            <div class="flex flex-wrap gap-2" :class="phone && 'flex-col'">
              <Button v-for="(a, j) in m.actions" :key="j" class="!h-auto min-h-8 min-w-0 max-w-full !whitespace-normal py-1.5 text-left [&_.truncate]:!whitespace-normal" :size="phone ? 'lg' : 'md'" :variant="j === 0 ? 'solid' : 'subtle'" :label="a.done ? a.label + ' · done' : a.label"
                :disabled="a.done || !canWrite()" :data-ask-action="a.kind" @click="runAction(m, j)" />
            </div>
          </div>
          <div v-if="m.cited && m.cited.length" class="text-sm text-ink-gray-6" data-ask-sources>Sources:
            <template v-for="(c, j) in m.cited" :key="c.n"><span v-if="j"> · </span><a href="#" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :data-ask-cite="c.n"
              @click.prevent="openCite(m, c.n)">{{ c.n }} {{ c.title }}</a></template>
          </div>
        </template>
      </div>
    </template>
    <Alert v-if="ask.refusal" :theme="ask.refusal.error === 'cap' ? 'amber' : 'gray'" :title="ask.refusal.error_text" data-ask-refusal :data-refusal="ask.refusal.error">
      <template v-if="ask.refusal.error === 'not_set_up'">An administrator adds the Anthropic API key in Settings, Admin, AI.
        <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'ai' } }" @click="ask.open = false">Open the setting</RouterLink></template>
      <template v-else-if="ask.refusal.error === 'cap'">{{ ask.refusal.spend?.text }}. The cap is in
        <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'ai' } }" @click="ask.open = false">Settings, Admin, AI</RouterLink>.</template>
      <template v-else-if="ask.refusal.error === 'off'">The owner can turn it on in Settings, Admin, AI.</template>
    </Alert>
  </div>
</template>
<script setup>
// One Ask thread: questions on the right, answers with numbered citations, the suggested actions and the sources.
// Clicking a citation opens the record in the pane; a suggested action changes nothing until it is clicked.
import { useMediaQuery } from '@vueuse/core'
import { Alert, Button, LoadingIndicator } from 'frappe-ui'
import Md from '../Md.vue'
import { canWrite } from '@/lib/store'
import { ask, openCite, runAction } from '@/lib/ask'
const phone = useMediaQuery('(max-width: 767px)')
</script>
