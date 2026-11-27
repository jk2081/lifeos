// The Drawer's layers (issue 128): the top layer is held in the URL as ?open=<type>:<name>, the layers under it in ?under=<ref>|<ref> (at most 4),
// so a reload rebuilds the stack and the browser's Back pops one layer. A layer is a chat (`ask:<thread>` or `ask:new`), a record or a list.
import { computed, onMounted, onUnmounted, reactive } from 'vue'
import router from '@/router'

export const TYPES = {
  task: { place: 'Goals', label: 'Task', doctype: 'Life Task' },
  inbox: { place: 'Brain', label: 'Inbox item', doctype: 'Life Inbox Item' },
  source: { place: 'Brain', label: 'Source' }, // an inbox item seen as a source, from the Sources screen
  change: { place: 'Library', label: 'Wiki change' },
  note: { place: 'Library', label: 'Note', doctype: 'Life Note' },
  vault: { place: 'Library', label: 'Vault document', doctype: 'Life Vault Document' },
  goal: { place: 'Goals', label: 'Goal', doctype: 'Life Goal' },
  chat: { place: 'Library', label: 'AI chat', doctype: 'Life Chat Log' },
  event: { place: 'Today', label: 'Event', doctype: 'Event' },
  date: { place: 'Today', label: 'Important date' },
  day: { place: 'Today', label: 'Day' },
  person: { place: 'Library', label: 'Person' },
  list: { place: 'Today', label: 'List' }, // issue 123: what a number counts (`list:needs-you`), shown by dashboard.list
  focus: { place: 'Goals', label: 'Focus' }, // issue 128: a focus's standard, principles and goals
  ask: { place: 'Chat', label: 'Chat' }, // issue 128: the chat as a layer (`ask:new` or `ask:<thread>`); `chat:` is a chat an assistant logged
}
export const MAX_UNDER = 4
export const listRows = reactive({}) // the row each list opened last, so Back finds it marked again
const BY_DOCTYPE = Object.fromEntries(Object.entries(TYPES).filter(([, t]) => t.doctype).map(([k, t]) => [t.doctype, k]))

// the rows of the list on screen, in order, so the pane can step to the previous and next one
export const paneNav = reactive({ rows: [] })

export function parseOpen(route) {
  const v = route.query.open
  if (!v) return null
  const s = String(v)
  const i = s.indexOf(':')
  return i > 0 && TYPES[s.slice(0, i)] ? { type: s.slice(0, i), name: s.slice(i + 1), ref: s } : null
}
export const current = computed(() => parseOpen(router.currentRoute.value))
function parseRef(s) {
  const i = s.indexOf(':')
  return i > 0 && TYPES[s.slice(0, i)] ? { type: s.slice(0, i), name: s.slice(i + 1), ref: s } : null
}
// the layers under the top one, bottom first
export const underOf = (route) => String(route.query.under || '').split('|').filter(Boolean).map(parseRef).filter(Boolean).slice(-MAX_UNDER)
/** Every layer of the Drawer, bottom first; the last one is on top. */
export const stack = computed(() => {
  const r = router.currentRoute.value
  const top = parseOpen(r)
  return top ? [...underOf(r), top] : []
})
const LAYER_QUERY = { focus: undefined, ptab: undefined, back: undefined }
const queryWith = (route, layers) => ({ ...route.query, ...LAYER_QUERY, open: layers.length ? layers[layers.length - 1] : undefined,
  under: layers.length > 1 ? layers.slice(0, -1).join('|') : undefined })
// a click inside the Drawer opens the next layer on top of its own; a click anywhere else on the screen replaces the layers
let clickInDrawer = false
if (typeof document !== 'undefined') {
  document.addEventListener('click', (e) => { clickInDrawer = !!e.target.closest?.('[data-drawer-host]'); setTimeout(() => { clickInDrawer = false }, 0) }, true)
}
export const refOf = (doctype, name) => (BY_DOCTYPE[doctype] ? `${BY_DOCTYPE[doctype]}:${name}` : null)

