// Capture on the phone (issue 50): what is captured or shared is sent at once when there is a connection, and kept in IndexedDB on
// this phone when there is not, then sent when the connection returns. Each capture carries its own id, which the server keeps as
// the capture's external_id (source "phone"), so a capture sent twice is one capture. The queue holds only what the person captured,
// never a server record, and logging out empties it. The service worker (lifeos/public/life-sw.js) uses the same database for shares.
import { reactive } from 'vue'
import { api } from './api'
import { store } from './store'
import { uploadFile } from './upload'

const DB = 'lifeos-phone'
const STORES = ['queue', 'shares']

export const queue = reactive({ waiting: 0, failed: 0 })

function openDb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1)
    r.onupgradeneeded = () => STORES.forEach((s) => !r.result.objectStoreNames.contains(s) && r.result.createObjectStore(s, { keyPath: 'id' }))
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}
async function run(store, mode, fn) {
  const db = await openDb()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(store, mode)
      const req = fn(tx.objectStore(store))
      tx.oncomplete = () => resolve(req?.result)
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } finally {
    db.close()
  }
}
export const listQueue = async () => ((await run('queue', 'readonly', (s) => s.getAll())) || []).sort((a, b) => a.created - b.created)
const putQueue = (entry) => run('queue', 'readwrite', (s) => s.put(entry))
const dropQueue = (id) => run('queue', 'readwrite', (s) => s.delete(id))
export const getShare = (id) => run('shares', 'readonly', (s) => s.get(id))
export const latestShare = async () => ((await run('shares', 'readonly', (s) => s.getAll())) || []).sort((a, b) => b.created - a.created)[0]
export const dropShare = (id) => run('shares', 'readwrite', (s) => s.delete(id))

export async function refreshQueue() {
  try {
    const rows = await listQueue()
    queue.waiting = rows.length
    queue.failed = rows.filter((r) => r.error).length
  } catch {
    queue.waiting = 0
    queue.failed = 0
  }
}

// logging out: nothing captured on this phone stays for the next person who signs in
export async function clearOffline() {
  for (const s of STORES) await run(s, 'readwrite', (st) => st.clear()).catch(() => {})
  queue.waiting = 0
  queue.failed = 0
}

// a fetch that never reached the server (offline, a dropped connection) is a TypeError; a refusal from the server is not
const isNetworkError = (e) => e instanceof TypeError

// Send one entry. It remembers how far it got (the item made, the files uploaded), so a retry never makes a second capture.
async function sendEntry(entry) {
  if (!entry.item) {
    const item = await api('inbox.create_item', { title: entry.title, source_type: entry.source_type, space: entry.space, instruction: entry.instruction,
      raw_text: entry.raw_text, source_url: entry.source_url, intent: entry.intent, source_system: 'phone', external_id: entry.id })
    entry.item = item.name
  }
  for (; entry.sent < entry.files.length; entry.sent++) {
    const f = entry.files[entry.sent]
    await uploadFile(new File([f.blob], f.name, { type: f.type }), 'Life Inbox Item', entry.item)
    await putQueue(entry).catch(() => {})
  }
}

let sending = false
export async function flush() {
  if (sending || !navigator.onLine || !store.user) return
  sending = true
  try {
    for (const entry of await listQueue()) {
      if (entry.user !== store.user) { await dropQueue(entry.id); continue } // someone else's: never send it
      try {
        await sendEntry(entry)
        await dropQueue(entry.id)
        window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
      } catch (e) {
        if (isNetworkError(e)) { await putQueue(entry).catch(() => {}); break }
        entry.error = String(e?.message || e).replace(/<[^>]+>/g, '').slice(0, 200)
        await putQueue(entry)
      }
    }
  } finally {
    sending = false
    await refreshQueue()
  }
}

// A capture: sent now, or kept on the phone. Returns 'sent' or 'queued'; any answer from the server that is a refusal throws.
// `capture` is { title, raw_text, instruction, source_url, intent, source_type, space, files: File[] }.
export async function submitCapture(capture) {
  const id = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const entry = { id, user: store.user, created: Date.now(), item: '', sent: 0, error: '', ...capture,
    files: (capture.files || []).map((f) => ({ name: f.name, type: f.type, blob: f })) }
  if (navigator.onLine) {
    try {
      await sendEntry(entry)
      return 'sent'
    } catch (e) {
      if (!isNetworkError(e)) throw e
    }
  }
  await putQueue(entry)
  await refreshQueue()
  return 'queued'
}

export function startQueue() {
  refreshQueue().then(flush)
  window.addEventListener('online', flush)
  setInterval(flush, 30000)
}
