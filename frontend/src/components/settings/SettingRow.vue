<template>
  <!-- One setting: label and one line of help on the left, the control on the right; stacked on a phone. -->
  <div class="flex items-start gap-4 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 max-md:flex-col max-md:gap-2" data-setting-row>
    <div class="min-w-0 flex-1">
      <div class="text-base-medium text-ink-gray-9">{{ label }}</div>
      <div v-if="help" class="text-sm text-ink-gray-6">{{ help }}</div>
    </div>
    <div class="flex shrink-0 flex-col items-end gap-1 max-md:items-start">
      <slot />
      <ErrorMessage v-if="error" :message="error" data-setting-error />
    </div>
  </div>
</template>
<script setup>
import { ErrorMessage } from 'frappe-ui'
defineProps({ label: String, help: String, error: String })
</script>
