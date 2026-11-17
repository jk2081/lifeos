// Ask from any screen (UX fixes, set 5): the state of the Ask panel and the scope each screen gives a question.
// A screen calls askScope({...}) in its setup; the pane's "Ask about this" and the goal pages give
// their own. With none, the scope comes from the route (see scopeFromRoute).
import { onMounted, onUnmounted, reactive } from 'vue'
import router from '@/router'
import { toast } from 'frappe-ui'
import { api, errorText } from './api'
import { store } from './store'
import { lookups } from './lookups'
import { openRef, recordChanged } from './pane'

export const ask = reactive({
  messages: [], // the open thread's messages: { role, text, status, cited, actions, read }
  busy: false,
  refusal: null, // { error: 'not_set_up' | 'cap' | 'off' | 'ai', error_text, spend }
  open: false, // the panel (desktop) or sheet (phone)
  thread: null, // the thread shown
  scope: null, // the scope chip of the next question: { kind, label, doctype, name, items }
  pageScope: null, // what the current screen offers
  draft: '',
  scopeChanged: false,
  seq: 0, // bumped to send `draft` as soon as the panel opens
  returnTo: null, // phone: the path to reopen the Ask sheet on once the cited record is closed
})

export function askScope(scope) {
  onMounted(() => { ask.pageScope = scope })
  onUnmounted(() => { if (ask.pageScope === scope) ask.pageScope = null })
}

/** The scope a question starts with, from where the owner is (UX_FIXES_5.md, section 2), and the lens (set 6). */
export function scopeFromRoute(route = router.currentRoute.value) {
  const p = route.path
  if (ask.pageScope) return typeof ask.pageScope === 'function' ? ask.pageScope() : { ...ask.pageScope }
  if (p.startsWith('/plan/goals/')) return { kind: 'goal', label: 'This goal', doctype: 'Life Goal', name: p.split('/')[3] }
  if (route.name === 'Note' && route.params.id) return { kind: 'record', label: 'This page', doctype: 'Life Note', name: route.params.id }
  if (store.lensArea) return lensScope() // a place narrowed to an area: questions start in that area
  if (['/plan/week', '/plan/month', '/plan/12-weeks', '/plan/year'].includes(p)) return { kind: 'journal', label: 'This cycle and month' }
  if (p === '/plan/goals') return { kind: 'goals', label: 'All goals' }
  if (p === '/library/notes') return { kind: 'notes', label: route.query.by === 'assistant' ? "The assistant's notes" : 'All notes' }
  return lensScope()
}
/** The scope of the lens (UX fixes, set 6): the lens's area with its sub-areas, or everything in the space. */
export function lensScope() {
  const a = store.lensArea && (lookups.areas || []).find((x) => x.name === store.lensArea)
  if (store.lensArea) return { kind: 'area', label: a?.area_name || 'This area', doctype: 'Life Area', name: store.lensArea }
  return { kind: 'space', label: 'Everything in this space' }
}

/** Open the panel with a question, in a scope (the screen's by default). An empty question just opens the panel. */
export function startAsk(question = '', scope = null) {
  ask.scope = scope || scopeFromRoute()
  ask.returnTo = null
  ask.thread = null
  ask.messages = []
  ask.refusal = null
  ask.draft = question
  ask.open = true
  if (question) send(question)
}

/** Send a question in the open thread (a follow-up keeps the thread's scope unless the chip was changed). */
export async function send(question) {
  const q = String(question || '').trim()
  if (!q || ask.busy) return
  ask.draft = ''
  ask.refusal = null
  ask.busy = true
  const clientId = Math.random().toString(36).slice(2) + Date.now().toString(36)
  ask.messages.push({ role: 'user', text: q })
  const answer = reactive({ role: 'assistant', text: '', status: 'Working', cited: [], actions: [], read: [] })
  ask.messages.push(answer)
  // the answer streams: realtime is not always there, so the text so far is polled
  let polling = true
  const poll = async () => {
    while (polling) {
      await new Promise((r) => setTimeout(r, 700))
      if (!polling) break
      try {
        const p = await api('ask.progress', { client_id: clientId })
        if (polling && p.text) answer.text = p.text
      } catch (e) { /* the final answer will come */ }
    }
  }
  poll()
  try {
    const scope = ask.scope ? { ...ask.scope, items: typeof ask.scope.items === 'function' ? ask.scope.items() : ask.scope.items } : null
    const res = await api('ask.ask', { question: q, space: store.space, thread: ask.thread || undefined, scope: ask.thread && !ask.scopeChanged ? undefined : JSON.stringify(scope),
      client_id: clientId })
    ask.thread = res.thread
    ask.scopeChanged = false
    if (res.error) {
      ask.messages.pop()
      ask.refusal = res
    } else Object.assign(answer, res.message)
  } catch (e) {
    Object.assign(answer, { status: 'Error', error: errorText(e) })
  } finally {
    polling = false
    ask.busy = false
  }
}

export async function loadThread(name) {
  const t = await api('ask.thread', { name })
  ask.thread = t.name
  ask.scope = t.scope
  ask.messages = t.messages
  ask.refusal = null
}

/** A suggested action: nothing changed until this click; the normal methods run with the person's permissions. */
export async function runAction(message, index) {
  const a = message.actions[index]
  try {
    const out = await api('ask.run_action', { message: message.name, index })
    if (out.to) { ask.open = false; return router.push(out.to) }
    a.done = true
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    if (out.kind === 'make_task') {
      recordChanged('task:' + out.task)
      toast.success(`Task made: ${out.title}`, { duration: 60000, action: { label: 'Undo', onClick: async () => { await api('ask.undo_made_task', { task: out.task }); a.done = false; recordChanged('task:' + out.task) } } })
    } else if (out.undo) {
      toast.success(`${a.label}: done.`, { duration: 60000, action: { label: 'Undo', onClick: async () => { await api('reset.undo', { log: JSON.stringify(out.undo) }); a.done = false; recordChanged('') } } })
    } else toast.success('Done.')
  } catch (e) { toast.error(errorText(e)) }
}

export function openCite(message, n) {
  const c = (message.cited || []).find((x) => x.n === n)
  if (c && c.pane) {
    // On a phone both are bottom sheets and the record's would open under the Ask sheet: hand over to the record, and
    // bring the Ask sheet back, with its thread, when the record is closed on the same screen (AskPanel watches this).
    if (window.matchMedia('(max-width: 767px)').matches && ask.open) {
      ask.returnTo = router.currentRoute.value.path
      ask.open = false
    }
    openRef(c.pane)
  } else if (c) toast.info(`${c.kind}: ${c.title}`)
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
