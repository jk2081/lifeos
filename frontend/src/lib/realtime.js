// Frappe's realtime socket, opened once. A record saved anywhere (the Brain, Hermes, Chat, another session) sends `doc_update` to the
// pane that has it open and `list_update` to the DocTypes this app watches; the screens reload on the same `lifeos-record-changed`
// event a change made here sends. When the socket is not connected (a bench without the socket server) an open record is read again
// every few seconds instead, so a pane never stays on an old version.
import { reactive } from 'vue'
import { io } from 'socket.io-client'
import { recordChanged } from '@/lib/pane'

export const live = reactive({ connected: false })
export const WATCHED = ['Life Task', 'Life Goal', 'Life Person', 'Life Note', 'Life Inbox Item', 'Life Chat Log', 'Life Vault Document']
export const POLL_MS = 1500

let socket = null
let me = ''
const open = new Map() // 'Doctype/name' -> Set of callbacks
let changed = null

const keyOf = (doctype, name) => `${doctype}/${name}`
function subscribeAll() {
  for (const d of WATCHED) socket.emit('doctype_subscribe', d)
  for (const k of open.keys()) socket.emit('doc_subscribe', ...k.split(/\/(.*)/s).slice(0, 2))
}

export function startRealtime(user) {
  me = user || me
  if (socket || typeof window === 'undefined' || !window.site_name) return
  socket = io(`${window.location.origin}/${window.site_name}`, { withCredentials: true, transports: ['websocket'], reconnectionDelayMax: 30000 })
  socket.on('connect', () => { live.connected = true; subscribeAll() })
  socket.on('disconnect', () => { live.connected = false })
  socket.on('doc_update', (d) => open.get(keyOf(d.doctype, d.name))?.forEach((cb) => cb(d)))
  socket.on('list_update', (d) => {
    if (d.user && d.user === me) return // a change made here already told the screens
    clearTimeout(changed)
    changed = setTimeout(() => recordChanged(''), 400)
  })
}
export function stopRealtime() {
  socket?.disconnect()
  socket = null
  live.connected = false
}

/** Call `cb` when this record changes on the server. Returns the function that stops. */
export function watchRecord(doctype, name, cb) {
  const k = keyOf(doctype, name)
  if (!open.has(k)) open.set(k, new Set())
  open.get(k).add(cb)
  if (socket?.connected) socket.emit('doc_subscribe', doctype, name)
  const poll = setInterval(() => { if (!live.connected && !document.hidden) cb(null) }, POLL_MS)
  return () => {
    clearInterval(poll)
    const set = open.get(k)
    set?.delete(cb)
    if (set && !set.size) { open.delete(k); if (socket?.connected) socket.emit('doc_unsubscribe', doctype, name) }
  }
}
