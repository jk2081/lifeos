import { createRouter, createWebHistory } from 'vue-router'

const page = (name) => () => import(`./pages/${name}.vue`)

const routes = [
  { path: '/', name: 'Today', component: page('Today') },
  { path: '/inbox', name: 'Inbox', component: page('Inbox') },
  { path: '/inbox/:id', name: 'Review', component: page('Review'), props: true },
  { path: '/timeline', name: 'Timeline', component: page('Timeline') },
  { path: '/tasks', name: 'Tasks', component: page('Tasks') },
  { path: '/calendar/:view?', name: 'Calendar', component: page('Calendar'), props: true },
  { path: '/journal/goals/:id', name: 'Goal', component: page('Goal'), props: true },
  { path: '/journal/pages/:id', name: 'JournalPage', component: page('JournalPage'), props: true },
  { path: '/journal/:tab?', name: 'Journal', component: page('Journal'), props: true },
  { path: '/areas', name: 'Areas', component: page('Areas') },
  { path: '/areas/:id', name: 'Area', component: page('Area'), props: true },
  { path: '/projects', name: 'Projects', component: page('Projects') },
  { path: '/projects/:id', name: 'Project', component: page('Project'), props: true },
  { path: '/library/:id?', name: 'Library', component: page('Library'), props: true },
  { path: '/vault', name: 'Vault', component: page('Vault') },
  { path: '/chats', name: 'Chats', component: page('Chats') },
  { path: '/graph', name: 'Graph', component: page('Graph') },
  { path: '/archive', name: 'Archive', component: page('Archive') },
  { path: '/settings', name: 'Settings', component: page('Settings') },
  { path: '/:rest(.*)*', redirect: '/' },
]

export default createRouter({ history: createWebHistory('/life'), routes, scrollBehavior: () => ({ top: 0 }) })
