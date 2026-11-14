import { diffDays, short, startOfWeek, addDays } from './dates'

export const PRIORITIES = ['I', 'II', 'III', 'IV']
export const OPEN = ['Open', 'Doing', 'Waiting']

// The pill at the right of a task row, as in the mockups.
export function taskPill(t, today) {
  if (t.status === 'Done') return { cls: 'g', text: 'Done' }
  if (t.status === 'Carried') return { cls: 'o', text: 'Carried' }
  if (t.status === 'Dropped') return { cls: 'n', text: 'Dropped' }
  if (t.due_date && t.due_date < today) {
    const n = diffDays(today, t.due_date)
    return { cls: 'r', text: `Overdue ${n} day${n === 1 ? '' : 's'}`, shortText: `${n} day${n === 1 ? '' : 's'}` }
  }
  if (t.status === 'Waiting') return { cls: 'o', text: 'Waiting' }
  if (t.carried_from) return { cls: 'o', text: 'Carried' }
  if (t.priority) return { cls: 'n', text: t.priority }
  if (t.goal) return { cls: 'b', text: '12WY' }
  return null
}

// The grey line under a task title.
export function taskMeta(t, today, { withDue = false } = {}) {
  const parts = []
  if (t.area_name) parts.push(t.area_name)
  if (t.project_title) parts.push(t.project_title)
  else if (t.goal_title) parts.push(t.goal_title)
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
