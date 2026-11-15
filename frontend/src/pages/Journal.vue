<template>
  <PageHead title="Journal">
    <template #sub>{{ sub || ' ' }}</template>
    <div id="jr-actions" class="contents"></div>
  </PageHead>
  <!-- seven tabs are wider than a phone: the strip scrolls sideways in its own row, the page does not -->
  <Tabs class="scroll-x" :model-value="current">
    <TabList class="min-w-max px-4 md:px-7" aria-label="Journal sections">
      <TabTrigger v-for="t in TABS" :key="t.key" :value="t.key" :label="t.label" :route="t.key === 'year' ? '/journal' : `/journal/${t.key}`">
        <span class="max-md:hidden">{{ t.label }}</span><span class="md:hidden">{{ t.short || t.label }}</span>
      </TabTrigger>
    </TabList>
  </Tabs>
  <component :is="VIEWS[current]" v-if="ready" :key="current" @sub="(s) => (sub = s)" />
</template>
<script setup>
// The journal: one header, a row of tabs that are links, and the tab's own screen below. Each tab teleports its buttons into the header.
import { computed, onMounted, ref } from 'vue'
import { TabList, Tabs, TabTrigger } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
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
