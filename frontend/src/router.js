import { createRouter, createWebHistory } from 'vue-router'

const page = (name) => () => import(`./pages/${name}.vue`)

const routes = [
  { path: '/', name: 'Today', component: page('Today') },
  { path: '/inbox', name: 'Inbox', component: page('Inbox') },
  { path: '/inbox/:id/review', name: 'Review', component: page('Review'), props: true },
  // an inbox item opens in the pane over the list; old links to /inbox/:id still work
  { path: '/inbox/:id', redirect: (to) => ({ path: '/inbox', query: { ...to.query, open: `inbox:${to.params.id}` } }) },
  { path: '/timeline', name: 'Timeline', component: page('Timeline') },
  { path: '/tasks', name: 'Tasks', component: page('Tasks') },
  { path: '/calendar/:view?', name: 'Calendar', component: page('Calendar'), props: true },
  { path: '/journal/goals/:id', name: 'Goal', component: page('Goal'), props: true },
  { path: '/journal/pages/:id', name: 'JournalPage', component: page('JournalPage'), props: true },
  { path: '/journal/:tab?', name: 'Journal', component: page('Journal'), props: true },
  { path: '/areas', name: 'Areas', component: page('Areas') },
  { path: '/areas/:id', name: 'Area', component: page('Area'), props: true },
  { path: '/goals', name: 'Goals', component: page('Goals') },
  { path: '/projects', name: 'Projects', component: page('Projects') },
  { path: '/someday', name: 'Someday', component: page('Someday') },
  { path: '/projects/:id', name: 'Project', component: page('Project'), props: true },
  { path: '/library/:id?', name: 'Library', component: page('Library'), props: true },
  { path: '/vault', name: 'Vault', component: page('Vault') },
  { path: '/sources', name: 'Sources', component: page('Sources') },
  { path: '/wiki', name: 'Wiki', component: page('Wiki') },
  // Chats is the Chats tab of Sources (UX fixes, set 4): filters carry over; the old report (group=day) is the By day view
  { path: '/chats', name: 'Chats', redirect: (to) => {
    const { group, open, view, ...rest } = to.query
    return { path: '/sources', query: { ...rest, tab: 'chats', ...(group === 'day' || view === 'report' ? { view: 'day' } : {}),
      ...(open ? { open: String(open).includes(':') ? open : 'chat:' + open } : {}) } }
  } },
  { path: '/graph', name: 'Graph', component: page('Graph') },
  { path: '/archive', name: 'Archive', component: page('Archive') },
  { path: '/settings', name: 'Settings', component: page('Settings') },
  // development only: the editor on a sample note (owner only, not in the sidebar)
  { path: '/dev/editor', name: 'EditorDev', component: () => import('./pages/dev/EditorDev.vue') },
  { path: '/:rest(.*)*', redirect: '/' },
]

// Opening or closing the pane and changing a filter only change the query: the list keeps its scroll position.
export default createRouter({ history: createWebHistory('/life'), routes,
  scrollBehavior: (to, from, saved) => (to.path === from.path ? false : saved || { top: 0 }) })
