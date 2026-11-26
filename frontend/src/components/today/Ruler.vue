<template>
  <nav class="flex h-[60px] flex-none flex-col px-4 pt-1.5 md:px-6" aria-label="Where you are" data-ruler :data-month="shown">
    <!-- the months: twelve ticks; this month labelled with an accent tick, the two beside it labelled in grey -->
    <div class="flex h-[30px] items-end" data-ruler-months>
      <Button v-for="m in months" :key="m.key" variant="ghost" class="relative !h-[30px] !min-w-0 flex-1 !items-end !justify-center !p-0 !px-0 hover:!bg-transparent" :aria-label="m.long" :title="m.long"
        :aria-current="m.key === todayMonth ? 'date' : undefined" :data-ruler-month="m.key" :data-current="m.key === todayMonth || undefined" :data-shown="m.key === shown || undefined" @click="shown = m.key">
        <span v-if="m.label" class="absolute left-1/2 top-0 -translate-x-1/2 whitespace-nowrap text-xs" :class="m.key === todayMonth ? 'text-sm-medium !text-ink-blue-8' : 'text-ink-gray-6'" data-ruler-label>{{ m.label }}</span>
        <span class="block w-px" :class="[m.key === todayMonth ? 'h-3 !w-0.5 bg-surface-blue-7' : 'h-2', m.key !== todayMonth && (m.key < todayMonth ? 'bg-surface-gray-3' : 'bg-surface-gray-5'), m.key === shown && m.key !== todayMonth && '!w-0.5 !bg-surface-gray-7']" />
      </Button>
    </div>
    <!-- the days of the shown month: one tick each; today labelled with an accent tick, two days either side labelled on a laptop, only today on a phone. A fixed height whatever the month's length -->
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
// The ruler (issue 123): where you are, in two slim strips at the top of every Today view. Twelve month ticks and one tick for each day of the month. It shows no
// counts and no colour beyond the accent. Today's label opens Today > Day; any other day opens that day in the pane; a month tick moves the day strip to that month
// (in place; the current month comes back on reload). One component at both widths: a phone labels only today's day and the months by their short names.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { Button } from 'frappe-ui'
import { MONTHS, iso, long, parse, weekday } from '@/lib/dates'
import { openRef } from '@/lib/pane'
import { store } from '@/lib/store'
import { todayPath } from '@/lib/nav'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const todayMonth = computed(() => store.today.slice(0, 7))
const shown = ref(store.today.slice(0, 7))
const monthAt = (n) => {
  const [y, m] = todayMonth.value.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return iso(d).slice(0, 7)
}
const months = computed(() => {
  const year = Number(todayMonth.value.slice(0, 4))
  return Array.from({ length: 12 }, (_, i) => {
    const key = `${year}-${String(i + 1).padStart(2, '0')}`
    const near = key === todayMonth.value || key === monthAt(-1) || key === monthAt(1)
    return { key, long: `${MONTHS[i]} ${year}`, label: near ? (phone.value ? MONTHS[i].slice(0, 3) : key === todayMonth.value ? MONTHS[i] : MONTHS[i].slice(0, 3)) : '' }
  })
})
const days = computed(() => {
  const [y, m] = shown.value.split('-').map(Number)
  const n = new Date(y, m, 0).getDate()
  return Array.from({ length: n }, (_, i) => {
    const date = `${shown.value}-${String(i + 1).padStart(2, '0')}`
    const gap = Math.round((parse(date) - parse(store.today)) / 86400000)
    const today = date === store.today
    const labelled = today || (!phone.value && Math.abs(gap) <= 2 && shown.value === todayMonth.value)
    return { date, today, long: `${weekday(date)} ${long(date, true)}`, label: labelled ? (today ? (phone.value ? String(i + 1) : `${weekday(date, 3)} ${i + 1}`) : String(i + 1)) : '' }
  })
})
function open(d) {
  if (d.today) router.push({ path: todayPath('day'), query: {} })
  else openRef('day:' + d.date)
}
</script>
