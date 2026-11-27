// A record in a pane, from frappe-ui's data layer: it shows from the cache at once, is read again for the current version, follows
// the server when the record is saved elsewhere, and is written with `save` (Frappe's own validation and hooks run).
import { onBeforeUnmount, watch } from 'vue'
import { useDoc } from 'frappe-ui'
import { watchRecord } from '@/lib/realtime'

export function useRecord(doctype, name) {
  const rec = useDoc({ doctype, name: () => (typeof name === 'function' ? name() : name), staleOnError: true })
  let stop = null
  const follow = () => {
    stop?.()
    const n = typeof name === 'function' ? name() : name
    // a change on the server (or a poll while there is no socket): read again unless this copy is already as new
    stop = n ? watchRecord(doctype, n, (d) => { if (!d || !rec.doc || d.modified !== rec.doc.modified) rec.reload() }) : null
  }
  if (typeof name === 'function') watch(name, follow)
  follow()
  onBeforeUnmount(() => stop?.())
  /** Write fields through the REST API and resolve with the saved record. */
  const save = (values) => rec.setValue.submit(values)
  return { rec, save }
}
