// The tooling itself: the setup switches, CI and the screenshots a failed check saves.
// Checks are numbered TOOLING.<n> in the order they appear here; `node tools/acceptance.mjs --only=TOOLING` runs this file's checks.
import { FAIL_SHOTS, areas, base, MAC_CHROME, ONLY, PLACES, SETUP, agentSecret, bench, check, env, execFileSync, failShots, fs, must, os, owner, path, resolveSetup, root, session } from './context.mjs'
import { ux, uxArea } from './ux.mjs'


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

// Issue 83: where am I. Every page below a place shows its path above the title, a back button, the place highlighted and a tab title.
const AREA = areas.find((a) => a.name === uxArea).area_name
// the first area of the demo data that opens as a focus page
const focusArea = await (async () => { for (const a of areas) { if (await owner.api('focus.get', { area: a.name }).then(() => true, () => false)) return a.name } return '' })()
// [route, the ancestors of the page's path, the place the sidebar highlights]
const ROUTES = [
  [`/life/goals/${ux.goal}`, ['Goals', AREA], 'Goals'],
  ...(focusArea ? [[`/life/focus/${focusArea}`, ['Goals', 'Focus'], 'Goals']] : []),
  [`/life/item/${ux.inbox}`, ['Brain', 'Activity'], 'Brain'],
  [`/life/brain/review/${ux.inbox}`, ['Brain', 'Needs you'], 'Brain'],
  ['/life/brain/outbox', ['Brain'], 'Brain'],
  ['/life/goals/someday', ['Goals'], 'Goals'],
  ['/life/library/archive', ['Library'], 'Library'],
  ['/life/library/timeline', ['Library'], 'Library'],
  ['/life/library/notes?view=tree', ['Library'], 'Library'],
]
const openRoute = async (pg, url) => {
  await pg.goto(base + url, { waitUntil: 'networkidle' })
  await pg.locator('[data-page-path]:visible').first().waitFor({ timeout: 20000 }).catch(() => { throw new Error(`${url}: no path above the title`) })
}
for (const width of [1440, 390]) {
  await check('TOOLING.5', `${width} px: every route below a place shows a path whose last part is the page title and whose links each open the right page`, async () => {
    const s = await session('owner@lifeos.test', width)
    try {
      for (const [url, up, place] of ROUTES) {
        await openRoute(s.page, url)
        const title = (await s.page.locator('[data-page-head]:visible [data-page-title]').first().innerText()).trim()
        const parts = (await s.page.locator('[data-page-path]:visible').first().innerText()).split('\n').map((t) => t.replace(/\s*\/$/, '').trim()).filter((t) => t && t !== '/')
        must(parts.at(-1) === title, `${url}: the path ends with "${parts.at(-1)}", the title is "${title}"`)
        must(JSON.stringify(parts.slice(0, -1)) === JSON.stringify(up), `${url}: the path is ${parts.join(' / ')}, not ${[...up, title].join(' / ')}`)
        const links = await s.page.locator('[data-page-path]:visible a').evaluateAll((as) => as.map((a) => a.getAttribute('href')))
        must(links.length === up.length, `${url}: ${links.length} links for ${up.length} ancestors`)
        for (const href of links) {
          await s.page.goto(base + href, { waitUntil: 'networkidle' })
          must(new URL(s.page.url()).pathname.startsWith('/life/' + place.toLowerCase()), `${url}: a link of its path opened ${href}`)
        }
      }
      return `${ROUTES.length} routes`
    } finally { await s.ctx.close() }
  })
}
await check('TOOLING.6', 'On the phone, the back button on a goal page opened from a direct link goes to Goals, not to a blank history', async () => {
  const s = await session('owner@lifeos.test', 390)
  try {
    // a new tab: no history behind the goal page
    const pg = await s.ctx.newPage()
    await openRoute(pg, `/life/goals/${ux.goal}`)
    must((await pg.evaluate(() => history.length)) <= 2, 'the page was not a direct link')
    await pg.locator('[data-page-back]:visible').first().click()
    await pg.waitForURL((u) => !u.pathname.includes(ux.goal), { timeout: 15000 })
    must(new URL(pg.url()).pathname === '/life/goals', 'back opened ' + pg.url())
  } finally { await s.ctx.close() }
})
await check('TOOLING.7', "The browser tab title of a goal page is '<goal> · <area> · Goals — Life OS'", async () => {
  const s = await session('owner@lifeos.test')
  try {
    await openRoute(s.page, `/life/goals/${ux.goal}`)
    const want = `${ux.goalTitle} · ${AREA} · Goals — Life OS`
    must((await s.page.title()) === want, `the tab says "${await s.page.title()}", not "${want}"`)
    await openRoute(s.page, '/life/brain/outbox')
    must((await s.page.title()) === 'Outbox · Brain — Life OS', 'Outbox tab: ' + (await s.page.title()))
  } finally { await s.ctx.close() }
})
await check('TOOLING.8', 'The sidebar highlights the right place on every route', async () => {
  const s = await session('owner@lifeos.test')
  try {
    const all = [...ROUTES.map(([u, , p]) => [u, p]), ['/life/today', 'Today'], ['/life/brain', 'Brain'], ['/life/goals/cycles', 'Goals'], ['/life/library/people', 'Library'],
      ['/life/settings', 'Settings'], [`/life/library/${ux.note}`, 'Library']]
    for (const [url, place] of all) {
      await s.page.goto(base + url, { waitUntil: 'networkidle' })
      const on = await s.page.locator('[data-sidebar] [aria-current="page"]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')))
      must(on.length === 1 && on[0] === place, `${url}: the sidebar highlights ${JSON.stringify(on)}, not ${place}`)
    }
    return `${all.length} routes`
  } finally { await s.ctx.close() }
})
