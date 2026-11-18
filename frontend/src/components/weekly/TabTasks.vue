<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-tasks>
    <div class="page-body !gap-4">
      <div><h2 class="text-xl-semibold text-ink-gray-9">Your commitments</h2></div>
      <PileBoard pkey="tasks" heading="Stuck and waiting, sorted by the assistant" @summary="(v) => (s = v)" />
    </div>
    <ReviewFooter back label="Next: Goals" :disabled="!r.head.done.tasks" :line="line" @back="emit('go', 'library')" @next="emit('go', 'goals')" />
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import PileBoard from './piles/PileBoard.vue'
import ReviewFooter from './ReviewFooter.vue'
import { useReview } from '@/lib/review'
const emit = defineEmits(['go'])
const r = useReview()
const s = ref(null)
const line = computed(() => (r.head.done.tasks ? 'Needs you and the three piles are cleared' : 'Opens when Needs you and the three piles are cleared'))
</script>
