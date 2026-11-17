<template>
  <PageHead :title="place || title" :sub="place ? title : undefined">
    <TabButtons v-if="switchOptions" :model-value="switchValue" :options="switchOptions" aria-label="Views" data-plan-views />
    <slot name="actions" />
    <Button icon="lucide-chevron-left" label="Previous" tooltip="Previous" data-cal-prev @click="step(-1)" />
    <Button icon="lucide-chevron-right" label="Next" tooltip="Next" data-cal-next @click="step(1)" />
    <Button class="max-md:hidden" variant="ghost" label="Today" data-cal-today @click="goToday" />
    <TabButtons v-if="!switchOptions" :model-value="mode" :options="VIEW_OPTIONS" aria-label="Calendar views" data-views />
    <template v-if="canWrite()">
      <Button label="Add important date" @click="openDate(cursor)" />
      <Button variant="solid" icon-left="lucide-plus" label="Add event" @click="openEvent(cursor)" />
    </template>
  </PageHead>

  <div class="page-body" data-calendar :data-view="mode">
    <slot name="above" />
    <Alert v-if="google && !google.connected" title="Google Calendar is not connected" description="Events added here stay on this site."
      :primary-action="{ label: 'Connect it in Frappe\'s Google settings', href: google.setup_url }" data-google-prompt />

    <!-- year: one column a month, one line a day, as in the journal -->
    <template v-if="mode === 'year' && yearData">
      <div class="flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-ink-gray-6">
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-current text-ink-blue-8"></i>Birthday or anniversary</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm border border-outline-gray-3 bg-surface-amber-2"></i>Trip</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm border border-outline-gray-3 bg-surface-red-2"></i>Document expiry</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block h-3 w-[3px] bg-surface-gray-9"></i>12 Week Year in progress</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm border-2 border-outline-gray-5"></i>Today</span>
      </div>
      <div class="overflow-hidden rounded-5 border border-outline-gray-2 max-md:hidden" data-year-grid><div class="overflow-x-auto"><div class="grid min-w-[1080px] grid-cols-12">
        <div v-for="mo in yearCells" :key="mo.m" class="min-w-0 border-r border-outline-gray-1 last:border-r-0">
          <div class="border-b border-outline-gray-1 bg-surface-gray-1 p-2 text-xs font-semibold" :class="mo.current ? 'text-ink-blue-8' : 'text-ink-gray-7'">{{ MONTHS[mo.m - 1] }}</div>
          <div v-for="c in mo.days" :key="c.day" class="relative flex h-6 items-center gap-1.5 overflow-hidden whitespace-nowrap border-b border-outline-gray-1 px-1.5 text-xs text-ink-gray-9 hover:bg-surface-gray-2"
            :class="[c.bg, c.today && 'rounded !border-2 !border-outline-gray-5']" :data-day="c.date" :data-today="c.today || undefined" :data-cycle="c.cycle || undefined">
            <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="`${c.day} ${MONTHS[mo.m - 1]}${c.first ? ', ' + c.first.title : ''}`" @click="openDay(c.date)" />
            <span v-if="c.cycle" class="absolute inset-y-0 left-0 w-[3px] bg-surface-gray-9" aria-hidden="true" />
            <span class="w-4 flex-none text-right tabular-nums" :class="c.today ? 'font-bold text-ink-gray-9' : 'text-ink-gray-6'">{{ c.day }}</span>
            <span v-if="c.first" class="min-w-0 flex-1 truncate font-medium" :class="c.ink">{{ c.first.label || c.first.title }}</span>
            <span v-if="c.count > 1" class="text-ink-gray-6">+{{ c.count - 1 }}</span>
          </div>
        </div>
      </div></div></div>
      <div class="flex flex-col gap-5 md:hidden">
        <section v-for="m in monthsWithEntries" :key="m">
          <SectionHead>{{ MONTHS[m - 1] }}</SectionHead>
          <Card flush>
            <Row v-for="day in entryDays(m)" :key="day" :pane="'day:' + ymd(year, m, day)" :label="`${day} ${MONTHS[m - 1]}`">
              <span class="w-16 flex-none tabular-nums text-ink-gray-7">{{ day }} {{ weekday(ymd(year, m, day), 3) }}</span>
              <span class="min-w-0 flex-1 break-words" :class="INK[yearFirst(m, day).type] || 'text-ink-gray-9'">{{ yearList(m, day).map((e) => e.label || e.title).join(', ') }}</span>
            </Row>
          </Card>
        </section>
        <Card v-if="!monthsWithEntries.length"><Empty :title="`Nothing in ${year} yet.`" hint="Add an important date or an all-day event, and it shows here." /></Card>
      </div>
      <p class="text-sm text-ink-gray-6 max-md:hidden">Laid out like the year pages in the journal: one column a month, one line a day. Timed meetings are left out. Click a day to add or open an entry.</p>
    </template>

    <!-- month -->
    <template v-else-if="mode === 'month' && data">
      <div class="overflow-hidden rounded-5 border border-outline-gray-2" data-month-grid><div class="grid grid-cols-7">
        <div v-for="w in DAY_HEADS" :key="w"
          class="border-b border-outline-gray-1 bg-surface-gray-1 p-2 text-xs font-semibold text-ink-gray-7 max-md:px-1 max-md:py-1.5">{{ w }}</div>
        <div v-for="c in monthCells" :key="c.date" class="relative flex min-h-[104px] min-w-0 flex-col gap-[3px] border-b border-r border-outline-gray-1 p-1.5 text-left hover:bg-surface-gray-2 max-md:min-h-16 max-md:p-1 [&:nth-child(7n)]:border-r-0"
          :class="[c.weekend ? 'bg-surface-gray-1' : 'bg-surface-base', c.date === data.today && '!border-2 !border-outline-gray-5']" :data-day="c.date" :data-today="c.date === data.today || undefined">
          <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="long(c.date, true)" @click="openDay(c.date)" />
          <span class="text-sm tabular-nums" :class="c.date === data.today ? 'font-bold text-ink-gray-9' : c.inMonth ? 'text-ink-gray-7' : 'text-ink-gray-4'">{{ c.day }}</span>
          <span v-for="(it, i) in itemsOn(c.date).slice(0, 3)" :key="i" class="truncate rounded px-[5px] text-xs leading-[1.5] max-md:h-1.5 max-md:p-0 max-md:text-[0px]" :class="CHIP[chipType(it)]">{{ it.all_day ? '' : time(it.start) + ' ' }}{{ it.label || it.title }}</span>
          <span v-if="itemsOn(c.date).length > 3" class="text-xs text-ink-gray-6">+{{ itemsOn(c.date).length - 3 }} more</span>
        </div>
      </div></div>
    </template>

    <!-- week -->
    <template v-else-if="mode === 'week' && data">
      <div class="grid grid-cols-7 items-start gap-2 max-md:grid-cols-1" data-week-grid>
        <Card v-for="dte in weekDays" :key="dte" class="flex min-h-40 min-w-0 flex-col gap-1.5 !p-2.5 max-md:min-h-0" :class="dte === data.today && '!border-outline-gray-5'" :data-day="dte" :data-today="dte === data.today || undefined">
          <Button class="-mx-1 !justify-start" variant="ghost" :label="`${weekday(dte, 3)} ${short(dte)}`" @click="openDay(dte)" />
          <div v-for="(it, i) in itemsOn(dte)" :key="i" class="relative cursor-pointer rounded px-1.5 py-[3px] text-sm [overflow-wrap:anywhere]" :class="CHIP[chipType(it)]">
            <button type="button" class="absolute inset-0 rounded focus-visible:focus-ring" :aria-label="it.label || it.title" :data-ref="itemRef(it)" @click="openRef(itemRef(it))" />
            <span v-if="!it.all_day" class="tabular-nums text-ink-gray-6">{{ time(it.start) }}</span> {{ it.label || it.title }}</div>
          <div v-if="!itemsOn(dte).length" class="text-sm text-ink-gray-6">Nothing</div>
        </Card>
      </div>
    </template>

    <!-- agenda -->
    <template v-else-if="mode === 'agenda' && data">
      <section v-for="dte in agendaDays" :key="dte">
        <SectionHead>{{ dte === data.today ? 'Today · ' : '' }}{{ weekday(dte) }}, {{ long(dte) }}</SectionHead>
        <Card flush>
          <Row v-for="(it, i) in itemsOn(dte)" :key="i" :pane="itemRef(it)" :label="it.label || it.title">
            <span class="w-16 flex-none tabular-nums text-ink-gray-7">{{ it.all_day ? 'All day' : time(it.start) }}</span>
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="INK[chipType(it)] || 'text-ink-gray-9'">{{ it.label || it.title }}</div>
              <div class="text-sm text-ink-gray-6">{{ SOURCE[it.source] }}</div></div>
          </Row>
        </Card>
      </section>
      <Card v-if="!agendaDays.length"><Empty title="Nothing in the next 30 days." hint="Events, important dates, tasks with a due date and expiring documents show here." /></Card>
    </template>
  </div>

  <NewRecord v-model="eventOpen" title="Add event" action="Add event" :fields="EVENT_FIELDS" :initial="eventInitial" :save="saveEvent" @saved="saved" />
  <NewRecord v-model="dateOpen" title="Add important date" action="Add date" :fields="DATE_FIELDS" :initial="dateInitial" :save="saveDate" @saved="saved" />
