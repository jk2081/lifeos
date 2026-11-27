// G3 and G4 of the cleanup guards (docs/BUILDING.md): the shared parts stay the only way to build a control, a list row or a section heading.
//   G3  a raw <button>, <select>, <input> or <textarea> in a .vue file outside components/ui/ (the whole-row <button class="absolute inset-0"> and <input type="file"> stay).
//   G4  every file in components/ui/ is listed in frontend/COMPONENTS.md; a .vue file that is not in tools/guard-ui-baseline.json does not hand-build a list row
//       (a v-for element with a border class and no Row) or a section heading (<h2> or <h3> outside a page header or a dialog).
// The baseline only shrinks: a file in it that no longer has the finding fails, so it is taken out.
// Run: node tools/guard-ui.mjs [root]. Exit 1 on any finding.
import fs from 'node:fs'
import path from 'node:path'

const UI = 'frontend/src/components/ui/'
// a whole tag, quoted attribute values (which may hold > as in =>) included
const TAG = /<([A-Za-z][\w-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g
const lineOf = (text, at) => text.slice(0, at).split('\n').length

export function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name)
    if (f.isDirectory()) walk(p, out)
    else if (f.name.endsWith('.vue')) out.push(p)
  }
  return out
}

/** G3: the raw controls in one file's text: [{ at, what }] */
export function rawControls(text) {
  const found = []
  for (const m of text.matchAll(TAG)) {
    const [tag, name, attrs] = m
    if (name === 'button' && !attrs.includes('absolute inset-0')) found.push({ at: lineOf(text, m.index), what: 'a raw <button>: use frappe-ui Button (ui/LinkButton for a link-looking one)' })
    else if (name === 'select') found.push({ at: lineOf(text, m.index), what: 'a raw <select>: use frappe-ui Select or FormControl type="select"' })
    else if (name === 'textarea') found.push({ at: lineOf(text, m.index), what: 'a raw <textarea>: use frappe-ui Textarea or FormControl type="textarea"' })
    else if (name === 'input' && !/type="file"/.test(attrs)) found.push({ at: lineOf(text, m.index), what: 'a raw <input>: use frappe-ui TextInput, FormControl, Checkbox or DatePicker' })
  }
  return found
}

/** G4: the hand-built rows and headings of one file's text: [{ at, what }] */
export function handBuilt(text) {
  const found = []
  const template = text.match(/<template[\s>][\s\S]*<\/template>/)?.[0] ?? ''
  const offset = template ? text.indexOf(template) : 0
  for (const m of template.matchAll(TAG)) {
    const [, name, attrs] = m
    if (name !== 'Row' && /\sv-for=/.test(attrs) && /\bborder-[bt]\b|\bdivide-y\b/.test(attrs.match(/\sclass="([^"]*)"/)?.[1] ?? ''))
      found.push({ at: lineOf(text, offset + m.index), what: `a hand-built list row (<${name} v-for> with a border class): use ui/Row` })
  }
  // a heading in a page header or a dialog is theirs; any other <h2> or <h3> is a section heading, which is SectionHead
  const bare = template.replace(/<(PageHead|PageHeader|Dialog)[\s>][\s\S]*?<\/\1>/g, (s) => s.replace(/[^\n]/g, ' '))
  for (const m of bare.matchAll(/<h[23][\s>]/g)) found.push({ at: lineOf(text, offset + m.index), what: 'a hand-built section heading (<h2> or <h3>): use ui/SectionHead' })
  return found
}

/** G4: files in components/ui/ that COMPONENTS.md does not list: [name] */
export function unlisted(root) {
  const docs = fs.readFileSync(path.join(root, 'frontend/COMPONENTS.md'), 'utf8')
  return walk(path.join(root, UI)).map((f) => path.basename(f)).filter((n) => !docs.includes(n)).sort()
}

const rel = (root, f) => path.relative(root, f).split(path.sep).join('/')

export function baselineOf(root) {
  const f = path.join(root, 'tools/guard-ui-baseline.json')
  return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : {}
}

/** Every finding on the tree, as lines. */
export function problems(root, baseline = baselineOf(root)) {
  const out = []
  const seen = new Set()
  for (const f of walk(path.join(root, 'frontend/src'))) {
    const r = rel(root, f)
    const text = fs.readFileSync(f, 'utf8')
    if (!r.startsWith(UI)) for (const x of rawControls(text)) out.push(`${r}:${x.at} ${x.what}`)
    if (r.startsWith(UI)) continue
    const hand = handBuilt(text)
    if (hand.length) seen.add(r)
    if (!(r in baseline)) for (const x of hand) out.push(`${r}:${x.at} ${x.what}`)
  }
  for (const r of Object.keys(baseline)) if (!seen.has(r)) out.push(`tools/guard-ui-baseline.json: ${r} has no hand-built row or heading now (or is gone); remove its entry`)
  for (const n of unlisted(root)) out.push(`frontend/COMPONENTS.md: components/ui/${n} is not listed; add one line on when to use it`)
  return out
}

if (process.argv[1] === import.meta.filename) {
  const found = problems(path.resolve(process.argv[2] || path.join(import.meta.dirname, '..')))
  for (const p of found) console.log(p)
  process.exit(found.length ? 1 : 0)
}