// A route the server gives for a record (links.route_of), turned into a pane reference where there is one.
export function refOfRoute(path) {
  const p = String(path || '').replace(/^\/life/, '')
  let m
  if ((m = /[?&]open=([a-z]+(?:%3A|:)[^&]+)/.exec(p))) return decodeURIComponent(m[1])
  if ((m = /^\/library\/([^/?]+)$/.exec(p))) return `note:${m[1]}`
  if ((m = /^\/goals\/([^/?]+)$/.exec(p))) return `goal:${m[1]}`
  return null
}

// Open a record in the Drawer over the current screen. From inside the Drawer (or with `push`) it goes on top of the layer there, with Back to it;
// from the screen it replaces the layers, so Close still empties the Drawer.
export function openRef(ref, extra = {}) {
  if (!ref) return
  const r = router.currentRoute.value
  const { push, ...query } = extra
  const layers = stack.value.map((l) => l.ref)
  if (layers.length && layers[layers.length - 1] === ref) return
  if (layers.length && (push || clickInDrawer)) {
    const next = [...layers.filter((x) => x !== ref), ref].slice(-(MAX_UNDER + 1))
    return router.push({ query: { ...queryWith(r, next), ...query } })
  }
  const target = { query: { ...queryWith(r, [ref]), ...query } }
  return layers.length ? router.replace(target) : router.push(target)
}
// The layer at the top changes for the next or previous row of its list (j and k): the layers under it stay.
export function swapTop(ref) {
  const r = router.currentRoute.value
  const layers = stack.value.map((l) => l.ref)
  layers[layers.length - 1] = ref
  return router.replace({ query: queryWith(r, layers) })
}
// Open the record a server route points to: in the pane when it has one, else by going there.
export function openRoute(path) {
  const ref = refOfRoute(path)
  return ref ? openRef(ref) : router.push(String(path || '/').replace(/^\/life/, '') || '/')
}
// The chat stays open while the owner goes from one screen to another (issue 120): a move to another path that names no layer carries the chat layer along
router.beforeEach((to, from) => {
  if (to.query.open || to.path === from.path || !from.query.open) return
  const ask = [...underOf(from), parseOpen(from)].filter(Boolean).find((l) => l.type === 'ask')
  if (ask) return { ...to, query: { ...to.query, open: ask.ref }, replace: true }
})
// Esc reaches the Drawer twice on a phone (our handler and the sheet's own), and router.back() is not instant: a second call would go back again
let closing = false
router.afterEach(() => { closing = false })
function goTo(layers) {
  if (closing) return
  closing = true
  setTimeout(() => { closing = false }, 600)
  const target = router.resolve({ path: router.currentRoute.value.path, query: queryWith(router.currentRoute.value, layers) })
  if (window.history.state && window.history.state.back === target.fullPath) router.back()
  else router.replace(target)
}
/** Close: the Drawer is emptied. */
export function closePane() {
  if (router.currentRoute.value.query.open) goTo([])
}
/** Back: the top layer goes, the one under it shows. With none under it, the Drawer closes. */
export function popLayer() {
  const layers = stack.value.map((l) => l.ref)
  if (layers.length) goTo(layers.slice(0, -1))
}
/** Take one layer out of the stack wherever it is (the chat is closed while a record is on top of it). */
export function dropLayer(type) {
  const layers = stack.value.map((l) => l.ref)
  const left = layers.filter((x) => !x.startsWith(type + ':'))
  if (left.length === layers.length) return
  if (layers[layers.length - 1].startsWith(type + ':')) return popLayer()
  router.replace({ query: queryWith(router.currentRoute.value, left) })
}

// Screens reload when a record changes in the pane or a task is added from anywhere.
export function recordChanged(ref) {
  window.dispatchEvent(new CustomEvent('lifeos-record-changed', { detail: ref }))
}
export function onRecordChanged(fn) {
  const run = (e) => fn(e.detail)
  onMounted(() => {
    window.addEventListener('lifeos-record-changed', run)
    window.addEventListener('lifeos-task-added', run)
  })
  onUnmounted(() => {
    window.removeEventListener('lifeos-record-changed', run)
    window.removeEventListener('lifeos-task-added', run)
  })
}