</template>

<script setup>
// The calendar: month, week, agenda and year. All four views are ours, drawn with token classes. A day, and every entry,
// opens in the record pane; events are created through the NewRecord dialogs and the lifeos.api methods.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Alert, Button, TabButtons, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import NewRecord from '@/components/NewRecord.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { onRecordChanged, openRef, recordChanged } from '@/lib/pane'
import { MONTHS, addDays, iso, long, parse, short, startOfWeek as mondayOf, time, weekday } from '@/lib/dates'
import { useTabKeys } from '@/lib/tabs'
import routerInstance from '@/router'

// In Plan (UX fixes, set 6) the calendar is a view of the Week, Month and Year tabs: `place` is the tab's title (the
// calendar's own title becomes the line under it) and `switchOptions` the tab's view switch, which replaces the calendar's.
const props = defineProps({ view: String, place: String, switchOptions: Array, switchValue: String })
// Settings > Rhythms: the week of the calendar starts on Monday or Sunday (week scores keep the cycle's Monday weeks)
const sunday = store.settings?.week_starts_on === 'Sunday'
const startOfWeek = (s) => (sunday ? addDays(mondayOf(addDays(s, 1)), -1) : mondayOf(s))
const DAY_HEADS = sunday ? ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const VIEWS = ['month', 'week', 'agenda', 'year']
const VIEW_OPTIONS = VIEWS.map((v) => ({ label: v[0].toUpperCase() + v.slice(1), value: v, route: `/calendar/${v}` }))
const SOURCE = { event: 'Event', important: 'Important date', task: 'Task due', vault: 'Vault document' }
// the colours of an entry by its type: as a chip (month, week) and as a line of text (agenda, year)
const CHIP = {
  event: 'bg-surface-gray-2 text-ink-gray-8', important: 'bg-surface-blue-2 text-ink-blue-9', trip: 'bg-surface-amber-2 text-ink-amber-9',
  vault: 'bg-surface-red-2 text-ink-red-8', task: 'border border-outline-gray-2 text-ink-gray-7',
}
const INK = { important: 'text-ink-blue-8', trip: 'text-ink-amber-9', vault: 'text-ink-red-8', task: 'text-ink-gray-7' }
const mode = computed(() => (VIEWS.includes(props.view) ? props.view : window.innerWidth < 768 ? 'agenda' : 'month'))
// set 3: the views keep their path form (/calendar/year); [ and ] open the previous and next view
if (!props.place) useTabKeys({ level: 1, step: (n) => { const next = VIEWS[VIEWS.indexOf(mode.value) + n]; if (next) routerInstance.push(`/calendar/${next}`) } })
const cursor = ref(store.today)
const data = ref(null)
const yearData = ref(null)
const google = ref(null)
const eventOpen = ref(false)
const dateOpen = ref(false)
const eventInitial = ref({})
const dateInitial = ref({})
const pad = (n) => String(n).padStart(2, '0')
const ymd = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`
const year = computed(() => parse(cursor.value).getFullYear())
const daysIn = (y, m) => new Date(y, m, 0).getDate()

const EVENT_FIELDS = [{ name: 'subject', label: 'Title', required: true }, { name: 'date', label: 'Date', type: 'date', required: true },
  { name: 'all_day', label: 'All day', options: [{ value: 1, label: 'Yes' }, { value: 0, label: 'No, it has a time' }], required: true },
  { name: 'start_time', label: 'Starts at', type: 'time' }, { name: 'end_time', label: 'Ends at', type: 'time' },
  { name: 'end_date', label: 'Last day, for a trip', type: 'date' }]
const DATE_FIELDS = [{ name: 'title', label: 'Name', required: true, placeholder: 'For example: Ruchi' },
  { name: 'kind', label: 'Kind', options: ['Birthday', 'Anniversary', 'Other'], required: true },
  { name: 'date', label: 'Date', type: 'date', required: true, help: 'It repeats on this day every year.' },
  { name: 'year', label: 'Year it first happened (optional)', type: 'number' }]

const title = computed(() => {
  const d = parse(cursor.value)
  if (mode.value === 'year') return String(d.getFullYear())
  if (mode.value === 'month') return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
  if (mode.value === 'week') return `Week of ${short(startOfWeek(cursor.value))}`
  return `From ${short(cursor.value)}`
})
const range = computed(() => {
  const d = parse(cursor.value)
  if (mode.value === 'month') {
    const first = startOfWeek(iso(new Date(d.getFullYear(), d.getMonth(), 1)))
    return [first, addDays(first, 41)]
  }
  if (mode.value === 'week') return [startOfWeek(cursor.value), addDays(startOfWeek(cursor.value), 6)]
  return [cursor.value, addDays(cursor.value, 30)]
})
const byDate = computed(() => {
  const map = {}
  for (const it of data.value?.items || []) {
    const last = it.multi_day ? it.end_date : it.date
    for (let day = it.date; day <= last; day = addDays(day, 1)) (map[day] = map[day] || []).push(it)
  }
  return map
})
const itemsOn = (dte) => byDate.value[dte] || []
const chipType = (it) => (it.source === 'event' ? (it.multi_day ? 'trip' : 'event') : it.source)
const monthCells = computed(() => {
  const m = parse(cursor.value).getMonth()
  return Array.from({ length: 42 }, (_, i) => {
    const dte = addDays(range.value[0], i)
    const d = parse(dte)
    return { date: dte, day: d.getDate(), inMonth: d.getMonth() === m, weekend: d.getDay() === 0 || d.getDay() === 6 }
  })
})
const weekDays = computed(() => Array.from({ length: 7 }, (_, i) => addDays(range.value[0], i)))
const agendaDays = computed(() => Object.keys(byDate.value).filter((k) => k >= range.value[0] && k <= range.value[1]).sort())

// year view helpers
const yearList = (m, day) => yearData.value.days[ymd(year.value, m, day)] || []
const yearFirst = (m, day) => yearList(m, day)[0]
// Every day of the year, with what its line shows: weekends tinted, a trip or an expiry filled, today outlined,
// and a bar on the days inside a 12 Week Year in progress.
const yearCells = computed(() => Array.from({ length: 12 }, (_, i) => {
  const m = i + 1
  return {
    m, current: yearData.value.today.slice(0, 7) === `${year.value}-${pad(m)}`,
    days: Array.from({ length: daysIn(year.value, m) }, (_, j) => {
      const day = j + 1
      const date = ymd(year.value, m, day)
      const list = yearList(m, day)
      const type = list[0]?.type
      const dow = new Date(year.value, m - 1, day).getDay()
      return {
        day, date, first: list[0], count: list.length, today: date === yearData.value.today,
        cycle: yearData.value.active_ranges.some((r) => date >= r.start && date <= r.end),
        bg: type === 'trip' ? 'bg-surface-amber-2' : type === 'vault' ? 'bg-surface-red-2' : dow === 0 || dow === 6 ? 'bg-surface-gray-1' : 'bg-surface-base',
        ink: INK[type] || '',
      }
    }),
  }
}))
const entryDays = (m) => Array.from({ length: daysIn(year.value, m) }, (_, i) => i + 1).filter((day) => yearList(m, day).length)
const monthsWithEntries = computed(() => Array.from({ length: 12 }, (_, i) => i + 1).filter((m) => entryDays(m).length))

async function reload() {
  if (mode.value === 'year') {
    const res = await tryCall(() => api('calendar.year', { space: store.space, year: year.value }))
    if (res) yearData.value = res
    if (!google.value) google.value = (await tryCall(() => api('calendar.get', { space: store.space, from_date: store.today, to_date: store.today })))?.google
  } else {
    const res = await tryCall(() => api('calendar.get', { space: store.space, from_date: range.value[0], to_date: range.value[1], area: store.lensArea || undefined }))
    if (res) {
      data.value = res
      google.value = res.google
    }
  }
}
function step(n) {
  const d = parse(cursor.value)
  if (mode.value === 'year') d.setFullYear(d.getFullYear() + n)
  else if (mode.value === 'month') d.setMonth(d.getMonth() + n, 1)
  else if (mode.value === 'week') d.setDate(d.getDate() + 7 * n)
  else d.setDate(d.getDate() + 30 * n)
  cursor.value = iso(d)
}
function goToday() {
  cursor.value = store.today
}
// a day opens in the record pane; its entries open their own records from there
const openDay = (dte) => openRef('day:' + dte)
const itemRef = (it) => ({ event: 'event', important: 'date', task: 'task', vault: 'vault' }[it.source] + ':' + it.name)
const onAdd = (e) => (e.detail.kind === 'event' ? openEvent(e.detail.date) : openDate(e.detail.date))
const saved = () => { reload(); recordChanged('day') }
onRecordChanged((ref_) => { if (ref_ !== 'day') reload() })
onMounted(() => window.addEventListener('lifeos-calendar-add', onAdd))
onUnmounted(() => window.removeEventListener('lifeos-calendar-add', onAdd))
function openEvent(dte) {
  eventInitial.value = { date: dte, all_day: 1 }
  eventOpen.value = true
}
function openDate(dte) {
  dateInitial.value = { date: dte, kind: 'Birthday' }
  dateOpen.value = true
}
async function saveEvent(v) {
  const allDay = Number(v.all_day) === 1 || !v.start_time
  const starts = allDay ? `${v.date} 00:00:00` : `${v.date} ${v.start_time}:00`
  let ends = null
  if (allDay && v.end_date) ends = `${v.end_date} 23:59:59`
  else if (!allDay && v.end_time) ends = `${v.date} ${v.end_time}:00`
  const res = await api('calendar.add_event', { space: store.space, subject: v.subject, starts_on: starts, ends_on: ends, all_day: allDay ? 1 : 0 })
  toast.success(res.synced_to_google ? 'Event added. It will be pushed to Google Calendar.' : 'Event added.')
}
async function saveDate(v) {
  const d = parse(v.date)
  await api('calendar.add_important_date', { space: store.space, title: v.title, kind: v.kind, day: d.getDate(), month: d.getMonth() + 1, year: v.year || null })
  toast.success('Added. It shows on this day every year.')
}
watch([mode, cursor], reload, { immediate: true })
</script>
