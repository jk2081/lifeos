import { reactive } from 'vue'
import { api } from './api'
import { store } from './store'

// Areas, tags and projects of the current space, shared by pickers and filters.
export const lookups = reactive({ space: '', areas: [], tags: [], projects: [], goals: [], loaded: false })

export async function loadLookups(force = false) {
  if (!force && lookups.loaded && lookups.space === store.space) return lookups
  const ctx = await api('meta.space_context', { space: store.space })
  Object.assign(lookups, { space: store.space, areas: ctx.areas, tags: ctx.tags, projects: ctx.projects, goals: ctx.goals,
    people: ctx.people, habits: ctx.habits, dimensions: ctx.dimensions, cycle: ctx.cycle, loaded: true })
  return lookups
}

export function areaLabel(a) {
  const parent = a.parent_area && lookups.areas.find((x) => x.name === a.parent_area)
  return (parent ? parent.area_name + ' / ' : '') + a.area_name
}
export const areaOptions = () => lookups.areas.map((a) => ({ value: a.name, label: areaLabel(a) }))
export const areaName = (id) => lookups.areas.find((a) => a.name === id)?.area_name || ''
