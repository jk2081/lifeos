// The places of the app (UX fixes, set 6): four places, Plan's and Library's tabs, Settings, and the letters after G.
// Icons are Lucide names, drawn by frappe-ui's icon plugin.
export const PLACES = [
  { label: 'Today', to: '/', icon: 'lucide-house', key: 't' },
  { label: 'Inbox', to: '/inbox', icon: 'lucide-inbox', key: 'i' },
  { label: 'Plan', to: '/plan/week', base: '/plan', icon: 'lucide-compass', key: 'p' },
  { label: 'Library', to: '/library', icon: 'lucide-library', key: 'l' },
]
// Plan's tabs: the rhythms first, then the lists (a gap between the two groups)
export const PLAN_TABS = [
  { value: 'week', label: 'Week', group: 'time' }, { value: 'month', label: 'Month', group: 'time' },
  { value: '12-weeks', label: '12 Weeks', group: 'time' }, { value: 'year', label: 'Year', group: 'time' },
  { value: 'goals', label: 'Goals', group: 'lists' }, { value: 'tasks', label: 'Tasks', group: 'lists' }, { value: 'someday', label: 'Someday', group: 'lists' },
]
export const LIBRARY_TABS = [
  { value: 'all', label: 'All' }, { value: 'notes', label: 'Notes' }, { value: 'captures', label: 'Captures' }, { value: 'outbox', label: 'Outbox' },
  { value: 'timeline', label: 'Timeline' }, { value: 'archive', label: 'Archive' },
]
export const planPath = (tab) => `/plan/${tab}`
export const libraryPath = (tab) => (tab === 'all' ? '/library' : `/library/${tab}`)
export const SETTINGS = { label: 'Settings', to: '/settings', key: 's', icon: 'lucide-settings' }

// G then a letter. The four places first, then the shortcuts kept from before set 6, pointing at the new homes.
export const GO = [
  ...PLACES,
  { label: 'Plan: Week', to: '/plan/week', key: 'w' }, { label: 'Plan: Month', to: '/plan/month', key: 'm' },
  { label: 'Plan: 12 Weeks', to: '/plan/12-weeks', key: 'j' }, { label: 'Plan: Year', to: '/plan/year', key: 'c' },
  { label: 'Plan: Goals', to: '/plan/goals', key: 'o' }, { label: 'Plan: Tasks', to: '/plan/tasks', key: 'k' },
  { label: 'Plan: Someday', to: '/plan/someday', key: 'y' }, { label: 'Reset', to: '/plan/reset', key: 'e' },
  { label: 'Library: Notes', to: '/library/notes', key: 'n' }, { label: 'Library: Captures', to: '/library/captures', key: 'u' },
  { label: 'Library: Chats', to: '/library/captures?tab=chats', key: 'h' }, { label: 'Library: Sensitive documents', to: '/library/captures?tab=documents&sensitive=1', key: 'v' },
  { label: "Library: The assistant's notes", to: '/library/notes?by=assistant', key: 'x' }, { label: 'Library: Graph', to: '/library/notes?view=graph', key: 'g' },
  { label: 'Library: Archive', to: '/library/archive', key: 'r' }, { label: 'Library: Outbox', to: '/library/outbox', key: 'b' },
  { label: 'Ask: history and insights', to: '/ask', key: 'q' }, { label: 'Settings: Areas', to: '/settings?tab=areas', key: 'a' },
  SETTINGS,
]
export const TOOLTIPS = { Today: 'What to do now', Inbox: 'What came in', Plan: 'Where you are going', Library: 'What you have and know' }
// the view switch of Library > Notes: List (the default), Tree and Graph, and the assistant's Changes and Health
export const NOTES_VIEWS = ['list', 'tree', 'graph', 'changes', 'health'].map((v) => ({ label: v[0].toUpperCase() + v.slice(1), value: v,
  route: { path: '/library/notes', query: { view: v } } }))
// "Written by" on Library > Notes
export const WRITTEN_BY = [{ label: 'Written by anyone', value: '' }, { label: 'Written by me', value: 'me' }, { label: 'Kept by the assistant', value: 'assistant' }]
