<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-library>
    <div class="page-body">
      <div><h2 class="text-xl-semibold text-ink-gray-9">What came in, and what it means</h2></div>
    </div>
    <ReviewFooter label="Next: Tasks" line="Nothing blocks you from going on" @next="emit('go', 'tasks')" />
  </div>
</template>
<script setup>
import ReviewFooter from './ReviewFooter.vue'
const emit = defineEmits(['go'])
</script>
