// Checks front-end source without building it. Run inside the bench container, from apps/lifeos/frontend:
//   node scripts/check-sfc.mjs                 every file under src/
//   node scripts/check-sfc.mjs src/pages/Today.vue src/components/item/TaskPane.vue
// It compiles each .vue file (template and script), checks that every lucide-* icon name exists, that imports of local
// files resolve, and that none of the patterns UX fixes set 2 removed has come back.
import fs from 'node:fs'
import path from 'node:path'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'

const root = path.resolve(import.meta.dirname, '..')
const iconsDir = path.join(root, 'node_modules/lucide-static/icons')
const args = process.argv.slice(2)
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]))
const files = (args.length ? args.map((a) => path.resolve(a)) : walk(path.join(root, 'src'))).filter((f) => /\.(vue|js|css)$/.test(f))

const BANNED = [
  [/class="[^"]*\b(bt|inp|ck|pl|cd|sh|mt|ch)\b(?![-\w])[^"]*"/, 'a removed helper class (bt, inp, ck, pl, cd, sh, mt, ch)'],
  [/window\.(prompt|confirm)\(|(?<![.\w])(prompt|confirm)\(/, 'a browser prompt() or confirm(): use a frappe-ui Dialog'],
  [/<select[\s>]/, 'a raw <select>: use frappe-ui Select or FormControl type="select"'],
  [/<textarea[\s>]/, 'a raw <textarea>: use frappe-ui Textarea or FormControl type="textarea"'],
  [/<input(?![^>]*type="file")[\s>]/, 'a raw <input>: use frappe-ui TextInput, FormControl, Checkbox or DatePicker'],
  [/Ico\.vue|<Ico[\s/]/, 'Ico.vue: use a lucide-* icon name'],
  [/var\(--(bg|side|soft|softer|line\d?|faint|ink2?|mut2?|fill|accent(-hover)?|[gborn]-(bg|ink)|shadow|read|series-\d)\)/, 'one of the old Life OS colour variables'],
]
const HEX_OK = /(LineChart\.vue|Graph\.vue|tokens\.js)$/
let bad = 0
const fail = (file, msg) => { bad++; console.log(`${path.relative(root, file)}: ${msg}`) }

for (const file of files) {
  const src = fs.readFileSync(file, 'utf8')
  const rel = path.relative(root, file)
  for (const [re, what] of BANNED) {
    const m = re.exec(src)
    if (m) fail(file, `${what}  ->  ${m[0].slice(0, 80)}`)
  }
  if (!HEX_OK.test(file)) {
    const m = /(?<![&\w])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b(?![-\w])/.exec(src.replace(/href="#"/g, ''))
    if (m) fail(file, `a hex colour (${m[0]}): use a token class or variable`)
  }
  if (/(from|import)\s*\(?\s*['"]@framework\/ui/.test(src) && !rel.startsWith('src/framework/')) fail(file, 'imports @framework/ui outside src/framework/')
  if (/(from|import)\s*\(?\s*['"]frappe-ui\/experimental/.test(src) && !rel.startsWith('src/experimental/')) fail(file, 'imports frappe-ui/experimental outside src/experimental/')
  for (const m of src.matchAll(/\blucide-([a-z0-9]+(?:-[a-z0-9]+)*)\b/g)) {
    if (!fs.existsSync(path.join(iconsDir, m[1] + '.svg'))) fail(file, `no Lucide icon named "${m[1]}"`)
  }
  for (const m of src.matchAll(/from '(@\/[^']+|\.{1,2}\/[^']+)'/g)) {
    const target = m[1].startsWith('@/') ? path.join(root, 'src', m[1].slice(2)) : path.resolve(path.dirname(file), m[1])
    if (![target, target + '.js', target + '.vue', path.join(target, 'index.js')].some((t) => fs.existsSync(t) && fs.statSync(t).isFile())) fail(file, `import not found: ${m[1]}`)
  }
  if (!file.endsWith('.vue')) continue
  try {
    const { descriptor, errors } = parse(src, { filename: file })
    for (const e of errors) fail(file, `parse: ${e.message}`)
    let bindings
    if (descriptor.scriptSetup || descriptor.script) {
      const script = compileScript(descriptor, { id: rel, inlineTemplate: false })
      bindings = script.bindings
      // a name the template uses as a component must be imported
      for (const m of (descriptor.template?.content || '').matchAll(/<([A-Z][A-Za-z0-9]+)[\s/>]/g)) {
        if (!(m[1] in bindings) && !['RouterLink', 'RouterView', 'Transition', 'TransitionGroup', 'Teleport', 'KeepAlive', 'Suspense'].includes(m[1])) fail(file, `<${m[1]}> is used but not imported`)
      }
    }
    if (descriptor.template) {
      const out = compileTemplate({ source: descriptor.template.content, filename: file, id: rel, compilerOptions: { bindingMetadata: bindings } })
      for (const e of out.errors) fail(file, `template: ${e.message || e}`)
    }
  } catch (e) {
    fail(file, `compile: ${String(e.message || e).split('\n')[0]}`)
  }
}
console.log(bad ? `\n${bad} problem${bad === 1 ? '' : 's'} in ${files.length} files.` : `ok: ${files.length} files.`)
process.exit(bad ? 1 : 0)
