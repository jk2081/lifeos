// The monthly and the 12-week review (issue 47): the weekly review's shared state (lib/review.js) over `periodic.*`.
// One of the two kinds, from the route: 'monthly' or '12-weeks'.
import { reactive } from 'vue'
import { toast } from 'frappe-ui'
import { api, errorText } from './api'
import { canWrite, store } from './store'
import { provideShell } from './review'

export function providePeriodic(kind) {
  const r = reactive({ head: null, saving: '', readOnly: false, notDue: false, version: 0, kind })
  r.load = async () => {
    let head
    try { head = await api('periodic.get', { space: store.space, kind }) } catch (e) { r.notDue = true; return null }
    if (canWrite() && !store.isAgent) {
      try { head = await api('periodic.start', { space: store.space, kind }) } catch (e) { r.readOnly = true }
    } else r.readOnly = true
    r.head = head
    return head
  }
  // POST a change; the answer's header replaces ours, and every tab reloads what it shows
  r.act = async (method, args = {}, okMessage) => {
    r.saving = 'Saving…'
    try {
      const out = await api(`periodic.${method}`, { space: store.space, kind, ...args })
      if (out?.header) r.head = out.header
      r.saving = 'Saved'
      r.version += 1
      if (okMessage) toast.success(okMessage)
      return out
    } catch (e) {
      r.saving = ''
      toast.error(errorText(e))
      throw e
    }
  }
  r.read = (method, args = {}) => api(`periodic.${method}`, { space: store.space, kind, ...args })
  provideShell(r)
  return r
}
