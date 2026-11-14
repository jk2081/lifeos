import { reactive, watch } from 'vue'
import { api } from './api'

export const store = reactive({
  ready: false,
  user: null,
  fullName: '',
  isAdmin: false,
  spaces: [],
  space: localStorage.getItem('lifeos-space') || '',
  counts: { to_review: 0 },
  settings: {},
  today: '',
  searchOpen: false,
  quickAdd: false,
})

export async function boot() {
  const data = await api('session.boot')
  Object.assign(store, {
    user: data.user, fullName: data.full_name, isAdmin: data.is_admin, spaces: data.spaces,
    settings: data.settings, today: data.today,
  })
  if (!data.spaces.find((s) => s.name === store.space)) store.space = data.default_space || data.spaces[0]?.name || ''
  store.ready = true
  refreshCounts()
}

export async function refreshCounts() {
  if (!store.space) return
  try {
    store.counts = await api('session.counts', { space: store.space })
  } catch (e) { /* the badge is not worth an error */ }
}

watch(() => store.space, (v) => {
  localStorage.setItem('lifeos-space', v || '')
  if (store.ready) refreshCounts()
})

export function canWrite() {
  return store.spaces.find((s) => s.name === store.space)?.access === 'Write'
}
