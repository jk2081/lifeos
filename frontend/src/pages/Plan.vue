<template>
  <PlanRhythm v-if="tab === 'week'" title="Week" :views="WEEK" :initial="reviewDay ? 'review' : 'calendar'">
    <template #above="{ view }"><WeekScore v-if="view !== 'review'" /></template>
    <template #actions><Button icon-left="lucide-rotate-ccw" label="Reset" route="/plan/reset" data-plan-reset>
      <template v-if="navDot('Reset')" #suffix><span class="size-2 rounded-full bg-surface-amber-7" role="img" :aria-label="navDot('Reset').label" /></template></Button></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'month'" title="Month" :views="MONTH">
    <template #above="{ view }"><p v-if="view === 'plan'" class="text-sm text-ink-gray-6" data-plan-pages>Written in the paper journal? <RouterLink
      class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/library/captures', query: { tab: 'pages' } }">The journal pages</RouterLink> are in the Library.</p></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === '12-weeks'" title="12 Weeks" :views="CYCLE">
    <template #above><p class="text-sm text-ink-gray-6" data-plan-pages>The plan comes from the paper journal: <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring"
      :to="{ path: '/library/captures', query: { tab: 'pages' } }">the pages that fed it</RouterLink> are in the Library.</p></template>
  </PlanRhythm>
  <PlanRhythm v-else-if="tab === 'year'" title="Year" :views="YEAR" />
  <Goals v-else-if="tab === 'goals'" />
  <Tasks v-else-if="tab === 'tasks'" />
  <Someday v-else-if="tab === 'someday'" />
</template>
<script setup>
// Plan, one of the four places (UX fixes, set 6): the rhythms (Week, Month, 12 Weeks, Year), then the lists (Goals,
// Tasks, Someday). The tabs are paths (/plan/week); every screen open here shows them under its header (PageHead).
// Reset stays a full screen, reached from the Week (its button and the review's first step) and from Today.
import { computed, provide } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PlanRhythm from '@/components/plan/PlanRhythm.vue'
import WeekScore from '@/components/plan/WeekScore.vue'
import WeeklyReview from '@/components/journal/WeeklyReview.vue'
import Month from '@/components/journal/Month.vue'
import Habits from '@/components/journal/Habits.vue'
import Checkins from '@/components/journal/Checkins.vue'
import WeekGrid from '@/components/journal/WeekGrid.vue'
import JournalGoals from '@/components/journal/Goals.vue'
import Goals from '@/pages/Goals.vue'
import Tasks from '@/pages/Tasks.vue'
import Someday from '@/pages/Someday.vue'
import { PLAN_TABS, planPath } from '@/lib/nav'
import { store } from '@/lib/store'
import { navDot } from '@/lib/newMenu'

const props = defineProps({ tab: String })
const router = useRouter()
const WEEK = [{ key: 'review', label: 'Review', comp: WeeklyReview }, { key: 'calendar', label: 'Calendar', cal: 'week' }, { key: 'agenda', label: 'Agenda', cal: 'agenda' }]
const MONTH = [{ key: 'plan', label: 'Plan', comp: Month }, { key: 'habits', label: 'Habits', comp: Habits }, { key: 'checkins', label: 'Check-ins', comp: Checkins },
  { key: 'calendar', label: 'Calendar', cal: 'month' }]
const CYCLE = [{ key: 'grid', label: 'Cycle', comp: WeekGrid }]
const YEAR = [{ key: 'calendar', label: 'Calendar', cal: 'year' }, { key: 'goals', label: 'Goals across cycles', comp: JournalGoals }]
// on the weekly review's day the Week opens on the review, which starts with Reset
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const reviewDay = computed(() => DAYS[new Date(store.today + 'T12:00').getDay()] === (store.settings?.weekly_review_day || 'Sunday'))
provide('placeTabs', computed(() => ({ tabs: PLAN_TABS, current: props.tab, label: 'Plan', set: (v) => router.push(planPath(v)) })))
</script>
