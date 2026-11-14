<template>
  <header class="hd tabs">
    <div><h1 class="h1">Journal</h1><div class="sub">{{ sub || '&nbsp;' }}</div></div>
    <div id="jr-actions" style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center"></div>
  </header>
  <nav class="tb" aria-label="Journal sections">
    <RouterLink v-for="t in TABS" :key="t.key" :to="t.key === 'year' ? '/journal' : `/journal/${t.key}`" :class="{ on: current === t.key }">
      <span class="only-desktop">{{ t.label }}</span><span class="only-phone">{{ t.short || t.label }}</span>
    </RouterLink>
  </nav>
  <component :is="VIEWS[current]" v-if="ready" :key="current" @sub="(s) => (sub = s)" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import WeekGrid from '@/components/journal/WeekGrid.vue'
import Goals from '@/components/journal/Goals.vue'
import Month from '@/components/journal/Month.vue'
import Habits from '@/components/journal/Habits.vue'
import Checkins from '@/components/journal/Checkins.vue'
import Pages from '@/components/journal/Pages.vue'
import WeeklyReview from '@/components/journal/WeeklyReview.vue'

const props = defineProps({ tab: String })
const TABS = [{ key: 'year', label: '12 Week Year', short: '12 Weeks' }, { key: 'goals', label: 'Goals' }, { key: 'month', label: 'Month' },
  { key: 'habits', label: 'Habits' }, { key: 'checkins', label: 'Check-ins' }, { key: 'pages', label: 'Pages' }, { key: 'review', label: 'Weekly review', short: 'Review' }]
const VIEWS = { year: WeekGrid, goals: Goals, month: Month, habits: Habits, checkins: Checkins, pages: Pages, review: WeeklyReview }
const current = computed(() => (VIEWS[props.tab] ? props.tab : 'year'))
const sub = ref('')
const ready = ref(false)
onMounted(() => (ready.value = true)) // the tab teleports its buttons into the header
</script>
