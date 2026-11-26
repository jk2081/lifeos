// The record pane: which record is open is held in the URL as ?open=<type>:<name>, so Back closes it and a reload reopens it.
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
}
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

// Open a record in the pane over the current screen. A second record replaces the first, so Back still closes the pane.
export function openRef(ref, extra = {}) {
  if (!ref) return
  const r = router.currentRoute.value
  // `back` is the list a record was opened from (the pane's Back button); a record opened from anywhere else has none
  const from = parseOpen(r)
  const query = { ...r.query, focus: undefined, ptab: undefined, back: from?.type === 'list' ? from.ref : undefined, ...extra, open: ref }
  return parseOpen(r) ? router.replace({ query }) : router.push({ query })
}
// Open the record a server route points to: in the pane when it has one, else by going there.
export function openRoute(path) {
  const ref = refOfRoute(path)
  return ref ? openRef(ref) : router.push(String(path || '/').replace(/^\/life/, '') || '/')
}
// Esc reaches the pane twice on a phone (our handler and the sheet's own), and router.back() is not instant: a second call would go back again
let closing = false
router.afterEach(() => { closing = false })
export function closePane() {
  const r = router.currentRoute.value
  if (!r.query.open || closing) return
  closing = true
  setTimeout(() => { closing = false }, 600)
  const target = router.resolve({ path: r.path, query: { ...r.query, open: undefined, back: undefined, focus: undefined, ptab: undefined } })
  if (window.history.state && window.history.state.back === target.fullPath) router.back()
  else router.replace(target)
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
