<template>
  <header class="hd tabs">
    <div style="display: flex; align-items: center; gap: 8px">
      <button class="bt s ic" type="button" aria-label="Previous" @click="step(-1)"><Ico d="m15 6-6 6 6 6" stroke="2" /></button>
      <h1 class="h1" style="min-width: 60px; text-align: center">{{ title }}</h1>
      <button class="bt s ic" type="button" aria-label="Next" @click="step(1)"><Ico d="m9 6 6 6-6 6" stroke="2" /></button>
      <button class="bt t only-desktop" type="button" @click="goToday">Today</button>
    </div>
    <div v-if="canWrite()" style="display: flex; gap: 8px; flex-wrap: wrap">
      <button class="bt s" type="button" @click="openDate(cursor)">Add important date</button>
      <button class="bt p" type="button" @click="openEvent(cursor)">Add event</button>
    </div>
  </header>
  <nav class="tb" aria-label="Calendar views">
    <RouterLink v-for="v in VIEWS" :key="v" :to="`/calendar/${v}`" :class="{ on: mode === v }">{{ v[0].toUpperCase() + v.slice(1) }}</RouterLink>
  </nav>

  <div class="bd">
    <div v-if="google && !google.connected" class="mt">Google Calendar is not connected, so events here stay on this site.
      <a :href="google.setup_url" target="_blank" rel="noopener">Connect it in Frappe's Google settings</a>.</div>

    <!-- year -->
    <template v-if="mode === 'year' && yearData">
      <div class="mt lgds">
        <span class="lgd"><i class="sw" style="background: var(--accent)"></i>Birthday or anniversary</span>
        <span class="lgd"><i class="sw" style="background: var(--o-bg); border: 1px solid var(--o-ink)"></i>Trip</span>
        <span class="lgd"><i class="sw" style="background: var(--r-bg); border: 1px solid var(--r-ink)"></i>Document expiry</span>
        <span class="lgd"><i class="sw" style="width: 3px; background: var(--ink)"></i>12 Week Year in progress</span>
        <span class="lgd"><i class="sw" style="box-shadow: inset 0 0 0 2px var(--accent)"></i>Today</span>
      </div>
      <div class="tblwrap only-desktop"><div class="tblscroll"><div class="yr">
        <div v-for="m in 12" :key="m" class="mo">
          <div class="mh" :class="{ cur: isCurMonth(m) }">{{ MONTHS[m - 1] }}</div>
          <button v-for="day in daysIn(year, m)" :key="day" class="dc" :class="yearClass(m, day)" type="button"
            :aria-label="`${day} ${MONTHS[m - 1]}${yearFirst(m, day) ? ', ' + yearFirst(m, day).title : ''}`" @click="openDay(ymd(year, m, day))">
            <span class="dn">{{ day }}</span>
            <span v-if="yearFirst(m, day)" class="dl">{{ yearFirst(m, day).label || yearFirst(m, day).title }}</span>
            <span v-if="yearList(m, day).length > 1" class="more">+{{ yearList(m, day).length - 1 }}</span>
          </button>
        </div>
      </div></div></div>
      <div class="only-phone">
        <section v-for="m in monthsWithEntries" :key="m" style="margin-bottom: 20px">
          <h2 class="sh">{{ MONTHS[m - 1] }}</h2>
          <div class="cd list">
            <button v-for="day in entryDays(m)" :key="day" class="rw rowbtn" type="button" @click="openDay(ymd(year, m, day))">
              <span class="when">{{ day }} {{ weekday(ymd(year, m, day), 3) }}</span>
              <span class="grow" :class="'yt-' + yearFirst(m, day).type">{{ yearList(m, day).map((e) => e.label || e.title).join(', ') }}</span>
            </button>
          </div>
        </section>
        <div v-if="!monthsWithEntries.length" class="cd"><Empty :title="`Nothing in ${year} yet.`" hint="Add an important date or an all-day event, and it shows here." /></div>
      </div>
      <p class="mt only-desktop" style="margin: 0">Laid out like the year pages in the journal: one column a month, one line a day. Timed meetings are left out. Click a day to add or open an entry.</p>
    </template>

    <!-- month -->
    <template v-else-if="mode === 'month' && data">
      <div class="tblwrap"><div class="mgrid">
        <div v-for="w in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']" :key="w" class="mhd">{{ w }}</div>
        <button v-for="c in monthCells" :key="c.date" class="mc" :class="{ out: !c.inMonth, we: c.weekend, td: c.date === data.today }" type="button"
          :aria-label="long(c.date, true)" @click="openDay(c.date)">
          <span class="dnum">{{ c.day }}</span>
          <span v-for="(it, i) in itemsOn(c.date).slice(0, 3)" :key="i" class="chip" :class="'s-' + chipType(it)">{{ it.all_day ? '' : time(it.start) + ' ' }}{{ it.label || it.title }}</span>
          <span v-if="itemsOn(c.date).length > 3" class="mt" style="font-size: 11px">+{{ itemsOn(c.date).length - 3 }} more</span>
        </button>
      </div></div>
    </template>

    <!-- week -->
    <template v-else-if="mode === 'week' && data">
      <div class="wgrid">
        <div v-for="dte in weekDays" :key="dte" class="cd wcol" :class="{ tdcol: dte === data.today }">
          <button class="wkhd" type="button" @click="openDay(dte)"><b>{{ weekday(dte, 3) }}</b> {{ short(dte) }}</button>
          <div v-for="(it, i) in itemsOn(dte)" :key="i" class="witem" :class="'s-' + chipType(it)" style="cursor: pointer" @click="openRef(itemRef(it))">
            <span v-if="!it.all_day" class="mt">{{ time(it.start) }}</span> {{ it.label || it.title }}</div>
          <div v-if="!itemsOn(dte).length" class="mt">Nothing</div>
        </div>
      </div>
    </template>

    <!-- agenda -->
    <template v-else-if="mode === 'agenda' && data">
      <section v-for="dte in agendaDays" :key="dte">
        <h2 class="sh">{{ dte === data.today ? 'Today · ' : '' }}{{ weekday(dte) }}, {{ long(dte) }}</h2>
        <div class="cd list"><div v-for="(it, i) in itemsOn(dte)" :key="i" class="rw rowlink" :data-ref="itemRef(it)" tabindex="0" @click="openRef(itemRef(it))" @keydown.enter.self="openRef(itemRef(it))">
          <span class="when">{{ it.all_day ? 'All day' : time(it.start) }}</span>
          <div class="grow"><div class="ttl" :class="'yt-' + chipType(it)">{{ it.label || it.title }}</div><div class="mt">{{ SOURCE[it.source] }}</div></div></div></div>
      </section>
      <div v-if="!agendaDays.length" class="cd"><Empty title="Nothing in the next 30 days." hint="Events, important dates, tasks with a due date and expiring documents show here." /></div>
    </template>
  </div>

  <NewRecord v-model="eventOpen" title="Add event" action="Add event" :fields="EVENT_FIELDS" :initial="eventInitial" :save="saveEvent" @saved="saved" />
  <NewRecord v-model="dateOpen" title="Add important date" action="Add date" :fields="DATE_FIELDS" :initial="dateInitial" :save="saveDate" @saved="saved" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { toast } from 'frappe-ui'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { onRecordChanged, openRef, recordChanged } from '@/lib/pane'
