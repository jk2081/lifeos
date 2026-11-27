// G5, the monthly cleanup check: runs the guards in report mode, jscpd and a dead-code scan of the Python (vulture), and opens ONE issue
// titled "Monthly cleanup check: <month>" with the findings, labelled `audit` (never `ready`). With no findings it opens nothing.
// Used by .github/workflows/monthly-cleanup.yml on the 1st of each month; by hand: node tools/monthly-cleanup.mjs [--root <dir>] [--dry-run].
// The `gh` it calls is $GH (default `gh`), so a test can put a recording stand-in there.
import { execFileSync, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { measure, ceilingOf } from './guard-dup.mjs'

const here = import.meta.dirname
const arg = (name) => { const i = process.argv.indexOf(name); return i < 0 ? null : process.argv[i + 1] }
const root = path.resolve(arg('--root') || path.join(here, '..'))
const dry = process.argv.includes('--dry-run')
const gh = process.env.GH || 'gh'

const lines = (s) => s.split('\n').map((l) => l.trimEnd()).filter(Boolean)
const run = (cmd, args) => { const r = spawnSync(cmd, args, { encoding: 'utf8', cwd: root }); return lines((r.stdout || '') + (r.error ? `${cmd} did not run: ${r.error.message}\n` : '')) }

/** Every section of the report: { title, found: [lines] } */
export function sections() {
  const out = [
    { title: 'Routes to a record (G0, tools/guard-routes.mjs)', found: run('node', [path.join(here, 'guard-routes.mjs')]) },
    { title: 'API nothing calls (G1, tools/guard-api.py)', found: run('python3', ['-I', path.join(here, 'guard-api.py'), root]) },
    { title: 'Raw controls, hand-built rows and headings, unlisted shared parts (G3 and G4, tools/guard-ui.mjs)', found: run('node', [path.join(here, 'guard-ui.mjs'), root]) },
  ]
  // jscpd in report mode: every folder's level against its ceiling, and the level itself (a level below the ceiling means the ceiling can come down)
  const dup = []
  const ceiling = fs.existsSync(path.join(root, 'tools/guard-dup-ceiling.json')) ? ceilingOf(root) : {}
  for (const [dir, max] of Object.entries(ceiling)) {
    const now = measure(path.join(root, dir))
    if (now > max) dup.push(`${dir}: ${now.toFixed(2)}% copied, above the ceiling of ${max}%`)
  }
  out.push({ title: 'Copy-paste above the ceiling (G2, jscpd)', found: dup })
  // vulture over the Python of the app (not its tests): code nothing uses. debug and searchfield are the fixed arguments of Frappe's hook signatures
  const lifeos = path.join(root, 'lifeos')
  out.push({ title: 'Dead Python (vulture, 80% confidence)', found: fs.existsSync(lifeos) ? run('python3', ['-m', 'vulture', 'lifeos', '--min-confidence', '80', '--ignore-names', 'debug,searchfield', '--exclude', 'lifeos/tests,lifeos/public']) : [] })
  return out
}

export function report(secs, month) {
  const open = secs.filter((s) => s.found.length)
  if (!open.length) return null
  const body = [`The monthly cleanup check of ${month}. Each section is a guard or scan run in report mode over \`main\`. Nothing here is work until it is read and turned into an issue labelled \`ready\`.`, '']
  for (const s of open) body.push(`## ${s.title} (${s.found.length})`, '', '```', ...s.found.slice(0, 60), ...(s.found.length > 60 ? [`… and ${s.found.length - 60} more`] : []), '```', '')
  return body.join('\n')
}

if (process.argv[1] === import.meta.filename) {
  const month = new Date().toLocaleString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })
  const title = `Monthly cleanup check: ${month}`
  const text = report(sections(), month)
  if (!text) { console.log('No findings; no issue opened.'); process.exit(0) }
  if (dry) { console.log(title + '\n\n' + text); process.exit(0) }
  const g = (args) => execFileSync(gh, args, { encoding: 'utf8', cwd: root })
  // one issue a month: a second run of the same month finds the first
  const same = g(['issue', 'list', '--state', 'all', '--label', 'audit', '--search', `"${title}" in:title`, '--json', 'title', '--jq', `[.[] | select(.title == "${title}")] | length`]).trim()
  if (same !== '0' && same !== '') { console.log(`${title} is already open; no second issue.`); process.exit(0) }
  try { g(['label', 'create', 'audit', '--color', 'BFD4F2', '--description', 'Findings of a check, not work until made ready']) } catch { /* it exists */ }
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'lifeos-audit-')), 'body.md')
  fs.writeFileSync(file, text)
  console.log(g(['issue', 'create', '--title', title, '--label', 'audit', '--body-file', file]).trim())
}
