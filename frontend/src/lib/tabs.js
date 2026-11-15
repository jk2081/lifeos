// Tabs: the URL rule, lazy loading, and the [ and ] keys. Every tab bar in the app is components/TabBar.vue, and its
// state comes from here.
//
// The open tab lives in the URL. Page and record-page tabs use `tab=`; tabs inside the record pane use `ptab=`, so the
// pane and the page behind it do not collide; a list's state tabs use the short parameter of the field they filter
// (`status=`, see ListView). The first tab is the default and adds nothing to the URL.
import { computed, onMounted, onUnmounted, reactive, toValue, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * The open tab of a screen, held in the URL.
 * @param key   the query parameter: 'tab' for a page, 'ptab' for the record pane
 * @param tabs  [{ value, label, count }], or a ref or getter of it. The first is the default.
 * @param options.replace  change the tab without a new history entry (the pane does: Back must close it in one step)
 * @returns { current, set, visited, shown }  `visited` is the set of tabs opened since the screen opened: load a tab
 *          when `shown(value)` first turns true and keep it loaded after that.
 */
export function useUrlTab(key = 'tab', tabs = [], { replace = false, fallback = null } = {}) {
  const route = useRoute()
  const router = useRouter()
  const all = () => toValue(tabs) || []
  // the tab with nothing in the URL: the first, or `fallback` (a getter) where the default depends on the record
  const first = () => (fallback && all().some((t) => t.value === toValue(fallback)) ? toValue(fallback) : all()[0]?.value)
  const current = computed(() => {
    const v = route.query[key] ? String(route.query[key]) : ''
    return all().some((t) => t.value === v) ? v : first()
  })
  function set(value) {
    if (value === current.value) return
    const query = { ...route.query, [key]: value === first() ? undefined : value }
    return replace ? router.replace({ query }) : router.push({ query })
  }
  const visited = reactive(new Set())
  watch(current, (v) => v !== undefined && visited.add(v), { immediate: true })
  const shown = (value) => visited.has(value)
  return { current, set, visited, shown }
}

// ---- [ and ]: the previous and next tab. The pane's tab bar wins over the page's while the pane is open. ----
const bars = []
/** Called by TabBar. `bar` is { level: 1 (page) | 2 (pane), step(direction) }. */
export function useTabKeys(bar) {
  onMounted(() => bars.push(bar))
  onUnmounted(() => {
    const i = bars.indexOf(bar)
    if (i >= 0) bars.splice(i, 1)
  })
}
/** Move to the previous (-1) or next (1) tab of the tab bar on screen. True when there was one. */
export function stepTab(direction) {
  let best = null
  for (const b of bars) if (!best || b.level >= best.level) best = b
  if (!best) return false
  best.step(direction)
  return true
}
