// Chat from any screen (UX fixes, set 5; Chat since issue 119): the state of the Chat panel and the scope each screen gives a question.
// A screen calls askScope({...}) in its setup; the pane's "Ask about this" and the goal pages give
// their own. With none, the scope comes from the route (see scopeFromRoute).
import { onMounted, onUnmounted, reactive, watch } from 'vue'
import router from '@/router'
import { toast } from 'frappe-ui'
import { api, errorText } from './api'
import { canWrite, store } from './store'
import { lookups } from './lookups'
import { openRef, parseOpen, recordChanged, TYPES } from './pane'
import { submitCapture } from './offline'
import { uploadFile } from './upload'

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
  wide: false, // Expand: the panel takes the whole width beside the menu (issue 120)
  view: 'chat', // 'chat' or 'history' (earlier conversations)
  files: [], // what the owner added to the next message: { file, name, size }
  scopeAuto: true, // the chip follows where the owner is, until they remove it
  sentScope: '', // the scope the thread last heard, so a changed chip is sent again
  record: null, // the record the owner has open: { doctype, name, label }
  recording: false, // the mic is listening
  loaded: false, // the one ongoing conversation has been looked for
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

/** Open the chat panel (laptop) or sheet (phone). The one ongoing conversation is opened: the newest, unless a thread is already showing. */
export async function openChat() {
  ask.open = true
  syncScope() // the chip is where the owner is now (the areas may have loaded since it was last set)
  if (!ask.loaded) {
    ask.loaded = true
    if (!ask.thread && !ask.messages.length) {
      try {
        const { name } = await api('chat.latest', { space: store.space })
        if (name && !ask.thread && !ask.messages.length) await loadThread(name)
      } catch (e) { /* a new conversation */ }
    }
  }
}
export function toggleChat() {
  if (ask.open) ask.open = false
  else openChat()
}

/** Open the chat with a question, in a scope (where the owner is, by default). It joins the one ongoing conversation; an empty question just opens it. */
export function startAsk(question = '', scope = null) {
  if (scope) { ask.scope = scope; ask.scopeAuto = false }
  ask.returnTo = null
  ask.view = 'chat'
  ask.refusal = null
  ask.draft = question
  openChat().then(() => { if (question) send(question) })
}

/** A new conversation: the old one stays under History. */
export function newChat() {
  ask.thread = null
  ask.channel = ''
  ask.title = ''
  ask.messages = []
  ask.refusal = null
  ask.sentScope = ''
  ask.view = 'chat'
  ask.scopeAuto = true
  syncScope()
}

// ---- the chip: where the owner is (a record on the screen, or the pane's record) ----
const labels = new Map()
async function labelOf(doctype, name) {
  const key = `${doctype}:${name}`
  if (!labels.has(key)) {
    try { labels.set(key, (await api('chat.about', { doctype, name })).label) } catch (e) { labels.set(key, '') }
  }
  return labels.get(key)
}
/** The record the screen is about: the pane's, or the goal or note page. */
export function recordOnScreen(route = router.currentRoute.value) {
  const open = parseOpen(route)
  if (open && TYPES[open.type]?.doctype) return { doctype: TYPES[open.type].doctype, name: open.name }
  if (route.name === 'Goal' && route.params.id) return { doctype: 'Life Goal', name: String(route.params.id) }
  if (route.name === 'Note' && route.params.id) return { doctype: 'Life Note', name: String(route.params.id) }
  return null
}
let seq = 0
/** Point the chip at where the owner is now, unless they removed it. */
export async function syncScope() {
  if (!ask.scopeAuto) return
  const mine = ++seq
  const rec = recordOnScreen()
  if (!rec) {
    ask.record = null
    ask.scope = scopeFromRoute()
    return
  }
  const label = await labelOf(rec.doctype, rec.name)
  if (mine !== seq || !ask.scopeAuto) return
  ask.record = { ...rec, label }
  ask.scope = { kind: rec.doctype === 'Life Goal' ? 'goal' : 'record', label: label ? `About: ${label}` : 'About: this', doctype: rec.doctype, name: rec.name }
}
/** The chip's x: the next messages are about everything, until the owner opens another record. */
export function clearScope() {
  ask.scopeAuto = false
  ask.record = null
  ask.scope = { kind: 'space', label: 'Everything in this space' }
}
let watching = false
export function followRoute() {
  if (watching) return
  watching = true
  watch(() => [router.currentRoute.value.fullPath, store.lensArea, ask.pageScope], () => {
    const r = recordOnScreen()
    const same = (ask.record?.doctype || '') + (ask.record?.name || '') === (r ? r.doctype + r.name : '')
    if (!same) ask.scopeAuto = true // another record: the chip comes back
    syncScope()
  }, { immediate: true })
}

// ---- files, the mic ----
export function addFiles(list) {
  for (const f of list || []) if (f && f.name && !ask.files.some((x) => x.file === f)) ask.files.push({ file: f, name: f.name, size: f.size })
  if (ask.files.length) openChat()
}
export function removeFile(i) { ask.files.splice(i, 1) }

