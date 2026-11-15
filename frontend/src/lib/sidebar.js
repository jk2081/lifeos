// The sidebar's state: which groups and parent areas are open, and the collapsed rail. Remembered per user with the
// other view state (lib/views.js, screen "sidebar"). Also the one active item, and the areas of the current space.
import { computed, reactive, watch } from 'vue'
import router from '@/router'
import { lookups } from './lookups'
import { saveView, savedView, whenViewsLoaded } from './views'
import { store } from './store'

export const nav = reactive({ closed: [], openAreas: [], rail: false })
function restore() {
  const s = savedView('sidebar') || {}
  nav.closed = s.closed || []
  nav.openAreas = s.open_areas || []
  nav.rail = !!s.rail
}
whenViewsLoaded(restore)
watch(() => store.space, () => whenViewsLoaded(restore))
const save = () => saveView('sidebar', { closed: [...nav.closed], open_areas: [...nav.openAreas], rail: nav.rail })
export function setGroup(key, closed) {
  nav.closed = closed ? [...new Set([...nav.closed, key])] : nav.closed.filter((k) => k !== key)
  save()
}
export function setAreaOpen(name, open) {
  nav.openAreas = open ? [...new Set([...nav.openAreas, name])] : nav.openAreas.filter((k) => k !== name)
  save()
}
export function setRail(on) {
  nav.rail = !!on
  save()
}

// the active areas of the current space as a tree one level deep, in their saved order (archived ones are not in lookups)
export const areaTree = computed(() => {
  const all = lookups.areas || []
  const top = all.filter((a) => !a.parent_area || !all.some((p) => p.name === a.parent_area))
  return top.map((a) => ({ ...a, children: all.filter((c) => c.parent_area === a.name) }))
})
export const MAX_AREAS = 12

// Exactly one item is active: an area on its page (its parent opens), Projects on a project page, the Areas heading on /areas.
export const activeKey = computed(() => {
  const p = router.currentRoute.value.path
  const m = /^\/areas\/([^/]+)/.exec(p)
  if (m) return 'area:' + m[1]
  if (p === '/areas') return 'areas'
  if (p === '/') return '/'
  if (p.startsWith('/graph')) return '/library'
  const first = '/' + p.split('/')[1]
  return first
})
watch(activeKey, (k) => {
  if (!k.startsWith('area:')) return
  const a = (lookups.areas || []).find((x) => x.name === k.slice(5))
  if (a?.parent_area && !nav.openAreas.includes(a.parent_area)) nav.openAreas = [...nav.openAreas, a.parent_area]
}, { immediate: true })
watch(() => lookups.areas, () => {
  const k = activeKey.value
  if (!k.startsWith('area:')) return
  const a = (lookups.areas || []).find((x) => x.name === k.slice(5))
  if (a?.parent_area && !nav.openAreas.includes(a.parent_area)) nav.openAreas = [...nav.openAreas, a.parent_area]
})
