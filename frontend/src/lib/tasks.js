import { diffDays, short } from './dates'

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
  if (t.area_name && !t.area_guessed) parts.push(t.area_name) // a guessed area shows as its own chip (AreaGuess)
  if (t.goal_title) parts.push(t.goal_title)
  else if (t.source_title) parts.push('from ' + t.source_title)
  else if (t.carried_from) parts.push('carried forward')
  if (!t.area_name && !parts.length) parts.push('Unfiled')
  if (withDue) parts.push(t.due_date ? (t.due_date === today ? 'due today' : 'due ' + short(t.due_date)) : 'no date')
  if (t.status === 'Waiting' && t.waiting_on) parts.push('waiting on ' + t.waiting_on)
  return parts.join(' · ')
}

export { plural } from './plural'