import { MONTHS, addDays, iso, long, parse, short, startOfWeek, time, weekday } from '@/lib/dates'

const props = defineProps({ view: String })
const VIEWS = ['month', 'week', 'agenda', 'year']
const SOURCE = { event: 'Event', important: 'Important date', task: 'Task due', vault: 'Vault document' }
const mode = computed(() => (VIEWS.includes(props.view) ? props.view : window.innerWidth < 800 ? 'agenda' : 'month'))
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
const isCurMonth = (m) => yearData.value.today.slice(0, 7) === `${year.value}-${pad(m)}`
function yearClass(m, day) {
  const dte = ymd(year.value, m, day)
  const first = yearFirst(m, day)
  const dow = new Date(year.value, m - 1, day).getDay()
  return {
    we: dow === 0 || dow === 6, td: dte === yearData.value.today, cy: yearData.value.active_ranges.some((r) => dte >= r.start && dte <= r.end),
    b: first?.type === 'important', t: first?.type === 'trip', v: first?.type === 'vault', e: first?.type === 'event' || first?.type === 'cycle',
  }
}
const entryDays = (m) => Array.from({ length: daysIn(year.value, m) }, (_, i) => i + 1).filter((day) => yearList(m, day).length)
const monthsWithEntries = computed(() => Array.from({ length: 12 }, (_, i) => i + 1).filter((m) => entryDays(m).length))

