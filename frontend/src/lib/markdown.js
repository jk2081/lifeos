import MarkdownIt from 'markdown-it'

// Markdown is rendered with raw HTML switched off, then passed through DOMPurify in the browser.
// markdown-it itself refuses javascript:, vbscript: and data: links.
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const escapeHtml = md.utils.escapeHtml
const WIKI = /^\[\[([^\[\]#|\n]+?)(?:#([^\[\]\n]+?))?\]\]/

// [[Title]] and [[Title#id]] links. Resolved ones become links, the rest are shown muted.
md.inline.ruler.before('link', 'wikilink', (state, silent) => {
  if (state.src.charCodeAt(state.pos) !== 0x5b || state.src.charCodeAt(state.pos + 1) !== 0x5b) return false
  const m = WIKI.exec(state.src.slice(state.pos))
  if (!m) return false
  if (!silent) {
    const token = state.push('wikilink', '', 0)
    token.meta = { text: m[1].trim(), id: (m[2] || '').trim() }
  }
  state.pos += m[0].length
  return true
})
md.renderer.rules.wikilink = (tokens, idx, options, env) => {
  const { text, id } = tokens[idx].meta
  const links = (env && env.links) || []
  const hit = links.find((l) => (id ? l.name === id : (l.text || '').toLowerCase() === text.toLowerCase()))
  if (hit && hit.ambiguous) return `<a class="wl ambiguous" href="/life${escapeHtml(hit.route)}" title="More than one wiki page has this title. This link goes to the oldest.">${escapeHtml(hit.title || text)} ⚠</a>`
  if (hit) return `<a class="wl" href="/life${escapeHtml(hit.route)}">${escapeHtml(hit.title || text)}</a>`
  return `<span class="wl missing" title="No record with this title yet">${escapeHtml(text)}</span>`
}
// Ask's citations (UX fixes, set 5): [3] after a claim is a numbered marker that opens the cited record, when the
// renderer is given the list of cited records (env.cites). Elsewhere [3] stays text.
md.inline.ruler.before('link', 'cite', (state, silent) => {
  const cites = state.env && state.env.cites
  if (!cites || state.src.charCodeAt(state.pos) !== 0x5b) return false
  const m = /^\[(\d{1,2})\]/.exec(state.src.slice(state.pos))
  if (!m || !cites.some((c) => String(c.n) === m[1])) return false
  if (!silent) state.push('cite', '', 0).meta = { n: m[1] }
  state.pos += m[0].length
  return true
})
md.renderer.rules.cite = (tokens, idx, options, env) => {
  const n = tokens[idx].meta.n
  const c = env.cites.find((x) => String(x.n) === n)
  return `<sup><a class="cite" href="#" data-cite="${escapeHtml(n)}" title="${escapeHtml(c ? c.title : '')}">${escapeHtml(n)}</a></sup>`
}
// Open outside links in a new tab.
const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const href = tokens[idx].attrGet('href') || ''
  if (/^https?:/i.test(href)) {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener noreferrer')
  }
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(text, { links = [], sanitize = null, cites = null } = {}) {
  let html = md.render(String(text || ''), { links, cites })
  html = html.replace(/\[\?\]/g, '<span class="unclear">[?] unclear</span>')
  return sanitize ? sanitize(html) : html
}
