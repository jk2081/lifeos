<template>
  <PageHead :title="String(year)" :sub="sub">
    <Button icon="lucide-chevron-left" label="Previous year" tooltip="Previous year" data-year-prev @click="step(-1)" />
    <Button label="Today" data-year-today @click="go(store.today)" />
    <Button icon="lucide-chevron-right" label="Next year" tooltip="Next year" data-year-next @click="step(1)" />
  </PageHead>
  <div class="page-body" data-year-view :data-year="year">
    <Dashboard v-if="mode === 'overview'" view="year" />
    <template v-else>
      <Ruler />
      <!-- twelve months: how many key dates each holds and the next one or two, by name; this month is outlined -->
      <div v-if="d" class="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6" data-year-months>
        <Card v-for="m in d.months" :key="m.month" class="flex min-h-24 min-w-0 flex-col gap-1 !p-3" :class="current(m) && '!border-outline-blue-3 ring-1 ring-outline-blue-3'" :data-month="m.month" :data-current="current(m) || undefined">
          <b class="text-sm font-semibold" :class="current(m) ? 'text-ink-blue-8' : 'text-ink-gray-9'">{{ MONTHS[m.month - 1].slice(0, 3) }}</b>
          <span class="text-sm text-ink-gray-6" data-month-count>{{ m.count }} key date{{ m.count === 1 ? '' : 's' }}</span>
          <Button v-for="k in m.next" :key="k.ref + k.date" class="!h-auto !justify-start !px-0 !py-0 text-left !text-sm !text-ink-gray-8" variant="ghost" :label="`${k.title} · ${ordinal(k.date)}`" data-key-date @click="openRef(k.ref)">
            <template #prefix><span class="size-1.5 shrink-0 rounded-full bg-surface-red-7" aria-hidden="true" /></template>
          </Button>
        </Card>
      </div>
      <div v-else class="py-8 text-sm text-ink-gray-6">{{ failed ? 'The year could not be loaded.' : 'Loading…' }}</div>
    </template>
  </div>
</template>
<script setup>
// Today > Year (issues 16, 100 and 132): Overview is the dashboard (the year's goals by area and the cycles); Calendar is the ruler and the twelve months, each with how many key dates it
// holds and the next one or two named. The cursor is `date=` (its year).
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Dashboard from './Dashboard.vue'
import Ruler from './Ruler.vue'
import PageHead from '@/components/PageHead.vue'
import { todayData } from '@/data/today'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged, openRef } from '@/lib/pane'
import { todayMode as mode } from '@/lib/todayMode'
import { MONTHS, diffDays, iso } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const year = computed(() => Number(String(route.query.date || store.today).slice(0, 4)))
const d = ref(null)
const failed = ref(false)
async function load() {
  if (mode.value !== 'calendar') return
  const res = await tryCall(() => todayData.calendar.year_months({ space: store.space, year: year.value }))
  failed.value = !res
  if (res) d.value = res
}
watch([year, mode, () => store.space], load, { immediate: true })
onRecordChanged(load)
const current = (m) => year.value === Number(store.today.slice(0, 4)) && m.month === Number(store.today.slice(5, 7))
const ordinal = (date) => { const n = Number(date.slice(8)); const t = n % 100 > 10 && n % 100 < 14 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10 > 3 ? 0 : n % 10]; return n + t }
const sub = computed(() => (year.value === Number(store.today.slice(0, 4)) ? `${diffDays(`${year.value}-12-31`, store.today)} days left` : ' '))
const go = (date) => router.push({ path: route.path, query: { ...route.query, open: undefined, shift: undefined, date: date === store.today ? undefined : date } })
const step = (n) => go(iso(new Date(year.value + n, 0, 1)))
</script>
