<template>
  <!-- set 8: the weekly review is its own screen, with its numbered tabs, not a view inside the Week's header -->
  <ReviewPage v-if="tab === 'week' && (route.query.view === 'review' || (!route.query.view && reviewDay))" />
  <PlanRhythm v-else-if="tab === 'week'" title="Week" :views="WEEK" :initial="reviewDay ? 'review' : 'calendar'">
    <template #above="{ view }"><WeekScore v-if="view !== 'review'" /></template>
    <template #actions><Button icon-left="lucide-rotate-ccw" label="Reset" route="/today/reset" data-plan-reset>
      <template v-if="navDot('Reset')" #suffix><span class="size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot('Reset').label" /></template></Button></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'month'" title="Month" :views="MONTH">
    <template #above="{ view }"><p v-if="view === 'plan'" class="text-sm text-ink-gray-6" data-plan-pages>Written in the paper journal? <RouterLink
      class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/library', query: { tab: 'pages' } }">The journal pages</RouterLink> are in the Library.</p></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'year'" title="Year" :views="YEAR">
    <template #above="{ view }"><p v-if="view === 'cycle'" class="text-sm text-ink-gray-6" data-plan-pages>The plan comes from the paper journal: <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring"
      :to="{ path: '/library', query: { tab: 'pages' } }">the pages that fed it</RouterLink> are in the Library.</p></template>
  </PlanRhythm>
</template>
<script setup>
// Plan's rhythms (UX fixes, set 6), now the Week, Month and Year tabs of Today (issue 14). The 12 Week Year grid is a
// view of the Year. Reset stays a full screen, reached from the Week (its button and the review's first step) and from Today.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import PlanRhythm from '@/components/plan/PlanRhythm.vue'
import WeekScore from '@/components/plan/WeekScore.vue'
import ReviewPage from '@/components/weekly/ReviewPage.vue'
import Month from '@/components/journal/Month.vue'
import Habits from '@/components/journal/Habits.vue'
import Checkins from '@/components/journal/Checkins.vue'
import WeekGrid from '@/components/journal/WeekGrid.vue'
import JournalGoals from '@/components/journal/Goals.vue'
import { isReviewDay } from '@/lib/sidebar'
import { navDot } from '@/lib/newMenu'

defineProps({ tab: String })
const route = useRoute()
const WEEK = [{ key: 'review', label: 'Review', comp: ReviewPage }, { key: 'calendar', label: 'Calendar', cal: 'week' }, { key: 'agenda', label: 'Agenda', cal: 'agenda' }]
const MONTH = [{ key: 'plan', label: 'Plan', comp: Month }, { key: 'habits', label: 'Habits', comp: Habits }, { key: 'checkins', label: 'Check-ins', comp: Checkins },
  { key: 'calendar', label: 'Calendar', cal: 'month' }]
const YEAR = [{ key: 'calendar', label: 'Calendar', cal: 'year' }, { key: 'cycle', label: '12 Weeks', comp: WeekGrid }, { key: 'goals', label: 'Goals across cycles', comp: JournalGoals }]
// on the weekly review's day the Week opens on the review, which starts with Reset
const reviewDay = computed(isReviewDay)
</script>
