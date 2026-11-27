// Today's two modes (issue 132): Overview (the work slice: cards and panels) and Calendar (the time slice: the ruler and the calendar). The mode is in the URL (`?mode=`) and remembered
// for the person (a Frappe user default, sent with the boot data), so Today opens in the last one used. Calendar is the default.
import { computed } from 'vue'
import router from '@/router'
import { todayData } from '@/data/today'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'

const MODES = ['overview', 'calendar']
export const todayMode = computed(() => {
  const q = router.currentRoute.value.query.mode
  return MODES.includes(q) ? q : MODES.includes(store.todayMode) ? store.todayMode : 'calendar'
})

/** Switch mode in place, keeping the period, and remember it. */
export function setMode(mode) {
  if (!MODES.includes(mode) || mode === todayMode.value) return
  store.todayMode = mode
  router.replace({ query: { ...router.currentRoute.value.query, mode } })
  tryCall(() => todayData.dashboard.set_mode({ mode }))
}
