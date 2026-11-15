// The record pane: which record is open is held in the URL as ?open=<type>:<name>, so Back closes it and a reload reopens it.
import { computed, onMounted, onUnmounted, reactive } from 'vue'
import router from '@/router'

export const TYPES = {
  task: { label: 'Task', doctype: 'Life Task' },
  inbox: { label: 'Inbox item', doctype: 'Life Inbox Item' },
  note: { label: 'Note', doctype: 'Life Note' },
  vault: { label: 'Vault document', doctype: 'Life Vault Document' },
  project: { label: 'Project', doctype: 'Life Project' },
  goal: { label: 'Goal', doctype: 'Life Goal' },
  page: { label: 'Journal page', doctype: 'Life Journal Page' },
  chat: { label: 'AI chat', doctype: 'Life Chat Log' },
  event: { label: 'Event', doctype: 'Event' },
  date: { label: 'Important date', doctype: 'Life Important Date' },
  checkin: { label: 'Check-in', doctype: 'Life Check-in' },
  month: { label: 'Month plan', doctype: 'Life Month Plan' },
  day: { label: 'Day' },
}
const BY_DOCTYPE = Object.fromEntries(Object.entries(TYPES).filter(([, t]) => t.doctype).map(([k, t]) => [t.doctype, k]))
// links written before the pane existed: /tasks?open=NAME, /vault?open=NAME, /chats?open=NAME
const LEGACY = { Tasks: 'task', Vault: 'vault', Chats: 'chat' }

// the rows of the list on screen, in order, so the pane can step to the previous and next one
export const paneNav = reactive({ rows: [] })

export function parseOpen(route) {
  const v = route.query.open
  if (!v) return null
  const s = String(v)
  const i = s.indexOf(':')
  if (i > 0 && TYPES[s.slice(0, i)]) return { type: s.slice(0, i), name: s.slice(i + 1), ref: s }
  const type = LEGACY[route.name]
  return type ? { type, name: s, ref: `${type}:${s}` } : null
}
export const current = computed(() => parseOpen(router.currentRoute.value))
export const refOf = (doctype, name) => (BY_DOCTYPE[doctype] ? `${BY_DOCTYPE[doctype]}:${name}` : null)

// A route the server gives for a record (links.route_of), turned into a pane reference where there is one.
export function refOfRoute(path) {
  const p = String(path || '').replace(/^\/life/, '')
  let m
  if ((m = /^\/(tasks|vault|chats)\?open=([^&]+)/.exec(p))) return `${{ tasks: 'task', vault: 'vault', chats: 'chat' }[m[1]]}:${decodeURIComponent(m[2])}`
  if ((m = /^\/library\/([^/?]+)$/.exec(p))) return `note:${m[1]}`
  if ((m = /^\/inbox\/([^/?]+)$/.exec(p))) return `inbox:${m[1]}`
  if ((m = /^\/projects\/([^/?]+)$/.exec(p))) return `project:${m[1]}`
  if ((m = /^\/journal\/goals\/([^/?]+)$/.exec(p))) return `goal:${m[1]}`
  if ((m = /^\/journal\/pages\/([^/?]+)$/.exec(p))) return `page:${m[1]}`
  return null
}

// Open a record in the pane over the current screen. A second record replaces the first, so Back still closes the pane.
export function openRef(ref, extra = {}) {
  if (!ref) return
  const r = router.currentRoute.value
  const query = { ...r.query, focus: undefined, ptab: undefined, ...extra, open: ref }
  return parseOpen(r) ? router.replace({ query }) : router.push({ query })
}
// Open the record a server route points to: in the pane when it has one, else by going there.
export function openRoute(path) {
  const ref = refOfRoute(path)
  return ref ? openRef(ref) : router.push(String(path || '/').replace(/^\/life/, '') || '/')
}
export function closePane() {
  const r = router.currentRoute.value
  if (!r.query.open) return
  const target = router.resolve({ path: r.path, query: { ...r.query, open: undefined, focus: undefined, ptab: undefined } })
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
