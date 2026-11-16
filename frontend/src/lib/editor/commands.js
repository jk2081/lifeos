// Formatting commands for the Markdown editor. Each one edits the text the way typing the Markdown would, so the
// stored note is plain Markdown and the toolbar, the shortcuts and the / menu all do the same thing.
import { EditorSelection } from '@codemirror/state'
import { indentLess, indentMore } from '@codemirror/commands'
import { startCompletion } from '@codemirror/autocomplete'

const LIST_PREFIX = /^(\s*)([-*+] \[[ xX]\] |[-*+] |\d+[.)] )?/

/** **bold**, *italic*: wrap the selection, or unwrap it when it is already wrapped; with no selection, place the cursor inside. */
export function wrap(markText) {
  return (view) => {
    const { state } = view
    const tr = state.changeByRange((r) => {
      const n = markText.length
      const before = state.sliceDoc(r.from - n, r.from)
      const after = state.sliceDoc(r.to, r.to + n)
      if (before === markText && after === markText) {
        return { changes: [{ from: r.from - n, to: r.from }, { from: r.to, to: r.to + n }], range: EditorSelection.range(r.from - n, r.to - n) }
      }
      return { changes: [{ from: r.from, insert: markText }, { from: r.to, insert: markText }], range: EditorSelection.range(r.from + n, r.to + n) }
    })
    view.dispatch(state.update(tr, { scrollIntoView: true, userEvent: 'input' }))
    view.focus()
    return true
  }
}

function eachLine(view, fn) {
  const { state } = view
  const changes = []
  const seen = new Set()
  for (const r of state.selection.ranges) {
    for (let n = state.doc.lineAt(r.from).number; n <= state.doc.lineAt(r.to).number; n++) {
      if (seen.has(n)) continue
      seen.add(n)
      const line = state.doc.line(n)
      const c = fn(line, seen.size - 1)
      if (c) changes.push(c)
    }
  }
  view.dispatch({ changes, userEvent: 'input' })
  view.focus()
  return true
}

/** Heading 1 to 3; the same level again turns the line back into text. */
export function heading(level) {
  return (view) => eachLine(view, (line) => {
    const m = /^(#{1,6}) /.exec(line.text)
    const want = '#'.repeat(level) + ' '
    if (m && m[1].length === level) return { from: line.from, to: line.from + m[0].length, insert: '' }
    return { from: line.from, to: line.from + (m ? m[0].length : 0), insert: want }
  })
}

/** A bulleted, numbered or check list; the same kind again turns the lines back into text. */
export function list(kind) {
  return (view) => eachLine(view, (line, i) => {
    const m = LIST_PREFIX.exec(line.text)
    const indent = m[1]
    const current = m[2] || ''
    const is = { bullet: /^[-*+] (?!\[)/, ordered: /^\d+[.)] /, task: /^[-*+] \[[ xX]\] / }[kind]
    if (current && is.test(current)) return { from: line.from + indent.length, to: line.from + indent.length + current.length, insert: '' }
    const insert = kind === 'bullet' ? '- ' : kind === 'ordered' ? `${i + 1}. ` : '- [ ] '
    return { from: line.from + indent.length, to: line.from + indent.length + current.length, insert }
  })
}

/** > quote */
export function quote(view) {
  return eachLine(view, (line) => (line.text.startsWith('> ') ? { from: line.from, to: line.from + 2, insert: '' } : { from: line.from, insert: '> ' }))
}

/** [text](address): the selection becomes the text and the address is selected for typing. */
export function link(view) {
  const { state } = view
  const r = state.selection.main
  const text = state.sliceDoc(r.from, r.to)
  const url = 'https://'
  const insert = `[${text}](${url})`
  const anchor = text ? r.from + text.length + 3 : r.from + 1
  view.dispatch({ changes: { from: r.from, to: r.to, insert }, selection: text ? EditorSelection.range(anchor, anchor + url.length) : EditorSelection.cursor(anchor), userEvent: 'input' })
  view.focus()
  return true
}

/** [[ and open the record picker. */
export function wikiLink(view) {
  const r = view.state.selection.main
  view.dispatch({ changes: { from: r.from, to: r.to, insert: '[[' }, selection: EditorSelection.cursor(r.from + 2), userEvent: 'input' })
  view.focus()
  startCompletion(view)
  return true
}

/** Put a block on its own line at the cursor: a table, a rule. */
export function insertBlock(text, cursorOffset = null) {
  return (view) => {
    const { state } = view
    const r = state.selection.main
    const line = state.doc.lineAt(r.from)
    const lead = line.text.trim() ? '\n\n' : ''
    const from = line.text.trim() ? line.to : line.from
    const to = line.text.trim() ? line.to : line.to
    const insert = lead + text
    view.dispatch({ changes: { from, to, insert }, selection: EditorSelection.cursor(from + lead.length + (cursorOffset ?? text.length)), userEvent: 'input' })
    view.focus()
    return true
  }
}
export const TABLE = '| Column | Column |\n| --- | --- |\n|  |  |\n'
export const table = insertBlock(TABLE, 2)
export const divider = insertBlock('---\n')

/** Tab and Shift-Tab indent a list item (and anything else, as before). */
export const indent = (view) => indentMore(view)
export const outdent = (view) => indentLess(view)

/** Insert text at the cursor, on its own line when it is a block (an image). */
export function insertAt(view, pos, text) {
  view.dispatch({ changes: { from: pos, insert: text }, selection: EditorSelection.cursor(pos + text.length), userEvent: 'input' })
}

// ---- the / menu at the start of a line ----
export const SLASH = [
  { label: 'Heading 1', keys: 'h1 heading', run: heading(1) },
  { label: 'Heading 2', keys: 'h2 heading', run: heading(2) },
  { label: 'Heading 3', keys: 'h3 heading', run: heading(3) },
  { label: 'Bulleted list', keys: 'bullet list ul', run: list('bullet') },
  { label: 'Numbered list', keys: 'numbered list ol', run: list('ordered') },
  { label: 'Checklist', keys: 'checklist todo task', run: list('task') },
  { label: 'Table', keys: 'table grid', run: table },
  { label: 'Quote', keys: 'quote', run: quote },
  { label: 'Divider', keys: 'divider rule hr line', run: divider },
  { label: 'Link to a record', keys: 'link record [[', run: wikiLink },
]

export function slashSource(context) {
  const line = context.state.doc.lineAt(context.pos)
  const before = context.state.sliceDoc(line.from, context.pos)
  const m = /^\/([\w ]*)$/.exec(before)
  if (!m) return null
  const q = m[1].trim().toLowerCase()
  // a word of the label or of its keys starts with what was typed: /tab finds Table, /check finds Checklist
  const words = (s) => [...s.label.toLowerCase().split(/\s+/), ...s.keys.split(/\s+/)]
  const items = SLASH.filter((s) => !q || s.label.toLowerCase().startsWith(q) || words(s).some((w) => w.startsWith(q)))
  return {
    from: line.from,
    filter: false,
    options: items.map((s) => ({
      label: s.label, type: 'slash',
      apply: (view, completion, from, to) => {
        view.dispatch({ changes: { from, to, insert: '' } })
        s.run(view)
      },
    })),
  }
}
