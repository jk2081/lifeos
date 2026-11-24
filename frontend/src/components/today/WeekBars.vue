<template>
  <div v-if="bars.length" class="grid grid-cols-1 gap-x-2 gap-y-1 md:grid-cols-7" data-week-bars>
    <div v-for="b in bars" :key="itemRef(b.it)" class="relative min-w-0 cursor-pointer rounded px-1.5 py-1 text-sm md:[grid-column:var(--cols)] md:[grid-row:var(--row)]"
      :class="chipClass(b.it)" :style="{ '--cols': `${b.from} / ${b.to}`, '--row': b.row }" data-week-bar :data-ref="itemRef(b.it)">
      <button type="button" class="absolute inset-0 rounded focus-visible:focus-ring" :aria-label="`${itemLabel(b.it)}, ${dayRange(b.it.date, b.it.end_date)}`" @click="openRef(itemRef(b.it))" />
      <span class="block truncate">{{ itemLabel(b.it) }}</span>
    </div>
  </div>
</template>
<script setup>
// All-day events of more than one day, one bar across their days in a strip above the days (issue 99).
import { computed } from 'vue'
import { chipClass, itemLabel, itemRef, weekBars } from '@/lib/calRange'
import { openRef } from '@/lib/pane'
import { dayRange } from '@/lib/dates'

const props = defineProps({ days: Array, items: Array })
const bars = computed(() => weekBars(props.days, props.items))
</script>
