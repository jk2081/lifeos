// The places of the app (issue 14): Today, Brain, Goals and Library, with Review after the first locked review, Settings,
// and the letters after G. Every tab of a place is its own path. Icons are Lucide names, drawn by frappe-ui's icon plugin.
export const PLACES = [
  { label: 'Today', to: '/today', base: '/today', icon: 'lucide-sun', key: 't' },
  { label: 'Brain', to: '/brain', base: '/brain', icon: 'lucide-sparkles', key: 'i' },
  { label: 'Goals', to: '/goals', base: '/goals', icon: 'lucide-target', key: 'o' },
  { label: 'Library', to: '/library', base: '/library', icon: 'lucide-library', key: 'l' },
]
// shown between Goals and Library once the person has locked a weekly review, or on the review's day
export const REVIEW = { label: 'Review', to: '/review', base: '/review', icon: 'lucide-calendar-check', key: 'd' }
export const SETTINGS = { label: 'Settings', to: '/settings', base: '/settings', key: 's', icon: 'lucide-settings' }

// each place's tabs; the first is the place's own path
export const TODAY_TABS = [{ value: 'day', label: 'Day' }, { value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }, { value: 'year', label: 'Year' }]
export const BRAIN_TABS = [{ value: 'needs-you', label: 'Needs you' }, { value: 'activity', label: 'Activity' }, { value: 'sources', label: 'Sources' }]
export const GOALS_TABS = [{ value: 'by-area', label: 'By area' }, { value: 'tasks', label: 'All tasks' }, { value: 'no-goal', label: 'No goal' }]
export const LIBRARY_TABS = [{ value: 'all', label: 'Everything' }, { value: 'notes', label: 'Notes' }, { value: 'documents', label: 'Documents' },
  { value: 'people', label: 'People' }, { value: 'chats', label: 'Chats' }]
const tabPath = (base, tabs) => (tab) => (tab === tabs[0].value ? base : `${base}/${tab}`)
export const todayPath = tabPath('/today', TODAY_TABS)
export const brainPath = tabPath('/brain', BRAIN_TABS)
export const goalsPath = tabPath('/goals', GOALS_TABS)
export const libraryPath = tabPath('/library', LIBRARY_TABS)

// G then a letter: the places, then the pages inside them. The letters from before issue 14 open their new homes
// (I, once the Inbox, opens the Brain; P, once Plan, opens Today's Week; U, once Captures, opens Brain > Activity).
export const GO = [
  ...PLACES, REVIEW,
  { label: 'Plan, now Today: Week', to: '/today/week', key: 'p' }, { label: 'Today: Week', to: '/today/week', key: 'w' },
  { label: 'Today: Month', to: '/today/month', key: 'm' }, { label: 'Today: 12 Weeks', to: '/today/year?view=cycle', key: 'j' },
  { label: 'Today: Year', to: '/today/year', key: 'c' }, { label: 'Today: Reset', to: '/today/reset', key: 'e' },
  { label: 'Goals: All tasks', to: '/goals/tasks', key: 'k' }, { label: 'Goals: Someday', to: '/goals/someday', key: 'y' },
  { label: 'Brain: Activity', to: '/brain/activity', key: 'u' }, { label: 'Brain: Outbox', to: '/brain/outbox', key: 'b' },
  { label: 'Library: Notes', to: '/library/notes', key: 'n' }, { label: 'Library: Chats', to: '/library/chats', key: 'h' },
  { label: 'Library: Sensitive documents', to: '/library/documents?tab=documents&sensitive=1', key: 'v' },
  { label: "Library: The assistant's notes", to: '/library/notes?by=assistant', key: 'x' }, { label: 'Library: Graph', to: '/library/notes?view=graph', key: 'g' },
  { label: 'Library: Trash and archive', to: '/library/archive', key: 'r' }, { label: 'Ask: history and insights', to: '/ask', key: 'q' },
  { label: 'Settings: Areas', to: '/settings?tab=areas', key: 'a' }, SETTINGS,
]
export const TOOLTIPS = { Today: 'What to do now', Brain: 'What came in and what the Brain did with it', Goals: 'Where you are going', Library: 'What you have and know' }
// the view switch of Library > Notes: List (the default), Tree and Graph, and the assistant's Changes and Health
export const NOTES_VIEWS = ['list', 'tree', 'graph', 'changes', 'health'].map((v) => ({ label: v[0].toUpperCase() + v.slice(1), value: v,
  route: { path: '/library/notes', query: { view: v } } }))
// "Written by" on Library > Notes
export const WRITTEN_BY = [{ label: 'Written by anyone', value: '' }, { label: 'Written by me', value: 'me' }, { label: 'Kept by the assistant', value: 'assistant' }]
// Settings > Data > Where things are (issue 14): every page that is not a place or a tab, with the place it lives in
export const ELSEWHERE = [
  { key: 'reset', label: 'Reset', home: 'Today, and the weekly review', to: '/today/reset' },
  { key: 'review', label: 'Weekly review', home: 'Review, once you have locked one; Today > Week on its day', to: '/review' },
  { key: 'cycle', label: '12 Weeks', home: 'Today > Year', to: { path: '/today/year', query: { view: 'cycle' } } },
  { key: 'habits', label: 'Habits', home: 'Today > Month', to: { path: '/today/month', query: { view: 'habits' } } },
  { key: 'checkins', label: 'Check-ins', home: 'Today > Month', to: { path: '/today/month', query: { view: 'checkins' } } },
  { key: 'someday', label: 'Someday', home: 'Goals', to: '/goals/someday' },
  { key: 'outbox', label: 'Outbox', home: 'Brain', to: '/brain/outbox' },
  { key: 'timeline', label: 'Timeline', home: 'Library', to: '/library/timeline' },
  { key: 'graph', label: 'Graph', home: 'Library > Notes', to: { path: '/library/notes', query: { view: 'graph' } } },
  { key: 'vault', label: 'Sensitive documents', home: 'Library > Documents, by the lock', to: { path: '/library/documents', query: { tab: 'documents', sensitive: '1' } } },
  { key: 'pages', label: 'Journal pages', home: 'Library > Everything', to: { path: '/library', query: { tab: 'pages' } } },
  { key: 'archive', label: 'Trash and archive', home: 'Library', to: '/library/archive' },
  { key: 'ask', label: 'Ask: history and insights', home: 'The Ask box in every header', to: '/ask' },
]
/**
 * A place's tab row while `current` is open. A page of the place that is not one of its tabs (the Outbox, Someday, the
 * Timeline, the archive) is added after a gap while it is open: the tab row must always show the open value, or it
 * would select its first tab by itself.
 */
export function withPage(tabs, current, pages) {
  return pages[current] ? [...tabs, { value: current, label: pages[current], group: 'page' }] : tabs
}
