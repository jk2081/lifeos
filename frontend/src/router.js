import { createRouter, createWebHistory } from 'vue-router'

const page = (name) => () => import(`./pages/${name}.vue`)

// The places (issue 14): Today, Brain, Goals and Library, each tab its own path, with Review, Settings and the Ask page
// beside them. Housekeeping pages live inside the place they belong to and are not tabs: the Outbox
// under Brain, Someday under Goals, the Timeline and the trash and archive under Library.
const TODAY = ['week', 'month', 'year']
const BRAIN = ['activity', 'captures', 'sources', 'skills', 'outbox', 'queue']
const GOALS = ['tasks', 'no-goal', 'cycles', 'someday']
const LIBRARY = ['pages', 'notes', 'documents', 'people', 'chats', 'files', 'timeline', 'archive']

const routes = [
  { path: '/', redirect: '/today' },
  { path: `/today/:tab(${TODAY.join('|')})?`, name: 'Today', component: page('TodayPlace'), props: true },
  { path: `/brain/:tab(${BRAIN.join('|')})?`, name: 'Brain', component: page('BrainPlace'), props: true },
  { path: '/brain/sources/:key', name: 'Source', component: page('SourcePage') },
  { path: '/brain/skills/:name', name: 'Skill', component: page('Skill'), props: true },
  { path: '/brain/review/:id', name: 'ItemReview', component: page('Review'), props: true },
  // issue 50: the screen the phone's share target opens
  { path: '/share', name: 'Share', component: page('Share') },
  // issue 10: one page per capture, with its source, files, summary, decisions and what came of it
  { path: '/item/:id', name: 'Item', component: page('Item'), props: true },
  { path: `/goals/:tab(${GOALS.join('|')})?`, name: 'Goals', component: page('GoalsPlace'), props: true },
  { path: '/goals/:id', name: 'Goal', component: page('Goal'), props: true },
  { path: '/focus/:id', name: 'Focus', component: page('Focus'), props: true },
  { path: `/library/:tab(${LIBRARY.join('|')})?`, name: 'Library', component: page('LibraryPlace'), props: true },
  // issue 111: a page for a person, a company, a part or a note
  { path: '/library/pages/:doctype/:name', name: 'Page', component: page('PagePage'), props: true },
  { path: '/library/people/:person', name: 'Person', component: page('LibraryPlace'), props: (r) => ({ tab: 'people', person: r.params.person }) },
  { path: '/library/:id', name: 'Note', component: page('Library'), props: true },
  // the weekly review: in the sidebar once one is locked, or on its day
  { path: '/review', name: 'WeeklyReview', component: page('WeeklyReview') },

  { path: '/how-it-works', name: 'HowItWorks', component: page('HowItWorks') },
  { path: '/ask', name: 'Ask', component: page('Ask') },
  { path: '/settings', name: 'Settings', component: page('Settings') },

  // development only: the editor on a sample note (owner only, not in the sidebar)
  { path: '/dev/editor', name: 'EditorDev', component: () => import('./pages/dev/EditorDev.vue') },
  // development only: a screen that fails on purpose, for the error boundary's check (bug fix 1)
  { path: '/dev/throw', name: 'ThrowDev', component: () => import('./pages/dev/ThrowDev.vue') },
  // any address that is not a screen lands on Today, which says the page moved (issue 61)
  { path: '/:rest(.*)*', redirect: { path: '/today', query: { moved: '1' } } },
]

// Opening or closing the pane and changing a filter only change the query: the list keeps its scroll position.
export default createRouter({ history: createWebHistory('/life'), routes,
  scrollBehavior: (to, from, saved) => (to.path === from.path ? false : saved || { top: 0 }) })
