// Remembered list views: one saved state per user, per screen, per space.
// The server holds them (Life View State), so the phone and the laptop agree. A copy in localStorage lets a list open
// at once; the server copy wins when it arrives. Saving waits a second after the last change and never blocks the screen.
import { reactive } from 'vue'
import { api } from './api'
import { store } from './store'

const views = reactive({ map: {}, loaded: false })
const timers = {}
const pending = {} // saves that are waiting for their second
let waiting = []
const lsKey = () => `lifeos-views:${store.user || ''}`
const key = (screen, space = store.space) => `${screen}|${space || ''}`

function readLocal() {
  try {
    return JSON.parse(localStorage.getItem(lsKey()) || '{}') || {}
  } catch {
    return {}
  }
}
function writeLocal() {
  try {
    localStorage.setItem(lsKey(), JSON.stringify(views.map))
  } catch { /* a full or blocked store only costs the instant open */ }
}

/** Read every saved state of this user in one call. Called once when the app starts; agents have none. */
export async function loadViews() {
  views.map = readLocal()
  if (store.isAgent) {
    views.loaded = true
    return
  }
  try {
    const server = await api('views.get_all')
    // a change made in this tab while the call was on its way is newer than the server copy
    const pending = Object.fromEntries(Object.keys(timers).map((k) => [k, views.map[k]]))
    views.map = { ...server, ...pending }
    writeLocal()
  } catch { /* offline or refused: the local copy stays */ }
  views.loaded = true
  waiting.splice(0).forEach((fn) => fn())
}

export const viewsLoaded = () => views.loaded
/** Run `fn` once the server copy is in. At once when it already is. */
export function whenViewsLoaded(fn) {
  if (views.loaded) fn()
  else waiting.push(fn)
}
export const savedView = (screen) => views.map[key(screen)] || null

export function saveView(screen, state) {
  if (store.isAgent) return
  const k = key(screen)
  if (JSON.stringify(views.map[k] || null) === JSON.stringify(state)) return
  views.map[k] = state
  writeLocal()
  const space = store.space
  clearTimeout(timers[k])
  pending[k] = { screen, space, state }
  timers[k] = setTimeout(() => {
    delete timers[k]
    delete pending[k]
    api('views.save', { screen, space, state }).catch(() => {}) // the next change tries again
  }, 1000)
}

// A change made in the last second before the tab closes or reloads is sent as the page goes, so it is not lost.
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    for (const k of Object.keys(pending)) {
      clearTimeout(timers[k])
      delete timers[k]
      fetch('/api/method/lifeos.api.views.save', { method: 'POST', keepalive: true, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' }, body: JSON.stringify(pending[k]) }).catch(() => {})
      delete pending[k]
    }
  })
}
