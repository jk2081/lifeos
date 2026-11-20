import { createRouter, createWebHistory } from 'vue-router'

const page = (name) => () => import(`./pages/${name}.vue`)

// The four places (UX fixes, set 6): Today, Inbox, Plan and Library, with Settings and the Ask page beside them.
// Plan's tabs: the rhythms, then the lists. Library's tabs: everything, then by kind, then time and the archive.
export const PLAN_TABS = ['week', 'month', '12-weeks', 'year', 'goals', 'tasks', 'someday']
export const LIBRARY_TABS = ['notes', 'captures', 'outbox', 'timeline', 'archive']

// the Projects screen's query on the Goals tab: open-ended goals, and a project's status as a goal state
const STATE = { Active: 'in_progress', 'On Hold': 'in_progress', Done: 'achieved', Dropped: 'closed', Someday: 'someday', all: 'all', current: 'in_progress' }
function projectQuery(q) {
  const { status, ...rest } = q
  return { ...rest, type: 'Open', ...(status ? { status: STATE[status] || 'in_progress' } : {}) }
}
// an old route that lands on a tab with its query carried over, and a few parameters of its own
const to = (path, extra = {}) => (r) => ({ path, query: { ...r.query, ...(typeof extra === 'function' ? extra(r) : extra) }, hash: r.hash })

const routes = [
  { path: '/', name: 'Today', component: page('Today') },
  { path: '/inbox', name: 'Inbox', component: page('Inbox') },
  { path: '/inbox/:id/review', name: 'Review', component: page('Review'), props: true },
  // issue 10: one page per capture, with its source, files, summary, decisions and what came of it
  { path: '/item/:id', name: 'Item', component: page('Item'), props: true },
  // an inbox item opens in the pane over the list; old links to /inbox/:id still work
  { path: '/inbox/:id', redirect: (r) => ({ path: '/inbox', query: { ...r.query, open: `inbox:${r.params.id}` } }) },

  // ---- Plan ----
  { path: '/plan', redirect: to('/plan/week') },
  { path: '/plan/goals/:id', name: 'Goal', component: page('Goal'), props: true },
  { path: '/plan/reset', name: 'Reset', component: page('Reset') },
  { path: `/plan/:tab(${PLAN_TABS.join('|')})`, name: 'Plan', component: page('Plan'), props: true },

  // ---- Library ----
  // /library?view=tree was the Notes screen's tree before set 6. ?view=list is now Library > All's own list view, so it stays.
  { path: `/library/:tab(${LIBRARY_TABS.join('|')})?`, name: 'Library', component: page('LibraryPlace'), props: true,
    beforeEnter: (r) => (!r.params.tab && r.query.view === 'tree' ? { path: '/library/notes', query: r.query } : true) },
  { path: '/library/:id', name: 'Note', component: page('Library'), props: true },

  { path: '/ask', name: 'Ask', component: page('Ask') },
  { path: '/settings', name: 'Settings', component: page('Settings') },

  // ---- every route from before set 6 lands on its new home, with its query ----
  { path: '/tasks', redirect: to('/plan/tasks') },
  { path: '/goals', redirect: to('/plan/goals') },
  { path: '/someday', redirect: to('/plan/someday') },
  { path: '/projects', redirect: (r) => ({ path: '/plan/goals', query: projectQuery(r.query) }) },
  { path: '/projects/:id', name: 'Project', component: page('ProjectRedirect'), props: true },
  { path: '/reset', redirect: to('/plan/week', { view: 'review', step: 'reset' }) },
  { path: '/calendar/:view?', redirect: (r) => {
    const v = r.params.view
    if (v === 'year') return { path: '/plan/year', query: r.query }
    if (v === 'month') return { path: '/plan/month', query: { ...r.query, view: 'calendar' } }
    return { path: '/plan/week', query: { ...r.query, view: v === 'agenda' ? 'agenda' : 'calendar' } }
  } },
  { path: '/journal/goals/:id', redirect: (r) => ({ path: `/plan/goals/${r.params.id}`, query: r.query }) },
  // journal pages are captures now: a page opens in the pane over Library > Captures
  { path: '/journal/pages/:id', redirect: (r) => ({ path: '/library/captures', query: { ...r.query, tab: 'pages', open: `page:${r.params.id}` } }) },
  { path: '/journal/:tab?', redirect: (r) => {
    const t = r.params.tab
    const map = { goals: ['/plan/year', { view: 'goals' }], month: ['/plan/month', {}], habits: ['/plan/month', { view: 'habits' }],
      checkins: ['/plan/month', { view: 'checkins' }], review: ['/plan/week', { view: 'review' }], pages: ['/library/captures', { tab: 'pages' }] }
    const [path, extra] = map[t] || ['/plan/12-weeks', {}]
    return { path, query: { ...r.query, ...extra } }
  } },
  { path: '/sources', redirect: to('/library/captures') },
  // Chats were a tab of Sources (set 4): filters carry over; the old report (group=day) is the By day view
  { path: '/chats', redirect: (r) => {
    const { group, open, view, ...rest } = r.query
    return { path: '/library/captures', query: { ...rest, tab: 'chats', ...(group === 'day' || view === 'report' ? { view: 'day' } : {}),
      ...(open ? { open: String(open).includes(':') ? open : 'chat:' + open } : {}) } }
  } },
  { path: '/wiki', redirect: to('/library/notes', (r) => ({ by: 'assistant', ...(r.query.tab && r.query.tab !== 'pages' ? { view: r.query.tab } : {}), tab: undefined })) },
  { path: '/vault', redirect: to('/library/captures', (r) => ({ tab: 'documents', sensitive: '1',
    ...(r.query.open && !String(r.query.open).includes(':') ? { open: 'vault:' + r.query.open } : {}) })) },
  { path: '/graph', redirect: to('/library/notes', { view: 'graph' }) },
  { path: '/timeline', redirect: to('/library/timeline') },
  { path: '/archive', redirect: to('/library/archive') },
  // area pages became the lens: an area opens Today narrowed to it; the list of areas is in Settings
  { path: '/areas', redirect: to('/settings', { tab: 'areas' }) },
  { path: '/areas/:id', redirect: (r) => ({ path: '/', query: { ...r.query, tab: undefined, area: r.params.id } }) },

  // development only: the editor on a sample note (owner only, not in the sidebar)
  { path: '/dev/editor', name: 'EditorDev', component: () => import('./pages/dev/EditorDev.vue') },
  // development only: a screen that fails on purpose, for the error boundary's check (bug fix 1)
  { path: '/dev/throw', name: 'ThrowDev', component: () => import('./pages/dev/ThrowDev.vue') },
  { path: '/:rest(.*)*', redirect: '/' },
]

// Opening or closing the pane and changing a filter only change the query: the list keeps its scroll position.
export default createRouter({ history: createWebHistory('/life'), routes,
  scrollBehavior: (to, from, saved) => (to.path === from.path ? false : saved || { top: 0 }) })
