// Chat from any screen (UX fixes, set 5; Chat since issue 119): the state of the Chat panel and the scope each screen gives a question.
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
  channel: '', // set when it is a conversation relayed from an assistant's channel ("Telegram"): read only here
  title: '',
  scope: null, // the scope chip of the next question: { kind, label, doctype, name, items }
  pageScope: null, // what the current screen offers
  draft: '',
  scopeChanged: false,
  seq: 0, // bumped to send `draft` as soon as the panel opens
  returnTo: null, // phone: the path to reopen the Chat sheet on once the cited record is closed
})

export function askScope(scope) {
  onMounted(() => { ask.pageScope = scope })
  onUnmounted(() => { if (ask.pageScope === scope) ask.pageScope = null })
}

/** The scope a question starts with, from where the owner is (UX_FIXES_5.md, section 2), and the lens (set 6). */
export function scopeFromRoute(route = router.currentRoute.value) {
  const p = route.path
  if (ask.pageScope) return typeof ask.pageScope === 'function' ? ask.pageScope() : { ...ask.pageScope }
  if (route.name === 'Goal' && route.params.id) return { kind: 'goal', label: 'This goal', doctype: 'Life Goal', name: route.params.id }
  if (route.name === 'Note' && route.params.id) return { kind: 'record', label: 'This page', doctype: 'Life Note', name: route.params.id }
  if (store.lensArea) return lensScope() // a place narrowed to an area: questions start in that area
  if (['/today/week', '/today/month', '/today/year'].includes(p)) return { kind: 'cycle', label: 'This cycle and month' }
  if (p === '/goals') return { kind: 'goals', label: 'All goals' }
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
  ask.channel = ''
  ask.messages = []
  ask.refusal = null
  ask.draft = question
  ask.open = true
  if (question) send(question)
}

/** Send a message in the open thread (a follow-up keeps the thread's scope unless the chip was changed). The run is Flow's: `chat.send` starts it and the
 *  screen polls `chat.progress` until the answer is Done. The record the person has open (the pane's, or a goal or note page) travels with it. */
export async function send(question, record = null) {
  const q = String(question || '').trim()
  if (!q || ask.busy) return
  ask.draft = ''
  ask.refusal = null
  ask.busy = true
  ask.messages.push({ role: 'user', text: q })
  const answer = reactive({ role: 'assistant', text: '', status: 'Working', cited: [], actions: [], done: [], read: [], reading: '' })
  ask.messages.push(answer)
  try {
    const scope = ask.scope ? { ...ask.scope, items: typeof ask.scope.items === 'function' ? ask.scope.items() : ask.scope.items } : null
    const open = record || recordOf(ask.scope)
    const res = await api('chat.send', { question: q, space: store.space, thread: ask.thread || undefined, scope: ask.thread && !ask.scopeChanged ? undefined : JSON.stringify(scope),
      record: open ? JSON.stringify(open) : undefined })
    ask.thread = res.thread
    ask.scopeChanged = false
    if (res.error) {
      ask.messages.pop()
      ask.refusal = res
    } else {
      Object.assign(answer, res.message)
      while (answer.status === 'Working') {
        await new Promise((r) => setTimeout(r, 900))
        try { Object.assign(answer, await api('chat.progress', { thread: res.thread, message: answer.name })) } catch (e) { /* the next poll will tell */ }
      }
      if (answer.done?.length) { window.dispatchEvent(new CustomEvent('lifeos-counts-stale')); recordChanged('') }
    }
  } catch (e) {
    Object.assign(answer, { status: 'Error', error: errorText(e) })
  } finally {
    ask.busy = false
  }
}

/** The record a scope is about (a goal page, a note, the pane's record), when it is one. */
function recordOf(scope) {
  return scope && scope.doctype && scope.name ? { doctype: scope.doctype, name: scope.name } : null
}

export async function loadThread(name) {
  const t = await api('chat.thread', { name })
  ask.thread = t.name
  ask.channel = t.channel || ''
  ask.title = t.title || ''
  ask.scope = t.scope
  ask.messages = t.messages
  ask.refusal = null
}

/** One line of an answer's Done list taken back: what Chat made is removed, and the line says so. */
export async function undoDone(message, index) {
  const line = message.done[index]
  try {
    await api('chat.undo_done', { message: message.name, index })
    line.undone = 1
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    recordChanged('')
    toast.success('Undone.')
  } catch (e) { toast.error(errorText(e)) }
}

/** Open a record from the Chat panel. On a phone both are bottom sheets and the record's would open under the Chat sheet: hand over to the record, and
 *  bring the Chat sheet back, with its thread, when the record is closed on the same screen (AskPanel watches this). */
export function openPane(pane) {
  if (window.matchMedia('(max-width: 767px)').matches && ask.open) {
    ask.returnTo = router.currentRoute.value.path
    ask.open = false
  }
  openRef(pane)
}

export function openCite(message, n) {
  const c = (message.cited || []).find((x) => x.n === n)
  if (c && c.pane) openPane(c.pane)
  else if (c && c.route) router.push(c.route)
  else if (c) toast.info(`${c.kind}: ${c.title}`)
}

/** The record pane's "Chat about this": the record and the records linked to it. */
export function askAbout(doctype, name, title) {
  startAsk('', { kind: 'record', label: title || 'This record', doctype, name })
}

// a question reads as a question: ends with "?", starts with a question word, or is more than six words
const WORDS = /^(what|why|how|when|where|who|whom|which|is|are|was|were|do|does|did|can|could|should|would|will|have|has|had|show|list|summarise|summarize|tell|find|give)\b/i
export function isQuestion(text) {
  const t = String(text || '').trim()
  return !!t && (t.endsWith('?') || WORDS.test(t) || t.split(/\s+/).length > 6)
}
