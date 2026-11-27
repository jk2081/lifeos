// A record in a pane, from frappe-ui's data layer: it shows from the cache at once, is read again for the current version, follows
// the server when the record is saved elsewhere, and is written with `save` (Frappe's own validation and hooks run).
import { onBeforeUnmount, watch } from 'vue'
import { useDoc } from 'frappe-ui'
import { watchRecord } from '@/lib/realtime'

/**
 * `options.fetchExtra()` reads what the record does not hold (names, badges); `options.show(doc, extra)` draws the pane from both,
 * and `options.onMissing()` runs when the record cannot be read at all. `loadExtra()` reads the extra part again.
 */
export function useRecord(doctype, name, { fetchExtra, show, onMissing } = {}) {
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
  let extra = {}
  const draw = () => { if (rec.doc && show) show(rec.doc, extra) }
  async function loadExtra() {
    try {
      extra = await fetchExtra()
      draw()
    } catch (e) {
      if (!rec.doc) onMissing?.()
    }
  }
  /** Replace the extra part with a newer one (a method that returns it) and draw again. */
  const setExtra = (more) => { extra = { ...extra, ...more }; draw() }
  if (show) watch(() => rec.doc, draw, { deep: true })
  watch(() => rec.error, (e) => { if (e && !rec.doc) onMissing?.() })
  const save = (values) => rec.setValue.submit(values)
  return { rec, save, loadExtra, setExtra, draw }
}
