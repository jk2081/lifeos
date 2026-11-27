<template>
  <!-- The ruler sits directly above a calendar. It is centred on today: eleven months (five before, this one, five after) over thirty-one days (fifteen either side), so the current month and today line up in the middle. -->
  <nav class="flex h-[60px] w-full flex-none flex-col" aria-label="Where you are" data-ruler>
    <div class="flex h-[30px] items-end" data-ruler-months>
      <Button v-for="m in months" :key="m.key" variant="ghost" class="relative !h-[30px] !min-w-0 flex-1 !items-end !justify-center !p-0 !px-0 hover:!bg-transparent" :aria-label="m.long" :title="m.long"
        :aria-current="m.current ? 'date' : undefined" :data-ruler-month="m.key" :data-current="m.current || undefined" :data-shown="m.key === shown || undefined" @click="goMonth(m)">
        <span v-if="m.label" class="absolute left-1/2 top-0 -translate-x-1/2 whitespace-nowrap text-xs" :class="m.current ? 'text-sm-medium !text-ink-blue-8' : 'text-ink-gray-6'" data-ruler-label>{{ m.label }}</span>
        <span class="block w-px" :class="[m.current ? 'h-3 !w-0.5 bg-surface-blue-7' : 'h-2', !m.current && (m.key < todayMonth ? 'bg-surface-gray-3' : 'bg-surface-gray-5'), m.key === shown && !m.current && '!w-0.5 !bg-surface-gray-7']" />
      </Button>
    </div>
    <div class="flex h-[30px] items-start" data-ruler-days>
      <Button v-for="d in days" :key="d.date" variant="ghost" class="relative !h-[30px] !min-w-0 flex-1 !items-start !justify-center !p-0 !px-0 hover:!bg-transparent" :aria-label="d.long" :title="phone ? undefined : d.long"
        :aria-current="d.today ? 'date' : undefined" :data-ruler-day="d.date" :data-today="d.today || undefined" @click="open(d)">
        <span class="block w-px" :class="[d.today ? 'h-3 !w-0.5 bg-surface-blue-7' : 'h-2', !d.today && (d.date < store.today ? 'bg-surface-gray-3' : 'bg-surface-gray-5')]" />
        <span v-if="d.label" class="absolute left-1/2 top-3.5 -translate-x-1/2 whitespace-nowrap text-xs" :class="d.today ? 'text-sm-medium !text-ink-blue-8' : 'text-ink-gray-6'" data-ruler-label>{{ d.label }}</span>
      </Button>
    </div>
  </nav>
</template>
<script setup>
// The ruler (issues 123 and 132): where you are, in two slim strips directly above a calendar (Today > Calendar only). Centred on today: 11 months, 5 either side of the current one,
// and 31 days, 15 either side of today. It shows no counts and no colour beyond the accent. Labels: the current month and the one either side, today and two days either side; a phone
// labels only today and the current month. Today opens Day; another day opens in the Drawer; a month moves the calendar to that month.
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { Button } from 'frappe-ui'
import { MONTHS, addDays, iso, long, weekday } from '@/lib/dates'
import { openRef } from '@/lib/pane'
import { store } from '@/lib/store'
import { todayPath } from '@/lib/nav'

const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const todayMonth = computed(() => store.today.slice(0, 7))
const shown = computed(() => String(route.query.date || store.today).slice(0, 7)) // the month the calendar below is on
const months = computed(() => {
  const [y, m] = todayMonth.value.split('-').map(Number)
  return Array.from({ length: 11 }, (_, i) => {
    const at = new Date(y, m - 1 + i - 5, 1)
    const key = iso(at).slice(0, 7)
    const near = Math.abs(i - 5) <= 1
    const name = MONTHS[at.getMonth()]
    return { key, long: `${name} ${at.getFullYear()}`, current: i === 5, label: i === 5 ? (phone.value ? name.slice(0, 3) : name) : near && !phone.value ? name.slice(0, 3) : '' }
  })
})
const days = computed(() => Array.from({ length: 31 }, (_, i) => {
  const date = addDays(store.today, i - 15)
  const today = i === 15
  const near = Math.abs(i - 15) <= 2
  return { date, today, long: `${weekday(date)} ${long(date, true)}`, label: today ? `${weekday(date, 3)} ${Number(date.slice(8))}` : near && !phone.value ? String(Number(date.slice(8))) : '' }
}))
function goMonth(m) {
  const date = m.current ? undefined : `${m.key}-01`
  router.push({ path: route.path, query: { ...route.query, open: undefined, shift: undefined, date } })
}
function open(d) {
  if (d.today) router.push({ path: todayPath('day'), query: { mode: route.query.mode } })
  else openRef('day:' + d.date)
}
</script>
