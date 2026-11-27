// The record cache of frappe-ui's data layer (docStore, kept in IndexedDB), and what may be kept in it.
//
// Kept across reloads: only the DocTypes in KEEP, and never a record marked sensitive. Everything else (the Vault's documents,
// captures and anything with a file or a secret, notes, chats) lives in memory for the session and is never written to IndexedDB.
// The whole cache is cleared on logout and when the space changes.
import { docStore } from '@fui/docStore'
import { idbStore } from '@fui/idbStore'

export const KEEP = ['Life Task', 'Life Goal', 'Life Person']

// a stored key reads `ns:<user>:doc:v2:<DocType>/<name>` (or without the user part)
const doctypeOf = (key) => /doc:[^:/]+:([^/]+)\//.exec(String(key))?.[1]

let installed = false
export function installDocCache() {
  if (installed) return
  installed = true
  const set = idbStore.set.bind(idbStore)
  const setMany = idbStore.setMany.bind(idbStore)
  const allowed = (key, doc) => !doctypeOf(key) || (KEEP.includes(doctypeOf(key)) && !doc?.is_sensitive)
  idbStore.set = (key, data) => (allowed(key, data) ? set(key, data) : Promise.resolve(null))
  idbStore.setMany = (data) => setMany(Object.fromEntries(Object.entries(data).filter(([k, v]) => allowed(k, v))))
}

// every record the data layer holds, in memory and on the device
export async function clearDocCache() {
  try { await docStore.clearAll() } catch (e) { /* nothing was kept */ }
  // everything frappe-ui keeps in its store (records, lists, DocType meta); the phone's capture queue has a database of its own
  await Promise.all((await idbStore.keys()).map((k) => idbStore.delete(k)))
}