async function reload() {
  if (mode.value === 'year') {
    const res = await tryCall(() => api('calendar.year', { space: store.space, year: year.value }))
    if (res) yearData.value = res
    if (!google.value) google.value = (await tryCall(() => api('calendar.get', { space: store.space, from_date: store.today, to_date: store.today })))?.google
  } else {
    const res = await tryCall(() => api('calendar.get', { space: store.space, from_date: range.value[0], to_date: range.value[1] }))
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

<style scoped>
.lgds { display: flex; gap: 6px 18px; flex-wrap: wrap; }
.lgd { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; box-sizing: border-box; }
.yr { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); min-width: 1080px; }
.mo { border-right: 1px solid var(--line); min-width: 0; }
.mo:last-child { border-right: 0; }
.mh { padding: 8px; font-size: 12px; font-weight: 600; color: var(--mut2); background: var(--side); border-bottom: 1px solid var(--line); }
.mh.cur { color: var(--accent); }
.dc { display: flex; align-items: center; gap: 6px; height: 24px; width: 100%; padding: 0 6px; border: 0; border-bottom: 1px solid var(--faint); background: var(--bg); font-size: 12px; white-space: nowrap; overflow: hidden; cursor: pointer; color: var(--ink); text-align: left; box-sizing: border-box; }
.dc:hover { background: var(--fill); }
.dc .dn { width: 16px; flex: none; text-align: right; color: var(--mut); font-variant-numeric: tabular-nums; }
.dc .dl { overflow: hidden; text-overflow: ellipsis; font-weight: 500; flex: 1; min-width: 0; }
.dc .more { color: var(--mut); font-size: 11px; }
.dc.we { background: var(--soft); }
.dc.b .dl { color: var(--accent); }
.dc.t { background: var(--o-bg); } .dc.t .dl { color: var(--o-ink); }
.dc.v { background: var(--r-bg); } .dc.v .dl { color: var(--r-ink); }
.dc.td { box-shadow: inset 0 0 0 2px var(--accent); border-radius: 5px; }
.dc.td .dn { color: var(--accent); font-weight: 700; }
.dc.cy { border-left: 3px solid var(--ink); padding-left: 3px; }
.when { width: 64px; flex: none; font-variant-numeric: tabular-nums; color: var(--mut2); }
.rowbtn { width: 100%; background: none; border-left: 0; border-right: 0; border-top: 0; text-align: left; color: var(--ink); font: inherit; cursor: pointer; }
.yt-important { color: var(--accent); } .yt-trip { color: var(--o-ink); } .yt-vault { color: var(--r-ink); } .yt-task { color: var(--mut2); }
.mgrid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.mhd { padding: 8px; font-size: 12px; font-weight: 600; color: var(--mut2); background: var(--side); border-bottom: 1px solid var(--line); }
.mc { min-height: 104px; border: 0; border-right: 1px solid var(--line2); border-bottom: 1px solid var(--line2); background: var(--bg); padding: 6px; display: flex; flex-direction: column; gap: 3px; align-items: stretch; text-align: left; cursor: pointer; min-width: 0; color: var(--ink); }
.mc:nth-child(7n) { border-right: 0; }
.mc.we { background: var(--soft); }
.mc.out .dnum { color: var(--line4); }
.mc.td { box-shadow: inset 0 0 0 2px var(--accent); }
.mc.td .dnum { color: var(--accent); font-weight: 700; }
.dnum { font-size: 12.5px; color: var(--mut2); font-variant-numeric: tabular-nums; }
.chip { font-size: 11.5px; line-height: 1.5; padding: 0 5px; border-radius: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: var(--fill); }
.s-important { background: var(--b-bg); color: var(--b-ink); } .s-trip { background: var(--o-bg); color: var(--o-ink); }
.s-vault { background: var(--r-bg); color: var(--r-ink); } .s-task { background: transparent; color: var(--mut2); box-shadow: inset 0 0 0 1px var(--line3); }
.wgrid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; align-items: start; }
.wcol { padding: 10px; display: flex; flex-direction: column; gap: 6px; min-height: 160px; }
.wcol.tdcol { border-color: var(--accent); }
.wkhd { border: 0; background: none; padding: 0; text-align: left; font: inherit; color: var(--ink); cursor: pointer; }
.witem { font-size: 12.5px; padding: 3px 6px; border-radius: 6px; background: var(--fill); overflow-wrap: anywhere; }
@media (max-width: 800px) {
  .wgrid { grid-template-columns: 1fr; } .wcol { min-height: 0; }
  .mc { min-height: 64px; padding: 4px; } .chip { font-size: 0; height: 6px; padding: 0; border-radius: 3px; } .mhd { padding: 6px 4px; font-size: 11px; }
}
</style>
