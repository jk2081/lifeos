// Live preview for the Markdown editor: one pane, formatted as you type, the way Obsidian does it with CodeMirror 6.
// The text stays Markdown. Decorations draw it formatted: headings at size, bold and italic, list bullets and checkboxes,
// links as links, [[links]] as chips, images inline, rules and quotes, and tables as tables. The Markdown marks of a line
// show only while the cursor is on that line (a table shows as text while the cursor is inside it).
// Everything rendered from the text is escaped or sanitised: nothing typed in a note can run script.
import { StateEffect, StateField, RangeSet } from '@codemirror/state'
import { Decoration, EditorView, WidgetType } from '@codemirror/view'
import { syntaxTree } from '@codemirror/language'
import DOMPurify from 'dompurify'
import { renderMarkdown } from '@/lib/markdown'

// ---- state the decorations depend on, besides the text and the selection ----
export const setFocused = StateEffect.define()
export const setRaw = StateEffect.define()
export const setLinks = StateEffect.define()
const focusField = StateField.define({ create: () => false, update: (v, tr) => tr.effects.reduce((a, e) => (e.is(setFocused) ? e.value : a), v) })
const rawField = StateField.define({ create: () => false, update: (v, tr) => tr.effects.reduce((a, e) => (e.is(setRaw) ? e.value : a), v) })
const linksField = StateField.define({ create: () => [], update: (v, tr) => tr.effects.reduce((a, e) => (e.is(setLinks) ? e.value || [] : a), v) })

