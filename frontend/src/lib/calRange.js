// Week and Month of Today (issue 16) read the same calendar: events, tasks planned at a time, tasks due, important dates and
// documents expiring, merged by the server (calendar.get). This holds the loading, the grouping by day and the colours.
import { computed, ref, watch } from 'vue'
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
export const chipClass = (it) => CHIP[chipType(it)]
export const itemRef = (it) => ({ event: 'event', important: 'date', task: 'task', vault: 'vault' }[it.source] + ':' + it.name)
export const itemLabel = (it) => it.label || it.title
/** Day opens for a date: Today's own screen, held to that day. */
export const openDay = (date) => router.push({ path: '/today', query: { ...router.currentRoute.value.query, open: undefined, date: date === store.today ? undefined : date } })

/** The calendar between two dates (at most 100 days), grouped by day, reloaded when a record changes. `range` is a computed [from, to]. */
export function useCalendarRange(range) {
  const data = ref(null)
  const failed = ref(false)
  async function reload() {
    const res = await tryCall(() => api('calendar.get', { space: store.space, from_date: range.value[0], to_date: range.value[1], area: store.lensArea || undefined }))
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
  watch(range, reload, { immediate: true })
  return { data, failed, byDate, itemsOn: (day) => byDate.value[day] || [], reload }
}
