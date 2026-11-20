<template>
  <Today v-if="current === 'day'" />
  <Plan v-else :tab="current" />
</template>
<script setup>
// Today, one of the four places (issue 14): Day (the day's plate), then the Week, Month and Year that were Plan's rhythms.
// The tabs are paths (/today, /today/week); every screen open here shows them under its header (PageHead).
import { computed, provide } from 'vue'
import { useRouter } from 'vue-router'
import Today from '@/pages/Today.vue'
import Plan from '@/pages/Plan.vue'
import { TODAY_TABS, todayPath } from '@/lib/nav'

const props = defineProps({ tab: String })
const router = useRouter()
const current = computed(() => props.tab || 'day')
provide('placeTabs', computed(() => ({ tabs: TODAY_TABS, current: current.value, label: 'Today', set: (v) => router.push(todayPath(v)) })))
</script>
