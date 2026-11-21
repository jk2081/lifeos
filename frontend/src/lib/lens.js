// Issue 46: there is no lens. What is left of it:
//  - `?area=` names the area a page narrows to. Each page reads it as its own area filter, and it is not carried to the
//    next page; a page without an area filter of its own shows it as a chip in its header (clearArea removes it).
//  - `?space=` is honoured only when the site has two or more spaces (a one-space site never shows a space), and then
//    it is carried to every page and remembered, as before.
// Choosing an area includes its sub-areas; the server does that (lifeos.api.utils.area_filter).
import { computed } from 'vue'
import router from '@/router'
import { store } from './store'
import { lookups } from './lookups'
import { saveView, savedView } from './views'

// the state is the store's lensArea (the page's area from the URL), so lib/store.js can count under it without importing this module
export const lens = { get area() { return store.lensArea }, set area(v) { store.lensArea = v || '' } }

// the dot of an area: a frappe-ui surface token, written out so Tailwind keeps every class
const DOTS = {
  blue: 'bg-surface-blue-7', green: 'bg-surface-green-7', amber: 'bg-surface-amber-7', red: 'bg-surface-red-7', violet: 'bg-surface-violet-7',
  teal: 'bg-surface-teal-7', orange: 'bg-surface-orange-7', pink: 'bg-surface-pink-7', cyan: 'bg-surface-cyan-7', gray: 'bg-surface-gray-7',
}
export const dotClass = (area) => DOTS[area?.colour] || DOTS.gray

export const lensArea = computed(() => (lens.area && (lookups.areas || []).find((a) => a.name === lens.area)) || null)
export const lensAreaName = computed(() => (lens.area ? lensArea.value?.area_name || 'This area' : 'All of life'))

/** True when the site has two or more spaces that are not archived: only then is a space shown anywhere. */
export const manySpaces = computed(() => store.spaces.length > 1)

const remember = () => saveView('lens', { space: store.space }, '')
const known = (s) => s && store.spaces.some((x) => x.name === s)

/** Change the space (two or more spaces only). */
export function setSpace(space) {
  if (!manySpaces.value || space === store.space) return
  store.space = space
  lens.area = ''
  remember()
  const cur = router.currentRoute.value
  router.push({ path: cur.path, query: { ...cur.query, space, area: undefined }, hash: cur.hash })
}
/** Remove the page's area filter. */
export function clearArea() {
  const cur = router.currentRoute.value
  const { area: _a, ...query } = cur.query
  lens.area = ''
  router.push({ path: cur.path, query, hash: cur.hash })
}

/** Once the session is known: take the space from the URL, or the remembered one (two or more spaces only). */
export async function initLens() {
  // the first navigation must be resolved first: before it, the current route is the start route "/"
  await router.isReady()
  const q = router.currentRoute.value.query
  if (manySpaces.value) {
    const saved = savedView('lens', '') || {}
    if (known(q.space)) store.space = String(q.space)
    else if (known(saved.space)) store.space = saved.space
  }
  lens.area = String(q.area || '')
  if (manySpaces.value) {
    const cur = router.currentRoute.value
    router.replace({ path: cur.path, query: { ...cur.query, space: store.space || undefined }, hash: cur.hash })
  }
}

// Every page takes its area from its own URL. On a site with two or more spaces the space is carried to every page.
router.beforeEach((to) => {
  if (!store.ready || to.path.startsWith('/dev/')) return true
  lens.area = String(to.query.area || '')
  if (!manySpaces.value) return true
  if (known(to.query.space) && to.query.space !== store.space) {
    store.space = String(to.query.space)
    remember()
    return true
  }
  if (!to.query.space && store.space) return { path: to.path, query: { ...to.query, space: store.space }, hash: to.hash }
  return true
})