/** The mic's recording to text on the server (faster-whisper); the text goes into the box to check and send. Nothing is sent to a model. */
export async function transcribe(blob, name) {
  const file = new File([blob], name, { type: blob.type })
  const up = await uploadFile(file)
  const out = await api('chat.transcribe', { file: up.name })
  if (!out.text) toast.info(out.note || 'Nothing was heard.')
  return out.text
}

/** Send what the owner wrote and added. A message with no question and no file, where they have no record open, is a capture: the Brain files it. */
export async function sendOrCapture(text) {
  const t = String(text || '').trim()
  if (!t && !ask.files.length) return
  if (t && canWrite() && !ask.files.length && !ask.record && !isQuestion(t) && !COMMAND.test(t)) return capture(t)
  await openChat() // the answer is shown in the panel or sheet
  return send(t)
}
async function capture(text) {
  ask.draft = ''
  try {
    const how = await submitCapture({ title: text.split('\n')[0].slice(0, 80), source_type: 'Message', space: store.space, raw_text: text, intent: 'Process', files: [] })
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    toast.success(how === 'queued' ? 'Kept on this phone. It is sent when you are back online.' : 'Sent to the Brain. It files it and asks you only if it needs to.')
  } catch (e) { toast.error(errorText(e)); ask.draft = text }
}

/** Send a message in the open thread. The run is Flow's: `chat.send` starts it and the screen polls `chat.progress` until the answer is Done. The record the person
 *  has open travels with it, and so do the files, which are uploaded first and read on the server before any model sees them. */
export async function send(question, record = null) {
  const q = String(question || '').trim()
  if ((!q && !ask.files.length) || ask.busy) return
  ask.draft = ''
  ask.refusal = null
  ask.busy = true
  const sending = ask.files.splice(0)
  ask.messages.push({ role: 'user', text: q || 'Added a file.', attached: sending.map((f) => f.name) })
  const answer = reactive({ role: 'assistant', text: '', status: 'Working', cited: [], actions: [], done: [], read: [], reading: '' })
  ask.messages.push(answer)
  try {
    const names = []
    for (const f of sending) names.push((await uploadFile(f.file)).name)
    const scope = ask.scope ? { ...ask.scope, items: typeof ask.scope.items === 'function' ? ask.scope.items() : ask.scope.items } : null
    const mark = JSON.stringify([scope?.kind, scope?.doctype, scope?.name])
    const open = record || recordOf(ask.scope)
    const res = await api('chat.send', { question: q, space: store.space, thread: ask.thread || undefined, scope: ask.thread && ask.sentScope === mark ? undefined : JSON.stringify(scope),
      record: open ? JSON.stringify(open) : undefined, files: names.length ? JSON.stringify(names) : undefined })
    ask.thread = res.thread
    ask.sentScope = mark
    ask.scopeChanged = false
    if (res.error) {
      ask.refusal = res
      if (res.done?.length) Object.assign(answer, { status: 'Done', done: res.done }) // the files were saved all the same: no model is needed for that
      else { ask.messages.splice(-2, 2); ask.files.unshift(...sending) }
    } else {
      Object.assign(answer, res.message)
      while (answer.status === 'Working') {
        await new Promise((r) => setTimeout(r, 900))
        try { Object.assign(answer, await api('chat.progress', { thread: res.thread, message: answer.name })) } catch (e) { /* the next poll will tell */ }
      }
      if (answer.done?.length || sending.length) { window.dispatchEvent(new CustomEvent('lifeos-counts-stale')); recordChanged('') }
    }
  } catch (e) {
    Object.assign(answer, { status: 'Error', error: errorText(e) })
    if (sending.length && !ask.files.length) ask.files.push(...sending)
  } finally {
    ask.busy = false
  }
}

/** The owner's tap on "Whose is this?": the card is saved for that person. */
export async function answerCard(message, index, holder) {
  try {
    const out = await api('chat.answer_card', { thread: ask.thread, message: message.name, index, holder })
    message.questions = (message.questions || []).filter((q) => q.index !== index)
    message.done = [...(message.done || []), out.line]
    recordChanged('')
  } catch (e) { toast.error(errorText(e)) }
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
  ask.loaded = true
  ask.sentScope = JSON.stringify([t.scope?.kind, t.scope?.doctype, t.scope?.name])
  ask.messages = t.messages
  ask.refusal = null
  ask.view = 'chat'
  ask.scopeAuto = true // the chip follows where the owner is now, not where the old conversation was
  syncScope()
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
  startAsk('', { kind: 'record', label: `About: ${title || 'this record'}`, doctype, name })
}

// a question reads as a question: ends with "?", starts with a question word, or is more than six words
const WORDS = /^(what|why|how|when|where|who|whom|which|is|are|was|were|do|does|did|can|could|should|would|will|have|has|had|show|list|summarise|summarize|tell|find|give)\b/i
// a request to Chat that is not a question: "add a note…", "cancel…", "make a task…"
const COMMAND = /^(add|make|create|cancel|delete|remove|move|reschedule|schedule|remind|file|save|put|note|tell|set|mark|follow|change|rename|link|book|call|send)\b/i
export function isQuestion(text) {
  const t = String(text || '').trim()
  return !!t && (t.endsWith('?') || WORDS.test(t) || t.split(/\s+/).length > 6)
}
