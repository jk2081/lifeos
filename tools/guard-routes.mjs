// The rule of the Drawer (issue 128): a record opens in the Drawer as a layer, never by going to its page. This finds the places in a .vue file that link or push
// straight to a record route: /goals/<id>, /item/<id>, /library/<id>, /library/people/<id>, /focus/<id>, /brain/review/<id>.
// Only the Drawer's Open full page (it gets its route from the layer, never written out in a template) and the router go to a record's page.
import fs from 'node:fs'
import path from 'node:path'

// a route written out with an id after it: `/goals/${g.name}`, '/item/' + id, "/focus/abc"
const ROUTE = /['"`]\/(?:life\/)?(goals|item|library\/people|library|focus|brain\/review)\/(\$\{|['"`]\s*\+|[A-Za-z0-9_-]+['"`])/g
// the tabs of a place are routes of their own, not records
const TABS = new Set(['goals/tasks', 'goals/plan', 'goals/cycles', 'goals/habits', 'goals/areas', 'goals/someday', 'goals/archive', 'library/notes', 'library/wiki', 'library/files', 'library/everything',
  'library/people', 'library/pages', 'library/pins', 'library/vault', 'library/chats', 'library/sources', 'library/graph', 'library/timeline', 'library/outbox', 'library/archive'])

// The Drawer's Open full page: a layer's body names the page its record has (`meta.fullPage`), and the Drawer's button goes there.
export const ALLOWED = ['frontend/src/components/item/ChangePane.vue', 'frontend/src/components/item/FocusPane.vue', 'frontend/src/components/item/GoalPane.vue',
  'frontend/src/components/item/NotePane.vue', 'frontend/src/components/item/SourcePane.vue']

export function findRecordLinks(text) {
  const found = []
  for (const m of text.matchAll(ROUTE)) {
    const tail = m[2].replace(/['"`]$/, '')
    if (TABS.has(`${m[1]}/${tail}`)) continue
    found.push({ route: m[0].slice(1), at: text.slice(0, m.index).split('\n').length })
  }
  return found
}

export function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name)
    if (f.isDirectory()) walk(p, out)
    else if (f.name.endsWith('.vue')) out.push(p)
  }
  return out
}

/** Every file under frontend/src with record links in it: { file: [found, ...] } */
export function scanTree(root) {
  const base = path.join(root, 'frontend/src')
  const out = {}
  for (const f of walk(base)) {
    if (ALLOWED.includes(path.relative(root, f))) continue
    const found = findRecordLinks(fs.readFileSync(f, 'utf8'))
    if (found.length) out[path.relative(root, f)] = found
  }
  return out
}

/** The screens #129 has not moved onto the Drawer yet: file -> how many links it still has. #129 empties this list; a file may not be added to it and may not gain a link. */
export const baseline = (root) => JSON.parse(fs.readFileSync(path.join(root, 'tools/guard-baseline.json'), 'utf8'))

/** What breaks the rule: a file with record links that is not in the baseline, or one that has more than the baseline says. */
export function problems(root) {
  const base = baseline(root)
  const out = []
  for (const [f, list] of Object.entries(scanTree(root))) {
    if (!(f in base)) out.push(`${f}:${list[0].at} goes to a record's page: ${list[0].route}`)
    else if (list.length > base[f]) out.push(`${f} has ${list.length} links to record pages, the baseline allows ${base[f]}`)
  }
  return out
}

if (process.argv[1] === import.meta.filename) {
  const found = problems(path.resolve(import.meta.dirname, '..'))
  for (const p of found) console.log(p)
  process.exit(found.length ? 1 : 0)
}
