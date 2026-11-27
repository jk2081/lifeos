<template>
  <!-- issue 102: why the Brain is off, until a call works again -->
  <div v-if="ladder.brain_off" class="mt-3 rounded-5 border border-outline-amber-1 bg-surface-amber-1 p-3 text-sm text-ink-gray-9" data-setup-brain-off>
    The Brain is off: {{ ladder.brain_off }}
    <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/settings', query: { tab: 'advanced' } }" @click="emit('go')">Settings › AI</RouterLink>
  </div>
  <!-- "Your setup · level n of 7" (issue 26): the next step and a link to How it works; gone after level 7 or when dismissed -->
  <div v-if="ladder.loaded && !ladder.complete && !ladder.dismissed" class="mt-3 rounded-5 border border-outline-gray-2 bg-surface-gray-1 p-3" data-setup-card>
    <div class="flex items-start justify-between gap-1">
      <div class="text-sm-medium text-ink-gray-9" data-setup-level>Your setup · level {{ ladder.level }} of {{ ladder.of }}</div>
      <Button class="-mr-1 -mt-1" variant="ghost" size="xs" icon="lucide-x" label="Dismiss your setup card" data-setup-dismiss @click="dismissLadder()" />
    </div>
    <div class="mt-1 flex gap-1" aria-hidden="true"><span v-for="n in ladder.of" :key="n" class="h-1 flex-1 rounded-full" :class="n <= ladder.level ? 'bg-surface-gray-7' : 'bg-surface-gray-3'" /></div>
    <p class="mt-2 text-sm text-ink-gray-7" data-setup-next>{{ ladder.next?.text }}</p>
    <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm">
      <RouterLink v-if="ladder.next" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="ladder.next.to" data-setup-step @click="emit('go')">Go</RouterLink>
      <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring" to="/how-it-works" data-setup-how @click="emit('go')">How it works</RouterLink>
    </div>
  </div>
</template>
<script setup>
import { Button } from 'frappe-ui'
import { ladder, dismissLadder } from '@/lib/ladder'

const emit = defineEmits(['go'])
</script>