const WIKI = /\[\[([^\[\]#|\n]+?)(?:#([^\[\]\n]+?))?\]\]/g
const SAFE_URL = /^(https?:|mailto:|\/(?!\/)|#)/i

export function safeUrl(url) {
  const u = String(url || '').trim()
  return SAFE_URL.test(u) ? u : ''
}

// ---- widgets ----
class Hidden extends WidgetType { toDOM() { return document.createElement('span') } }

class Bullet extends WidgetType {
  eq() { return true }
  toDOM() { const s = document.createElement('span'); s.className = 'cm-lp-bullet'; s.textContent = '•'; s.setAttribute('aria-hidden', 'true'); return s }
}

class Checkbox extends WidgetType {
  constructor(checked, pos) { super(); this.checked = checked; this.pos = pos }
  eq(o) { return o.checked === this.checked && o.pos === this.pos }
  toDOM(view) {
    const s = document.createElement('span')
    s.className = 'cm-lp-task ' + (this.checked ? 'lucide-square-check' : 'lucide-square')
    s.setAttribute('role', 'checkbox')
    s.setAttribute('aria-checked', String(this.checked))
    s.setAttribute('aria-label', this.checked ? 'Done' : 'Not done')
    s.dataset.taskPos = String(this.pos)
    s.addEventListener('mousedown', (e) => {
      e.preventDefault()
      const at = Number(s.dataset.taskPos)
      const now = view.state.sliceDoc(at, at + 3)
      if (!/^\[[ xX]\]$/.test(now)) return
      view.dispatch({ changes: { from: at + 1, to: at + 2, insert: now[1] === ' ' ? 'x' : ' ' } })
    })
    return s
  }
  ignoreEvent() { return true }
}

class Rule extends WidgetType {
  eq() { return true }
  toDOM() { const s = document.createElement('span'); s.className = 'cm-lp-hr'; s.setAttribute('role', 'separator'); return s }
}

class Chip extends WidgetType {
  constructor(text, hit) { super(); this.text = text; this.hit = hit }
  eq(o) { return o.text === this.text && (o.hit && o.hit.route) === (this.hit && this.hit.route) && !!o.hit?.ambiguous === !!this.hit?.ambiguous }
  toDOM() {
    const s = document.createElement('span')
    s.className = 'cm-lp-chip' + (this.hit ? (this.hit.ambiguous ? ' ambiguous' : '') : ' missing')
    s.textContent = (this.hit ? this.hit.title || this.text : this.text) + (this.hit?.ambiguous ? ' ⚠' : '')
    if (this.hit) s.dataset.href = '/life' + this.hit.route
    if (this.hit?.ambiguous) s.title = 'More than one wiki page has this title. This link goes to the oldest; see Health.'
    else if (!this.hit) s.title = 'No record with this title yet'
    return s
  }
  ignoreEvent() { return false }
}

class Image extends WidgetType {
  constructor(url, alt) { super(); this.url = url; this.alt = alt }
  eq(o) { return o.url === this.url && o.alt === this.alt }
  toDOM() {
    const img = document.createElement('img')
    img.className = 'cm-lp-img'
    img.alt = this.alt || ''
    img.loading = 'lazy'
    img.src = this.url
    return img
  }
}

class Table extends WidgetType {
  constructor(source) { super(); this.source = source }
  eq(o) { return o.source === this.source }
  toDOM() {
    const d = document.createElement('div')
    d.className = 'cm-lp-table md prose prose-sm max-w-none'
    d.innerHTML = renderMarkdown(this.source, { sanitize: (h) => DOMPurify.sanitize(h, { FORBID_TAGS: ['style', 'form', 'input', 'iframe'] }) })
    return d
  }
  ignoreEvent() { return false }
}

// ---- building the decorations ----
const hide = Decoration.replace({ widget: new Hidden() })
const mark = (cls, attrs) => Decoration.mark({ class: cls, attributes: attrs })
const line = (cls) => Decoration.line({ class: cls })

function build(state) {
  if (state.field(rawField)) return Decoration.none
  const focused = state.field(focusField)
  const doc = state.doc
  const sel = state.selection.ranges
  const activeLines = new Set()
  if (focused) for (const r of sel) for (let n = doc.lineAt(r.from).number; n <= doc.lineAt(r.to).number; n++) activeLines.add(n)
  const lineActive = (pos) => activeLines.has(doc.lineAt(pos).number)
  const touches = (from, to) => focused && sel.some((r) => r.to >= from && r.from <= to)
  const out = []
  const add = (from, to, deco) => { if (to >= from) out.push(deco.range(from, to)) }

  // [[links]] first: the Markdown parser sees their brackets as links of its own, which are skipped inside them
  const wiki = []
  const links = state.field(linksField)
  const text = doc.toString()
  for (const m of text.matchAll(WIKI)) {
    const from = m.index
    const to = from + m[0].length
    wiki.push([from, to])
    if (touches(from, to)) { add(from, to, mark('cm-lp-wiki-src')); continue }
    const label = m[1].trim()
    const id = (m[2] || '').trim()
    const hit = links.find((l) => (id ? l.name === id : (l.text || '').toLowerCase() === label.toLowerCase())) || null
    add(from, to, Decoration.replace({ widget: new Chip(label, hit) }))
  }
  const inWiki = (from, to) => wiki.some(([a, b]) => from < b && to > a)

  syntaxTree(state).iterate({
    enter(node) {
      const { name, from, to } = node
      if (inWiki(from, to) && name !== 'Document' && name !== 'Paragraph' && !/List|ListItem|Blockquote/.test(name)) return false
      const ln = doc.lineAt(from)
      const active = lineActive(from)
      if (/^ATXHeading[1-6]$/.test(name)) {
        add(ln.from, ln.from, line('cm-lp-h' + name.slice(-1)))
        return
      }
      if (/^SetextHeading[12]$/.test(name)) {
        add(ln.from, ln.from, line('cm-lp-h' + name.slice(-1)))
        return
      }
      switch (name) {
        case 'HeaderMark': {
          if (active) { add(from, to, mark('cm-lp-mark')); return }
          const space = doc.sliceString(to, to + 1) === ' ' ? 1 : 0
          if (node.node.parent && /^ATX/.test(node.node.parent.name)) add(from, to + space, hide)
          return
        }
        case 'EmphasisMark': case 'StrikethroughMark':
          if (active) add(from, to, mark('cm-lp-mark'))
          else add(from, to, hide)
          return
        case 'Emphasis': add(from, to, mark('cm-lp-em')); return
        case 'StrongEmphasis': add(from, to, mark('cm-lp-strong')); return
        case 'Strikethrough': add(from, to, mark('cm-lp-strike')); return
        case 'InlineCode': {
          add(from, to, mark('cm-lp-code'))
          if (!active) for (const c of node.node.getChildren('CodeMark')) add(c.from, c.to, hide)
          return false
        }
        case 'FencedCode': case 'CodeBlock': {
          for (let n = ln.number; n <= doc.lineAt(to).number; n++) add(doc.line(n).from, doc.line(n).from, line('cm-lp-codeblock'))
          return false
        }
        case 'Blockquote': {
          for (let n = ln.number; n <= doc.lineAt(to).number; n++) add(doc.line(n).from, doc.line(n).from, line('cm-lp-quote'))
          return
        }
        case 'QuoteMark': {
          if (active) add(from, to, mark('cm-lp-mark'))
          else add(from, to + (doc.sliceString(to, to + 1) === ' ' ? 1 : 0), hide)
          return
        }
        case 'HorizontalRule':
          if (!active) add(from, to, Decoration.replace({ widget: new Rule() }))
          return
        case 'ListMark': {
          const item = node.node.parent
          const task = item && item.getChild('Task')
          if (task) {
            const marker = task.getChild('TaskMarker')
            if (marker && !active) {
              const checked = /x/i.test(doc.sliceString(marker.from, marker.to))
              const end = marker.to + (doc.sliceString(marker.to, marker.to + 1) === ' ' ? 1 : 0)
              add(from, end, Decoration.replace({ widget: new Checkbox(checked, marker.from) }))
              if (checked) add(end, doc.lineAt(end).to, mark('cm-lp-done'))
            }
            return
          }
          if (!active && item && item.parent && item.parent.name === 'BulletList') add(from, to, Decoration.replace({ widget: new Bullet() }))
          return
        }
        case 'TaskMarker': return
        case 'Link': {
          const marks = node.node.getChildren('LinkMark')
          const url = node.node.getChild('URL')
          if (marks.length < 2) return false
          const href = url ? safeUrl(doc.sliceString(url.from, url.to)) : ''
          const textFrom = marks[0].to
          const textTo = marks[1].from
          if (active) { add(from, to, mark('cm-lp-link-src')); return false }
          add(textFrom, textTo, mark('cm-lp-link', href ? { 'data-href': href } : undefined))
          add(from, textFrom, hide)
          add(textTo, to, hide)
          return false
        }
        case 'Image': {
          const url = node.node.getChild('URL')
          const marks = node.node.getChildren('LinkMark')
          const href = url ? safeUrl(doc.sliceString(url.from, url.to)) : ''
          if (active || !href) { add(from, to, mark('cm-lp-link-src')); return false }
          const alt = marks.length >= 2 ? doc.sliceString(marks[0].to, marks[1].from) : ''
          add(from, to, Decoration.replace({ widget: new Image(href, alt) }))
          return false
        }
        case 'URL': {
          // a bare address (GFM autolink)
          const href = safeUrl(doc.sliceString(from, to))
          if (href && (!node.node.parent || node.node.parent.name !== 'Link')) add(from, to, mark('cm-lp-link', { 'data-href': href }))
          return
        }
        case 'Table': {
          if (touches(from, to)) {
            for (let n = ln.number; n <= doc.lineAt(to).number; n++) add(doc.line(n).from, doc.line(n).from, line('cm-lp-table-src'))
            return false
          }
          add(from, to, Decoration.replace({ widget: new Table(doc.sliceString(from, to)), block: true }))
          return false
        }
        default:
      }
    },
  })
  return RangeSet.of(out, true)
}

const decorations = StateField.define({
  create: (state) => build(state),
  update(value, tr) {
    if (tr.docChanged || tr.selection || tr.effects.some((e) => e.is(setFocused) || e.is(setRaw) || e.is(setLinks))) return build(tr.state)
    if (syntaxTree(tr.state) !== syntaxTree(tr.startState)) return build(tr.state) // the parser caught up
    return value
  },
  provide: (f) => EditorView.decorations.from(f),
})

// Following a link: a [[link]] chip on click; a web link with Cmd or Ctrl held, or on click while the editor is not focused.
function follow(onOpen) {
  return EditorView.domEventHandlers({
    mousedown(e, view) {
      const el = e.target.closest && e.target.closest('[data-href]')
      if (!el) return false
      const chip = el.classList.contains('cm-lp-chip')
      if (!(chip || e.metaKey || e.ctrlKey || !view.hasFocus)) return false
      e.preventDefault()
      onOpen(el.dataset.href)
      return true
    },
  })
}

export function livePreview({ onOpen }) {
  return [
    focusField, rawField, linksField, decorations, follow(onOpen),
    EditorView.focusChangeEffect.of((state, focusing) => setFocused.of(focusing)),
  ]
}
