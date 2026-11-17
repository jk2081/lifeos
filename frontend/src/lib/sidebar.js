// The sidebar's state: whether Plan is open to its tabs, and the collapsed rail. Remembered per user with the other view
// state (lib/views.js, screen "sidebar", across spaces). Also which place and which Plan tab are active.
import { computed, reactive } from 'vue'
import router from '@/router'
import { saveView, savedView, whenViewsLoaded } from './views'

export const nav = reactive({ planOpen: true, rail: false })
function restore() {
  const s = savedView('sidebar', '') || {}
  nav.planOpen = s.plan_open !== false
  nav.rail = !!s.rail
}
const save = () => saveView('sidebar', { plan_open: nav.planOpen, rail: nav.rail }, '')
export function setPlanOpen(open) {
  nav.planOpen = !!open
  save()
}
export function setRail(on) {
  nav.rail = !!on
  save()
}

/** The place the route belongs to: '/', '/inbox', '/plan', '/library', '/settings', '/ask' or ''. */
export const activePlace = computed(() => {
  const p = router.currentRoute.value.path
  if (p === '/') return '/'
  const first = '/' + p.split('/')[1]
  return ['/inbox', '/plan', '/library', '/settings', '/ask'].includes(first) ? first : ''
})
/** The open Plan tab, for the sidebar's sub-items: a goal's page and Reset count as Goals and Week. */
export const activePlanTab = computed(() => {
  const p = router.currentRoute.value.path
  if (p.startsWith('/plan/goals')) return 'goals'
  if (p.startsWith('/plan/reset')) return 'week'
  const m = /^\/plan\/([^/]+)/.exec(p)
  return m ? m[1] : ''
})
whenViewsLoaded(restore)
