// Sidebar entries. Icons are Lucide names, drawn by frappe-ui's icon plugin.
export const NAV = [
  ['Today', '/', 'lucide-house', 't'],
  ['Inbox', '/inbox', 'lucide-inbox', 'i'],
  ['Timeline', '/timeline', 'lucide-clock', 'l'],
  ['Tasks', '/tasks', 'lucide-list-checks', 'k'],
  ['Calendar', '/calendar', 'lucide-calendar', 'c'],
  ['Journal', '/journal', 'lucide-notebook', 'j'],
  ['Areas', '/areas', 'lucide-folder', 'a'],
  ['Projects', '/projects', 'lucide-chart-no-axes-column', 'p'],
  ['Library', '/library', 'lucide-library', 'n'],
  ['Vault', '/vault', 'lucide-lock', 'v'],
  ['Chats', '/chats', 'lucide-message-square', 'h'],
  ['Graph', '/graph', 'lucide-waypoints', 'g'],
  ['Archive', '/archive', 'lucide-archive', 'r'],
].map(([label, to, icon, key]) => ({ label, to, icon, key }))

export const SETTINGS = { label: 'Settings', to: '/settings', key: 's', icon: 'lucide-settings' }
