<template>
  <div class="flex-none px-4 py-1.5 max-md:w-full md:px-7" data-mode-row>
    <div class="inline-flex rounded-5 border border-outline-gray-2 bg-surface-gray-2 p-0.5 max-md:flex max-md:w-full" role="radiogroup" aria-label="Overview or Calendar" data-mode-switch :data-mode="todayMode">
      <Button v-for="m in MODES" :key="m.value" class="max-md:flex-1" size="sm" :variant="todayMode === m.value ? 'subtle' : 'ghost'" :label="m.label" role="radio" :aria-checked="todayMode === m.value"
        :class="todayMode === m.value && '!bg-surface-white !text-ink-gray-9 shadow-sm'" :data-mode-option="m.value" @click="setMode(m.value)" />
    </div>
  </div>
</template>
<script setup>
// The switch of Today: Overview (the work slice) or Calendar (the time slice), on the right of the Day, Week, Month and Year tabs; under them, full width, on a phone.
import { Button } from 'frappe-ui'
import { setMode, todayMode } from '@/lib/todayMode'

const MODES = [{ value: 'overview', label: 'Overview' }, { value: 'calendar', label: 'Calendar' }]
</script>
