<template>
  <component :is="bare ? 'div' : Card" class="grid gap-2 text-center" :style="`grid-template-columns: repeat(${Math.min(Math.max(habits.length, 4), 6)}, minmax(0, 1fr))`">
    <div v-for="h in habits" :key="h.habit" class="min-w-0">
      <Button class="!size-11 !text-lg-semibold md:!size-11" size="lg" :variant="h.done ? 'solid' : 'outline'" :label="h.title.slice(0, 1).toUpperCase()"
        :aria-label="`${h.title}, ${h.done ? 'done' : 'not done'}`" :aria-pressed="h.done" data-habit @click="$emit('toggle', h)" />
      <div class="mt-1 truncate text-sm text-ink-gray-6">{{ h.title }}</div>
    </div>
  </component>
</template>
<script setup>
// Today's habits as one box each: tap to tick, tap again to untick. A box is a frappe-ui Button at its largest size.
import { Button } from 'frappe-ui'
import Card from './ui/Card.vue'
defineProps({ habits: Array, bare: Boolean })
defineEmits(['toggle'])
</script>
