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

export const PILE_TEXT = {
  keep: { title: 'Keep', dot: 'bg-surface-green-7', verb: 'Keep all', done: 'kept', inbox: { line: 'proposals accepted as they are', verb: 'Accept all', done: 'accepted' },
    tasks: { line: 'stay open' } },
  park: { title: 'Park in Someday', dot: 'bg-surface-amber-7', verb: 'Park all', done: 'parked in Someday', inbox: { line: 'kept as ideas in Someday, back in 3 months' },
    tasks: { line: 'back for a look in 3 months' } },
  letgo: { title: 'Let go', dot: 'bg-surface-gray-7', verb: 'Let go of all', done: 'let go', inbox: { line: 'discarded, back from the trash for 30 days' },
    tasks: { line: 'dropped; bring them back from the Outbox' } },
}
export const pileText = (pile, key, field) => PILE_TEXT[pile][key]?.[field] ?? PILE_TEXT[pile][field]

// The three choices on a row, worded for its source (Needs you): an Inbox item, a stuck task, a task waiting on someone
export function choicesFor(row) {
  if (row.source === 'Inbox') return [{ label: 'Accept', decision: 'keep' }, { label: 'Park', decision: 'park' }, { label: 'Discard', decision: 'letgo' }]
  if (row.source === 'Waiting') return [{ label: 'Chase', decision: 'keep', chase: 1 }, { label: 'Got it', decision: 'letgo' }, { label: 'Keep waiting', decision: 'keep', chase: 0 }]
  return [{ label: 'This week', decision: 'keep' }, { label: 'Someday', decision: 'park' }, { label: 'Drop', decision: 'letgo' }]
}

export function ageText(row) {
  const d = row.age || 0
  if (row.source === 'Inbox') return d ? `captured ${d} day${d === 1 ? '' : 's'} ago` : 'captured today'
  if (row.source === 'Waiting') return `waiting ${d} day${d === 1 ? '' : 's'}${row.waiting_on ? ' on ' + row.waiting_on : ''}`
  return `untouched ${d} days`
}
