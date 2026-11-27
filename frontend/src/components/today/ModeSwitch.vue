<template>
  <div class="flex-none px-4 py-1.5 max-md:w-full md:px-7" data-mode-row>
    <div class="inline-flex rounded-5 border border-outline-gray-2 bg-surface-gray-2 p-0.5 max-md:flex max-md:w-full" role="radiogroup" aria-label="Overview, Goals or Calendar" data-mode-switch :data-mode="todayMode">
      <Button v-for="m in shown" :key="m.value" class="max-md:flex-1" size="sm" :variant="todayMode === m.value ? 'subtle' : 'ghost'" :label="m.label" role="radio" :aria-checked="todayMode === m.value"
        :class="todayMode === m.value && '!bg-surface-white !text-ink-gray-9 shadow-sm'" :data-mode-option="m.value" @click="setMode(m.value)" />
    </div>
  </div>
</template>
<script setup>
// The switch of Today: Overview (real work), Goals (planning; only once a goal exists) or Calendar (the time slice), on the right of the Day, Week, Month and Year tabs; under them, full width, on a phone.
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { setMode, todayMode, todayModes } from '@/lib/todayMode'

const LABELS = { overview: 'Overview', goals: 'Goals', calendar: 'Calendar' }
const shown = computed(() => todayModes.value.map((value) => ({ value, label: LABELS[value] })))
</script>
