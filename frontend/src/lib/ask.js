// Ask from any screen (UX fixes, set 5): the state of the Ask panel and the scope each screen gives a question.
// A screen calls askScope({...}) in its setup; the pane's "Ask about this" and the area, project and goal pages give
// their own. With none, the scope comes from the route (see scopeFromRoute).
import { onMounted, onUnmounted, reactive } from 'vue'
import router from '@/router'

export const ask = reactive({
  open: false, // the panel (desktop) or sheet (phone)
  thread: null, // the thread shown
  scope: null, // the scope chip of the next question: { kind, label, doctype, name, items }
  pageScope: null, // what the current screen offers
  draft: '',
  seq: 0, // bumped to send `draft` as soon as the panel opens
})

export function askScope(scope) {
  onMounted(() => { ask.pageScope = scope })
  onUnmounted(() => { if (ask.pageScope === scope) ask.pageScope = null })
}

const SPACE_WIDE = ['/', '/tasks', '/inbox', '/sources', '/timeline', '/calendar', '/archive', '/vault', '/areas']
/** The scope a question starts with, from where the owner is (the table in UX_FIXES_5.md, section 2). */
export function scopeFromRoute(route = router.currentRoute.value) {
  const p = route.path
  const first = '/' + (p.split('/')[1] || '')
  if (ask.pageScope) return { ...ask.pageScope }
  if (p.startsWith('/journal/goals/')) return { kind: 'goal', label: 'This goal', doctype: 'Life Goal', name: p.split('/')[3] }
  if (first === '/journal') return { kind: 'journal', label: 'This cycle and month' }
  if (first === '/goals') return { kind: 'goals', label: 'All goals' }
  if (first === '/library' && route.params.id) return { kind: 'record', label: 'This page', doctype: 'Life Note', name: route.params.id }
  if (first === '/library' || first === '/wiki' || first === '/graph') return { kind: 'notes', label: first === '/wiki' ? 'All wiki pages' : 'All notes' }
  if (SPACE_WIDE.includes(first) || first === '/ask') return { kind: 'space', label: 'Everything in this space' }
  return { kind: 'space', label: 'Everything in this space' }
}

/** Open the panel with a question, in a scope (the screen's by default). An empty question just opens the panel. */
export function startAsk(question = '', scope = null) {
  ask.scope = scope || scopeFromRoute()
  ask.thread = null
  ask.draft = question
  ask.open = true
  if (question) ask.seq++
}

/** The record pane's "Ask about this": the record and the records linked to it. */
export function askAbout(doctype, name, title) {
  startAsk('', { kind: 'record', label: title || 'This record', doctype, name })
}

// a question reads as a question: ends with "?", starts with a question word, or is more than six words
const WORDS = /^(what|why|how|when|where|who|whom|which|is|are|was|were|do|does|did|can|could|should|would|will|have|has|had|show|list|summarise|summarize|tell|find|give)\b/i
export function isQuestion(text) {
  const t = String(text || '').trim()
  return !!t && (t.endsWith('?') || WORDS.test(t) || t.split(/\s+/).length > 6)
}
