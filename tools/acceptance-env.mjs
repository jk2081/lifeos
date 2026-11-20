// Where the acceptance tooling finds the bench, the browser and the test users' password (issue 5). The defaults are the
// owner's Mac: the Docker bench `lifeos-bench`, Google Chrome from /Applications and .env. GitHub Actions sets
// LIFEOS_BENCH_CMD=local with LIFEOS_BENCH_PATH, has no Chrome there (so Playwright's bundled Chromium is used) and puts
// a password made for the run in LIFEOS_DEV_PASSWORD.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

export const MAC_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const root = path.resolve(import.meta.dirname, '..')

// `env`, `exists` and `readEnvFile` are parameters so the I5.1 check can try the other machine's setup
export function resolveSetup({ env = process.env, exists = fs.existsSync, readEnvFile = readDotEnv } = {}) {
  const local = env.LIFEOS_BENCH_CMD === 'local'
  const fromEnv = env.LIFEOS_DEV_PASSWORD
  return {
    bench: local ? `local bench in ${env.LIFEOS_BENCH_PATH}` : 'docker exec lifeos-bench',
    // undefined launches Playwright's own Chromium
    chrome: exists(MAC_CHROME) ? MAC_CHROME : undefined,
    password: fromEnv || readEnvFile().LIFEOS_DEV_PASSWORD,
    passwordFrom: fromEnv ? 'environment' : '.env',
  }
}

function readDotEnv() {
  const file = path.join(root, '.env')
  if (!fs.existsSync(file)) throw new Error('set LIFEOS_DEV_PASSWORD or write it to .env')
  return Object.fromEntries(fs.readFileSync(file, 'utf8').split('\n').filter((l) => l.includes('='))
    .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]))
}

// run Python on a site of the bench, through tools/bench.sh (the one helper that reaches the bench)
export function benchPython(script) {
  return execFileSync(path.join(root, 'tools/bench.sh'), ['-i', 'cd sites && ../env/bin/python -W ignore -'],
    { input: script, encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] })
}
