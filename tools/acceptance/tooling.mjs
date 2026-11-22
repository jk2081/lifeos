// The tooling itself: the setup switches, CI and the screenshots a failed check saves.
// Checks are numbered TOOLING.<n> in the order they appear here; `node tools/acceptance.mjs --only=TOOLING` runs this file's checks.
import { FAIL_SHOTS, MAC_CHROME, ONLY, PLACES, SETUP, agentSecret, bench, check, env, execFileSync, failShots, fs, must, os, owner, path, resolveSetup, root, session } from './context.mjs'
import { ux } from './ux.mjs'


// Issue 5: the acceptance walk runs in GitHub Actions too. These check the switches, the workflow's job as written, the
// screenshots taken on a failure and that no password or key reaches the workflow file or the logs it uploads.
const ciJob = (name) => {
  const yml = fs.readFileSync(path.join(root, '.github/workflows/ci.yml'), 'utf8')
  const at = yml.indexOf(`\n  ${name}:\n`)
  if (at < 0) return ''
  const rest = yml.slice(at + 1)
  const next = rest.slice(1).search(/\n  [\w-]+:\n/)
  return next < 0 ? rest : rest.slice(0, next + 1)
}
await check('TOOLING.1', 'Without the switches the tooling uses the Docker bench, Chrome and .env; with them, a local bench, Playwright\'s Chromium and the environment', async () => {
  const mac = resolveSetup({ env: {}, exists: () => true, readEnvFile: () => ({ LIFEOS_DEV_PASSWORD: 'from-file' }) })
  must(mac.bench === 'docker exec lifeos-bench' && mac.chrome === MAC_CHROME && mac.passwordFrom === '.env' && mac.password === 'from-file',
    'the Mac defaults changed: ' + JSON.stringify({ ...mac, password: undefined }))
  const ci = resolveSetup({ env: { LIFEOS_BENCH_CMD: 'local', LIFEOS_BENCH_PATH: '/b', LIFEOS_DEV_PASSWORD: 'from-env' }, exists: () => false,
    readEnvFile: () => { throw new Error('.env was read') } })
  must(ci.bench === 'local bench in /b' && ci.chrome === undefined && ci.passwordFrom === 'environment' && ci.password === 'from-env',
    'the switches did not apply: ' + JSON.stringify({ ...ci, password: undefined }))
  // the one helper reaches this run's bench
  const v = execFileSync(path.join(root, 'tools/bench.sh'), ['bench --version'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  must(/\d+\.\d+/.test(v), 'tools/bench.sh did not reach the bench: ' + v)
  return `this run: ${SETUP.bench}, ${SETUP.chrome ? 'Google Chrome' : "Playwright's Chromium"}, password from ${SETUP.passwordFrom}`
})

await check('TOOLING.2', 'CI has an acceptance job that builds the front end, makes acceptance.localhost, serves it and runs every check', async () => {
  const job = ciJob('acceptance')
  must(job, 'no acceptance job in .github/workflows/ci.yml')
  for (const step of ['LIFEOS_BENCH_CMD: local', 'bench build --app lifeos', 'scripts/acceptance-site.sh', 'node tools/acceptance.mjs'])
    must(job.includes(step), 'the job lacks: ' + step)
  must(!/acceptance\.mjs[^\n]*--(only|ux)/.test(job), 'the job runs only some checks')
  must(PLACES.every((p) => new RegExp('part: \\[[^\\]]*\\b' + p + '\\b').test(job)) && job.includes('--part=${{ matrix.part }}'), 'the job does not run every place')
  if (process.env.GITHUB_ACTIONS) {
    must(!ONLY, 'this CI run was given --only')
    must(SETUP.bench.startsWith('local bench') && !SETUP.chrome && SETUP.passwordFrom === 'environment', 'CI is not using the switches')
  }
  return process.env.GITHUB_ACTIONS ? 'running in GitHub Actions' : 'the job as written'
})

await check('TOOLING.3', 'A failed check saves screenshots, and CI uploads them with the logs as an artifact', async () => {
  const job = ciJob('acceptance')
  must(/LIFEOS_FAIL_SHOTS: \S+/.test(job), 'the job does not set LIFEOS_FAIL_SHOTS')
  must(/if: failure\(\)\s*\n\s*uses: actions\/upload-artifact@/.test(job), 'the job does not upload an artifact on failure')
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lifeos-i5-'))
  const s = await session('owner@lifeos.test')
  try {
    const saved = await failShots('I5.3', dir)
    must(saved.length && saved.every((f) => fs.statSync(f).size > 1000), 'no screenshot was saved: ' + saved.join(', '))
    return `${saved.length} pages saved`
  } finally {
    await s.ctx.close()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

await check('TOOLING.4', 'No password or key in the workflow file or in the logs a failed run uploads', async () => {
  const yml = fs.readFileSync(path.join(root, '.github/workflows/ci.yml'), 'utf8')
  const job = ciJob('acceptance')
  // a value written into the job: `PASSWORD: x`, `secret=x`; values made in the job start with $
  const literal = job.split('\n').filter((l) => /(password|secret|api[_-]?key|token)\w*["']?\s*[:=]\s*["']?(?![$"'\s])\S/i.test(l))
  must(!literal.length, 'written into the acceptance job: ' + literal.map((l) => l.trim()).join(' | '))
  must(!yml.includes(SETUP.password) && !yml.includes(agentSecret), "this run's password or agent key is in ci.yml")
  // searched on the bench, which prints only the names of the logs that hold one (the script goes in on stdin, never printed)
  const found = JSON.parse(bench(`import json, os
secrets = ${JSON.stringify([SETUP.password, agentSecret])}
logs = [f for f in ('/tmp/acc-site.log', '/tmp/serve-acceptance.log', '/tmp/worker-acceptance.log') if os.path.exists(f)]
print(json.dumps({"read": len(logs), "holding": [f for f in logs if any(s in open(f, errors="replace").read() for s in secrets)]}))`).split('\n').pop())
  must(found.read > 0, 'the bench logs could not be read')
  must(!found.holding.length, "this run's password or agent key is in " + found.holding.join(', '))
  if (FAIL_SHOTS && fs.existsSync(FAIL_SHOTS)) {
    const names = fs.readdirSync(FAIL_SHOTS).join(' ')
    must(!names.includes(SETUP.password), 'a screenshot name holds the password')
  }
})
