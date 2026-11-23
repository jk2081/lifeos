// The review's shared state, for the weekly, monthly and 12-week reviews: the header (period, tabs done and openable), and one
// way to change anything that saves at once and says "Saved". Created by components/review/ReviewPage.vue and injected by its tabs.
import { inject, provide, reactive } from 'vue'
import { toast } from 'frappe-ui'
import { errorText } from './api'
import { reviewData } from '@/data/review'
import { canWrite, store } from './store'

export const TABS = [
  { value: 'library', label: 'Library', n: 1 },
  { value: 'tasks', label: 'Tasks', n: 2 },
  { value: 'goals', label: 'Goals', n: 3 },
  { value: 'reflect', label: 'Reflect', n: 4 },
]
const KEY = Symbol('review')

// kind: 'weekly' (`weekly.*`), 'monthly' or '12-weeks' (`periodic.*`, which also take the kind)
export function provideReview(kind = 'weekly') {
  const weekly = kind === 'weekly'
  const send = (method, args) => (weekly ? reviewData.weekly(method, { space: store.space, ...args }) : reviewData.periodic(method, { space: store.space, kind, ...args }))
  const r = reactive({ head: null, saving: '', readOnly: false, notDue: false, version: 0, kind })
  r.load = async () => {
    let head
    try { head = await send('get') } catch (e) { if (weekly) throw e; r.notDue = true; return null }
    if (canWrite() && !store.isAgent) {
      // resume or start (a site that refuses writes keeps the unsaved review, which reads the same)
      try { head = await send('start') } catch (e) { r.readOnly = true }
    } else r.readOnly = true
    r.head = head
    return head
  }
  // POST a change; the answer's header (when it has one) replaces ours, and every tab reloads what it shows
  r.act = async (method, args = {}, okMessage) => {
    r.saving = 'Saving…'
    try {
      const out = await send(method, args)
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
  r.read = (method, args = {}) => send(method, args)
  provide(KEY, r)
  return r
}

export const useReview = () => inject(KEY)
