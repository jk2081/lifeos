<template>
  <GoalsByArea v-if="current === 'by-area' && byArea" />
  <Goals v-else-if="current === 'by-area'" />
  <Tasks v-else-if="current === 'tasks' || current === 'no-goal'" :key="current" :screen="current === 'no-goal' ? 'tasks-no-goal' : 'tasks'" />
  <Someday v-else-if="current === 'someday'" />
  <PlaceLinks :links="LINKS" label="More in Goals" />
</template>
<script setup>
// Goals, one of the four places (issue 14): By area (the goals list), All tasks, and No goal (the tasks with no goal).
// Someday is a page of Goals, linked under every tab. Until each tab's own issue lands, it shows the nearest screen.
import { computed, provide, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GoalsByArea from '@/components/goals/GoalsByArea.vue'
import Goals from '@/pages/Goals.vue'
import Tasks from '@/pages/Tasks.vue'
import Someday from '@/pages/Someday.vue'
import PlaceLinks from '@/components/PlaceLinks.vue'
import { GOALS_TABS, goalsPath, withPage } from '@/lib/nav'

const props = defineProps({ tab: String })
const route = useRoute()
const router = useRouter()
const current = computed(() => props.tab || 'by-area')
// By area (issue 20) is the front of Goals; a link that names a filter or an open goal (status=, open=, f=...) still gets the list it counts
const OWN = ['space', 'area', 'show', 'sort']
const byArea = computed(() => Object.keys(route.query).every((k) => OWN.includes(k)))
const LINKS = [{ key: 'someday', label: 'Someday', icon: 'lucide-lightbulb', to: '/goals/someday' }]
// No goal is All tasks with goal=none; another goal picked there is All tasks with that goal
watch(() => [current.value, route.query.goal], ([c, goal]) => {
  if (c !== 'no-goal' || goal === 'none') return
  if (goal) router.replace({ path: '/goals/tasks', query: route.query })
  else router.replace({ query: { ...route.query, goal: 'none' } })
}, { immediate: true })
const PAGES = { someday: 'Someday' }
provide('placeTabs', computed(() => ({ tabs: withPage(GOALS_TABS, current.value, PAGES), current: current.value, label: 'Goals',
  set: (v) => router.push(goalsPath(v)) })))
</script>
