// The lens (UX fixes, set 6): the space and area every place narrows to. It lives in the URL as `space=` and `area=`,
// so a reload, Back and a copied link keep it, and it is remembered per user with the other view state (lib/views.js,
// screen "lens", across spaces). Choosing an area includes its sub-areas; the server does that (lifeos.api.utils.area_filter).
//
// Links built anywhere in the app need not carry the lens: the guard below adds it to every navigation that has none.
// Clearing the area goes through setLens, which empties the state first so the guard does not put it back.
import { computed } from 'vue'
import router from '@/router'
import { store } from './store'
import { lookups } from './lookups'
import { saveView, savedView } from './views'

// the state is the store's lensArea, so lib/store.js can count under the lens without importing this module
export const lens = { get area() { return store.lensArea }, set area(v) { store.lensArea = v || '' } }

// the dot of an area: a frappe-ui surface token, written out so Tailwind keeps every class
const DOTS = {
  blue: 'bg-surface-blue-7', green: 'bg-surface-green-7', amber: 'bg-surface-amber-7', red: 'bg-surface-red-7', violet: 'bg-surface-violet-7',
  teal: 'bg-surface-teal-7', orange: 'bg-surface-orange-7', pink: 'bg-surface-pink-7', cyan: 'bg-surface-cyan-7', gray: 'bg-surface-gray-7',
}
export const dotClass = (area) => DOTS[area?.colour] || DOTS.gray

export const lensArea = computed(() => (lens.area && (lookups.areas || []).find((a) => a.name === lens.area)) || null)
export const lensAreaName = computed(() => (lens.area ? lensArea.value?.area_name || 'This area' : 'All of life'))
/** "Private · All of life": the lens in words, for the picker and the phone's title. */
export const lensLabel = computed(() => `${store.space || 'No space'} · ${lensAreaName.value}`)
/** The lens as list arguments: { area } or {}. */
export const lensArgs = () => (lens.area ? { area: lens.area } : {})

/** The active areas of the space as a tree: top-level areas in their order, each with its sub-areas. */
export const lensTree = computed(() => {
  const all = lookups.areas || []
  const top = all.filter((a) => !a.parent_area || !all.some((p) => p.name === a.parent_area))
  const below = (a, depth) => all.filter((c) => c.parent_area === a.name).flatMap((c) => [{ ...c, depth }, ...below(c, depth + 1)])
  return top.flatMap((a) => [{ ...a, depth: 0 }, ...below(a, 1)])
})
/** The areas pinned to the sidebar under "Focus on an area", in the areas' order. */
export const pinnedAreas = computed(() => (lookups.areas || []).filter((a) => a.is_pinned))

const remember = () => saveView('lens', { space: store.space, area: lens.area }, '')

/** Change the lens. A new space starts on All of life unless an area of it is given. */
export function setLens({ space, area } = {}) {
  if (space !== undefined && space !== store.space) {
    store.space = space
    lens.area = area || ''
  } else if (area !== undefined) {
    lens.area = area || ''
  }
  remember()
  const cur = router.currentRoute.value
  router.push({ path: cur.path, query: { ...cur.query, space: store.space || undefined, area: lens.area || undefined }, hash: cur.hash })
}
export const clearArea = () => setLens({ area: '' })

/** Once the session is known: take the lens from the URL, or the remembered one, and write it into the URL. */
export async function initLens() {
  // the first navigation must be resolved first: before it, the current route is the start route "/", and replacing with
  // it sent a deep link (a reload, a copied URL) to Today
  await router.isReady()
  const q = router.currentRoute.value.query
  const saved = savedView('lens', '') || {}
  const known = (s) => s && store.spaces.some((x) => x.name === s)
  if (known(q.space)) store.space = String(q.space)
  else if (known(saved.space)) store.space = saved.space
  if (q.area !== undefined) lens.area = String(q.area || '')
  else if (saved.space === store.space && saved.area) lens.area = saved.area
  const cur = router.currentRoute.value
  router.replace({ path: cur.path, query: { ...cur.query, space: store.space || undefined, area: lens.area || undefined }, hash: cur.hash })
}

// Every navigation carries the lens. A URL that names one (a copied link, Back) sets it.
router.beforeEach((to) => {
  if (!store.ready || to.path.startsWith('/dev/')) return true
  const q = { ...to.query }
  let add = false
  if (q.space && q.space !== store.space && store.spaces.some((x) => x.name === q.space)) {
    store.space = String(q.space)
    if (q.area === undefined) lens.area = ''
    remember()
  } else if (!q.space && store.space) {
    q.space = store.space
    add = true
  }
  if (q.area !== undefined) {
    if (String(q.area || '') !== lens.area) {
      lens.area = String(q.area || '')
      remember()
    }
    if (!q.area) {
      delete q.area
      add = true
    }
  } else if (lens.area) {
    q.area = lens.area
    add = true
  }
  return add ? { path: to.path, query: q, hash: to.hash } : true
})
