// Screenshots of the weekly review (set 8) on the acceptance site, at 1440 x 900 and 390 x 844, light and dark, with the page
// and sideways scroll measured. It changes the acceptance site: run scripts/acceptance-site.sh first, never on lifeos.localhost.
//   node tools/review-shots.mjs [--schemes light,dark] [--widths 1440,390]
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const root = path.resolve(import.meta.dirname, '..')
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env'), 'utf8').split('\n').filter(Boolean).map((l) => l.split('=')))
const args = process.argv.slice(2)
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def }
const base = 'http://localhost:19000'
const SITE = 'acceptance.localhost'
const out = path.join(root, 'screenshots')
fs.mkdirSync(out, { recursive: true })
const bench = (code) => execFileSync('docker', ['exec', '-i', 'lifeos-bench', 'bash', '-lc', 'cd ~/frappe-bench/sites && ../env/bin/python -W ignore -'],
  { input: `import frappe; frappe.init("${SITE}"); frappe.connect()\n${code}\nfrappe.db.commit()\n`, encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] }).trim()
const report = []
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
for (const width of opt('widths', '1440,390').split(',').map(Number)) {
  for (const scheme of opt('schemes', 'light,dark').split(',')) {
    const phone = width < 800
    const stamp = `shot ${width} ${scheme}`
    JSON.parse(bench(`import json\nfrom lifeos import devtools_review\nprint(json.dumps(devtools_review.setup("${stamp}"), default=str))`).split('\n').pop())
    const ctx = await browser.newContext({ viewport: { width, height: phone ? 844 : 900 }, colorScheme: scheme, timezoneId: 'Asia/Kolkata', isMobile: phone, hasTouch: phone })
    const pg = await ctx.newPage()
    const errors = []
    pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
    await pg.request.post(base + '/api/method/login', { form: { usr: 'owner@lifeos.test', pwd: env.LIFEOS_DEV_PASSWORD } })
    await pg.goto(base + '/life', { waitUntil: 'networkidle' })
    await pg.evaluate((sc) => localStorage.setItem('theme', sc), scheme)
    const shot = async (name) => {
      await pg.waitForTimeout(700)
      const o = await pg.evaluate(() => ({ x: document.documentElement.scrollWidth - window.innerWidth, y: document.documentElement.scrollHeight - window.innerHeight }))
      const file = path.join(out, `s8-${name}-${width}-${scheme}.png`)
      await pg.screenshot({ path: file })
      report.push(`${path.basename(file)}  scrollX=${o.x} scrollY=${o.y}${errors.length ? '  ERRORS: ' + errors.splice(0).join(' | ') : ''}`)
    }
    const open = async (q) => { await pg.goto(`${base}/life/plan/week?area=&${q}`, { waitUntil: 'networkidle' }); await pg.waitForTimeout(900) }
    const api = async (m, a) => { const csrf = await pg.evaluate(() => window.csrf_token); const r = await pg.request.post(`${base}/api/method/lifeos.api.${m}`, { data: a, headers: { 'X-Frappe-CSRF-Token': csrf } }); return (await r.json()).message }
    await open('view=review&tab=library')
    await shot('library')
    const meet = pg.locator('[data-strip-meeting]:visible').first()
    if (await meet.count()) { await meet.click(); await shot('meeting'); await pg.keyboard.press('Escape') }
    await pg.locator('[data-review-the-piles]').click(); await shot('inbox-piles'); await pg.keyboard.press('Escape')
    await open('view=review&tab=tasks')
    await shot('tasks')
    await pg.locator('[data-pile-card][data-pile="park"] [data-pile-open]').click(); await shot('pile-drawer')
    await pg.locator('[data-pile-accept]').click(); await pg.waitForTimeout(800); await shot('pile-accepted')
    // clear the rest through the API, then Goals
    const get = async (m, a) => (await (await pg.request.get(`${base}/api/method/lifeos.api.${m}`, { params: a })).json()).message
    const sum = await get('weekly.pile_summary', { space: 'Private', key: 'tasks' })
    for (const n of sum.needs.filter((x) => !x.settled)) await api('weekly.pile_settle', { space: 'Private', key: 'tasks', ref: n.ref, decision: 'keep' })
    for (const p of ['keep', 'letgo', 'park']) await api('weekly.pile_accept', { space: 'Private', key: 'tasks', pile: p })
    await open('view=review&tab=goals')
    await shot('goals')
    await pg.locator('[data-goal-row] button').first().click(); await shot('goal-drawer'); await pg.keyboard.press('Escape')
    if (phone) { await pg.locator('[data-goals-week-btn]').click(); await shot('goals-week'); await pg.keyboard.press('Escape') }
    const g = await get('weekly.goals', { space: 'Private' })
    for (const [i, r] of g.rows.entries()) await api('weekly.goal_save', { space: 'Private', goal: r.goal, values: { next_action: `Next step ${i}`, task: null, minutes: 60 } })
    await open('view=review&tab=reflect')
    await shot('reflect')
    await pg.locator('[data-went-well] textarea, textarea[data-went-well]').first().fill('A good week')
    await pg.locator('[data-review-next]').click(); await pg.waitForTimeout(1500)
    await shot('done')
    await pg.goto(base + '/life?area=', { waitUntil: 'networkidle' }); await shot('today')
    await ctx.close()
    bench(`from lifeos import devtools_review\ndevtools_review.cleanup("${stamp}")`)
  }
}
await browser.close()
console.log(report.join('\n'))
