import { diffDays, short, startOfWeek, addDays } from './dates'

export const PRIORITIES = ['I', 'II', 'III', 'IV']
export const OPEN = ['Open', 'Doing', 'Waiting']

// The badge at the right of a task row, as in the mockups: { theme, text } for frappe-ui's Badge.
export function taskPill(t, today) {
  if (t.status === 'Done') return { theme: 'green', text: 'Done' }
  if (t.status === 'Carried') return { theme: 'amber', text: 'Carried' }
  if (t.status === 'Dropped') return { theme: 'gray', text: 'Dropped' }
  if (t.due_date && t.due_date < today) {
    const n = diffDays(today, t.due_date)
    return { theme: 'red', text: `Overdue ${n} day${n === 1 ? '' : 's'}`, shortText: `${n} day${n === 1 ? '' : 's'}` }
  }
  if (t.status === 'Waiting') return { theme: 'amber', text: 'Waiting' }
  if (t.carried_from) return { theme: 'amber', text: 'Carried' }
  if (t.priority) return { theme: 'gray', text: t.priority }
  if (t.goal) return { theme: 'blue', text: '12WY' }
  return null
}

// The grey line under a task title.
export function taskMeta(t, today, { withDue = false } = {}) {
  const parts = []
  if (t.area_name) parts.push(t.area_name)
  if (t.goal_title) parts.push(t.goal_title)
  else if (t.source_title) parts.push('from ' + t.source_title)
  else if (t.carried_from) parts.push('carried forward')
  if (!t.area_name && !parts.length) parts.push('Unfiled')
  if (withDue) parts.push(t.due_date ? (t.due_date === today ? 'due today' : 'due ' + short(t.due_date)) : 'no date')
  if (t.status === 'Waiting' && t.waiting_on) parts.push('waiting on ' + t.waiting_on)
  return parts.join(' · ')
}

export function groupByDue(tasks, today) {
  const weekEnd = addDays(startOfWeek(today), 6)
  const groups = [['Overdue', []], ['Today', []], ['This week', []], ['Later', []], ['No date', []]]
  for (const t of tasks) {
    const d = t.due_date
    const i = !d ? 4 : d < today ? 0 : d === today ? 1 : d <= weekEnd ? 2 : 3
    groups[i][1].push(t)
  }
  return groups.filter(([, list]) => list.length).map(([label, list]) => ({ label, tasks: list }))
}

export const VAULT_TYPES = ['ID', 'Travel', 'Insurance', 'Property', 'Tax', 'Medical', 'Other']
export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
// "4 of 10 tasks done" leads to the tasks of the goal with Show done on. Archived ones are counted, so they are listed too.
// "x of y tasks done" counts every task of the goal but the carried ones: the All tab with that one condition
export const doneLink = (g) => ({ path: '/tasks', query: { goal: g.name, archived: '1', f: JSON.stringify([['status', '!=', 'Carried']]) } })
