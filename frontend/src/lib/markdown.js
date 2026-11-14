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
  if (hit) return `<a class="wl" href="/life${escapeHtml(hit.route)}">${escapeHtml(hit.title || text)}</a>`
  return `<span class="wl missing" title="No record with this title yet">${escapeHtml(text)}</span>`
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

export function renderMarkdown(text, { links = [], sanitize = null } = {}) {
  let html = md.render(String(text || ''), { links })
  html = html.replace(/\[\?\]/g, '<span class="unclear">[?] unclear</span>')
  return sanitize ? sanitize(html) : html
}
