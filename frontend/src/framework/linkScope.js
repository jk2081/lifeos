// The one place that narrows link searches for the filing DocTypes: areas, tags, habits, dimensions and goals.
// Every picker, Filter and QuickFilter of @framework/ui searches with frappe.desk.search.search_link, and the library's
// Filter and QuickFilter send no filters of their own. So this helper adds them to that one request: the current space,
// and (on the server, lifeos/queries.py) only active records: not archived; goals in progress.
// A screen that needs more says so with useLinkScope(): the Archive asks for archived records too, marked "(archived)",
// and a list on a goal state tab that holds closed goals asks for those outcomes.
import { onBeforeUnmount, onMounted } from 'vue'
import { store } from '@/lib/store'

export const SCOPED_DOCTYPES = ['Life Area', 'Life Tag', 'Life Habit', 'Life Dimension', 'Life Goal']
const overrides = [] // a stack: the innermost screen wins

/** The filters a link search for `doctype` gets: { space, include_archived?, goal_outcome? } */
export function linkFilters(doctype, extra = {}) {
  if (!SCOPED_DOCTYPES.includes(doctype)) return extra
  const top = overrides[overrides.length - 1] || {}
  const out = { space: store.space }
  if (top.archived) out.include_archived = 1
  if (doctype === 'Life Goal' && top.goalOutcome?.length) out.goal_outcome = top.goalOutcome
  return { ...out, ...extra }
}

/** Widen the link searches while the calling component is on screen: { archived: true } or { goalOutcome: ['Achieved'] }.
 *  `get` may be a function, read at each search. */
export function useLinkScope(get) {
  const entry = { get archived() { return (typeof get === 'function' ? get() : get).archived },
    get goalOutcome() { return (typeof get === 'function' ? get() : get).goalOutcome } }
  onMounted(() => overrides.push(entry))
  onBeforeUnmount(() => { const i = overrides.indexOf(entry); if (i >= 0) overrides.splice(i, 1) })
}

function scope(body) {
  if (!body || !SCOPED_DOCTYPES.includes(body.doctype)) return body
  let given = body.filters
  if (typeof given === 'string') { try { given = JSON.parse(given || '{}') } catch { given = {} } }
  if (Array.isArray(given)) given = Object.fromEntries(given.map((f) => [f.length > 3 ? f[1] : f[0], f[f.length - 1]]))
  return { ...body, filters: linkFilters(body.doctype, given || {}) }
}

/** Install once at start-up: every search_link request for a scoped DocType gets linkFilters(). */
export function installLinkScope() {
  if (window.__lifeLinkScope) return
  window.__lifeLinkScope = true
  const fetch0 = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || ''
    if (url.includes('frappe.desk.search.search_link')) {
      try {
        if (init.body && typeof init.body === 'string') {
          init = { ...init, body: JSON.stringify(scope(JSON.parse(init.body))) }
        } else if (!init.body && url.includes('?')) {
          const [path, q] = url.split('?')
          const params = Object.fromEntries(new URLSearchParams(q))
          const next = scope(params)
          if (next !== params) input = path + '?' + new URLSearchParams({ ...next, filters: JSON.stringify(next.filters) })
        }
      } catch { /* leave a request we cannot read as it is */ }
    }
    return fetch0(input, init)
  }
}
