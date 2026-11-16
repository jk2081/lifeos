// The New menu of the sidebar and the phone's More list, and the two counts the navigation shows.
import router from '@/router'
import { store } from './store'

export function newMenuItems() {
  return [
    { label: 'Task', icon: 'lucide-square-check', onClick: () => (store.quickAdd = true) },
    { label: 'Note', icon: 'lucide-file-text', onClick: () => (store.newKind = 'note') },
    { label: 'Project', icon: 'lucide-chart-no-axes-column', onClick: () => (store.newKind = 'project') },
    { label: 'Idea for Someday', icon: 'lucide-lightbulb', onClick: () => (store.newKind = 'idea') },
    { label: 'Add to Inbox', icon: 'lucide-inbox', onClick: () => router.push('/inbox') },
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
