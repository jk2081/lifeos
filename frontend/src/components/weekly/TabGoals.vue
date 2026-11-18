<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-goals>
    <div class="page-body"><h2 class="text-xl-semibold text-ink-gray-9">Where your goals stand, and next week</h2></div>
    <ReviewFooter back label="Next: Reflect" disabled line="" @back="emit('go', 'tasks')" />
  </div>
</template>
<script setup>
import ReviewFooter from './ReviewFooter.vue'
const emit = defineEmits(['go'])
</script>
