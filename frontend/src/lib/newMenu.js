// The counts the navigation shows. (The New menu became + Capture in issue 14, and + Capture became the chat in issue 120: components/ask/.)
import { store } from './store'

// The navigation's numbers come from the count helper with the list each opens (UX fixes, set 5): Inbox, Tasks (due
// today or overdue) and Someday.
// Brain carries the Inbox's number: Needs you is the Inbox (issue 14)
const DOORS = { Brain: ['inbox', 'nav-review', 'to review'], Inbox: ['inbox', 'nav-review', 'to review'], Tasks: ['tasks', 'nav-due', 'due today or overdue'], Someday: ['someday', 'nav-someday', 'on the Someday list'] }
export function navCount(label) {
  const d = DOORS[label]
  const c = d && store.counts.doors?.[d[0]]
  if (!c || !c.n) return null
  return { n: c.n, to: c.to, label: `${c.n} ${d[2]}`, door: d[1], count: c }
}
