<template>
  <!-- set 8: the weekly review is its own screen, with its numbered tabs, not a view inside the Week's header -->
  <ReviewPage v-if="tab === 'week' && route.query.view === 'review'" />
  <PlanRhythm v-else-if="tab === 'week'" title="Week" :views="WEEK" :initial="'calendar'">
    <template #above="{ view }"><WeekScore v-if="view !== 'review'" /></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'month'" title="Month" :views="MONTH" />
  <PlanRhythm v-else-if="tab === 'year'" title="Year" :views="YEAR" />
</template>
<script setup>
// Plan's rhythms (UX fixes, set 6), now the Week, Month and Year tabs of Today (issue 14). The month goals and the 12 Week Year
// are Goals > Cycles (issue 45); their old views redirect there. Since issue 16 the Week, Month and Year open on their own screens (components/today); the views below are the ones
// with `view=` in the URL. Reset is a section of Settings > Data, reached from All tasks (the Week's button went in issue 99).
import { useRoute } from 'vue-router'
import PlanRhythm from '@/components/goals/PlanRhythm.vue'
import WeekScore from '@/components/goals/WeekScore.vue'
import ReviewPage from '@/components/review/ReviewPage.vue'
import Habits from '@/components/goals/Habits.vue'
import JournalGoals from '@/components/goals/Goals.vue'

defineProps({ tab: String })
const route = useRoute()
const WEEK = [{ key: 'review', label: 'Review', comp: ReviewPage }, { key: 'calendar', label: 'Calendar', cal: 'week' }, { key: 'agenda', label: 'Agenda', cal: 'agenda' }]
const MONTH = [{ key: 'habits', label: 'Habits', comp: Habits }, { key: 'calendar', label: 'Calendar', cal: 'month' }]
const YEAR = [{ key: 'calendar', label: 'Calendar', cal: 'year' }, { key: 'goals', label: 'Goals across cycles', comp: JournalGoals }]
</script>
