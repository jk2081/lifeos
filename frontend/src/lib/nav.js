// Sidebar entries with the icon paths from the mockups.
export const NAV = [
  ['Today', '/', 'M4 11l8-7 8 7v9H4z', 't'],
  ['Inbox', '/inbox', 'M4 13l2-8h12l2 8v6H4zM4 13h5l1 3h4l1-3h5', 'i'],
  ['Timeline', '/timeline', 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z', 'l'],
  ['Tasks', '/tasks', 'M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2', 'k'],
  ['Calendar', '/calendar', 'M5 5h14v15H5zM5 10h14M9 3v4M15 3v4', 'c'],
  ['Journal', '/journal', 'M6 3h12v18H6zM10 3v18', 'j'],
  ['Areas', '/areas', 'M4 6h6l2 2h8v11H4z', 'a'],
  ['Projects', '/projects', 'M4 20V10M10 20V4M16 20v-7M22 20H2', 'p'],
  ['Library', '/library', 'M5 4h4v16H5zM11 4h4v16h-4zM17 6l3 13', 'n'],
  ['Vault', '/vault', 'M5 11h14v9H5zM8 11V8a4 4 0 0 1 8 0v3', 'v'],
  ['Chats', '/chats', 'M4 5h16v11H9l-5 4z', 'h'],
  ['Graph', '/graph', 'M8 7l8 1.5M17 11l-7 6M4 6a2 2 0 1 0 4 0 2 2 0 1 0-4 0M16 9a2 2 0 1 0 4 0 2 2 0 1 0-4 0M7 18a2 2 0 1 0 4 0 2 2 0 1 0-4 0', 'g'],
  ['Archive', '/archive', 'M4 5h16v4H4zM6 9v10h12V9M10 13h4', 'r'],
].map(([label, to, d, key]) => ({ label, to, d, key }))

export const SETTINGS = { label: 'Settings', to: '/settings', key: 's',
  d: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM4 12h2M18 12h2M12 4v2M12 18v2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M6.3 17.7l1.4-1.4M16.3 7.7l1.4-1.4' }
export const MORE_ICON = 'M4 7h16M4 12h16M4 17h16'
export const SEARCH_ICON = 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4'
export const PLUS_ICON = 'M12 5v14M5 12h14'
