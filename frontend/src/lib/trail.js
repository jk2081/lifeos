// Where am I (issue 83): the path above every page below a place, and the browser tab's title.
// A page gives its ancestors as a list of { label, to }, place first: Goals / Career for a goal in Career. The page's own title is the last part.
export const APP_NAME = 'Life OS'

/** The path of a page: its ancestors (each a link), then its own title (not a link). */
export function trailOf(ancestors, title) {
  return [...(ancestors || []).map((a) => ({ label: a.label, to: a.to })), { label: title }]
}
/** The browser tab's title: the path in reverse, `Documents (PDF) · Sources · Brain — Life OS`. */
export function tabTitle(title, ancestors) {
  const parts = [title, ...(ancestors || []).map((a) => a.label).reverse()].filter(Boolean)
  return `${parts.join(' · ')} — ${APP_NAME}`
}
