<template>
  <!-- one primary button, and one line saying what is left before it opens (boards 30 and 31) -->
  <div class="sticky bottom-0 z-10 mt-auto flex flex-none items-center gap-3 border-t border-outline-gray-1 bg-surface-base px-4 py-3 md:px-7
    max-md:bottom-[calc(72px+env(safe-area-inset-bottom))]" data-review-footer>
    <Button v-if="back" label="Back" data-review-back @click="emit('back')" />
    <span class="ml-auto min-w-0 text-right text-sm text-ink-gray-6" data-review-footer-line>{{ line }}</span>
    <Button variant="solid" :label="label" :disabled="disabled" :loading="loading" data-review-next @click="emit('next')" />
  </div>
</template>
<script setup>
import { Button } from 'frappe-ui'
defineProps({ label: String, line: String, back: Boolean, disabled: Boolean, loading: Boolean })
const emit = defineEmits(['back', 'next'])
</script>
