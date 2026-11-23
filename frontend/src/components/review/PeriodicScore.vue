<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-score>
    <div class="page-body !gap-4">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">{{ d ? d.title : 'The cycle' }}: the score</h2>
        <p class="text-sm text-ink-gray-6">Read only. Twelve weeks of ticks, and where each goal ended.</p>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <div v-else class="grid items-start gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card class="flex min-w-0 flex-col gap-3" data-score-weeks>
          <div class="flex flex-wrap items-baseline gap-x-3">
            <span class="text-3xl-semibold tabular-nums text-ink-gray-9" data-score-average>{{ Math.round(d.average) }}%</span>
            <span class="text-sm text-ink-gray-7">average against a target of {{ d.target }}%</span>
          </div>
          <Progress size="sm" :value="Math.min(100, d.average)" :aria-label="`Average ${Math.round(d.average)}% against ${d.target}%`" />
          <ol class="flex items-end gap-1.5 md:gap-2" aria-label="Weekly scores">
            <li v-for="w in d.weeks" :key="w.week" class="flex min-w-0 flex-1 flex-col items-center gap-1" data-score-week :data-score="Math.round(w.percent)">
              <span class="text-xs tabular-nums text-ink-gray-6">{{ Math.round(w.percent) }}</span>
              <div class="flex h-20 w-full items-end"><div class="w-full rounded-4 bg-surface-gray-9" :style="{ height: Math.max(w.percent, 6) + '%' }" /></div>
              <span class="text-xs text-ink-gray-6">W{{ w.week }}</span>
            </li>
          </ol>
        </Card>
        <Card class="flex min-w-0 flex-col" data-score-goals>
          <h3 class="pb-1 text-base-medium text-ink-gray-9">Each goal's result</h3>
          <div v-for="g in d.goals" :key="g.name" class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 py-2 last:border-b-0" data-score-goal>
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ g.title }}</span>
            <span class="text-sm text-ink-gray-7">{{ g.result.label }}</span>
            <Badge v-if="g.result.kind === 'number' || g.result.kind === 'cycle'" :theme="g.result.reached ? 'green' : 'gray'" :label="Math.round(g.percent) + '% of ticks'" />
          </div>
          <p v-if="!d.goals.length" class="text-sm text-ink-gray-6">No goals in this cycle.</p>
        </Card>
      </div>
    </div>
    <ReviewFooter label="Next: Each goal" :line="`About ${r.head?.tab_minutes?.score || 8} minutes`" @next="emit('go', 'goals')" />
  </div>
</template>
<script setup>
// 12-week review, tab 1: the twelve weekly scores, the average against the target, and each goal's result.
import { onMounted, ref } from 'vue'
import { Badge, Progress, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'

const emit = defineEmits(['go'])
const r = useReview()
const d = ref(null)
onMounted(async () => { d.value = await r.read('look') })
</script>
