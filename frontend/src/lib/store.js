import { reactive, watch } from 'vue'
import { api } from './api'
import { loadViews } from './views'

export const store = reactive({
  ready: false,
  user: null,
  fullName: '',
  isAdmin: false,
  isAgent: false,
  spaces: [],
  space: localStorage.getItem('lifeos-space') || '',
  counts: { to_review: 0, due: 0 },
  settings: {},
  today: '',
  searchOpen: false,
  quickAdd: false,
  newKind: '', // the New menu's note, goal or idea dialog
  lensArea: '', // the lens's area (lib/lens.js keeps it), here so the counts can follow it without importing the lens
})

export async function boot({ beforeReady } = {}) {
  const data = await api('session.boot')
  Object.assign(store, {
    user: data.user, fullName: data.full_name, isAdmin: data.is_admin, isAgent: data.is_agent, spaces: data.spaces,
    settings: data.settings, today: data.today,
  })
  if (!data.spaces.find((s) => s.name === store.space)) store.space = data.default_space || data.spaces[0]?.name || ''
  // saved list views: the local copy is used at once, and the server copy for at most a moment before the first screen draws
  await Promise.race([loadViews(), new Promise((r) => setTimeout(r, 1200))])
  if (beforeReady) beforeReady() // the lens: from the URL or remembered (lib/lens.js)
  store.ready = true
  refreshCounts()
}

export async function refreshCounts() {
  if (!store.space) return
  try {
    store.counts = await api('session.counts', { space: store.space, area: store.lensArea || undefined })
  } catch (e) { /* the badge is not worth an error */ }
}

// a change that can move the counts asks for them again, at most once in a short while
let stale = null
if (typeof window !== 'undefined') {
  const later = () => { clearTimeout(stale); stale = setTimeout(refreshCounts, 250) }
  window.addEventListener('lifeos-counts-stale', later)
  window.addEventListener('lifeos-record-changed', later)
  window.addEventListener('lifeos-task-added', later)
}

watch(() => store.space, (v) => localStorage.setItem('lifeos-space', v || ''))
watch(() => [store.space, store.lensArea], () => { if (store.ready) refreshCounts() })

export function canWrite() {
  return store.spaces.find((s) => s.name === store.space)?.access === 'Write'
}
