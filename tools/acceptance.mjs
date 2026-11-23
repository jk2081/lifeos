// Walks the app as a person would, against the throwaway site acceptance.localhost (http://localhost:19000): a logged-in
// browser for the owner and for a second user, and agent/fake_agent.py over HTTP with an API key.
//   node tools/acceptance.mjs                          every place on its own fresh site, one after another, each with the clean-up and the scan
//   node tools/acceptance.mjs --only=TODAY             one place's checks (TODAY, BRAIN, GOALS, LIBRARY, REVIEW, SETTINGS, PHONE, TOOLING)
//   node tools/acceptance.mjs --only=TODAY.3,BRAIN.7   single checks
//   node tools/acceptance.mjs --part=today             one place, with the clean-up: what each parallel job of CI runs
// The checks live in tools/acceptance/<place>.mjs, numbered by place (TODAY.3); the shared state and helpers are in
// tools/acceptance/context.mjs. scripts/acceptance-site.sh rebuilds the site from a snapshot with seed and demo data before every
// run, so lifeos.localhost stays clean for the owner. Needs the Docker bench running and .env with LIFEOS_DEV_PASSWORD.
// `--no-reset` keeps the acceptance site as it is. The bench, the browser and the password can come from elsewhere
// (tools/acceptance-env.mjs), as in GitHub Actions; LIFEOS_FAIL_SHOTS names a folder that gets a screenshot of every open page
// when a check fails. `--owner-read-only` only walks every screen on the owner's site, lifeos.localhost, changing nothing.
// It prints one line per check and exits 1 if any fails.
import { chromium } from 'playwright-core'
import { walkScreens } from './screen-walk.mjs'
import { resolveSetup, benchPython } from './acceptance-env.mjs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const SETUP = resolveSetup()
const env = { LIFEOS_DEV_PASSWORD: SETUP.password }
const SITE = process.env.LIFEOS_SITE || 'acceptance.localhost'
if (SITE === 'lifeos.localhost') throw new Error('acceptance runs on its own site, never on lifeos.localhost')
// Bug fix 1: `--owner-read-only` walks every screen on the owner's site (lifeos.localhost, http://localhost:18000) at both
// widths, opening screens only. Requests that could write are refused in the browser (the remembered views, the Error Log),
// and the site's Life tables and Error Log are compared before and after, so the run provably changed nothing.
async function ownerReadOnly() {
  const ownerBase = process.env.LIFEOS_OWNER_URL || 'http://localhost:18000'
  // reads the screens send as POST; everything else that is not a GET is refused
  const READS = /\/api\/method\/(frappe\.desk\.form\.load\.getdoctype|frappe\.desk\.search\.search_link|lifeos\.api\.(journal\.month|week\.goal_plan|wiki\.overview))$/
  const snapshot = () => benchPython(`import frappe, json; frappe.init("lifeos.localhost"); frappe.connect()
out = {}
for (t,) in frappe.db.sql("show tables like 'tabLife %'") + (("tabError Log",),):
    out[t] = [str(v) for v in frappe.db.sql(f"select count(*), max(modified) from \`{t}\`")[0]]
print(json.dumps(out))`).trim().split('\n').pop()
  const before = JSON.parse(snapshot())
  const ob = await chromium.launch({ executablePath: SETUP.chrome, headless: true })
  let bad = 0
  for (const width of [1440, 390]) {
    const ctx = await ob.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, timezoneId: 'Asia/Kolkata', isMobile: width < 800, hasTouch: width < 800 })
    const page = await ctx.newPage()
    const res = await page.request.post(ownerBase + '/api/method/login', { form: { usr: 'owner@lifeos.test', pwd: env.LIFEOS_DEV_PASSWORD } })
    if (!res.ok()) throw new Error('login failed on the owner site')
    const refused = new Set()
    await page.route(/\/api\//, (r) => {
      const req = r.request()
      const create = req.method() !== 'GET' && /journal\.month$/.test(req.url()) && /"create":\s*(1|true)/.test(req.postData() || '')
      if (req.method() === 'GET' || (READS.test(req.url()) && !create)) return r.continue()
      refused.add(new URL(req.url()).pathname.replace('/api/method/', ''))
      return r.abort()
    })
    await page.goto(ownerBase + '/life', { waitUntil: 'networkidle' })
    const { seen, failures } = await walkScreens(page, { width })
    console.log(`${failures.length ? 'FAIL' : 'PASS'}  owner site at ${width} px: ${seen} screens${failures.length ? '  — ' + failures.join('; ') : ''}`)
    // set 8: every tab of the weekly review and every drawer in it (read only, every tab can be looked at)
    const review = await walkReview(page, ownerBase, width)
    console.log(`${review.failures.length ? 'FAIL' : 'PASS'}  owner site at ${width} px: the weekly review, ${review.seen} tabs and drawers${review.failures.length ? '  — ' + review.failures.join('; ') : ''}`)
    bad += review.failures.length
    if (refused.size) console.log(`      refused writes: ${[...refused].join(', ')}`)
    bad += failures.length
    await ctx.close()
  }
  await ob.close()
  const after = JSON.parse(snapshot())
  const changed = Object.keys(after).filter((t) => JSON.stringify(after[t]) !== JSON.stringify(before[t]))
  console.log(`${changed.length ? 'FAIL' : 'PASS'}  the owner's site is unchanged${changed.length ? '  — changed: ' + changed.join(', ') : ''}`)
  return bad || changed.length ? 1 : 0
}
// set 8: open each tab of the weekly review by URL and each drawer in it, and report a script error, the error message, or a
// tab or drawer that did not show
async function walkReview(page, origin, width) {
  const failures = []
  let seen = 0
  const errors = []
  const onError = (e) => errors.push(String(e).split('\n')[0])
  page.on('pageerror', onError)
  const wait = () => page.waitForTimeout(700)
  const look = async (name, sel) => {
    await wait()
    const ok = await page.locator(sel).first().isVisible().catch(() => false)
    if (errors.length) failures.push(`${name}: script error: ${errors.splice(0).join(' | ')}`)
    if (await page.locator('[data-screen-error]').count()) failures.push(`${name}: the screen could not be shown`)
    if (!ok) failures.push(`${name}: not shown`)
    seen += 1
  }
  const drawer = async (name, opener, sel = '[data-drawer]') => {
    const el = page.locator(opener).first()
    if (!(await el.count()) || !(await el.isVisible()) || await el.isDisabled().catch(() => false)) return
    await el.click()
    await look(name, sel)
    await page.keyboard.press('Escape')
    await wait()
  }
  for (const tab of ['library', 'tasks', 'goals', 'reflect']) {
    await page.goto(`${origin}/life/today/week?view=review&tab=${tab}&area=`, { waitUntil: 'networkidle' })
    await look(`review > ${tab}`, `[data-review-${tab}]`)
    if (tab === 'library') {
      await drawer('a meeting', '[data-strip-meeting]:visible')
      await drawer('the Inbox piles', '[data-review-the-piles]')
      await drawer('the meetings that matter', '[data-meetings-door]')
    } else if (tab === 'tasks') {
      for (const p of ['keep', 'park', 'letgo']) await drawer(`the ${p} pile`, `[data-pile-card][data-pile="${p}"] [data-pile-open]`)
    } else if (tab === 'goals') {
      await drawer('a goal', '[data-goal-row] button')
      await drawer('other goals', '[data-goals-plan-any]')
      if (width < 800) await drawer('next week', '[data-goals-week-btn]')
    }
  }
  page.off('pageerror', onError)
  return { seen, failures }
}
if (process.argv.includes('--owner-read-only')) process.exit(await ownerReadOnly())

