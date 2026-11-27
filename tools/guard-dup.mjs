// G2, the copy-paste ceiling: jscpd over frontend/src and lifeos/ fails when the share of duplicated lines is above the ceiling stored in tools/guard-dup-ceiling.json.
// The ceiling is the level after the cleanup (#142 to #147) and only goes down: when a run is clearly below it, lower it (`node tools/guard-dup.mjs --measure` prints the numbers).
// Run: node tools/guard-dup.mjs [root]. Exit 1 above the ceiling.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const JSCPD = 'jscpd@5.4.3'
const IGNORE = '**/node_modules/**,**/public/**,**/tests/**,**/*.json,**/*.md,**/dist/**'

/** The share of duplicated lines (percent) in one folder, by jscpd. */
export function measure(dir) {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'lifeos-jscpd-'))
  try {
    execFileSync('npx', ['--yes', JSCPD, dir, '--reporters', 'json', '--output', out, '--silent', '--ignore', IGNORE], { stdio: 'ignore' })
    return JSON.parse(fs.readFileSync(path.join(out, 'jscpd-report.json'), 'utf8')).statistics.total.percentage
  } finally {
    fs.rmSync(out, { recursive: true, force: true })
  }
}

export function ceilingOf(root) {
  return JSON.parse(fs.readFileSync(path.join(root, 'tools/guard-dup-ceiling.json'), 'utf8'))
}

/** Lines for every folder above its ceiling. */
export function problems(root, ceiling = ceilingOf(root), measureFn = measure) {
  const out = []
  for (const [dir, max] of Object.entries(ceiling)) {
    const now = measureFn(path.join(root, dir))
    if (now > max) out.push(`${dir}: ${now.toFixed(2)}% of the lines are copied, above the ceiling of ${max}% (tools/guard-dup-ceiling.json); share the code instead of pasting it`)
  }
  return out
}

if (process.argv[1] === import.meta.filename) {
  const root = path.resolve(process.argv.find((a, i) => i > 1 && !a.startsWith('--')) || path.join(import.meta.dirname, '..'))
  if (process.argv.includes('--measure')) {
    for (const dir of Object.keys(ceilingOf(root))) console.log(`${dir}: ${measure(path.join(root, dir)).toFixed(3)}%`)
    process.exit(0)
  }
  const found = problems(root)
  for (const p of found) console.log(p)
  process.exit(found.length ? 1 : 0)
}
