<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-look>
    <div class="page-body !gap-4">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">{{ d ? d.title : 'The month' }}, looked back on</h2>
        <p class="text-sm text-ink-gray-6">Read only. What the month's goals, habits and weeks came to.</p>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <div v-else class="grid items-start gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card class="flex min-w-0 flex-col gap-1" data-look-goals>
          <h3 class="text-base-medium text-ink-gray-9">Goals · {{ counts }}</h3>
          <div v-for="g in d.goals" :key="g.row" class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 py-2 last:border-b-0" data-look-goal :data-result="g.result">
            <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ g.title }}</span>
            <Badge v-if="g.area_name" :label="g.area_name" />
            <Badge :theme="THEME[g.result]" :label="LABEL[g.result]" />
          </div>
          <p v-if="!d.goals.length" class="text-sm text-ink-gray-6">No goals were set for this month.</p>
        </Card>
        <div class="flex min-w-0 flex-col gap-4">
          <Card class="flex flex-col gap-2" data-look-habits>
            <h3 class="text-base-medium text-ink-gray-9">Habits</h3>
            <div v-for="h in d.habits" :key="h.habit" class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] items-center gap-3" data-look-habit>
              <span class="min-w-0 truncate text-ink-gray-9">{{ h.title }}</span>
              <Progress size="sm" :value="h.percent" :aria-label="`${h.title}: ${h.done} of ${h.target}`" />
              <span class="text-sm tabular-nums text-ink-gray-6">{{ h.done }} of {{ h.target }}</span>
            </div>
            <p v-if="!d.habits.length" class="text-sm text-ink-gray-6">No habits were tracked this month.</p>
          </Card>
          <Card class="flex flex-col gap-2" data-look-weeks>
            <h3 class="text-base-medium text-ink-gray-9">Weekly scores<template v-if="d.average != null"> · average {{ Math.round(d.average) }}% against {{ d.target }}%</template></h3>
            <div v-for="w in d.weeks" :key="w.week" class="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)_3rem] items-center gap-3" data-look-week>
              <span class="truncate text-sm text-ink-gray-7">Week {{ w.week }} · {{ w.label }}</span>
              <Progress size="sm" :value="Math.min(100, w.percent)" :aria-label="`Week ${w.week}`" />
              <span class="text-right text-sm tabular-nums text-ink-gray-7">{{ Math.round(w.percent) }}%</span>
            </div>
            <p v-if="!d.weeks.length" class="text-sm text-ink-gray-6">No 12 Week Year weeks ended in this month.</p>
          </Card>
        </div>
      </div>
    </div>
    <ReviewFooter label="Next: Decide" :line="`About ${r.head?.tab_minutes?.look || 4} minutes`" @next="emit('go', 'decide')" />
  </div>
</template>
<script setup>
// Monthly review, tab 1: the month's goals (done, in progress, missed), its habits against their target and the weekly scores of
// its weeks. Read only.
import { computed, onMounted, ref } from 'vue'
import { Badge, Progress, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import ReviewFooter from '@/components/weekly/ReviewFooter.vue'
import { useReview } from '@/lib/review'

const emit = defineEmits(['go'])
const r = useReview()
const d = ref(null)
const THEME = { done: 'green', progress: 'blue', missed: 'orange' }
const LABEL = { done: 'Done', progress: 'In progress', missed: 'Missed' }
const counts = computed(() => ['done', 'progress', 'missed'].map((k) => `${d.value.goals.filter((g) => g.result === k).length} ${LABEL[k].toLowerCase()}`).join(', '))
onMounted(async () => { d.value = await r.read('look') })
</script>
