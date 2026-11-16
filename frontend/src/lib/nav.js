// The places of the app. Icons are Lucide names, drawn by frappe-ui's icon plugin. `key` is the letter after G.
// The sidebar groups them (components/AppSidebar.vue); Graph is a view of Notes and not in the sidebar, but keeps its key.
export const NAV = [
  ['Today', '/', 'lucide-house', 't'],
  ['Inbox', '/inbox', 'lucide-inbox', 'i'],
  ['Tasks', '/tasks', 'lucide-list-checks', 'k'],
  ['Calendar', '/calendar', 'lucide-calendar', 'c'],
  ['Journal', '/journal', 'lucide-notebook', 'j'],
  ['Goals', '/goals', 'lucide-target', 'o'],
  ['Projects', '/projects', 'lucide-chart-no-axes-column', 'p'],
  ['Someday', '/someday', 'lucide-clock', 'y'],
  ['Areas', '/areas', 'lucide-folder', 'a'],
  ['Sources', '/sources', 'lucide-layers', 'u'],
  ['Notes', '/library', 'lucide-library', 'n'],
  ['Wiki', '/wiki', 'lucide-book-open', 'w'],
  ['Vault', '/vault', 'lucide-lock', 'v'],
  // Chats is the Chats tab of Sources (UX fixes, set 4); G then H still opens it
  ['Chats', '/sources?tab=chats', 'lucide-message-square', 'h'],
  ['Timeline', '/timeline', 'lucide-clock', 'l'],
  ['Graph', '/graph', 'lucide-waypoints', 'g'],
  ['Reset', '/reset', 'lucide-rotate-ccw', 'e'],
  ['Archive', '/archive', 'lucide-archive', 'r'],
].map(([label, to, icon, key]) => ({ label, to, icon, key }))

export const SETTINGS = { label: 'Settings', to: '/settings', key: 's', icon: 'lucide-settings' }
const by = (label) => NAV.find((n) => n.label === label)
// the groups of the sidebar and of the phone's More list
export const GROUPS = [
  { key: 'main', label: '', items: ['Today', 'Inbox', 'Tasks', 'Calendar'].map(by) },
  { key: 'plan', label: 'Plan', items: ['Journal', 'Goals', 'Projects', 'Someday'].map(by) },
  { key: 'areas', label: 'Areas', items: [] },
  { key: 'records', label: 'Records', items: ['Sources', 'Notes', 'Wiki', 'Vault', 'Timeline'].map(by) },
]
export const BOTTOM = [by('Reset'), by('Archive'), SETTINGS]
export const TOOLTIPS = { Timeline: 'Everything, by date', Sources: 'Everything captured', Wiki: 'Pages an agent writes from your sources' }
// the view switch of Notes
// Notes opens on the List (UX fixes, set 4); Tree and Graph are view choices
export const NOTES_VIEWS = [{ label: 'List', value: 'list', route: { path: '/library', query: { view: 'list' } } }, { label: 'Tree', value: 'tree', route: { path: '/library', query: { view: 'tree' } } },
  { label: 'Graph', value: 'graph', route: '/graph' }]
