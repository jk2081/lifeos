<template>
  <!-- this week's score, above the week's calendar: the review shows it in full -->
  <div v-if="s" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-base text-ink-gray-8" data-week-score>
    <span class="text-base-medium text-ink-gray-9">Week {{ s.week }} of 12</span>
    <span class="tabular-nums">{{ Math.round(s.percent) }}%</span>
    <div class="w-32"><Progress size="sm" :value="Math.round(s.percent)" /></div>
    <span class="text-sm text-ink-gray-6">{{ s.done }} of {{ s.planned }} ticks · target {{ store.settings.score_target }}%</span>
    <NumLink class="text-sm" :to="{ path: '/plan/12-weeks' }">Open the cycle</NumLink>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Progress } from 'frappe-ui'
import NumLink from '@/components/ui/NumLink.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'

const s = ref(null)
onMounted(async () => {
  try {
    s.value = await api('journal.week_score', { space: store.space })
    if (!s.value.week || s.value.week > 12) s.value = null
  } catch (e) { /* no active cycle: nothing to score */ }
})
</script>
