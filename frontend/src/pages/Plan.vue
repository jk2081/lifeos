<template>
  <!-- set 8: the weekly review is its own screen, with its numbered tabs, not a view inside the Week's header -->
  <ReviewPage v-if="tab === 'week' && route.query.view === 'review'" />
  <PlanRhythm v-else-if="tab === 'week'" title="Week" :views="WEEK" :initial="'calendar'">
    <template #above="{ view }"><WeekScore v-if="view !== 'review'" /></template>
    <template #actions><Button icon-left="lucide-rotate-ccw" label="Reset" route="/today/reset" data-plan-reset>
      <template v-if="navDot('Reset')" #suffix><span class="size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot('Reset').label" /></template></Button></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'month'" title="Month" :views="MONTH" />
  <PlanRhythm v-else-if="tab === 'year'" title="Year" :views="YEAR" />
</template>
<script setup>
// Plan's rhythms (UX fixes, set 6), now the Week, Month and Year tabs of Today (issue 14). The month plan and the 12 Week Year
// are Goals > Cycles (issue 45); their old views redirect there. Since issue 16 the Week, Month and Year open on their own screens (components/today); the views below are the ones
// with `view=` in the URL. Reset stays a full screen, reached from the Week (its button and the review's first step) and from Today.
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import PlanRhythm from '@/components/plan/PlanRhythm.vue'
import WeekScore from '@/components/plan/WeekScore.vue'
import ReviewPage from '@/components/weekly/ReviewPage.vue'
import Habits from '@/components/journal/Habits.vue'
import Checkins from '@/components/journal/Checkins.vue'
import JournalGoals from '@/components/journal/Goals.vue'
import { navDot } from '@/lib/newMenu'

defineProps({ tab: String })
const route = useRoute()
const WEEK = [{ key: 'review', label: 'Review', comp: ReviewPage }, { key: 'calendar', label: 'Calendar', cal: 'week' }, { key: 'agenda', label: 'Agenda', cal: 'agenda' }]
const MONTH = [{ key: 'habits', label: 'Habits', comp: Habits }, { key: 'checkins', label: 'Check-ins', comp: Checkins },
  { key: 'calendar', label: 'Calendar', cal: 'month' }]
const YEAR = [{ key: 'calendar', label: 'Calendar', cal: 'year' }, { key: 'goals', label: 'Goals across cycles', comp: JournalGoals }]
</script>
