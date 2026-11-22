import { reactive } from 'vue'
import { api } from './api'
import { store } from './store'

// Areas and goals in progress of the current space, shared by pickers and filters.
export const lookups = reactive({ space: '', areas: [], goals: [], loaded: false })

export async function loadLookups(force = false) {
  if (!force && lookups.loaded && lookups.space === store.space) return lookups
  const ctx = await api('meta.space_context', { space: store.space })
  Object.assign(lookups, { space: store.space, areas: ctx.areas, goals: ctx.goals,
    people: ctx.people, habits: ctx.habits, dimensions: ctx.dimensions, cycle: ctx.cycle, loaded: true })
  return lookups
}

export function areaLabel(a) {
  const parent = a.parent_area && lookups.areas.find((x) => x.name === a.parent_area)
  return (parent ? parent.area_name + ' / ' : '') + a.area_name
}
// The area pickers (issue 11): the seven areas of life that are on, each followed by its parts, indented. The server sends
// them in that order and leaves out the areas that are off. `title` is the full name, for the chosen value.
export const PART_INDENT = '\u2003'
export function areaOptionsOf(areas) {
  // a part sits one step in, and a focus (issue 57) under it two
  const path = (a) => {
    const parent = a.parent_area && areas.find((x) => x.name === a.parent_area)
    return parent ? [...path(parent), a] : [a]
  }
  return (areas || []).map((a) => {
    const chain = path(a)
    return { value: a.name, label: PART_INDENT.repeat(chain.length - 1) + a.area_name, title: chain.map((x) => x.area_name).join(' / ') }
  })
}
export const areaOptions = () => areaOptionsOf(lookups.areas)
export const areaName = (id) => lookups.areas.find((a) => a.name === id)?.area_name || ''

// The goal picker on a task: every goal in progress, grouped by horizon (12 weeks, Month, Year, Long term) in that order
const GOAL_HORIZONS = ['12 weeks', 'Month', 'Year', 'Long term']
// What a goal can serve: the goals one horizon up come first (a Month goal suggests a 12-week goal, that a Year goal)
const UP = { Month: '12 weeks', '12 weeks': 'Year', Year: 'Long term' }
export function parentOptions(goal, goals = lookups.goals || []) {
  const others = goals.filter((x) => x.name !== goal.name)
  const first = others.filter((x) => x.horizon === UP[goal.horizon])
  return [...goalOptions(first, { empty: null }), ...goalOptions(others.filter((x) => !first.includes(x)), { empty: null })]
}
export function goalOptions(goals = lookups.goals || [], { empty = '—' } = {}) {
  const out = empty === null ? [] : [{ label: empty, value: '' }]
  for (const t of GOAL_HORIZONS) for (const g of goals.filter((x) => x.horizon === t)) out.push({ label: `${t} · ${g.title}`, value: g.name })
  return out
}
