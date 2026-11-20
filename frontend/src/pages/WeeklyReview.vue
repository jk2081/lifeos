<template>
  <ReviewPage />
</template>
<script setup>
// Review (issue 14): the weekly review as a place of its own. It joins the sidebar after the first locked review, or on
// the review's day; the review itself is set 8's, the same as Today > Week on the review's day.
import ReviewPage from '@/components/weekly/ReviewPage.vue'
</script>