// A full run is every place on its own fresh site, one after another, as CI runs them side by side: a place never meets the
// records of another, so it passes alone, in a full run and in CI alike.
const { PLACES } = await import('./acceptance/places.mjs')
if (!process.argv.some((a) => a.startsWith('--part=') || a.startsWith('--only='))) {
  // scripts/run-issues.sh sets LIFEOS_RUNNER: GitHub Actions runs the full walk on every pull request, so a run on the Mac
  // only costs an hour and proves nothing more
  if (process.env.LIFEOS_RUNNER) {
    console.log('The full walk runs on GitHub for every pull request. Here, run only the checks you need: --only=GOALS or --only=GOALS.3,BRAIN.7.')
    process.exit(2)
  }
  const failed = []
  for (const place of PLACES) {
    console.log(`\n== ${place} ==`)
    try {
      execFileSync(process.execPath, [process.argv[1], `--part=${place}`, ...process.argv.slice(2)], { stdio: 'inherit' })
    } catch { failed.push(place) }
  }
  console.log(failed.length ? `\nFailed: ${failed.join(', ')}.` : `\nEvery place passes.`)
  process.exit(failed.length ? 1 : 0)
}

if (!process.argv.includes('--no-reset')) execFileSync(path.join(root, 'scripts/acceptance-site.sh'), { stdio: 'inherit' })

const C = await import('./acceptance/context.mjs')
for (const place of C.PLACES) if (C.placeRuns(place)) await import(`./acceptance/${place}.mjs`)
if (!C.ONLY) await import('./acceptance/end.mjs')

await C.browser.close()
const failed = C.results.filter((r) => !r[1])
console.log(`\n${C.results.length - failed.length} of ${C.results.length} acceptance checks pass.`)
process.exit(failed.length ? 1 : 0)
