<template>
  <GoalsByArea v-if="current === 'by-area' && byArea" />
  <Goals v-else-if="current === 'by-area'" />
  <GoalsAllTasks v-else-if="current === 'tasks' && allTasks" />
  <GoalsNoGoal v-else-if="current === 'no-goal' && noGoal" @changed="loadCount" />
  <GoalsCycles v-else-if="current === 'cycles'" />
  <Tasks v-else-if="current === 'tasks' || current === 'no-goal'" :key="current" :screen="current === 'no-goal' ? 'tasks-no-goal' : 'tasks'" />
  <Someday v-else-if="current === 'someday'" />
  <PlaceLinks :links="LINKS" label="More in Goals" />
</template>
<script setup>
// Goals, one of the four places (issue 14): By area (the goals list), All tasks, and No goal (the tasks with no goal).
// Someday is a page of Goals, linked under every tab. Until each tab's own issue lands, it shows the nearest screen.
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GoalsByArea from '@/components/goals/GoalsByArea.vue'
import GoalsNoGoal from '@/components/goals/GoalsNoGoal.vue'
import GoalsCycles from '@/components/goals/GoalsCycles.vue'
import GoalsAllTasks from '@/components/goals/GoalsAllTasks.vue'
import Goals from '@/pages/Goals.vue'
import Tasks from '@/pages/Tasks.vue'
import Someday from '@/pages/Someday.vue'
import PlaceLinks from '@/components/PlaceLinks.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged } from '@/lib/pane'
import { GOALS_TABS, goalsPath, withPage } from '@/lib/nav'

const props = defineProps({ tab: String })
const route = useRoute()
const router = useRouter()
const current = computed(() => props.tab || 'by-area')
// By area (issue 20) is the front of Goals; a link that names a filter or an open goal (status=, open=, f=...) still gets the list it counts
const OWN = ['space', 'area', 'show', 'sort']
const byArea = computed(() => Object.keys(route.query).every((k) => OWN.includes(k)))
// All tasks (issue 21) is the front of Goals > All tasks; an address that names a filter of the old list (status=, view=, f=, due=...) still gets that list
const TASK_OWN = ['space', 'area', 'group', 'show', 'q']
const allTasks = computed(() => Object.keys(route.query).every((k) => TASK_OWN.includes(k)))
// No goal (issue 22) is its own screen; an address that names a filter (goal=none, status=...) still gets the old list
const noGoal = computed(() => Object.keys(route.query).every((k) => ['space', 'area'].includes(k)))
const LINKS = [{ key: 'someday', label: 'Someday', icon: 'lucide-lightbulb', to: '/goals/someday' }]
// No goal is All tasks with goal=none; another goal picked there is All tasks with that goal
watch(() => [current.value, route.query.goal, noGoal.value], ([c, goal, own]) => {
  if (c !== 'no-goal' || goal === 'none' || own) return
  if (goal) router.replace({ path: '/goals/tasks', query: route.query })
  else router.replace({ query: { ...route.query, goal: 'none' } })
}, { immediate: true })
const PAGES = { someday: 'Someday' }
// the number on the No goal tab: open tasks with no goal that nobody has marked as fine without one
const noGoalCount = ref(null)
async function loadCount() {
  const res = await tryCall(() => api('tasks.no_goal_total', { space: store.space }))
  if (res) noGoalCount.value = res.count
}
watch(() => store.space, loadCount)
onMounted(loadCount)
onRecordChanged(loadCount)
const tabs = computed(() => GOALS_TABS.map((t) => (t.value === 'no-goal' && noGoalCount.value !== null ? { ...t, count: noGoalCount.value, noun: 'tasks without a goal' } : t)))
provide('placeTabs', computed(() => ({ tabs: withPage(tabs.value, current.value, PAGES), current: current.value, label: 'Goals',
  set: (v) => router.push(goalsPath(v)) })))
</script>
