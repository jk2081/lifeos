import { createRouter, createWebHistory } from 'vue-router'

const page = (name) => () => import(`./pages/${name}.vue`)

// The places (issue 14): Today, Brain, Goals and Library, each tab its own path, with Review, Settings and the Ask page
// beside them. Housekeeping pages live inside the place they belong to and are not tabs: Reset under Today, the Outbox
// under Brain, Someday under Goals, the Timeline and the trash and archive under Library.
const TODAY = ['week', 'month', 'year']
const BRAIN = ['activity', 'captures', 'sources', 'outbox', 'queue']
const GOALS = ['tasks', 'no-goal', 'someday']
const LIBRARY = ['notes', 'documents', 'people', 'chats', 'timeline', 'archive']

// the Projects screen's query on the Goals tab: open-ended goals, and a project's status as a goal state
const STATE = { Active: 'in_progress', 'On Hold': 'in_progress', Done: 'achieved', Dropped: 'closed', Someday: 'someday', all: 'all', current: 'in_progress' }
function projectQuery(q) {
  const { status, ...rest } = q
  return { ...rest, type: 'Open', ...(status ? { status: STATE[status] || 'in_progress' } : {}) }
}
// an old route that lands on a tab with its query carried over, and a few parameters of its own
const to = (path, extra = {}) => (r) => ({ path, query: { ...r.query, ...(typeof extra === 'function' ? extra(r) : extra) }, hash: r.hash })
// Captures (set 6) is the list at Brain > Captures (Activity, issue 18, is the feed beside it): everything that came in. Opened on Documents or Chats it is that tab of the
// Library, and on notes Library > Notes; any other kind stays a kind of Activity.
const KIND_TAB = { documents: '/library/documents', chats: '/library/chats', notes: '/library/notes' }
const libraryKind = (r, extra = {}) => {
  const q = { ...r.query, ...extra }
  return { path: KIND_TAB[q.tab] || '/brain/captures', query: q, hash: r.hash }
}
// Plan's old tabs, by their new homes
const PLAN_HOME = { week: '/today/week', month: '/today/month', year: '/today/year', goals: '/goals', tasks: '/goals/tasks', someday: '/goals/someday' }

