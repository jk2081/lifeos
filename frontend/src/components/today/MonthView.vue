<template>
  <PageHead :title="title" :sub="sub">
    <Button icon="lucide-chevron-left" label="Previous month" tooltip="Previous month" data-cal-prev @click="step(-1)" />
    <Button label="This month" data-cal-today @click="go(store.today)" />
    <Button icon="lucide-chevron-right" label="Next month" tooltip="Next month" data-cal-next @click="step(1)" />
  </PageHead>
  <div class="page-body" data-month-view :data-month="month">
    <ViewLinks :links="LINKS" />
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6" data-legend>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-gray-3"></i>meetings</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-blue-3"></i>goal work and key dates</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-red-3"></i>due dates</span>
    </div>
    <div class="overflow-hidden rounded-5 border border-outline-gray-2" data-month-grid><div class="grid grid-cols-7">
      <div v-for="w in HEADS" :key="w" class="border-b border-outline-gray-1 bg-surface-gray-1 p-2 text-xs font-semibold text-ink-gray-7 max-md:px-1 max-md:py-1.5">{{ w }}</div>
      <div v-for="c in cells" :key="c.date" class="relative flex min-h-[104px] min-w-0 flex-col gap-[3px] border-b border-r border-outline-gray-1 p-1.5 text-left hover:bg-surface-gray-2 max-md:min-h-14 max-md:items-center max-md:p-1 [&:nth-child(7n)]:border-r-0"
        :class="[c.date === store.today && 'bg-surface-gray-1', c.date === picked && phone && '!bg-surface-gray-3']" :data-day="c.date" :data-today="c.date === store.today || undefined">
        <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="long(c.date, true)" @click="phone ? (picked = c.date) : openDay(c.date)" />
        <span class="inline-flex size-6 items-center justify-center rounded-full text-sm tabular-nums"
          :class="c.date === store.today ? 'bg-surface-gray-9 font-semibold text-ink-base' : c.inMonth ? 'text-ink-gray-8' : 'text-ink-gray-6'">{{ c.day }}</span>
        <template v-if="!phone">
          <div v-for="(it, i) in itemsOn(c.date).slice(0, MAX)" :key="i" class="relative truncate rounded px-[5px] text-xs leading-[1.5]" :class="chipClass(it)" data-month-item :data-source="it.source">
            <button type="button" class="absolute inset-0 rounded focus-visible:focus-ring" :aria-label="itemLabel(it)" :data-ref="itemRef(it)" @click="openRef(itemRef(it))" />
            {{ it.all_day ? '' : time(it.start) + ' ' }}{{ itemLabel(it) }}</div>
          <span v-if="itemsOn(c.date).length > MAX" class="text-xs text-ink-gray-6">+{{ itemsOn(c.date).length - MAX }} more</span>
        </template>
        <span v-else class="flex gap-0.5"><i v-for="(it, i) in itemsOn(c.date).slice(0, 3)" :key="i" class="size-1.5 rounded-full" :class="dotClass(it)" /></span>
      </div>
    </div></div>
    <!-- a phone: the grid is compact, the chosen day's items are listed below it -->
    <section v-if="phone" data-month-list>
      <SectionHead>{{ weekday(picked) }}, {{ long(picked) }}</SectionHead>
      <Card flush>
        <Row v-for="(it, i) in itemsOn(picked)" :key="i" :pane="itemRef(it)" :label="itemLabel(it)" class="!items-center">
          <span class="w-14 flex-none text-sm tabular-nums text-ink-gray-6">{{ it.all_day ? 'All day' : time(it.start) }}</span>
          <span class="min-w-0 flex-1 break-words rounded px-1.5 py-0.5 text-base" :class="chipClass(it)">{{ itemLabel(it) }}</span>
        </Row>
        <Empty v-if="!itemsOn(picked).length" title="Nothing on this day." />
      </Card>
      <Button class="mt-2" label="Open in Day" data-open-day @click="openDay(picked)" />
    </section>
  </div>
</template>
<script setup>
// Today > Month (issue 16): the month grid with meetings, goal work, due tasks and key dates. A day opens in Day and an item in the
// record pane; on a phone the grid is compact and the chosen day is listed below it. The cursor is `date=`.
import { computed, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import ViewLinks from './ViewLinks.vue'
import { store } from '@/lib/store'
import { chipClass, dotClass, itemLabel, itemRef, openDay, useCalendarRange } from '@/lib/calRange'
import { openRef } from '@/lib/pane'
import { MONTHS, addDays, iso, long, parse, startOfWeek, time, weekday } from '@/lib/dates'

const MAX = 3
const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const LINKS = [{ label: 'Month goals', to: '/goals/cycles' }, { label: 'Habits', to: { path: '/today/month', query: { view: 'habits' } } }]
const sunday = store.settings?.week_starts_on === 'Sunday'
const HEADS = sunday ? ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const cursor = computed(() => parse(route.query.date || store.today))
const month = computed(() => iso(new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1)).slice(0, 7))
const first = computed(() => { const d = startOfWeek(`${month.value}-01`); return sunday ? addDays(d, -1) : d })
// whole weeks, from the one the month starts in to the one it ends in
const cells = computed(() => {
  const lead = Math.round((parse(`${month.value}-01`) - parse(first.value)) / 86400000)
  const weeks = Math.ceil((lead + new Date(cursor.value.getFullYear(), cursor.value.getMonth() + 1, 0).getDate()) / 7)
  return Array.from({ length: weeks * 7 }, (_, i) => {
    const date = addDays(first.value, i)
    return { date, day: parse(date).getDate(), inMonth: date.startsWith(month.value) }
  })
})
const { data, itemsOn } = useCalendarRange(computed(() => [first.value, addDays(first.value, 41)]))
const picked = ref(store.today)
watch(month, (m) => { picked.value = store.today.startsWith(m) ? store.today : `${m}-01` }, { immediate: true })

const title = computed(() => `${MONTHS[cursor.value.getMonth()]} ${cursor.value.getFullYear()}`)
const inMonth = (it) => it.date.startsWith(month.value)
const sub = computed(() => {
  const items = (data.value?.items || []).filter(inMonth)
  const meetings = items.filter((i) => i.source === 'event').length
  const due = items.filter((i) => i.source === 'task' && !i.scheduled).length
  return data.value ? `${meetings} meeting${meetings === 1 ? '' : 's'} · ${due} due date${due === 1 ? '' : 's'}` : ' '
})
const go = (date) => router.push({ path: route.path, query: { ...route.query, open: undefined, date: date === store.today ? undefined : date } })
const step = (n) => go(iso(new Date(cursor.value.getFullYear(), cursor.value.getMonth() + n, 1)))
</script>
