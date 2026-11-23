// Every server call the goals screens make (Goals, Plan, Habits, Cycles, the calendar and the task lists inside them).
// A component calls these, never `api(` directly. Each call is a frappe-ui resource; a failed call rejects with the
// server's error, so a screen wraps it in tryCall where it shows the message.
import { createResource } from 'frappe-ui'
import { queryParams } from '@/lib/api'
import GET_METHODS from '@/lib/getMethods.json'

const GET = new Set(GET_METHODS)
// the sidebar's counts follow any change that can move them (same rule as lib/api.js)
const CHANGES = /^(tasks\.(set_status|update|quick_add|carry_forward|reschedule_overdue|confirm_area)|periodic\.)/

function call(ns, name) {
  const method = `${ns}.${name}`
  const url = `lifeos.api.${method}`
  const get = GET.has(url)
  return (args = {}) => {
    const resource = createResource({ url, method: get ? 'GET' : 'POST', makeParams: get ? queryParams : undefined })
    const out = resource.submit(args)
    if (CHANGES.test(method)) out.then(() => window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))).catch(() => {})
    return out
  }
}

function group(ns, names) {
  return Object.fromEntries(names.map((name) => [name, call(ns, name)]))
}

export const goalsData = {
  calendar: group('calendar', ['add_event', 'add_important_date', 'get', 'year']),
  goals: group('goals', ['across_cycles', 'add_reading', 'by_area', 'close', 'confirm_reading', 'create', 'create_cycle', 'cycles', 'delete_goal', 'edit', 'grid', 'habit_library', 'habits_year', 'month_habits', 'plan_next_cycle', 'reject_reading', 'reorder', 'save_goal', 'set_action_status', 'set_month_habits', 'start_cycle', 'suggest_horizon', 'suggest_measure', 'this_month', 'tick', 'toggle_habit', 'update', 'week_score']),
  tasks: group('tasks', ['all_tasks', 'confirm_area', 'keep_standalone', 'make_goal', 'no_goal', 'quick_add', 'set_status', 'update']),
  counts: group('counts', ['get']),
  periodic: group('periodic', ['due']),
  focus: group('focus', ['annual_for', 'sort_open']),
}
