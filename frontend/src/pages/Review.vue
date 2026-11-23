<template>
  <ReviewBody :id="id" page />
</template>
<script setup>
// The review screen as a full page, for deep work. It is reached with Open full page from the pane.
import ReviewBody from '@/components/review/InboxReview.vue'

defineProps({ id: String })
</script>
