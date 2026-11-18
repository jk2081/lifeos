<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-reflect>
    <div class="page-body"><h2 class="text-xl-semibold text-ink-gray-9">What did you learn this week?</h2></div>
    <ReviewFooter back label="Lock the week" disabled line="" @back="emit('go', 'goals')" />
  </div>
</template>
<script setup>
import ReviewFooter from './ReviewFooter.vue'
const emit = defineEmits(['go'])
</script>