const routes = [
  { path: '/', redirect: to('/today') },
  { path: `/today/:tab(${TODAY.join('|')})?`, name: 'Today', component: page('TodayPlace'), props: true },
  { path: '/today/reset', name: 'Reset', component: page('Reset') },
  { path: `/brain/:tab(${BRAIN.join('|')})?`, name: 'Brain', component: page('BrainPlace'), props: true },
  { path: '/brain/review/:id', name: 'ItemReview', component: page('Review'), props: true },
  // issue 10: one page per capture, with its source, files, summary, decisions and what came of it
  { path: '/item/:id', name: 'Item', component: page('Item'), props: true },
  { path: `/goals/:tab(${GOALS.join('|')})?`, name: 'Goals', component: page('GoalsPlace'), props: true },
  { path: '/goals/:id', name: 'Goal', component: page('Goal'), props: true },
  // /library?view=tree was the Notes screen's tree before set 6. ?view=list is now Library > Everything's own list view, so it stays.
  { path: `/library/:tab(${LIBRARY.join('|')})?`, name: 'Library', component: page('LibraryPlace'), props: true,
    beforeEnter: (r) => (!r.params.tab && r.query.view === 'tree' ? { path: '/library/notes', query: r.query } : true) },
  { path: '/library/:id', name: 'Note', component: page('Library'), props: true },
  // the weekly review: in the sidebar once one is locked, or on its day
  { path: '/review', name: 'WeeklyReview', component: page('WeeklyReview') },

  { path: '/ask', name: 'Ask', component: page('Ask') },
  { path: '/settings', name: 'Settings', component: page('Settings') },

  // ---- every route from before issue 14 lands on its new home, with its query ----
  // a bare /inbox is Needs you; one with a filter or a state (a count's door) is the Queue, the list that count is of
  { path: '/inbox', redirect: (r) => {
    const { all, area, space, ...rest } = r.query
    return { path: Object.keys(rest).length ? '/brain/queue' : '/brain', query: r.query, hash: r.hash }
  } },
  { path: '/inbox/:id/review', redirect: (r) => ({ path: `/brain/review/${r.params.id}`, query: r.query }) },
  // an inbox item opens in the pane over the list; old links to /inbox/:id still work
  { path: '/inbox/:id', redirect: (r) => ({ path: '/brain/queue', query: { ...r.query, open: `inbox:${r.params.id}` } }) },
  { path: '/plan', redirect: to('/today/week') },
  { path: '/plan/goals/:id', redirect: (r) => ({ path: `/goals/${r.params.id}`, query: r.query, hash: r.hash }) },
  { path: '/plan/reset', redirect: to('/today/reset') },
  { path: '/plan/12-weeks', redirect: to('/today/year', { view: 'cycle' }) },
  { path: '/plan/:tab(week|month|year|goals|tasks|someday)', redirect: (r) => ({ path: PLAN_HOME[r.params.tab], query: r.query, hash: r.hash }) },
  { path: '/library/captures', redirect: (r) => libraryKind(r) },
  { path: '/library/outbox', redirect: to('/brain/outbox') },
  { path: '/tasks', redirect: to('/goals/tasks') },
  { path: '/someday', redirect: to('/goals/someday') },
  { path: '/outbox', redirect: to('/brain/outbox') },
  { path: '/projects', redirect: (r) => ({ path: '/goals', query: projectQuery(r.query) }) },
  { path: '/projects/:id', name: 'Project', component: page('ProjectRedirect'), props: true },
  { path: '/reset', redirect: to('/today/week', { view: 'review', step: 'reset' }) },
  { path: '/calendar/:view?', redirect: (r) => {
    const v = r.params.view
    if (v === 'year') return { path: '/today/year', query: r.query }
    if (v === 'month') return { path: '/today/month', query: { ...r.query, view: 'calendar' } }
    return { path: '/today/week', query: { ...r.query, view: v === 'agenda' ? 'agenda' : 'calendar' } }
  } },
  { path: '/journal/goals/:id', redirect: (r) => ({ path: `/goals/${r.params.id}`, query: r.query }) },
  // journal pages are captures now: a page opens in the pane over Library > Everything
  { path: '/journal/pages/:id', redirect: (r) => ({ path: '/library', query: { ...r.query, tab: 'pages', open: `page:${r.params.id}` } }) },
  { path: '/journal/:tab?', redirect: (r) => {
    const t = r.params.tab
    const map = { goals: ['/today/year', { view: 'goals' }], month: ['/today/month', {}], habits: ['/today/month', { view: 'habits' }],
      checkins: ['/today/month', { view: 'checkins' }], review: ['/today/week', { view: 'review' }], pages: ['/library', { tab: 'pages' }] }
    const [path, extra] = map[t] || ['/today/year', { view: 'cycle' }]
    return { path, query: { ...r.query, ...extra } }
  } },
  { path: '/sources', redirect: (r) => libraryKind(r) },
  // Chats were a tab of Sources (set 4): filters carry over; the old report (group=day) is the By day view
  { path: '/chats', redirect: (r) => {
    const { group, open, view, ...rest } = r.query
    return { path: '/library/chats', query: { ...rest, tab: 'chats', ...(group === 'day' || view === 'report' ? { view: 'day' } : {}),
      ...(open ? { open: String(open).includes(':') ? open : 'chat:' + open } : {}) } }
  } },
  { path: '/wiki', redirect: to('/library/notes', (r) => ({ by: 'assistant', ...(r.query.tab && r.query.tab !== 'pages' ? { view: r.query.tab } : {}), tab: undefined })) },
  { path: '/vault', redirect: to('/library/documents', (r) => ({ tab: 'documents', sensitive: '1',
    ...(r.query.open && !String(r.query.open).includes(':') ? { open: 'vault:' + r.query.open } : {}) })) },
  { path: '/graph', redirect: to('/library/notes', { view: 'graph' }) },
  { path: '/timeline', redirect: to('/library/timeline') },
  { path: '/archive', redirect: to('/library/archive') },
  // area pages became the lens: an area opens Today narrowed to it; the list of areas is in Settings
  { path: '/areas', redirect: to('/settings', { tab: 'areas' }) },
  { path: '/areas/:id', redirect: (r) => ({ path: '/today', query: { ...r.query, tab: undefined, area: r.params.id } }) },

  // development only: the editor on a sample note (owner only, not in the sidebar)
  { path: '/dev/editor', name: 'EditorDev', component: () => import('./pages/dev/EditorDev.vue') },
  // development only: a screen that fails on purpose, for the error boundary's check (bug fix 1)
  { path: '/dev/throw', name: 'ThrowDev', component: () => import('./pages/dev/ThrowDev.vue') },
  { path: '/:rest(.*)*', redirect: '/today' },
]

// Opening or closing the pane and changing a filter only change the query: the list keeps its scroll position.
export default createRouter({ history: createWebHistory('/life'), routes,
  scrollBehavior: (to, from, saved) => (to.path === from.path ? false : saved || { top: 0 }) })
