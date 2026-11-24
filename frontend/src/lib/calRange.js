// Week and Month of Today (issue 16) read the same calendar: events, tasks planned at a time, tasks due, important dates and
// documents expiring, merged by the server (calendar.get). This holds the loading, the grouping by day and the colours.
import { computed, ref, watch } from 'vue'
import { current } from '@/lib/pane'
import router from '@/router'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged } from '@/lib/pane'
import { addDays } from '@/lib/dates'

// Grey: meetings. Blue: goal work (tasks planned at a time) and important dates. Red: due dates and expiries. Amber: a trip.
const CHIP = {
  event: 'bg-surface-gray-2 text-ink-gray-8', trip: 'bg-surface-amber-2 text-ink-amber-9', planned: 'bg-surface-blue-2 text-ink-blue-9',
  important: 'bg-surface-blue-2 text-ink-blue-9', due: 'bg-surface-red-2 text-ink-red-8', vault: 'bg-surface-red-2 text-ink-red-8',
}
export const chipType = (it) => (it.source === 'event' ? (it.multi_day ? 'trip' : 'event') : it.source === 'task' ? (it.scheduled ? 'planned' : 'due') : it.source)
// the dot of an item on a phone's compact month, in the strong colour of its chip
const DOT = { event: 'bg-surface-gray-6', trip: 'bg-surface-amber-7', planned: 'bg-surface-blue-7', important: 'bg-surface-blue-7', due: 'bg-surface-red-7', vault: 'bg-surface-red-7' }
export const dotClass = (it) => DOT[chipType(it)]
export const chipClass = (it) => CHIP[chipType(it)] + (it.hidden ? ' opacity-60 line-through' : '')
// a repeat of a repeating event is `name@date`, so each repeat has its own notes (issue 99)
export const itemRef = (it) => ({ event: 'event', important: 'date', task: 'task', vault: 'vault' }[it.source] + ':' + it.name + (it.source === 'event' && it.repeats ? '@' + it.date : ''))
// an all-day event of more than one day is one bar across its days, above the timed events (issue 99)
export const isBar = (it) => it.source === 'event' && !!it.multi_day && !!it.all_day
/** The bars of a week: each with its first and last column (1 to 7) and a row, so bars that overlap stack. */
export function weekBars(days, items) {
  const first = days[0], last = days[days.length - 1]
  const seen = new Set()
  const bars = []
  for (const it of items || []) {
    if (!isBar(it) || seen.has(itemRef(it)) || it.end_date < first || it.date > last) continue
    seen.add(itemRef(it))
    const from = Math.max(days.indexOf(it.date), 0), to = it.end_date > last ? days.length - 1 : days.indexOf(it.end_date)
    bars.push({ it, from: from + 1, to: to + 2, row: 0 })
  }
  bars.sort((a, b) => a.from - b.from || b.to - a.to)
  const ends = []
  for (const b of bars) {
    let row = ends.findIndex((e) => e <= b.from)
    if (row < 0) row = ends.length
    ends[row] = b.to
    b.row = row + 1
  }
  return bars
}
/** Events hidden in Life OS: Show hidden events in the week menu brings them back. */
export const showHidden = ref(false)
/** True while the record pane is open on a desktop: the week makes room for it instead of lying under it. */
export const paneOpen = computed(() => !!current.value)
export const WEEK_ROOM = 'md:!pr-[532px]'
export const itemLabel = (it) => it.label || it.title
/** Day opens for a date: Today's own screen, held to that day. */
export const openDay = (date) => router.push({ path: '/today', query: { ...router.currentRoute.value.query, open: undefined, date: date === store.today ? undefined : date } })

/** The calendar between two dates (at most 100 days), grouped by day, reloaded when a record changes. `range` is a computed [from, to]. */
export function useCalendarRange(range) {
  const data = ref(null)
  const failed = ref(false)
  async function reload() {
    const res = await tryCall(() => api('calendar.get', { space: store.space, from_date: range.value[0], to_date: range.value[1], area: store.lensArea || undefined, show_hidden: showHidden.value ? 1 : undefined }))
    failed.value = !res
    if (res) data.value = res
  }
  const byDate = computed(() => {
    const map = {}
    for (const it of data.value?.items || []) {
      const last = it.multi_day ? it.end_date : it.date
      for (let day = it.date; day <= last; day = addDays(day, 1)) (map[day] = map[day] || []).push(it)
    }
    return map
  })
  onRecordChanged(reload)
  watch([range, showHidden], reload, { immediate: true })
  return { data, failed, byDate, itemsOn: (day) => byDate.value[day] || [], reload }
}
