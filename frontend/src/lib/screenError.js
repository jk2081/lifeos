// A screen that fails to render (bug fix 1). ScreenBoundary (around the routed page in App.vue), app.config.errorHandler
// and router.onError all come here. The failure shows as a plain message in the page area while the sidebar, the lens
// and navigation keep working; it is logged to the console with its stack and to Frappe's Error Log under a short
// reference, with no record contents.
import { ref } from 'vue'
import { call } from 'frappe-ui'

// { reference, kind: 'render' | 'chunk', hard, href } while a screen is broken; null otherwise. `href` is the screen a
// failed navigation was going to, which Reload opens.
export const screenError = ref(null)

// Vue's error codes (the `info` of an error hook: a name in development, `…#runtime-<code>` in production). Only these
// stop a screen from being shown; an event handler or a lifecycle hook that fails leaves the screen as it is.
const FATAL = { 'setup function': '0', 'render function': '1', 'async component loader': '13', 'scheduler flush': '14', 'component update': '15' }
// a failure inside Vue's patching (not in a render function) can leave the page's tree half built, so leaving the screen
// then loads the next one afresh instead of patching over it
const HARD = new Set(['14', '15'])

export function errorCode(info) {
  const s = String(info || '')
  return s.match(/#runtime-(\w+)$/)?.[1] ?? FATAL[s] ?? s
}
export const isFatal = (info) => Object.values(FATAL).includes(errorCode(info))

// a lazy-loaded screen's file that is gone after a rebuild
export function isChunkError(err) {
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i
    .test(String(err?.message || err))
}

const newReference = () => Math.random().toString(36).slice(2, 8).toUpperCase()
let sent = 0
const MAX_SENT = 5 // a page load never sends more than this; the server limits each user as well

function send(reference, err, info, kind, component) {
  if (sent >= MAX_SENT) return
  sent += 1
  call('lifeos.api.client_errors.log', {
    reference, kind, info: String(errorCode(info)), component: component || '', path: window.location.pathname,
    message: String(err?.message || err).slice(0, 500), stack: String(err?.stack || '').slice(0, 4000),
  }).catch(() => {})
}

const componentName = (instance) => instance?.$options?.name || instance?.$options?.__name || ''

// a screen could not be shown: show the message, log it, and report it once
export function failScreen(err, { info = '', instance = null, kind = 'render', hard = false, href = '' } = {}) {
  if (screenError.value) {
    // already showing the message: a second failure while the broken page is taken down only makes leaving it a full load
    if (hard) screenError.value.hard = true
    console.error('[Life OS] a further screen error', err)
    return screenError.value.reference
  }
  const reference = newReference()
  screenError.value = { reference, kind, href, hard: hard || HARD.has(errorCode(info)) }
  console.error(`[Life OS] This screen could not be shown (reference ${reference}, ${info || kind})`, err)
  send(reference, err, info, kind, componentName(instance))
  return reference
}

export function clearScreenError() {
  screenError.value = null
}

// Vue's app-level handler: anything a screen did not handle. Errors that stop rendering show the message; the rest are
// only logged to the console, as Vue does without a handler.
export function appErrorHandler(err, instance, info) {
  if (isFatal(info)) failScreen(err, { info, instance, hard: true })
  else console.error(err)
}

// A failed navigation: a lazy-loaded screen that cannot be fetched gets the message that a newer version is out.
export function routerErrorHandler(err, to) {
  if (isChunkError(err)) failScreen(err, { kind: 'chunk', info: 'async component loader', href: to?.href || '' })
  else console.error(err)
}
