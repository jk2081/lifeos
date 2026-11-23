// The weekly review's shared state (set 8): the header (period, tabs done and openable), and one way to change anything
// that saves at once and says "Saved". Created by components/weekly/ReviewPage.vue and injected by its tabs.
import { inject, provide, reactive } from 'vue'
import { toast } from 'frappe-ui'
import { api, errorText } from './api'
import { canWrite, store } from './store'

export const TABS = [
  { value: 'library', label: 'Library', n: 1 },
  { value: 'tasks', label: 'Tasks', n: 2 },
  { value: 'goals', label: 'Goals', n: 3 },
  { value: 'reflect', label: 'Reflect', n: 4 },
]
const KEY = Symbol('review')

export function provideReview() {
  const r = reactive({ head: null, saving: '', readOnly: false, version: 0 })
  r.load = async () => {
    let head = await api('weekly.get', { space: store.space })
    if (canWrite() && !store.isAgent) {
      // resume or start (a site that refuses writes keeps the unsaved review, which reads the same)
      try { head = await api('weekly.start', { space: store.space }) } catch (e) { r.readOnly = true }
    } else r.readOnly = true
    r.head = head
    return head
  }
  // POST a change; the answer's header (when it has one) replaces ours, and every tab reloads what it shows
  r.act = async (method, args = {}, okMessage) => {
    r.saving = 'Saving…'
    try {
      const out = await api(`weekly.${method}`, { space: store.space, ...args })
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
  r.read = (method, args = {}) => api(`weekly.${method}`, { space: store.space, ...args })
  provide(KEY, r)
  return r
}

export const useReview = () => inject(KEY)
// the monthly and 12-week reviews (issue 47) provide their own state of the same shape, so the shell's header and footer are shared
export const provideShell = (r) => provide(KEY, r)
