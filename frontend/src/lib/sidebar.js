// The sidebar's state: the collapsed rail, remembered per user with the other view state (lib/views.js, screen "sidebar",
// across spaces). Also which place is active, and whether Review is in the menu (issue 14).
import { computed, reactive } from 'vue'
import router from '@/router'
import { store } from './store'
import { saveView, savedView, whenViewsLoaded } from './views'

export const nav = reactive({ rail: false })
function restore() {
  nav.rail = !!(savedView('sidebar', '') || {}).rail
}
export function setRail(on) {
  nav.rail = !!on
  saveView('sidebar', { rail: nav.rail }, '')
}

// the pages that live inside a place without being one of its tabs
const HOME = { '/item': '/brain', '/inbox': '/brain' }
/** The place the route belongs to: '/today', '/brain', '/goals', '/library', '/review', '/settings', '/ask' or ''. */
export const activePlace = computed(() => {
  const first = '/' + router.currentRoute.value.path.split('/')[1]
  if (HOME[first]) return HOME[first]
  return ['/today', '/brain', '/goals', '/library', '/review', '/settings', '/ask', '/how-it-works'].includes(first) ? first : ''
})

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
/** Today is the weekly review's day (Settings > Rhythms). */
export function isReviewDay() {
  if (!store.today) return false
  return DAYS[new Date(store.today + 'T12:00').getDay()] === (store.settings?.weekly_review_day || 'Sunday')
}
/** Review joins the menu after the person's first locked weekly review, and on the review's day before that. */
export const reviewShown = computed(() => !store.isAgent && (!!store.counts.reviewed || isReviewDay()))
whenViewsLoaded(restore)
