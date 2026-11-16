<template>
  <!-- pill: one pill per habit with its full name and a tick when done (Today). box: a letter box per habit (the default). -->
  <component :is="bare ? 'div' : Card" v-if="variant === 'pill'" class="flex flex-wrap gap-2" data-habit-pills>
    <Button v-for="h in habits" :key="h.habit" class="!h-11 max-w-full !px-3 !text-base" size="md" :variant="h.done ? 'subtle' : 'outline'" :theme="h.done ? 'blue' : 'gray'"
      :icon-left="h.done ? 'lucide-circle-check' : 'lucide-circle'" :aria-label="`${h.title}, ${h.done ? 'done' : 'not done'}`" :aria-pressed="h.done"
      data-habit @click="$emit('toggle', h)"><span class="truncate" :class="h.done && 'text-ink-blue-9'">{{ h.title }}</span></Button>
  </component>
  <component :is="bare ? 'div' : Card" v-else class="grid gap-2 text-center" :style="`grid-template-columns: repeat(${Math.min(Math.max(habits.length, 4), 6)}, minmax(0, 1fr))`">
    <div v-for="h in habits" :key="h.habit" class="min-w-0">
      <Button class="!size-11 !text-lg-semibold md:!size-11" size="lg" :variant="h.done ? 'solid' : 'outline'" :label="h.title.slice(0, 1).toUpperCase()"
        :aria-label="`${h.title}, ${h.done ? 'done' : 'not done'}`" :aria-pressed="h.done" data-habit @click="$emit('toggle', h)" />
      <div class="mt-1 truncate text-sm text-ink-gray-6">{{ h.title }}</div>
    </div>
  </component>
</template>
<script setup>
// Today's habits: tap to tick, tap again to untick. Each is a frappe-ui Button at its largest size (44 px high).
import { Button } from 'frappe-ui'
import Card from './ui/Card.vue'
defineProps({ habits: Array, bare: Boolean, variant: { type: String, default: 'box' } })
defineEmits(['toggle'])
</script>
