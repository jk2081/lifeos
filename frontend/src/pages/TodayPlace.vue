<template>
  <DayOther v-if="current === 'day' && otherDay" :date="otherDay" />
  <Today v-else-if="current === 'day'" />
  <Plan v-else-if="route.query.view" :tab="current" />
  <WeekView v-else-if="current === 'week'" />
  <MonthView v-else-if="current === 'month'" />
  <YearView v-else />
</template>
<script setup>
// Today, one of the four places (issue 14): Day (the day's plate), then Week, Month and Year (issue 16). The tabs are paths (/today,
// /today/week); every screen open here shows them under its header (PageHead). Day holds to a date with `date=` (Week and Month open
// a day there); the older views of a rhythm (the weekly review, the month plan, habits, the 12 Week grid, the calendar grids) keep
// their `view=` and are still Plan's screens.
import { computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Today from '@/pages/Today.vue'
import Plan from '@/pages/Plan.vue'
import DayOther from '@/components/today/DayOther.vue'
import WeekView from '@/components/today/WeekView.vue'
import MonthView from '@/components/today/MonthView.vue'
import YearView from '@/components/today/YearView.vue'
import { TODAY_TABS, todayPath } from '@/lib/nav'
import { store } from '@/lib/store'

const props = defineProps({ tab: String })
const route = useRoute()
const router = useRouter()
const current = computed(() => props.tab || 'day')
const otherDay = computed(() => (/^\d{4}-\d{2}-\d{2}$/.test(String(route.query.date || '')) && route.query.date !== store.today ? route.query.date : null))
provide('placeTabs', computed(() => ({ tabs: TODAY_TABS, current: current.value, label: 'Today', set: (v) => router.push(todayPath(v)) })))
</script>
