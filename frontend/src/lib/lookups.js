import { reactive } from 'vue'
import { api } from './api'
import { store } from './store'

// Areas, tags and goals in progress of the current space, shared by pickers and filters.
export const lookups = reactive({ space: '', areas: [], tags: [], goals: [], loaded: false })

export async function loadLookups(force = false) {
  if (!force && lookups.loaded && lookups.space === store.space) return lookups
  const ctx = await api('meta.space_context', { space: store.space })
  Object.assign(lookups, { space: store.space, areas: ctx.areas, tags: ctx.tags, goals: ctx.goals,
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
  return (areas || []).map((a) => {
    const parent = a.parent_area && areas.find((x) => x.name === a.parent_area)
    return { value: a.name, label: (a.parent_area ? PART_INDENT : '') + a.area_name, title: (parent ? parent.area_name + ' / ' : '') + a.area_name }
  })
}
export const areaOptions = () => areaOptionsOf(lookups.areas)
export const areaName = (id) => lookups.areas.find((a) => a.name === id)?.area_name || ''

// The goal picker on a task: every goal in progress, grouped by type (12 Week Year, Annual, Open) in that order
const GOAL_TYPES = ['12 Week Year', 'Annual', 'Open']
export function goalOptions(goals = lookups.goals || [], { empty = '—' } = {}) {
  const out = empty === null ? [] : [{ label: empty, value: '' }]
  for (const t of GOAL_TYPES) for (const g of goals.filter((x) => (x.goal_type || '12 Week Year') === t)) out.push({ label: `${t} · ${g.title}`, value: g.name })
  return out
}
