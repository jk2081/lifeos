// Today's three modes (issues 132 and 135): Overview (the work slice: tasks, mail, people), Goals (the planning slice: goals, the 12 Week Year, reviews, habits) and Calendar (the time
// slice: the ruler and the calendar). The mode is in the URL (`?mode=`) and remembered for the person (a Frappe user default, sent with the boot data), so Today opens in the last one
// used; Overview for someone who has never chosen. Goals is a mode only once a goal exists (`store.goalsMode`); asking for it before that shows Overview.
import { computed } from 'vue'
import router from '@/router'
import { todayData } from '@/data/today'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'

const MODES = ['overview', 'goals', 'calendar']
const usable = (m) => MODES.includes(m) && (m !== 'goals' || store.goalsMode)
export const todayModes = computed(() => (store.goalsMode ? MODES : MODES.filter((m) => m !== 'goals')))
export const todayMode = computed(() => {
  const q = router.currentRoute.value.query.mode
  return usable(q) ? q : usable(store.todayMode) ? store.todayMode : 'overview'
})

/** Switch mode in place, keeping the period, and remember it. */
export function setMode(mode) {
  if (!usable(mode) || mode === todayMode.value) return
  store.todayMode = mode
  router.replace({ query: { ...router.currentRoute.value.query, mode } })
  tryCall(() => todayData.dashboard.set_mode({ mode }))
}
