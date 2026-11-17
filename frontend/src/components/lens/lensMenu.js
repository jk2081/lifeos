// The lens picker's menu (UX fixes, set 6): the user's spaces, then "All of life" and every active area with its
// sub-areas indented, each with its colour dot, then "Pin areas to the sidebar" and "Manage areas". The sidebar's header
// shows it as a dropdown; the phone shows the same entries in a sheet (LensSheet.vue).
import { computed, h } from 'vue'
import router from '@/router'
import { store } from '@/lib/store'
import { dotClass, lens, lensTree, setLens } from '@/lib/lens'

const dot = (a) => () => h('span', { class: ['size-2 shrink-0 rounded-full', dotClass(a)], style: a.depth ? { marginLeft: `${a.depth * 1}rem` } : undefined, 'aria-hidden': 'true' })
const letter = (s) => () => h('span', { class: 'grid size-5 shrink-0 place-items-center rounded-[5px] bg-surface-gray-3 text-xs font-medium text-ink-gray-7', 'aria-hidden': 'true' }, (s || '?').charAt(0).toUpperCase())

/** The entries, for the dropdown and the sheet alike: { key, group, label, selected, depth, area, space, onClick }. */
export const lensEntries = computed(() => [
  ...store.spaces.map((s) => ({ key: 'space:' + s.name, group: 'Space', label: s.name, space: s.name, selected: s.name === store.space,
    onClick: () => setLens({ space: s.name }) })),
  { key: 'area:', group: 'Area', label: 'All of life', selected: !lens.area, onClick: () => setLens({ area: '' }) },
  ...lensTree.value.map((a) => ({ key: 'area:' + a.name, group: 'Area', label: a.area_name, area: a, depth: a.depth, selected: lens.area === a.name,
    onClick: () => setLens({ area: a.name }) })),
  { key: 'pin', group: 'more', label: 'Pin areas to the sidebar', icon: 'lucide-pin', onClick: () => router.push({ path: '/settings', query: { tab: 'areas', pin: 1 } }) },
  { key: 'manage', group: 'more', label: 'Manage areas', icon: 'lucide-folder-cog', onClick: () => router.push({ path: '/settings', query: { tab: 'areas' } }) },
])

/** The same entries as frappe-ui menu groups, for the sidebar's header. */
export const lensMenu = computed(() => {
  const opt = (e) => ({ label: e.label, selected: e.selected, icon: e.icon, onClick: e.onClick, 'data-lens-item': e.key,
    slots: e.area ? { prefix: dot(e.area) } : e.space ? { prefix: letter(e.space) } : undefined })
  const by = (g) => lensEntries.value.filter((e) => e.group === g).map(opt)
  return [{ group: 'Space', options: by('Space') }, { group: 'Area', options: by('Area') }, { group: 'More', hideLabel: true, options: by('more') }]
})
