// The New menu of the sidebar and the phone's More list, and the two counts the navigation shows.
import router from '@/router'
import { store } from './store'

export function newMenuItems() {
  return [
    // the four things (UX fixes, set 6): Capture, Task, Goal, Note; an idea is a capture parked on Someday
    { label: 'Capture', icon: 'lucide-inbox', onClick: () => router.push({ path: '/inbox', query: { capture: 1 } }), 'data-new': 'capture' },
    { label: 'Task', icon: 'lucide-square-check', onClick: () => (store.quickAdd = true), 'data-new': 'task' },
    { label: 'Goal', icon: 'lucide-target', onClick: () => (store.newKind = 'goal'), 'data-new': 'goal' },
    { label: 'Note', icon: 'lucide-file-text', onClick: () => (store.newKind = 'note'), 'data-new': 'note' },
    { label: 'Idea for Someday', icon: 'lucide-lightbulb', onClick: () => (store.newKind = 'idea'), 'data-new': 'idea' },
  ]
}

// The navigation's numbers come from the count helper with the list each opens (UX fixes, set 5): Inbox, Tasks (due
// today or overdue) and Someday. Reset shows an amber dot when the stuck count is over the limit.
const DOORS = { Inbox: ['inbox', 'nav-review', 'to review'], Tasks: ['tasks', 'nav-due', 'due today or overdue'], Someday: ['someday', 'nav-someday', 'on the Someday list'] }
export function navCount(label) {
  const d = DOORS[label]
  const c = d && store.counts.doors?.[d[0]]
  if (!c || !c.n) return null
  return { n: c.n, to: c.to, label: `${c.n} ${d[2]}`, door: d[1], count: c }
}
export function navDot(label) {
  return label === 'Reset' && store.counts.over_limit ? { label: `${store.counts.doors?.stuck?.n} tasks stuck, above your limit` } : null
}
