// Key results (set 7): the measure of a goal as the API takes it, the check the server also makes, and Make it a habit.
import { toast } from 'frappe-ui'
import { api } from './api'
import { store } from './store'

export const emptyMeasure = (g = {}) => ({ measure_kind: g.measure_kind || '', done_when: g.done_when || '', measure: g.measure || '', unit: g.unit || '',
  start_value: g.start_value ?? '', target_value: g.target_value ?? '' })

// What is missing before a goal with this measure can be saved; '' when it is complete. A goal with no kind yet is refused
// only when `required` (a new goal, or an edit of its kind or measure).
export function measureProblem(m, required = true) {
  if (!m.measure_kind) return required ? 'Say how you will know this goal is done: a finish line or a number.' : ''
  if (m.measure_kind === 'Milestone' && !(m.done_when || '').trim()) return 'Write the finish line.'
  if (m.measure_kind === 'Number') {
    if (!(m.measure || '').trim()) return 'Say what is measured.'
    if (m.start_value === '' || m.start_value == null || m.target_value === '' || m.target_value == null) return 'A number goal needs a start and a target.'
    if (Number(m.start_value) === Number(m.target_value)) return 'The target must differ from the start.'
  }
  return ''
}

export function measureArgs(m) {
  if (!m.measure_kind) return { done_when: (m.done_when || '').trim() || undefined }
  if (m.measure_kind === 'Milestone') return { measure_kind: 'Milestone', done_when: m.done_when.trim() }
  return { measure_kind: 'Number', measure: m.measure.trim(), unit: (m.unit || '').trim(), start_value: Number(m.start_value), target_value: Number(m.target_value),
    done_when: (m.done_when || '').trim() || undefined }
}

export async function makeHabit(habit, { area, space } = {}) {
  const r = await api('goals.make_habit', { title: habit.title, days_per_week: habit.days_per_week, area: area || undefined, space: space || store.space })
  toast.success(`${r.title} is a habit in this month's plan.`)
  return r
}
