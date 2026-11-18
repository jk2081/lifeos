<template>
  <Card class="flex min-w-0 flex-col gap-2" :class="p.done && 'border-outline-green-3 !bg-surface-green-1'" data-pile-card :data-pile="pile"
    :data-pile-done="p.done ? 1 : 0" :data-pile-count="p.count">
    <div class="flex items-center gap-2">
      <span class="size-2.5 rounded-full" :class="PILE_TEXT[pile].dot" aria-hidden="true" />
      <h3 class="flex-1 text-base-medium text-ink-gray-9">{{ PILE_TEXT[pile].title }}</h3>
      <span v-if="p.done" class="flex size-5 items-center justify-center rounded-full bg-surface-green-7 text-ink-base" role="img" aria-label="Done">
        <span class="lucide-check size-3.5" aria-hidden="true" /></span>
    </div>
    <div class="flex items-baseline gap-2">
      <span class="text-3xl-semibold tabular-nums text-ink-gray-9" data-pile-n>{{ p.count }}</span>
      <span class="text-sm text-ink-gray-7">{{ p.done ? pileText(pile, pkey, 'done') : pileText(pile, pkey, 'line') }}</span>
    </div>
    <template v-if="p.done">
      <p class="text-sm text-ink-gray-7" data-pile-moved>{{ movedText || 'Done for this review.' }}</p>
      <div class="mt-auto flex gap-1">
        <Button variant="ghost" label="See them" data-pile-see @click="emit('open')" />
        <Button variant="ghost" label="Undo" data-pile-undo @click="emit('undo')" />
      </div>
    </template>
    <template v-else>
      <ul v-if="p.first.length" class="flex flex-col">
        <li v-for="i in p.first" :key="i.ref" class="flex min-w-0 items-center gap-2 border-b border-outline-gray-1 py-1.5 text-sm text-ink-gray-8 last:border-b-0">
          <Badge size="sm" theme="gray" :label="i.source" /><span class="min-w-0 truncate">{{ i.title }}</span></li>
      </ul>
      <p v-else class="text-sm text-ink-gray-6">Nothing here.</p>
      <p v-if="p.count > p.first.length" class="text-sm text-ink-gray-6">+ {{ p.count - p.first.length }} more ·
        <a href="#" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" @click.prevent="emit('open')">see all and change</a></p>
      <Button class="mt-auto w-full" label="Open pile" :disabled="p.empty" data-pile-open @click="emit('open')" />
    </template>
  </Card>
</template>
<script setup>
// One pile on the tab (board 24), and its done state once accepted (board 26).
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { PILE_TEXT, pileText } from '@/lib/review'

const props = defineProps({ pile: String, pkey: String, p: Object })
const emit = defineEmits(['open', 'undo'])
const movedText = computed(() => Object.entries(props.p.moved || {}).map(([to, n]) => `${n} moved to ${PILE_TEXT[to].title}`).join(' · '))
</script>
