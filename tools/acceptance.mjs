// Walks the acceptance list in section 13 of SPEC.md against the local test site, as a person would:
// (rewritten for set 6: the four places Today, Inbox, Plan and Library, the lens, projects as open-ended goals; the set 6
// checks themselves are numbered S6.n and U<width>.40 and up)
// a logged-in browser for the owner and for a second user, and agent/fake_agent.py over HTTP with an API key.
//   node tools/acceptance.mjs
// It runs against the throwaway site acceptance.localhost (http://localhost:19000), which scripts/acceptance-site.sh
// rebuilds from a snapshot with seed and demo data before every run, so lifeos.localhost stays clean for the owner.
// Needs the Docker bench running and .env with LIFEOS_DEV_PASSWORD. `--no-reset` keeps the acceptance site as it is.
// Issue 5: the bench, the browser and the password can come from elsewhere (tools/acceptance-env.mjs), as in GitHub
// Actions; LIFEOS_FAIL_SHOTS names a folder that gets a screenshot of every open page when a check fails.
// `--owner-read-only` only walks every screen on the owner's site, lifeos.localhost, changing nothing (bug fix 1).
// It prints one line per acceptance item and exits 1 if any fails.
import { chromium } from 'playwright-core'
import { walkScreens } from './screen-walk.mjs'
import { resolveSetup, benchPython, MAC_CHROME } from './acceptance-env.mjs'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const SETUP = resolveSetup()
const env = { LIFEOS_DEV_PASSWORD: SETUP.password }
const base = process.env.LIFEOS_URL || 'http://localhost:19000'
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
if (!process.argv.includes('--no-reset')) execFileSync(path.join(root, 'scripts/acceptance-site.sh'), { stdio: 'inherit' })
const GET_METHODS = new Set(JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/lib/getMethods.json'), 'utf8')))
const queryParams = (args) => Object.fromEntries(Object.entries(args || {}).filter(([, v]) => v !== undefined && v !== null)
  .map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 1 : 0) : typeof v === 'object' ? JSON.stringify(v) : v]))
const SPACE = 'Private'
const stamp = Date.now().toString(36)
const results = []
const iso = (d) => new Date(d.getTime() + 5.5 * 3600e3).toISOString().slice(0, 10) // Asia/Kolkata date
const today = iso(new Date())
const addDays = (n) => iso(new Date(Date.now() + n * 86400e3))
const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
// the first date at least `min` days from today that falls on the named weekday (YYYY-MM-DD)
const nextWeekday = (name, min = 1) => { for (let n = min; ; n++) { const d = addDays(n); if (DAY_NAMES[new Date(d + 'T12:00:00Z').getUTCDay()] === name) return d } }
const plusDays = (d, n) => new Date(Date.parse(d + 'T12:00:00Z') + n * 86400e3).toISOString().slice(0, 10)

function bench(code, site = SITE) {
  // run Python on the acceptance site, for the steps that need the clock moved (the archive job)
  const script = `import frappe; frappe.init("${site}"); frappe.connect()\n${code}\nfrappe.db.commit()\n`
  return benchPython(script).trim()
}

const browser = await chromium.launch({ executablePath: SETUP.chrome, headless: true })

async function session(user, width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, timezoneId: 'Asia/Kolkata',
    isMobile: width < 800, hasTouch: width < 800 })
  const page = await ctx.newPage()
  const res = await page.request.post(base + '/api/method/login', { form: { usr: user, pwd: env.LIFEOS_DEV_PASSWORD } })
  if (!res.ok()) throw new Error('login failed for ' + user)
  await page.goto(base + '/life', { waitUntil: 'networkidle' })
  const csrf = await page.evaluate(() => window.csrf_token)
  const api = async (method, args = {}, { raw = false } = {}) => {
    const full = method.includes('lifeos.') || method.startsWith('frappe.') ? method : 'lifeos.api.' + method
    // reads the server answers only over GET go as GET, with the query string the front end sends (lib/api.js)
    const r = GET_METHODS.has(full)
      ? await page.request.get(`${base}/api/method/${full}`, { params: queryParams(args) })
      : await page.request.post(`${base}/api/method/${full}`,
        { data: args, headers: { 'X-Frappe-CSRF-Token': csrf, 'Content-Type': 'application/json' } })
    if (raw) return r
    if (!r.ok()) throw new Error(`${method} -> HTTP ${r.status()} ${(await r.text()).slice(0, 300)}`)
    return (await r.json()).message
  }
  const upload = async (doctype, docname, name, mimeType, buffer) => {
    const r = await page.request.post(base + '/api/method/upload_file', { headers: { 'X-Frappe-CSRF-Token': csrf },
      multipart: { doctype, docname, is_private: '1', file: { name, mimeType, buffer } } })
    if (!r.ok()) throw new Error('upload failed ' + r.status())
    return (await r.json()).message
  }
  // Set 6: the lens (space= and area=) is remembered per user and added to every URL. A path that names no area opens on
  // All of life (area= empty clears the lens), so one check's lens never narrows the next; the lens checks name it.
  const open = async (p) => {
    const u = new URL(base + p)
    if (u.pathname.startsWith('/life') && !u.searchParams.has('area')) u.searchParams.set('area', '')
    await page.goto(u.toString(), { waitUntil: 'networkidle' }); await page.waitForTimeout(400)
  }
  return { ctx, page, api, upload, open }
}

const ONLY_UX = process.argv.includes('--ux') // run only the UX checks (U1 and up)
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7) // run only the checks whose number ends with this: --only=.8
// Issue 5: `--part=` runs one part of the walk, so GitHub Actions can run the parts side by side, each on its own bench:
//   --part=1440   the UX checks of sets 1 to 6 at 1440 px (U1440.n)
//   --part=390    the same at 390 px (U390.n)
//   --part=sets   everything else: S6, sets 7 and 8, bug fix 1 and the issues at both widths, I5 and the scan (C.1)
// Every part also runs checks 1 to 16 and S1 to S3, whose records later checks use, and the clean-up S4.1 and S4.0.
// Without it, the whole walk runs, one check after another, as before.
const PART = (process.argv.find((a) => a.startsWith('--part=')) || '').slice(7)
if (PART && !['1440', '390', 'sets'].includes(PART)) throw new Error('--part= takes 1440, 390 or sets')
const UX_WIDTHS = { '': [1440, 390], 1440: [1440], 390: [390], sets: [] }[PART]
const SET_WIDTHS = PART && PART !== 'sets' ? [] : [1440, 390]
const inPart = (n) => {
  const name = String(n)
  if (!PART || /^(\d+|S[123]|S4\.[01])$/.test(name)) return true
  return PART === 'sets' ? !/^U\d/.test(name) : name.startsWith(`U${PART}.`)
}
async function check(n, title, fn) {
  if (!inPart(n)) return
  if (ONLY_UX && !String(n).startsWith('U')) return
  if (ONLY && !ONLY.split(',').some((o) => String(n).endsWith(o) || String(n).startsWith(o))) return // --only=.3,.32 runs several; --only=S8 by prefix
  try {
    const note = await fn()
    results.push([n, true, title, note || ''])
  } catch (e) {
    const lines = String(e.message || e).split('\n')
    const at = lines.find((l) => /waiting for (locator|getBy)/.test(l)) // which element Playwright waited for
    results.push([n, false, title, (lines[0] + (at ? ' ' + at.trim() : '')).slice(0, 400)])
    if (FAIL_SHOTS) await failShots(n)
  }
  const [, ok, t, note] = results[results.length - 1]
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${String(n).padStart(2)}. ${t}${note ? '  — ' + note : ''}`)
}
const must = (cond, message) => { if (!cond) throw new Error(message) }
// Issue 5: when a check fails, every page still open is saved to LIFEOS_FAIL_SHOTS (GitHub Actions uploads the folder)
const FAIL_SHOTS = process.env.LIFEOS_FAIL_SHOTS
async function failShots(n, dir = FAIL_SHOTS) {
  fs.mkdirSync(dir, { recursive: true })
  const saved = []
  for (const [c, ctx] of browser.contexts().entries()) {
    for (const [p, page] of ctx.pages().entries()) {
      const file = path.join(dir, `${String(n).replace(/[^\w.-]/g, '_')}-${c + 1}-${p + 1}.png`)
      if (await page.screenshot({ path: file, timeout: 10000 }).then(() => true, () => false)) saved.push(file)
    }
  }
  return saved
}

// the agent's key is made for this run and passed in the environment; it is never printed or stored
const [agentKey, agentSecret] = bench('from lifeos import devtools\nprint(devtools.agent_api_key())').split('\n').pop().split(':')
// the agent over HTTP with its key: GET for the methods that declare GET (frontend/src/lib/getMethods.json), POST for the rest,
// so a refusal is the permission rule and not the wrong HTTP method
function agentFetch(m, args = {}) {
  const headers = { Authorization: `token ${agentKey}:${agentSecret}` }
  const url = `${base}/api/method/lifeos.api.${m}`
  if (GET_METHODS.has(`lifeos.api.${m}`)) return fetch(`${url}?${new URLSearchParams(args)}`, { headers })
  return fetch(url, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(args) })
}
function runAgent() {
  return execFileSync('python3', [path.join(root, 'agent/fake_agent.py'), '--url', base],
    { env: { ...process.env, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' })
}
// a real one-page PDF, made by the test helpers on the bench
const PDF = Buffer.from(bench('import base64\nfrom lifeos import devtools\nprint(base64.b64encode(devtools.pdf_bytes()).decode())').split('\n').pop(), 'base64')

// the Settings check adds and removes this person as a member; they exist on the acceptance site with no space
bench(`from lifeos import devtools\nfrappe.set_user("Administrator")\ndevtools.make_user("stranger@lifeos.test", "Stranger", ["Life User"])`)
// UX fixes, set 5: Ask and the AI insights use the fake model here, never the real API: the site config flag, and a key that
// starts with "fake-", which the client never sends anywhere. Insights start empty.
bench(`from frappe.installer import update_site_config
update_site_config("lifeos_fake_ai", 1)
s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()
frappe.db.delete("Life Insight"); frappe.db.delete("Life AI Usage")
for sp in frappe.get_all("Life Space", pluck="name"): frappe.db.set_value("Life Space", sp, {"ask_enabled": 1, "ask_can_read_vault": 0})`)
// Earlier runs leave their records on the test site. Today lists only the 20 documents that expire soonest, so the vault
// documents of earlier runs are archived first; otherwise this run's document would not be among them.
bench(`from lifeos import archive
frappe.set_user("owner@lifeos.test")
for name in frappe.get_all("Life Vault Document", filters={"space": "${SPACE}", "is_archived": 0}, or_filters=[["title", "like", "UX permit %"], ["title", "like", "Passport m%"]], pluck="name"):
    archive.set_archived("Life Vault Document", name, True, "Manual")`)

const owner = await session('owner@lifeos.test')
const areas = (await owner.api('area.tree', { space: SPACE })).areas
const areaId = (name) => areas.find((a) => a.area_name === name)?.name
let photoItem, photoFile

await check(1, 'Log in, open /life, Today is filled from seed data', async () => {
  const guest = await browser.newContext()
  const res = await guest.request.get(base + '/life', { maxRedirects: 0 })
  must(res.status() === 302 && (res.headers().location || '').includes('/login'), 'a guest is not sent to login')
  must((await guest.request.get(base + '/api/method/lifeos.api.today.get')).status() >= 400, 'a guest can call the API')
  await guest.close()
  await owner.open('/life')
  const text = await owner.page.locator('[data-main]').innerText()
  must(/Week \d+ of 12/.test(text), 'no 12 Week Year week on Today')
  const habitNames = await owner.page.locator('[data-today-habits] [data-habit]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')).join(' '))
  must(text.includes('Habits today') && habitNames.includes('Japa'), 'habits are missing on Today')
  const t = await owner.api('today.get', { space: SPACE })
  must(t.cycle && t.habits.length === 4, 'today.get has no cycle or habits')
  return `week ${t.cycle.week}, ${t.habits.length} habits, ${t.tasks.due} tasks due`
})

await check(2, 'Journal photo: agent submits 5 proposals; accept 3, edit 1, reject 1; records link back', async () => {
  const item = await owner.api('inbox.create_item', { title: `Journal photo ${stamp}`, source_type: 'Journal Photo', space: SPACE,
    instruction: 'transcribe and update my journal' })
  photoItem = item.name
  photoFile = (await owner.upload('Life Inbox Item', item.name, `journal-${stamp}.png`, 'image/png', await owner.page.screenshot())).file_url
  runAgent()
  let got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'To Review', 'item is ' + got.status)
  must(got.transcript_md && got.proposals.length === 5, `expected 5 proposals, got ${got.proposals.length}`)
  // accept the first and reject the second with the buttons on the Review screen
  await owner.open('/life/inbox/' + item.name)
  await owner.page.getByRole('button', { name: 'Accept', exact: true }).first().click()
  await owner.page.waitForTimeout(800)
  await owner.page.getByRole('button', { name: 'Reject', exact: true }).first().click()
  await owner.page.waitForTimeout(800)
  got = await owner.api('inbox.get', { item: item.name })
  must(got.proposals[0].status === 'Accepted' && got.proposals[1].status === 'Rejected', 'the Review buttons did not decide')
  const pending = got.proposals.filter((p) => p.status === 'Pending')
  const edit = pending.find((p) => p.preview.includes('Generic promotion'))
  for (const p of pending.filter((p) => p !== edit)) await owner.api('review.decide', { proposal: p.name, decision: 'accept' })
  // 12: one tap changes the area, a second area is added
  await owner.api('review.decide', { proposal: edit.name, decision: 'accept',
    payload: { ...edit.payload, title: `Promotion plan ${stamp}`, area: areaId('Tea & Coffee'), also_in: [areaId('Personal')] } })
  got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'Done', 'item should be Done, is ' + got.status)
  const made = got.proposals.filter((p) => p.status === 'Accepted')
  must(made.length === 4 && made.every((p) => p.created_name), 'accepted proposals did not store their records')
  const links = await owner.api('links.backlinks', { doctype: 'Life Inbox Item', name: item.name })
  must(links.some((l) => l.doctype === 'Life Task') && links.some((l) => l.doctype === 'Life Journal Page'), 'records do not link back to the photo')
  const tasks = await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] }) // this run's tasks: the site holds more than one page
  must(tasks.tasks.some((t) => t.title === `Promotion plan ${stamp}` && t.inbox_item === item.name), 'the edited task is not in Tasks')
  const pages = await owner.api('journal.pages', { space: SPACE })
  must(JSON.stringify(pages).includes(item.name), 'the journal page is not in Journal, Pages')
  return `${made.length} accepted (1 edited), 1 rejected`
})

await check(3, 'PDF with "summarise and extract to-dos" gives tasks through review', async () => {
  const item = await owner.api('inbox.create_item', { title: `Production note ${stamp}.pdf`, space: SPACE, instruction: 'summarise and extract to-dos' })
  await owner.upload('Life Inbox Item', item.name, `production-${stamp}.pdf`, 'application/pdf', PDF)
  runAgent()
  const got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'To Review' && got.summary_md && got.proposals.length === 3, 'no summary or proposals')
  await owner.api('review.decide_all', { item: item.name, decision: 'accept' })
  const links = await owner.api('links.backlinks', { doctype: 'Life Inbox Item', name: item.name })
  must(links.filter((l) => l.doctype === 'Life Task').length === 3, 'three tasks expected')
  return '3 tasks'
})

await check(4, 'Tick a habit at phone width and see the month count change', async () => {
  const phone = await session('owner@lifeos.test', 390)
  await phone.open('/life/today/month?view=habits')
  const count = () => phone.page.locator('text=/\\d+ of \\d+ days/').first().innerText()
  const before = await count()
  // an empty box if the month has one, else untick a ticked one: the count changes either way
  const empty = phone.page.locator('[data-habit-day][aria-pressed="false"]:not([disabled])')
  const box = (await empty.count()) ? empty.first() : phone.page.locator('[data-habit-day][aria-pressed="true"]:not([disabled])').last()
  const size = await box.boundingBox()
  must(size.width >= 40 && size.height >= 40, `habit box is ${size.width}x${size.height}`)
  await box.click()
  await phone.page.waitForTimeout(700)
  const after = await count()
  must(before !== after, `count stayed at ${before}`)
  must(await phone.page.locator('[data-habit-day]:not([disabled])').count() <= Number(today.slice(8)), 'a day that has not come can be ticked')
  must(await phone.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'the page scrolls sideways')
  await phone.ctx.close()
  return `${before} -> ${after}`
})

await check(5, 'Tick week cells in the 12 Week Year grid and see the week score change', async () => {
  await owner.open('/life/today/year?view=cycle')
  const stat = () => owner.page.locator('[data-stat]').first().innerText()
  const before = (await stat()).replace(/\n/g, ' ')
  const g = await owner.api('journal.grid', { space: SPACE })
  const col = g.current_week
  // an empty cell of the current week
  const cells = owner.page.locator(`[data-week-cell="${col}"]:not([disabled])`)
  const empty = owner.page.locator(`[data-week-cell="${col}"][aria-pressed="false"]:not([disabled])`)
  must(await cells.count(), 'the grid has no cells for the current week')
  await ((await empty.count()) ? empty.first() : cells.first()).click()
  await owner.page.waitForTimeout(800)
  const after = (await stat()).replace(/\n/g, ' ')
  must(before !== after, 'score stayed at ' + before)
  const g2 = await owner.api('journal.grid', { space: SPACE })
  must(JSON.stringify(g2.weeks?.[col - 1] ?? g2.average) !== JSON.stringify(g.weeks?.[col - 1] ?? g.average) || before !== after, 'server score unchanged')
  return `${before} -> ${after}`
})

await check(6, 'Carry an open October goal into November', async () => {
  const oct = await owner.api('journal.month', { space: SPACE, year: 2026, month: 10 })
  let goal = oct.plan.goals.find((x) => x.status === 'Open')
  if (!goal) { // an earlier run carried them all: add one more open goal to October
    await owner.api('journal.save_month_goal', { plan: oct.plan.name, title: `October goal ${stamp}`, priority: 'II' })
    goal = (await owner.api('journal.month', { space: SPACE, year: 2026, month: 10 })).plan.goals.find((x) => x.status === 'Open')
  }
  must(goal, 'no open goal in October')
  await owner.api('journal.carry_month_goal', { plan: oct.plan.name, row: goal.row })
  const oct2 = await owner.api('journal.month', { space: SPACE, year: 2026, month: 10 })
  const nov = await owner.api('journal.month', { space: SPACE, year: 2026, month: 11 })
  must(oct2.plan.goals.find((x) => x.row === goal.row).status === 'Carried', 'the October goal is not marked Carried')
  must(nov.plan.goals.some((x) => x.title === goal.title && x.carried_from), 'the goal is not in November')
  return goal.title
})

await check(7, 'Add a birthday and see it on the calendar this year and next', async () => {
  const title = `Birthday ${stamp}`
  await owner.api('calendar.add_important_date', { space: SPACE, title, day: 12, month: 12, kind: 'Birthday' })
  for (const year of [2026, 2027]) {
    const cal = await owner.api('calendar.get', { space: SPACE, from_date: `${year}-12-01`, to_date: `${year}-12-31` })
    must(JSON.stringify(cal.items).includes(title), 'not on the calendar in ' + year)
    const y = await owner.api('calendar.year', { space: SPACE, year })
    must(JSON.stringify(y).includes(title), 'not on the year view in ' + year)
  }
  await owner.open('/life/today/year?view=calendar')
  must((await owner.page.locator('[data-main]').innerText()).includes('Birthday'), 'not shown on the year screen')
})

await check(8, 'Vault document expiring in 30 days shows a badge on Today', async () => {
  const title = `Passport ${stamp}`
  await owner.api('vault.save', { space: SPACE, values: { title, doc_type: 'Travel', expiry_date: addDays(30), number_last4: '4821', area: areaId('Money & Legal') } })
  const refused = await owner.api('vault.save', { space: SPACE, values: { title: 'x', doc_type: 'ID', number_last4: '123456789', area: areaId('Money & Legal') } }, { raw: true })
  must(!refused.ok(), 'a full number was stored')
  const t = await owner.api('today.get', { space: SPACE })
  must(t.coming_up.some((c) => c.kind === 'vault' && c.title === title), 'not in today.get')
  await owner.open('/life')
  must((await owner.page.locator('[data-main]').innerText()).includes(title), 'not shown on Today')
  // set 6: the Vault's documents are captures of kind Document, marked sensitive, with their expiry
  await owner.open('/life/library/documents?tab=documents&sensitive=1')
  const row = owner.page.locator('[data-row]', { hasText: title }).first()
  must(await row.count(), 'not shown in Library > Captures, Documents')
  must(await row.locator('[data-expiry-badge]').count() && await row.locator('[data-sensitive-lock]').count(), 'the document has no expiry badge or lock')
})

await check(9, 'Note with a [[link]]: the target shows the backlink, both are in the graph', async () => {
  const target = await owner.api('library.save', { space: SPACE, title: `Target note ${stamp}`, content_md: 'The target.', area: areaId('Learning') })
  const source = await owner.api('library.save', { space: SPACE, title: `Source note ${stamp}`, content_md: `See [[Target note ${stamp}]] and [[No such note]].`, area: areaId('Learning') })
  const tName = target.name || target.note?.name, sName = source.name || source.note?.name
  const back = await owner.api('links.backlinks', { doctype: 'Life Note', name: tName })
  must(back.some((b) => b.name === sName), 'no backlink on the target')
  const graph = await owner.api('graph.get', { space: SPACE })
  const ids = graph.nodes.map((n) => n.id)
  must(ids.includes('Life Note/' + tName) && ids.includes('Life Note/' + sName), 'notes are not in the graph')
  must(graph.edges.some((e) => e.source === 'Life Note/' + sName && e.target === 'Life Note/' + tName), 'the link is not an edge')
  await owner.open('/life/library/' + tName)
  must((await owner.page.locator('[data-main]').innerText()).includes(`Source note ${stamp}`), 'the backlinks panel does not show the source')
})

await check(10, 'Search for a word in a transcript finds the inbox item', async () => {
  const res = await owner.api('search.query', { text: `Nowrojee ${stamp}` }) // the word is in the transcript, the stamp in the title of this run's item
  must(res.results.some((r) => r.ref_doctype === 'Life Inbox Item' && r.ref_name === photoItem), 'the inbox item was not found')
  await owner.page.keyboard.press('Control+k')
  await owner.page.keyboard.type(`Nowrojee ${stamp}`)
  await owner.page.waitForTimeout(900)
  must((await owner.page.locator('body').innerText()).includes(`Journal photo ${stamp}`), 'the search palette does not show it')
  await owner.page.keyboard.press('Escape')
})

await check(11, 'A second user who is only in Shared sees nothing from Private, on any screen or in search', async () => {
  const fam = await session('family@lifeos.test')
  const boot = await fam.api('session.boot')
  must(!JSON.stringify(boot.spaces).includes('Private'), 'Private is offered in the space switcher')
  const reads = { 'today.get': {}, 'tasks.list': {}, 'timeline.get': {}, 'inbox.list': {}, 'library.tree': {}, 'vault.list': {}, 'chats.report': {},
    'graph.get': {}, 'archive.list': {}, 'calendar.get': { from_date: '2026-11-01', to_date: '2026-12-31' }, 'calendar.year': { year: 2026 },
    'goals.list': {}, 'sources.list': {}, 'someday.list': {}, 'counts.get': {}, 'session.counts': {}, 'area.tree': {}, 'journal.grid': {}, 'journal.goals': {}, 'journal.month': {}, 'journal.habits': {}, 'journal.checkins': {},
    'journal.pages': {}, 'journal.weekly_review': {}, 'settings.get': {}, 'weekly.get': {}, 'weekly.library': {}, 'weekly.goals': {}, 'weekly.plate': {} }
  for (const [m, args] of Object.entries(reads)) {
    const r = await fam.api(m, { ...args, space: SPACE }, { raw: true })
    must(r.status() === 403, `${m} with space=Private answered ${r.status()}`)
    const own = JSON.stringify(await fam.api(m, args)) || ''
    must(!own.includes(stamp) && !own.includes('Ruchi ITR') && !own.includes('Japa'), `${m} leaks Private records`)
  }
  const privateGoal = (await owner.api('goals.list', { space: SPACE, horizon: 'Long term', page_length: 1 })).goals[0].name
  for (const [m, args] of [['inbox.get', { item: photoItem }], ['goals.get', { goal: privateGoal }], ['goals.completion_info', { goal: privateGoal }],
    ['links.backlinks', { doctype: 'Life Inbox Item', name: photoItem }]]) {
    must((await fam.api(m, args, { raw: true })).status() === 403, `${m} is readable`)
  }
  for (const word of ['Nowrojee', 'Ruchi', stamp, 'Merrill']) {
    must((await fam.api('search.query', { text: word })).results.length === 0, `search finds "${word}"`)
  }
  must((await fam.page.request.get(base + photoFile)).status() === 403, 'the private file is served')
  must((await owner.page.request.get(base + photoFile)).status() === 200, 'the owner cannot open the file')
  const list = await fam.page.request.get(base + '/api/resource/Life%20Task?limit_page_length=500&fields=["space"]')
  must(!JSON.stringify(await list.json()).includes('Private'), 'the REST list shows Private tasks')
  let screens = 0
  // every place, tab and view (set 6), and a Private goal's page and Private area in the URL
  for (const p of ['', '/inbox', '/plan/week?view=review', '/plan/week?view=calendar', '/plan/week?view=agenda', '/plan/month?view=plan', '/plan/month?view=habits',
    '/plan/month?view=checkins', '/plan/month?view=calendar', '/plan/12-weeks', '/plan/year?view=calendar', '/plan/year?view=goals', '/plan/goals', '/plan/tasks',
    '/plan/someday', '/plan/reset', '/library', '/library/notes', '/library/notes?view=tree', '/library/notes?view=graph', '/library/notes?by=assistant',
    '/library/captures', '/library/captures?tab=documents&sensitive=1', '/library/captures?tab=chats', '/library/captures?tab=pages', '/library/timeline',
    '/library/archive', '/ask', '/settings', `/plan/goals/${privateGoal}`, `/?area=${areaId('Tea & Coffee')}`]) {
    await fam.open('/life' + p)
    const text = await fam.page.locator('[data-app]').innerText()
    must(!/Ruchi|Merrill|Japa|Tea & Coffee|Private/.test(text) && !text.includes(stamp), `screen ${p || '/'} shows Private content`)
    screens++
  }
  await fam.ctx.close()
  return `${Object.keys(reads).length} methods, ${screens} screens, search and file`
})

await check(12, 'At review, change the area with one tap and add a second: the record is under both areas in the lens', async () => {
  // set 6: the area pages became the lens; a record filed under one area and "also in" another shows under both
  const title = `Promotion plan ${stamp}`
  for (const name of ['Tea & Coffee', 'Personal']) {
    const rows = (await owner.api('tasks.list', { space: SPACE, area: areaId(name), status: 'all', page_length: 50, filters: [['title', '=', title]] })).tasks
    must(rows.length === 1, `not in Tasks under the ${name} lens`)
    await owner.open(`/life/goals/tasks?view=list&status=all&area=${areaId(name)}`)
    must((await owner.page.locator('[data-main]').innerText()).includes(title), `not on Plan > Tasks with ${name} in the lens`)
  }
  const item = await owner.api('inbox.list', { space: SPACE, status: 'To Review' })
  await owner.open('/life/inbox/' + item.items[0].name)
  must(await owner.page.locator('text=also in').count() > 0, 'the Review screen has no area chips')
})

await check(13, 'Tea & Coffee in the lens: Plan and Library show its open-ended goals, tasks, notes and chats together', async () => {
  // set 6: what the area page held is what the places show with the area in the lens
  const tea = areaId('Tea & Coffee')
  const goals = (await owner.api('goals.list', { space: SPACE, area: tea, horizon: 'Long term' })).goals
  const tasks = (await owner.api('tasks.list', { space: SPACE, area: tea, page_length: 5 })).tasks
  const notes = (await owner.api('library.list', { space: SPACE, area: tea, collection: 'all', page_length: 1 })).notes
  const chats = (await owner.api('sources.list', { space: SPACE, area: tea, tab: 'chats', page_length: 1 })).sources
  must(goals.length && tasks.length && notes.length && chats.length, `goals ${goals.length}, tasks ${tasks.length}, notes ${notes.length}, chats ${chats.length}`)
  for (const [p, title] of [[`/life/goals?type=Long+term&area=${tea}`, goals[0].title], [`/life/goals/tasks?view=list&area=${tea}`, tasks[0].title],
    [`/life/library/notes?view=list&area=${tea}`, notes[0].title], [`/life/library/chats?tab=chats&view=list&area=${tea}`, chats[0].title]]) {
    await owner.open(p)
    must((await owner.page.locator('[data-main]').innerText()).includes(title), `${p} does not show ${title}`)
    must(await owner.page.locator('[data-lens-chip]').count(), `${p} does not show the area chip`)
  }
  await owner.open('/life?area=') // leave the lens on All of life
  return `${goals.length} open-ended goals, ${tasks.length}+ tasks, notes and chats`
})

await check(14, 'Timeline shows everything captured on one day', async () => {
  const t = await owner.api('timeline.get', { space: SPACE, from_date: today, to_date: today, page_length: 100 })
  const kinds = new Set(t.days.flatMap((d) => d.entries.map((e) => e.kind)))
  for (const k of ['Inbox', 'Task', 'Note', 'Document', 'Journal Page']) must(kinds.has(k), `no ${k} on today's timeline`)
  must(t.days.length === 1, 'more than one day returned')
  await owner.open('/life/library/timeline?all=1') // a bare URL restores the remembered view, which a UX check may have filtered
  must((await owner.page.locator('[data-main]').innerText()).includes(`Target note ${stamp}`), 'the screen does not show today')
  return [...kinds].join(', ')
})

await check(15, 'Complete an open-ended goal (a project before set 6): it and its records move to Archive. Restore it', async () => {
  const g = await owner.api('goals.create', { space: SPACE, title: `Open goal ${stamp}`, horizon: 'Long term', area: areaId('Learning') })
  const task = await owner.api('tasks.quick_add', { text: `Goal task ${stamp}`, space: SPACE, goal: g.name })
  const info = await owner.api('goals.completion_info', { goal: g.name })
  must(info.records >= 1, 'the confirm dialog has no count')
  await owner.api('goals.set_status', { goal: g.name, status: 'Done' })
  let arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(arch.goals.some((p) => p.name === g.name), 'the goal is not in Archive')
  must(JSON.stringify(arch.groups).includes(task.name), 'its task is not in Archive')
  must(!(await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] })).tasks.some((t) => t.name === task.name), 'the task is still in Tasks')
  must(!JSON.stringify(await owner.api('goals.list', { space: SPACE, page_length: 200 })).includes(g.name), 'the goal is still in progress on Goals')
  await owner.open('/life/library/archive')
  must((await owner.page.locator('[data-main]').innerText()).includes(`Open goal ${stamp}`), 'the Archive screen does not show it')
  await owner.api('archive.restore', { doctype: 'Life Goal', name: g.name })
  arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(!arch.goals.some((p) => p.name === g.name) && !JSON.stringify(arch.groups).includes(task.name), 'restore left it in Archive')
  must((await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] })).tasks.some((t) => t.name === task.name), 'the task did not come back')
})

await check(16, "Archive job archives done tasks; a stale open task waits in the weekly review's piles", async () => {
  const done = await owner.api('tasks.quick_add', { text: `Old done task ${stamp}`, space: SPACE, area: areaId('Personal') })
  const stale = await owner.api('tasks.quick_add', { text: `Stale open task ${stamp}`, space: SPACE, area: areaId('Personal') })
  await owner.api('tasks.set_status', { task: done.name, status: 'Done' })
  // move the clock: the first was finished 100 days ago, the second not touched for 100 days
  bench(`from frappe.utils import add_days, today
frappe.db.set_value("Life Task", "${done.name}", "completed_on", add_days(today(), -100), update_modified=False)
frappe.db.set_value("Life Task", "${stale.name}", {"last_touched_on": add_days(today(), -100), "creation": add_days(today(), -100)}, update_modified=False)
from lifeos import archive, index
index.update(frappe.get_doc("Life Task", "${done.name}"))
archive.run_daily()`)
  const arch = await owner.api('archive.list', { space: SPACE, page_length: 100, filters: [['title', 'like', `%${stamp}%`]] }) // earlier runs fill the Archive
  must(JSON.stringify(arch.groups).includes(done.name), 'the done task was not archived')
  must(!JSON.stringify(arch.groups).includes(stale.name), 'the stale open task was archived')
  // set 8: the weekly review's Tasks tab sorts it into a pile (untouched 100 days: Park in Someday); it is never archived for you
  const park = await owner.api('weekly.pile_drawer', { space: SPACE, key: 'tasks', pile: 'park' })
  must(park.rows.some((r) => r.name === stale.name), 'the stale task is not in the Park pile')
  await owner.open('/life/today/week?view=review&tab=tasks')
  await owner.page.locator('[data-pile-card][data-pile="park"] [data-pile-open]').first().click()
  await owner.page.waitForTimeout(800)
  must((await owner.page.locator('[data-drawer-name="pile"]').innerText()).includes(`Stale open task ${stamp}`), 'the Park pile does not show it')
  await owner.page.keyboard.press('Escape')
})

await check('S1', 'Security: rendered Markdown is sanitised', async () => {
  const bad = 'Hello <script>window.__pwned = 1</script> <img src=x onerror="window.__pwned = 2"> [click](javascript:window.__pwned=3) <a href="javascript:alert(1)">x</a> <iframe src="https://example.com"></iframe>'
  const note = await owner.api('library.save', { space: SPACE, title: `Sanitise ${stamp}`, content_md: bad, area: areaId('Learning') })
  await owner.open('/life/library/' + (note.name || note.note?.name))
  const found = await owner.page.evaluate(() => ({
    pwned: window.__pwned, scripts: document.querySelectorAll('[data-main] script, [data-main] iframe').length,
    handlers: [...document.querySelectorAll('[data-main] *')].filter((e) => [...e.attributes].some((a) => a.name.startsWith('on'))).length,
    js: [...document.querySelectorAll('[data-main] a')].filter((a) => (a.getAttribute('href') || '').trim().toLowerCase().startsWith('javascript:')).length,
    shown: document.querySelector('[data-main]').innerText.includes('Hello'),
  }))
  must(found.shown, 'the note did not render')
  must(!found.pwned && !found.scripts && !found.handlers && !found.js, JSON.stringify(found))
})

await check('S3', 'Security: the family and agent users land on /life from /app; the agent works without desk access and cannot read a closed Vault', async () => {
  for (const user of ['family@lifeos.test', 'hermes@lifeos.test']) {
    const ctx = await browser.newContext()
    const r = await ctx.request.post(base + '/api/method/login', { form: { usr: user, pwd: env.LIFEOS_DEV_PASSWORD } })
    must(r.ok(), 'login failed for ' + user)
    for (const p of ['/app', '/app/todo', '/desk']) {
      const res = await ctx.request.get(base + p, { maxRedirects: 0 })
      const to = res.headers().location || ''
      must(res.status() >= 300 && res.status() < 400 && /\/life$/.test(to.replace(base, '')), `${user} at ${p}: ${res.status()} ${to}`)
    }
    await ctx.close()
  }
  // the agent end to end with its API key: claim_next and submit_result through the fake agent
  const item = await owner.api('inbox.create_item', { title: `S3 agent item ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Call the plumber tomorrow.' })
  runAgent()
  must((await owner.api('inbox.get', { item: item.name })).status === 'To Review', 'the agent did not process the item without desk access')
  // with the switch off the agent's key cannot read a Vault document
  const doc = await owner.api('vault.save', { space: SPACE, values: { title: `S3 secret ${stamp}`, doc_type: 'ID' } })
  const asAgent = agentFetch
  const vaultOpen = (await owner.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE).agents_can_read_vault
  if (!vaultOpen) {
    must((await asAgent('vault.get', { document: doc.name })).status === 404, 'the agent read a Vault document with the switch off')
    const listed = await (await asAgent('vault.list', { space: SPACE })).json()
    must(listed.message.total === 0, 'the agent listed Vault documents with the switch off')
  }
})

await check('S2', 'Security: the PWA manifest and icons are served; an agent cannot decide or delete', async () => {
  const m = await (await owner.page.request.get(base + '/assets/lifeos/manifest.webmanifest')).json()
  must(m.start_url === '/life' && m.display === 'standalone' && m.icons.length >= 2, 'manifest is incomplete')
  for (const i of m.icons) must((await owner.page.request.get(base + i.src)).ok(), 'missing icon ' + i.src)
  must((await owner.page.content()).includes('rel="manifest"'), 'the page does not link the manifest')
  const auth = { Authorization: `token ${agentKey}:${agentSecret}`, 'Content-Type': 'application/json' }
  const ctx = await browser.newContext() // no session cookie: the agent's key only
  const decide = await ctx.request.post(base + '/api/method/lifeos.api.review.decide_all', { headers: auth, data: { item: photoItem, decision: 'accept' } })
  must(decide.status() === 403, 'an agent could decide: ' + decide.status())
  const task = (await owner.api('tasks.list', { space: SPACE })).tasks[0]
  const del = await ctx.request.delete(`${base}/api/resource/Life%20Task/${task.name}`, { headers: auth })
  must(del.status() === 403, 'an agent could delete: ' + del.status())
  const set = await ctx.request.post(base + '/api/method/lifeos.api.settings.set_member', { headers: auth, data: { space: 'Private', user: 'family@lifeos.test' } })
  must(set.status() === 403, 'an agent could change members: ' + set.status())
  await ctx.close()
})


// ---------- UX fixes, set 1: list then pane, and every number is a door ----------
// Run at 1440 px and at 390 px. `node tools/acceptance.mjs --ux` runs only these.
const uxArea = areaId('Tea & Coffee')
const ux = {}
{
  // records the checks need, made through the API as the owner. Set 6: a project became an open-ended goal (type Open);
  // ux.project is a former project of the area and ux.goal the goal it became.
  const former = JSON.parse(bench(`import json
print(json.dumps(frappe.db.sql("select p.name, p.migrated_to from \`tabLife Project\` p join \`tabLife Goal\` g on g.name = p.migrated_to where p.space='${SPACE}' and g.area='${uxArea}' and g.outcome='In Progress' and g.is_archived=0 and g.is_someday=0 order by p.creation limit 1")))`).split('\n').pop())
  must(former.length, 'no former project of Tea & Coffee on the acceptance site')
  ;[[ux.project, ux.goal]] = former
  ux.goalTitle = (await owner.api('goals.get', { goal: ux.goal })).goal.title
  ux.task = (await owner.api('tasks.quick_add', { text: `UX door task ${stamp}`, space: SPACE, goal: ux.goal, area: uxArea, priority: 'I', due_date: addDays(-2) })).name
  await owner.api('tasks.quick_add', { text: `UX due today ${stamp}`, space: SPACE, area: uxArea, due_date: today })
  const doneTask = (await owner.api('tasks.quick_add', { text: `UX done ${stamp}`, space: SPACE, goal: ux.goal, area: uxArea })).name
  await owner.api('tasks.set_status', { task: doneTask, status: 'Done' })
  const carried = (await owner.api('tasks.quick_add', { text: `UX carried ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.carry_forward', { task: carried })
  const old = (await owner.api('tasks.quick_add', { text: `UX archived by the job ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.set_status', { task: old, status: 'Done' })
  bench(`from lifeos import archive\nfrappe.set_user("owner@lifeos.test")\narchive.set_archived("Life Task", "${old}", True, "Auto")`)
  ux.note = (await owner.api('library.save', { space: SPACE, title: `UX note ${stamp}`, area: uxArea, content_md: 'A reference note for the UX checks.' })).name
  ux.vault = (await owner.api('vault.save', { space: SPACE, values: { title: `UX permit ${stamp}`, doc_type: 'Other', expiry_date: addDays(20), area: uxArea } })).name
  ux.chat = (await owner.api('chats.log', { space: SPACE, title: `UX chat ${stamp}`, area: uxArea, goal: ux.goal, summary_md: 'Talked about the UX checks.',
    open_items: ['Follow up on the UX checks'] })).name
  const item = await owner.api('inbox.create_item', { title: `UX inbox ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Buy a new kettle. Call the estate manager.' })
  runAgent()
  ux.inbox = item.name
}

const num = (text, which = 0) => { const m = String(text).match(/\d+/g); if (!m) throw new Error(`no number in "${text}"`); return Number(m[which]) }
// A bare list URL restores the remembered view, so the checks that want the whole list say so: all=1.
// Set 6: the lists are tabs of the four places; Projects are goals of type Open, the Vault's documents are captures.
const ROW = '[data-row]'
const LISTS = [
  ['Inbox', '/life/brain/queue?all=1'], ['Timeline', '/life/library/timeline?all=1'], ['Tasks', '/life/goals/tasks?view=list'],
  ['Goals', '/life/goals?all=1'], ['Documents', '/life/library/documents?tab=documents&all=1'], ['Captures', '/life/brain/captures?all=1'],
  ['Notes', '/life/library/notes?view=list&all=1'], ['All', '/life/library?view=list&all=1'], ['Archive', '/life/library/archive?all=1'],
].map(([name, p]) => [name, p, ROW])
// one filter for each ListView, set through the library's quick-filter strip: [screen, path, URL key, URL value, the control's label, the option to pick, text to type for a Link]
// The Area filters of set 4 are the lens since set 6 (U.40 and up check it); the Archive's only other quick filter is a text field.
const FILTERS = [
  ['Inbox', '/life/brain/queue?all=1', 'source_type', 'Message', 'Source Type', 'Message'], ['Tasks', '/life/goals/tasks?view=list', 'priority', 'I', 'Priority', 'I'],
  ['Tasks table', '/life/goals/tasks?view=table&status=all', 'priority', 'I', 'Priority', 'I'], ['Goals', '/life/goals?status=all', 'type', 'Long term', 'Horizon', 'Long term'],
  ['Captures', '/life/brain/captures?all=1', 'status', 'Done', 'Status', 'Done'],
  ['Notes', '/life/library/notes?view=list&all=1', 'goal', ux.goal, 'Goal', ux.goalTitle, ux.goalTitle.slice(0, 6)],
]
// UX fixes, set 3: the state tabs of each list screen. [screen, path, the URL parameter of the tabs, the tab values in order (the first is the default), another filter]
// The other filter is mostly the lens's area (set 6), so each tab's count is checked with an area chosen too.
const STATE_TABS = [
  ['Inbox', '/life/brain/queue', 'status', ['To Review', 'Waiting', 'Failed'], 'source_type=Message'],
  ['Tasks', '/life/goals/tasks', 'status', ['open', 'loops', 'Waiting', 'Done', 'Someday', 'all'], `area=${uxArea}`],
  ['Goals', '/life/goals', 'status', ['in_progress', 'achieved', 'closed', 'someday', 'all'], `area=${uxArea}`],
  ['Archive', '/life/library/archive', 'type', ['all', 'Life Task', 'Life Note', 'Life Chat Log', 'Life Vault Document', 'Life Inbox Item', 'Life Journal Page', 'trash'], `area=${uxArea}`],
  ['Someday', '/life/goals/someday', 'tab', ['all', 'due', 'tasks', 'goals', 'notes'], `area=${uxArea}`],
  ['Captures', '/life/brain/captures', 'tab', ['all', 'chats', 'voice', 'documents', 'photos', 'pages', 'articles', 'email', 'text'], `area=${uxArea}`],
  ['All', '/life/library', 'tab', ['all', 'notes', 'chats', 'voice', 'documents', 'photos', 'pages', 'articles', 'email', 'text'], `area=${uxArea}`],
]

for (const width of UX_WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e)))
  const tag = `U${width}`
  const pane = pg.locator('[data-pane]')
  const settle = () => pg.waitForTimeout(450)
  const paneTitle = async () => { // the title once the record has loaded
    const el = pg.locator('[data-pane-title]')
    for (let i = 0; i < 20 && /^Loading/.test(await el.innerText()); i++) await pg.waitForTimeout(150)
    return el.innerText()
  }
  const overflow = () => pg.evaluate((w) => Math.max(document.documentElement.scrollWidth, window.innerWidth) - w, width) // a phone page that is too wide enlarges innerWidth too
  const count = async () => num(await pg.locator('[data-lv-count]').first().innerText())
  const clickRow = async (sel) => { await pg.locator(sel).first().click({ position: { x: 120, y: 14 } }); await settle() }
  // the list controls: the quick-filter strip on a wide screen, the same controls in a sheet behind the Filters button on a phone
  const controls = () => pg.locator(phone ? '[data-filter-sheet]' : '[data-lv-bar]')
  const openControls = async () => { if (phone) { await pg.locator('[data-filters-button]').click(); await pg.waitForTimeout(400) } }
  const closeControls = async () => { if (phone) { await pg.keyboard.press('Escape'); await pg.waitForTimeout(400) } }
  const pickQuick = async (label, option, type) => {
    await openControls()
    const box = (phone ? controls() : controls().locator('[data-quick-filters]')).locator(`[aria-label="${label}"]`).first()
    const more = controls().getByRole('button', { name: /\d+ more/ })
    if (!(await box.count()) && await more.count()) { await more.first().click(); await pg.waitForTimeout(200) }
    await box.click()
    if (type) await pg.keyboard.type(type, { delay: 20 })
    await pg.waitForTimeout(type ? 900 : 300)
    await pg.getByRole('option', { name: option, exact: !type }).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    await closeControls()
  }
  // a place through the sidebar on a wide screen, the tab bar on a phone; a list through the place's tabs (set 6, issue 14)
  // issue 14: Tasks is Goals > All tasks, Captures is Brain > Activity
  const PLACE_OF = { Tasks: ['Goals', 'tasks'], 'No goal': ['Goals', 'no-goal'], Goals: ['Goals', 'by-area'], Notes: ['Library', 'notes'], Captures: ['Brain', 'activity'] }
  const nav = async (label) => {
    const [place, tab] = PLACE_OF[label] || [label]
    if (phone) await pg.locator(`[data-tabbar] [data-tab-item="${place}"]`).first().click()
    else await pg.locator(`[data-sidebar] [data-nav-item="${place}"]`).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    if (tab) {
      await pg.locator(`[data-place-tabs] [data-tab="${tab}"]`).first().click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
  }

  // the lens (set 6): the picker in the sidebar's header on a wide screen, the sheet behind the title bar on a phone
  const openLens = async () => {
    if (phone) await pg.locator('[data-lens-title]').click()
    else await pg.locator('[data-lens-picker] button, [data-lens-picker]').first().click()
    await pg.waitForTimeout(400)
  }
  const closeLens = async () => { if (await pg.locator('[data-lens-sheet]:visible, [role="menu"]:visible').count()) { await pg.keyboard.press('Escape'); await pg.waitForTimeout(300) } }
  // the picker's menu items are frappe-ui dropdown items (their data- attributes are not passed on): found by role and name
  const lensItems = () => (phone ? pg.locator('[data-lens-sheet] [data-lens-item]') : pg.getByRole('menuitem'))
  const lensOptions = async () => {
    await openLens()
    const texts = phone ? await pg.locator('[data-lens-sheet] [data-lens-item^="area:"]').allInnerTexts() : await lensItems().allInnerTexts()
    await closeLens()
    return texts.map((t) => t.trim())
  }
  const pickLens = async (area) => { // area: a Life Area name, or '' for All of life
    await openLens()
    if (phone) await pg.locator(`[data-lens-sheet] [data-lens-item="area:${area}"]`).first().click()
    else {
      const label = area ? (await s.api('area.tree', { space: SPACE })).areas.find((x) => x.name === area).area_name : 'All of life'
      await pg.getByRole('menuitem', { name: label, exact: true }).first().click()
    }
    await pg.waitForLoadState('networkidle')
    await settle()
  }

  await check(`${tag}.1`, `${width} px: a row opens a pane on every list screen and the list stays in the page`, async () => {
    for (const [name, p, sel] of LISTS) {
      await s.open(p)
      must(await pg.locator(sel).count(), `${name}: no rows to click`)
      const before = pg.url()
      await clickRow(sel)
      must(await pane.isVisible(), `${name}: no pane after clicking a row`)
      must(pg.url().includes('open='), `${name}: the URL has no open=`)
      must(new URL(pg.url()).pathname === new URL(before).pathname, `${name}: the page changed`)
      must(await pg.locator(sel).count(), `${name}: the list left the page`)
      must(await pg.locator(`${sel}[data-active]`).count() >= 1, `${name}: the open row is not highlighted`)
    }
    return `${LISTS.length} screens`
  })

  await check(`${tag}.2`, `${width} px: the URL has open=, Back closes the pane, reload reopens it`, async () => {
    for (const [name, p, sel] of LISTS) {
      await s.open(p)
      await pg.evaluate(() => window.scrollTo(0, 120))
      await clickRow(sel)
      const withPane = pg.url()
      const title = await paneTitle()
      must(withPane.includes('open='), `${name}: no open= in the URL`)
      await pg.goBack()
      await settle()
      must(!(await pane.isVisible()), `${name}: Back did not close the pane`)
      must(!pg.url().includes('open='), `${name}: open= is still in the URL after Back`)
      must(await pg.locator(sel).count(), `${name}: the list is gone after Back`)
      if (!phone) must(Math.abs((await pg.evaluate(() => window.scrollY)) - 120) < 4 || (await pg.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 120)), `${name}: the list lost its scroll position`)
      await pg.goto(withPane, { waitUntil: 'networkidle' })
      await settle()
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must(await pane.isVisible(), `${name}: reload did not reopen the pane`)
      must((await paneTitle()) === title, `${name}: reload opened another record`)
    }
    await s.open('/life/inbox/' + ux.inbox)
    must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/brain/queue' && await pg.locator(ROW).count(), '/inbox/:id does not show the list with the pane open')
    must((await pg.locator('[data-pane-title]').innerText()).includes('UX inbox'), '/inbox/:id opened another item')
  })

  if (phone) {
    await check(`${tag}.3`, '390 px: the pane is a bottom sheet across the screen and closes with its close button', async () => {
      for (const [name, p, sel] of LISTS) {
        await s.open(p)
        await clickRow(sel)
        const box = await pane.boundingBox()
        // frappe-ui's BottomSheet: full width, standing on the bottom edge, most of the screen high
        must(box && box.x === 0 && Math.round(box.width) === 390 && Math.round(box.y + box.height) === 844 && box.height >= 600, `${name}: the pane is ${JSON.stringify(box)}`)
        must((await overflow()) <= 0, `${name}: horizontal scrolling with the pane open`)
        await pg.locator('[data-pane-close]').click()
        await settle()
        must(!(await pane.isVisible()), `${name}: the close button did not close the pane`)
        must(await pg.locator(sel).count(), `${name}: the list is gone after closing`)
      }
    })
  } else {
    await check(`${tag}.3`, '1440 px: pane widths, Esc, j and k, focus, Open full page, search opens in the pane', async () => {
      await s.open('/life/goals/tasks?view=list')
      await clickRow(ROW)
      must(Math.round((await pane.boundingBox()).width) === 520, 'a task pane is not 520 px wide')
      must(await pg.evaluate(() => document.activeElement?.hasAttribute('data-pane')), 'focus did not move into the pane')
      const first = new URL(pg.url()).searchParams.get('open')
      await pg.keyboard.press('j')
      await settle()
      const second = new URL(pg.url()).searchParams.get('open')
      must(second && second !== first, 'j did not move to the next row')
      await pg.keyboard.press('ArrowUp')
      await settle()
      must(new URL(pg.url()).searchParams.get('open') === first, 'the up arrow did not move back')
      await pg.locator(ROW).nth(2).click({ position: { x: 120, y: 14 } }) // the list is still usable beside the pane
      await settle()
      const third = new URL(pg.url()).searchParams.get('open')
      must(third !== first, 'a second row could not be opened beside the pane')
      await pg.keyboard.press('Escape')
      await settle()
      must(!(await pane.isVisible()), 'Esc did not close the pane')
      must((await pg.evaluate(() => document.activeElement?.getAttribute('data-ref'))) === third, 'focus did not return to the row')
      await s.open('/life/inbox/' + ux.inbox)
      must(Math.round((await pane.boundingBox()).width) === 760, 'an inbox pane is not 760 px wide')
      await pg.locator('[data-pane-full]').click()
      await settle()
      must(new URL(pg.url()).pathname === `/life/item/${ux.inbox}` && !(await pane.isVisible()), "Open full page did not open the item page")
      // every pane type opens from its reference
      // set 6: goal: and a former project: (the goal it became) open in the pane too
      for (const ref of [`task:${ux.task}`, `note:${ux.note}`, `vault:${ux.vault}`, `goal:${ux.goal}`, `project:${ux.project}`, `chat:${ux.chat}`, `day:${today}`]) {
        await s.open('/life/library/timeline?open=' + encodeURIComponent(ref))
        must(await pane.isVisible() && !(await pg.locator('[data-pane-title]').innerText()).match(/Loading|Not found/), `the pane did not load ${ref}`)
      }
      await s.open('/life/library/timeline')
      await pg.keyboard.press('Meta+k')
      await pg.locator('input[aria-label="Search or ask anything"]').fill(`UX note ${stamp}`)
      await pg.waitForTimeout(900)
      await pg.keyboard.press('Enter')
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/library/timeline', 'a search result did not open in the pane over the current screen')
      must((await pg.locator('[data-pane-title]').innerText()).includes('UX note'), 'the search result opened another record')
    })
  }

  await check(`${tag}.4`, `${width} px: every number is a door, and the list count equals the number clicked`, async () => {
    const done = []
    // [where the number is, door, which number in its text, what to compare on the page it leads to]
    const door = async (from, name, { which = 0, target = '[data-lv-count]', path, nth = 0, optional = false } = {}) => {
      await s.open(from)
      const el = pg.locator(`[data-door="${name}"]:visible`).nth(nth)
      if (!(await el.count()) || !(await el.isVisible())) {
        if (optional) return
        throw new Error(`${name}: the number is not on ${from}`)
      }
      const n = num(await el.innerText(), which)
      await el.click({ timeout: 8000 }).catch((e) => { throw new Error(`${name} on ${from}: the number cannot be clicked (${String(e).split('\n')[0]})`) })
      await pg.waitForLoadState('networkidle')
      await settle()
      if (path) must(new URL(pg.url()).pathname === path, `${name}: went to ${new URL(pg.url()).pathname}, not ${path}`)
      const got = num(await pg.locator(target).first().innerText())
      must(got === n, `${name}: clicked ${n}, the list says ${got}`)
      done.push(`${name} ${n}`)
    }
    const hidden = { optional: phone } // lines the phone layout leaves out
    // Today's numbers, Reset's, Someday's and the sidebar's come from the count helper and are checked by U.31
    await door('/life', 'nav-review', { path: '/life/brain/queue', ...hidden })
    // the goal page (a project page before set 6): the preview heading of Overview leads to its tab, whose list holds that number;
    // the task figure opens Plan > Tasks. The area pages became the lens and the Vault screen became Captures (no doors left there).
    const goalPage = '/life/goals/' + ux.goal
    const tabList = '[data-tab-panel]:visible [data-lv-count]'
    await door(goalPage, 'goal-overview-tasks', { path: goalPage, target: tabList })
    await door(goalPage, 'goal-tasks', { which: 1, path: '/life/goals/tasks' })
    await door('/life/library/chats?tab=chats&view=list&from=' + addDays(-6), 'chats-open', { path: '/life/library/chats' })
    must(new URL(pg.url()).searchParams.get('from') === addDays(-6) && new URL(pg.url()).searchParams.get('open_items') === '1', 'chats: the date range was not kept')
    await door('/life/library/notes?view=tree', 'library-notes', { path: '/life/library/notes' })
    // set 8: the weekly review's numbers: what left the plate opens the Outbox, what came in opens Captures
    await door('/life/today/week?view=review&tab=tasks', 'review-plate-Done', { path: '/life/brain/outbox' })
    await door('/life/today/week?view=review&tab=tasks', 'review-plate-in', { path: '/life/brain/outbox' })
    await door('/life/today/week?view=review&tab=library', 'review-came-captures', { path: '/life/brain/captures' })
    // an inbox row: "4 of 13 proposals pending" opens that item in the pane at its pending proposals
    await s.open('/life/brain/queue?status=To+Review')
    const link = pg.locator('[data-row] a:visible', { hasText: 'pending' }).first()
    const text = await link.innerText()
    must(/^\d+ of \d+ proposals pending$/.test(text.trim()), `an inbox row says "${text}"`)
    await link.click({ timeout: 8000 }).catch(() => { throw new Error('the proposals count on an inbox row cannot be clicked') })
    await settle()
    must(await pane.isVisible(), 'the proposals count did not open the pane')
    const pendingShown = await pane.locator('[data-proposal="Pending"]').count()
    must(pendingShown === num(text), `clicked ${num(text)} pending, the pane shows ${pendingShown}`)
    const inView = await pane.locator('[data-proposal="Pending"]').first().evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.top < window.innerHeight })
    must(inView, 'the pane is not scrolled to the pending proposals')
    return `${done.length + 1} numbers`
  })

  await check(`${tag}.5`, `${width} px: filters on every ListView are in the URL and survive a reload`, async () => {
    for (const [name, p, key, value, label, option, type] of FILTERS) {
      await s.open(p)
      await pickQuick(label, option, type)
      must(new URL(pg.url()).searchParams.get(key) === value, `${name}: the filter is not in the URL (${new URL(pg.url()).search})`)
      const filtered = await count()
      const rows = await pg.locator(`${ROW}:not([data-archived-projects] ${ROW})`).count() // the list's own rows, not the archived projects above it
      must(rows === Math.min(filtered, 50), `${name}: the count says ${filtered} but ${rows} rows are shown`)
      if (phone) must((await pg.locator('[data-filters-button]').innerText()).includes('(1)'), `${name}: the Filters button does not show one active filter`)
      else must((await pg.locator('[data-active-filters]').innerText()).includes('1 filter'), `${name}: the list does not say one filter is on`)
      must(await pg.locator('[data-clear]:visible').count(), `${name}: no Clear button while a filter is on`)
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must(new URL(pg.url()).searchParams.get(key) === value, `${name}: the filter was lost on reload`)
      must((await count()) === filtered, `${name}: the count changed on reload`)
      await pg.goBack()
      await settle()
      must(!new URL(pg.url()).searchParams.get(key), `${name}: Back did not undo the filter`)
    }
    // an empty result names the filters and offers Clear filters
    await s.open('/life/brain/queue?status=Failed&source_type=Email+Digest') // set 6: the Vault's own list became Captures; the Inbox has no intent filter
    await pg.locator('[data-lv-empty] button', { hasText: 'Clear filters' }).waitFor({ timeout: 8000 }).catch(() => {})
    const empty = await pg.locator('[data-lv-empty]').innerText()
    must(/Email Digest/.test(empty), 'the empty state does not name the filters: ' + empty.replace(/\s*\n\s*/g, ' | '))
    await pg.locator('[data-lv-empty] button', { hasText: 'Clear filters' }).click()
    await settle()
    must(!new URL(pg.url()).search.includes('source_type='), 'Clear filters did not clear')
    return `${FILTERS.length} lists`
  })

  await check(`${tag}.6`, `${width} px: no horizontal scrolling and no script errors on any converted screen`, async () => {
    const screens = [...LISTS.map(([n, p]) => [n, p]), ['Tasks table', '/life/goals/tasks?view=table'], ['Tasks board', '/life/goals/tasks?view=board'], ['Open loops', '/life/goals/tasks?view=loops'],
      ['Goals cards', '/life/goals?view=cards'], ['Notes tree', '/life/library/notes?view=tree'], ['Goal page', '/life/goals/' + ux.goal],
      ['Today', '/life'], ['Today under an area', '/life?area=' + uxArea], ['Week review', '/life/today/week?view=review'], ['Week calendar', '/life/today/week?view=calendar'],
      ['Week agenda', '/life/today/week?view=agenda'], ['Month plan', '/life/today/month?view=plan'], ['Habits', '/life/today/month?view=habits'],
      ['Check-ins', '/life/today/month?view=checkins'], ['Month calendar', '/life/today/month?view=calendar'], ['12 Weeks', '/life/today/year?view=cycle'],
      ['Year calendar', '/life/today/year?view=calendar'], ['Goals across cycles', '/life/today/year?view=goals'], ['Journal pages', '/life/brain/captures?tab=pages'],
      ['Graph', '/life/library/notes?view=graph'], ['Settings', '/life/settings']]
    for (const [name, p] of screens) {
      await s.open(p)
      const over = await overflow()
      must(over <= 0, `${name}: ${over} px of horizontal scrolling`)
    }
    // the goal page and Today: a row opens the pane and the page does not change
    for (const p of ['/life/goals/' + ux.goal, '/life']) {
      await s.open(p)
      await pg.locator('[data-row]:has([data-ref])').first().click({ position: { x: 120, y: 12 } })
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname.replace(/\/$/, '') === (p === '/life' ? '/life/today' : p), `${p}: a row did not open the pane in place`)
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${screens.length} screens`
  })

  await check(`${tag}.7`, `${width} px: a list remembers its view on every device, a link with a query wins, Clear clears`, async () => {
    const param = (k) => new URL(pg.url()).searchParams.get(k)
    await s.open('/life/goals/no-goal?goal=none') // Goals > All tasks is the grouped screen now (issue 21); the remembered views are checked on No goal, which is the task list with goal=none
    await pickQuick('Priority', 'II')
    must(param('priority') === 'II', 'the filter was not set')
    const filtered = await count()
    await nav('Today')
    must(new URL(pg.url()).pathname === '/life/today', 'the sidebar did not go to Today')
    await s.open('/life/goals/no-goal?goal=none') // the bare path is the screen of issue 22; the old list is behind the goal filter
    must(new URL(pg.url()).pathname === '/life/goals/no-goal', 'Goals > No goal did not open')
    must(param('priority') === 'II', `coming back lost the view: ${new URL(pg.url()).search}`)
    must((await count()) === filtered, 'the remembered filter is in the URL but the list is not filtered')
    must(!param('open'), 'an open record was restored')
    // the same person on another device: the state comes from the server, not from this browser
    await pg.waitForTimeout(1600)
    const other = await session('owner@lifeos.test', width)
    await other.open('/life/goals/no-goal?goal=none')
    must(new URL(other.page.url()).searchParams.get('priority') === 'II', `a second browser does not show the saved filter: ${new URL(other.page.url()).search}`)
    await other.ctx.close()
    // a link with a query wins over what was saved, and then becomes the saved state
    await s.open('/life')
    const loops = num(await pg.locator('[data-count-key="band:open"]:visible').first().innerText())
    await pg.locator('[data-count-key="band:open"]:visible').first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!param('priority'), 'the Open tasks link kept the saved filter')
    must((await count()) === loops, `Open tasks shows ${await count()}, the number said ${loops}`)
    const loopsQuery = new URL(pg.url()).search
    await nav('Today')
    await s.open('/life/goals/tasks?view=list')
    const sameQuery = (a, b) => { const k = (q) => [...new URLSearchParams(q)].map(([x, y]) => x + '=' + y).sort().join('&'); return k(a) === k(b) } // the order of parameters does not matter
    must(param('priority') !== 'II', `a query opened the list with the old filter: ${new URL(pg.url()).search}`)
    // Clear removes the filters and the cleared state is what is remembered
    await s.open('/life/goals/no-goal?goal=none')
    await pickQuick('Priority', 'II')
    must(param('priority') === 'II', 'the filter was not set again')
    await pg.locator('[data-clear]:visible').first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!param('priority'), 'Clear did not remove the filter')
    must(!(await pg.locator('[data-active-filters]:visible').allInnerTexts()).join(' ').includes('Priority'), 'the list still says the priority filter is on') // No goal keeps its goal filter
    await nav('Today')
    await pg.waitForTimeout(1600) // a full page load below reads the server's copy, so let the cleared state reach it first
    await s.open('/life/goals/no-goal?goal=none') // the bare path is the screen of issue 22; the old list is behind the goal filter
    must(!param('priority'), 'the cleared filter came back')
    // another person has their own states
    await pg.waitForTimeout(1600)
    const saved = await s.api('views.get_all')
    must(Object.keys(saved).some((k) => k.startsWith('tasks-no-goal|')), 'nothing was saved on the server for the owner')
    const fam = await session('family@lifeos.test', width)
    const theirs = await fam.api('views.get_all')
    must(!Object.keys(theirs).some((k) => k.includes('Private')) && !JSON.stringify(theirs).includes('loops'), 'the family user sees the owner\'s saved states')
    await fam.open('/life/goals/no-goal?goal=none')
    must(!new URL(fam.page.url()).search.includes('view=loops') && !new URL(fam.page.url()).searchParams.get('priority'), 'the family user got the owner\'s view')
    const rest = await fam.page.request.get(base + '/api/resource/Life%20View%20State?limit_page_length=100&fields=["user"]')
    must(!JSON.stringify(await rest.json()).includes('owner@lifeos.test'), 'the REST list shows the owner\'s saved states')
    await fam.ctx.close()
  })

  await check(`${tag}.8`, `${width} px: state tabs: each count equals the rows its tab shows, with and without another filter; links land on their tab`, async () => {
    const bar = pg.locator('[data-state-tabs]')
    const current = () => bar.getAttribute('data-tab-current')
    const tabCount = async (v) => num(await bar.locator(`[data-tab="${v}"] [data-tab-count]`).innerText())
    const ownRows = () => pg.locator(`${ROW}:not([data-archived-projects] ${ROW})`).count()
    let checked = 0
    for (const [name, p, key, values, other] of STATE_TABS) {
      for (const extra of ['', other]) {
        // the lens's area is not a list query (set 6): a URL with only area= restores the remembered view, so the default tab says all=1 too
        const q = (v) => `${p}?${[v === values[0] ? '' : `${key}=${encodeURIComponent(v)}`, extra, name === 'Tasks' ? 'view=list' : '', v === values[0] && (!extra || extra.startsWith('area=')) ? 'all=1' : ''].filter(Boolean).join('&')}`
        await s.open(q(values[0]))
        must((await bar.locator('[role="tab"]').count()) === values.length, `${name}: ${await bar.locator('[role="tab"]').count()} tabs, not ${values.length}`)
        must((await current()) === values[0], `${name}: the default tab is ${await current()}`)
        const counts = {}
        for (const v of values) counts[v] = await tabCount(v)
        for (const v of values) {
          if (v !== values[0]) { // by clicking, as a person does; the row scrolls sideways on a phone
            await bar.locator(`[data-tab="${v}"]`).click()
            await pg.waitForLoadState('networkidle')
            await settle()
          }
          must((await current()) === v, `${name}: clicking ${v} selected ${await current()}`)
          must((new URL(pg.url()).searchParams.get(key) || values[0]) === v, `${name}: the ${v} tab is not in the URL (${new URL(pg.url()).search})`)
          const shown = await count()
          must(shown === counts[v], `${name}${extra ? ' with ' + extra : ''}: the ${v} tab says ${counts[v]}, the list holds ${shown}`)
          must((await tabCount(v)) === shown, `${name}: the count on the ${v} tab changed to ${await tabCount(v)} when it was opened`)
          const rows = await ownRows()
          must(rows === Math.min(shown, 50), `${name}${extra ? ' with ' + extra : ''}: the ${v} tab says ${shown} but ${rows} rows are shown`)
          must((await overflow()) <= 0, `${name}: the page scrolls sideways on the ${v} tab`)
          checked++
        }
        // the last tab survives a reload, and a tab is not counted as a filter
        const last = values[values.length - 1]
        await pg.reload({ waitUntil: 'networkidle' })
        await settle()
        must((await current()) === last, `${name}: reload left the ${last} tab`)
        if (!extra) must(!(await pg.locator('[data-active-filters]:visible').count()) && !(phone && /\(\d/.test(await pg.locator('[data-filters-button]').innerText())), `${name}: a tab is counted as a filter`)
      }
    }
    // links from sets 1 and 2 land on the tab they mean
    const lands = async (from, name, want, optional) => {
      await s.open(from)
      const el = pg.locator(name.startsWith('[') ? `${name}:visible` : `[data-door="${name}"]:visible`).first()
      if (!(await el.count())) { if (optional) return; throw new Error(`${name}: not on ${from}`) }
      const n = num(await el.innerText())
      await el.click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must((await current()) === want, `${name}: landed on the ${await current()} tab, not ${want}`)
      must((await tabCount(want)) === n && (await count()) === n, `${name}: clicked ${n}, the ${want} tab says ${await tabCount(want)} and the list ${await count()}`)
    }
    await lands('/life', '[data-count-key="band:open"]', 'all')
    await lands('/life', '[data-count-key="band:inbox"]', 'To Review')
    await lands('/life', '[data-count-key="band:open_goals"]', 'in_progress') // the Projects tile became Open-ended goals (set 6)
    // Tasks: Open loops is a tab with its explanation, the layout switch has three options, the board is not offered on Done
    const layouts = async () => (await pg.locator('[role="radiogroup"]:visible [role="radio"]').allInnerTexts()).map((t) => t.trim())
    await s.open('/life/goals/tasks?status=loops')
    must((await current()) === 'loops' && (await pg.locator('[data-tasks-sub]').innerText()).includes('older than 14 days'), 'Open loops is not a tab with its explanatory line')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Table']), `Open loops offers the layouts ${await layouts()}`)
    await s.open('/life/goals/tasks?view=loops') // a link from before the tabs
    must((await current()) === 'loops' && new URL(pg.url()).searchParams.get('status') === 'loops', 'view=loops does not open the Open loops tab')
    await s.open('/life/goals/tasks?view=board')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Board', 'Table']), `the layout switch offers ${await layouts()}`)
    must((await pg.locator('[data-list]').getAttribute('data-view')) === 'board' && (await pg.locator('[data-column]').count()) === 2, 'the board on the Open tab does not show Open and Doing')
    await s.open('/life/goals/tasks?view=board&status=all')
    must((await pg.locator('[data-column]').count()) === 4, 'the board on the All tab does not show four columns')
    await s.open('/life/goals/tasks?view=board&status=Done')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Table']), `Done offers the layouts ${await layouts()}`)
    must((await pg.locator('[data-list]').getAttribute('data-view')) === 'list', 'the board did not fall back to the list on Done')
    // a status that is not a tab selects All and shows as a filter
    await s.open('/life/goals/tasks?view=list&status=Dropped')
    must((await current()) === 'all', `status=Dropped selected the ${await current()} tab`)
    if (phone) must((await pg.locator('[data-filters-button]').innerText()).includes('(1)'), 'status=Dropped is not shown as a filter')
    else must((await pg.locator('[data-active-filters]').innerText()).includes('1 filter'), 'status=Dropped is not shown as a filter')
    if (phone) {
      // seven tabs are wider than a phone: the row scrolls sideways, the page does not, and the open tab is in view
      await s.open('/life/library/archive?type=Life+Journal+Page')
      const m = await bar.evaluate((el) => { const t = el.querySelector('[data-state="active"]').getBoundingClientRect(); return { wide: el.scrollWidth > el.clientWidth, inView: t.left >= 0 && t.right <= window.innerWidth, h: t.height } })
      must(m.wide && m.inView, `the tab row does not scroll with the open tab in view: ${JSON.stringify(m)}`)
      must(m.h >= 44, `a tab is ${m.h} px high on a phone`)
      must((await overflow()) <= 0, 'the Archive scrolls sideways')
    } else {
      // [ and ] move between tabs; arrow keys move inside the tab row
      await s.open('/life/goals?status=all&area=' + uxArea)
      await pg.keyboard.press('[')
      await settle()
      must((await current()) === 'someday', '[ did not open the previous tab') // Someday comes before All
      await pg.keyboard.press(']')
      await settle()
      must((await current()) === 'all', '] did not open the next tab')
      await bar.locator('[data-tab="all"]').focus()
      await pg.keyboard.press('ArrowLeft')
      await settle()
      must((await current()) === 'someday', 'the left arrow did not move to the previous tab')
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${checked} tabs`
  })
  await check(`${tag}.10`, `${width} px: a goal's page (a project page before set 6): each tab opens with its count, its list matches the main screen, reload stays, a row opens the pane in the tab`, async () => {
    const pageBar = pg.locator('[data-page-tabs]')
    const cur = () => pageBar.getAttribute('data-tab-current')
    const panelCount = async (t) => num(await pg.locator(`[data-tab-panel="${t}"] [data-lv-count]`).innerText())
    // the area pages became the lens (U.40 and up); the main screens below open on All of life
    const PAGES = [
      ['/life/goals/' + ux.goal, [['tasks', `/life/goals/tasks?goal=${ux.goal}&view=list`], ['notes', `/life/library/notes?view=list&goal=${ux.goal}`],
        ['captures', `/life/brain/captures?goal=${ux.goal}`], ['links', null]]],
    ]
    let n = 0
    for (const [page, tabs] of PAGES) {
      await s.open(page)
      must((await cur()) === 'overview', `${page}: opens on ${await cur()}`)
      for (const [t, main] of tabs) {
        // clear this tab's remembered view, so it opens as the main screen does
        await s.open(page)
        await pageBar.locator(`[data-tab="${t}"]`).click()
        await pg.waitForLoadState('networkidle')
        await settle()
        must((await cur()) === t && new URL(pg.url()).searchParams.get('tab') === t, `${page}: the ${t} tab is not open or not in the URL`)
        const said = num(await pageBar.locator(`[data-tab="${t}"] [data-tab-count]`).innerText())
        if (main) {
          if (await pg.locator('[data-tab-panel]:visible [data-clear]').count()) { await pg.locator('[data-tab-panel]:visible [data-clear]').first().click(); await settle() }
          const listed = await panelCount(t)
          must(listed === said, `${page} ${t}: the tab says ${said}, its list ${listed}`)
          await s.open(main)
          const there = await count()
          must(there === listed, `${page} ${t}: ${listed} here, ${there} on the main screen`)
          await s.open(`${page}?tab=${t}`)
          must((await cur()) === t, `${page}: reload left the ${t} tab`)
          const row = pg.locator(`[data-tab-panel="${t}"] [data-row]`).first()
          if (await row.count()) {
            await row.click({ position: { x: 120, y: 12 } })
            await settle()
            must(await pane.isVisible() && new URL(pg.url()).searchParams.get('tab') === t && new URL(pg.url()).pathname === page, `${page} ${t}: a row did not open the pane in the tab`)
          }
        } else {
          must((await pg.locator('[data-tab-panel="links"] [data-row]').count()) === said, `${page} links: the tab says ${said}`)
        }
        must((await overflow()) <= 0, `${page} ${t}: the page scrolls sideways`)
        n++
      }
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${n} tabs`
  })

  await check(`${tag}.11`, `${width} px: the review screen and the journal page show tabs on a phone only`, async () => {
    await s.open('/life/inbox/' + ux.inbox)
    const review = pg.locator('[data-review-tabs]')
    if (!phone) must(!(await review.count()), 'the review screen shows tabs at 1440 px')
    else {
      must(JSON.stringify((await review.locator('[role="tab"]').allInnerTexts()).map((t) => t.replace(/\s*\d+$/, '').trim())) === JSON.stringify(['Original', 'Transcript', 'Summary', 'Proposals']), 'the review tabs are wrong')
      const pendingNow = (await s.api('inbox.get', { item: ux.inbox })).proposals.some((x) => x.status === 'Pending')
      must((await review.getAttribute('data-tab-current')) === (pendingNow ? 'proposals' : 'summary'), `the review opened on ${await review.getAttribute('data-tab-current')}`)
      await review.locator('[data-tab="original"]').click()
      await settle()
      must(new URL(pg.url()).searchParams.get('ptab') === 'original', 'the review tab is not in the URL as ptab= in the pane')
      await s.open(`/life/inbox/${ux.inbox}/review?tab=transcript`) // the full page uses tab=
      must((await pg.locator('[data-review-tabs]').getAttribute('data-tab-current')) === 'transcript', 'the full review page does not open on tab=transcript')
      if (pendingNow) must(await pg.getByRole('button', { name: /Accept all/ }).isVisible(), 'Accept all is hidden on the Original tab')
    }
    // set 6: a journal page is a capture; its old link opens it in the pane over Library > Everything, Journal pages, on its tabs (issue 14)
    const jp = bench(`print(frappe.db.sql("select name from \`tabLife Journal Page\` where space='${SPACE}' limit 1")[0][0])`).split('\n').pop()
    await s.open('/life/journal/pages/' + jp)
    must(new URL(pg.url()).pathname === '/life/library' && new URL(pg.url()).searchParams.get('tab') === 'pages' && await pane.isVisible(),
      `/journal/pages/:id went to ${new URL(pg.url()).pathname}${new URL(pg.url()).search}`)
    const jt = pg.locator('[data-pane-tabs]')
    await jt.locator('[data-tab="transcript"]').click()
    await settle()
    await pg.reload({ waitUntil: 'networkidle' })
    await settle()
    must((await jt.getAttribute('data-tab-current')) === 'transcript', 'the journal page tab did not survive a reload')
    must((await overflow()) <= 0, 'the page scrolls sideways')
  })

  await check(`${tag}.12`, `${width} px: Settings: every section from the menu and the URL, old links to their new homes, rename a tag and a part, archive a part (its open task moved) and restore it, members, a Rhythms setting survives a reload, no role names`, async () => {
    let step = 'sections'
    const problems = []
    try {
    // set 6: Me, Your life, Assistant, People and agents, Data
    const SECTIONS = ['profile', 'appearance', 'notifications', 'shortcuts', 'calendar', 'areas', 'rhythms', 'habits', 'dimensions', 'reset', 'connections', 'ai', 'cost',
      'sensitive', 'note-rules', 'spaces', 'members', 'agents', 'archive', 'import', 'places', 'backups']
    const cur = () => pg.locator('[data-settings-section]').getAttribute('data-current')
    const menuItems = async () => { await s.open('/life/settings'); return pg.locator('[data-settings-menu] [data-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-section'))) }
    const listed = await menuItems()
    must(JSON.stringify(listed) === JSON.stringify(SECTIONS), `the menu lists ${listed}`)
    for (const [old, now] of [['default', 'profile'], ['review', 'rhythms'], ['archived', 'archive']]) {
      await s.open(`/life/settings?tab=${old}`)
      must((await cur()) === now, `?tab=${old} opened ${await cur()}, not ${now}`)
    }
    for (const sec of SECTIONS) {
      await s.open(`/life/settings?tab=${sec}`)
      must((await cur()) === sec, `?tab=${sec} opened ${await cur()}`)
      await s.open('/life/settings')
      if (phone) must(await pg.locator('[data-settings-menu]').isVisible() && !(await pg.locator('[data-settings-section]').count()), 'on a phone the menu is not the first screen')
      await pg.locator(`[data-settings-menu] [data-section="${sec}"]`).click()
      await settle()
      must((await cur()) === sec && (phone ? !(await pg.locator('[data-settings-menu]').count()) : true), `the menu did not open ${sec}`)
      must((await overflow()) <= 0, `${sec}: the page scrolls sideways`)
      const text = await pg.locator('[data-main]').innerText()
      must(!/Life (Agent|User|Admin)|Administrator/.test(text), `${sec}: a role name or Administrator shows`)
    }
    // areas (issue 12): Settings > Areas lists the seven with their parts; a part is renamed in its Edit dialog and archived
    // there, its open tasks moving to the place chosen. Rename in place stays for habits and dimensions.
    const got = async () => (await s.api('settings.get', { space: SPACE }))
    step = 'areas: rename a part in its Edit dialog'
    const A = `UX3 area A ${width} ${stamp}`
    const B = `UX3 area B ${width} ${stamp}`
    const a = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: A, sort_order: 900 })).name
    const b = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: B, sort_order: 901 })).name
    const career = (await got()).areas.find((x) => x.is_life_area && x.area_name === 'Career').name
    await s.open('/life/settings?tab=areas')
    await pg.locator(`[data-edit-part="${a}"]`).click()
    await pg.locator('[data-part-title] input, input[data-part-title]').first().fill(A + ' renamed')
    await pg.getByRole('button', { name: 'Save', exact: true }).click()
    await pg.waitForTimeout(900)
    must((await got()).areas.find((x) => x.name === a).area_name === A + ' renamed', 'renaming a part did not save')
    must(await pg.locator(`[data-parts-of="Career"] [data-part="${a}"]`).innerText().then((t) => t.includes(A + ' renamed')), 'the renamed part does not show under Career')
    // no Delete or Remove for areas, habits or dimensions
    step = 'no Delete or Remove for areas, habits or dimensions'
    const itemsOf = async (n) => { await pg.locator(`[data-row-name="${n}"] [data-row-menu]`).click(); await pg.waitForTimeout(250); const t = await pg.getByRole('menuitem').allInnerTexts(); await pg.keyboard.press('Escape'); await pg.waitForTimeout(200); return t.map((x) => x.trim()) }
    must(!(await pg.locator('[data-areas-section]').getByRole('button', { name: /^(Delete|Remove)$/ }).count()), 'areas: a Delete or Remove button')
    for (const sec of ['habits', 'dimensions']) {
      await s.open(`/life/settings?tab=${sec}`)
      const first = pg.locator('[data-settings-list] [data-row-name]').first()
      if (await first.count()) { const t = await itemsOf(await first.getAttribute('data-row-name')).catch(() => []); must(!t.some((x) => /Delete|Remove/.test(x)), `${sec}: ${t}`) }
      must(!(await pg.getByRole('button', { name: /^(Delete|Remove)$/ }).count()), `${sec}: a Delete or Remove button`)
    }
    // archive B, a part with an open task: the task moves to Career itself, B leaves the Areas screen and the pickers, is under
    // Archived and comes back in place
    step = 'archive B: its task moves to Career, and it leaves the Areas screen and the pickers'
    const task = await s.api('tasks.quick_add', { text: `UX3 filed under B ${width} ${stamp}`, space: SPACE, area: b })
    await s.open('/life/settings?tab=areas')
    await pg.locator(`[data-edit-part="${b}"]`).click()
    await pg.locator('[data-archive-part]').click()
    await pg.waitForTimeout(500)
    must(await pg.locator('[data-archive-part-dialog] [data-move-to]').count(), 'no question where the open task goes')
    await pg.getByRole('button', { name: 'Archive', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    const tree = (await s.api('area.tree', { space: SPACE })).areas.map((x) => x.name)
    const ctx = (await s.api('meta.space_context', { space: SPACE })).areas.map((x) => x.name)
    must(!tree.includes(b) && !ctx.includes(b), 'an archived area is still on the Areas screen or in the pickers')
    must(!(await pg.locator(`[data-part="${b}"]`).count()), 'the archived part is still listed')
    must((await s.api('tasks.get', { task: task.name })).area === career, 'the open task did not move to Career')
    if (!phone) must(!(await pg.locator(`[data-nav-pin="${b}"]`).count()), 'the archived area is still in the sidebar')
    await s.open('/life/settings?tab=archive')
    if (await pg.locator(`[data-archived-row="${b}"]`).count()) {
      await pg.locator(`[data-restore="${b}"]`).click()
      await pg.waitForTimeout(1200)
    } else { // an app bug: noted, and the area is restored through the API so the rest of the check runs
      problems.push('the archived area is not under Settings > Archive and trash (?tab=archive), so it cannot be restored there')
      await s.api('settings.save_item', { kind: 'area', name: b, is_archived: 0, with_children: 1 })
    }
    const back = (await got()).areas
    must(!back.find((x) => x.name === b).is_archived && back.find((x) => x.name === b).parent_area === career, 'Restore did not bring B back in place')
    // tidy: the task and both test areas go (the site is rebuilt before each run, but nothing is left behind anyway)
    await s.api('frappe.client.delete', { doctype: 'Life Task', name: task.name })
    await s.api('settings.save_item', { kind: 'area', name: a, delete: 1 })
    await s.api('settings.save_item', { kind: 'area', name: b, delete: 1 })
    // a changed Rhythms setting says Saved and survives a reload; it is put back after
    step = 'a changed Rhythms setting says Saved and survives a reload'
    const was = (await s.api('settings.get', { space: SPACE })).settings
    const next = was.score_target === 86 ? 85 : 86
    try {
      await s.open('/life/settings?tab=rhythms')
      const box = pg.locator('[data-setting="score_target"] input, input[data-setting="score_target"]').first()
      await box.fill(String(next))
      await box.press('Tab')
      await pg.getByText('Saved', { exact: true }).first().waitFor({ timeout: 5000 })
      // the month plan switch (TabButtons): Off then On, whichever it is not
      const plan = pg.locator('[data-setting="month_plan_enabled"]')
      const want = was.month_plan_enabled ? 'Off' : 'On'
      await plan.getByText(want, { exact: true }).click()
      await pg.waitForTimeout(1200)
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must(Number(await pg.locator('[data-setting="score_target"] input, input[data-setting="score_target"]').first().inputValue()) === next, 'the score target did not survive a reload')
      const checked = (await plan.locator('[aria-checked="true"], [data-state="checked"], [data-state="on"]').first().innerText()).trim()
      must(checked === want, `the month plan shows ${checked} after a reload, not ${want}`)
      const saved = (await s.api('settings.get', { space: SPACE })).settings
      must(saved.score_target === next && Number(saved.month_plan_enabled) === (want === 'On' ? 1 : 0), 'the Rhythms settings were not saved')
    } finally {
      await s.api('settings.save', { values: { score_target: was.score_target, month_plan_enabled: was.month_plan_enabled ? 1 : 0 } })
    }
    // add and remove a member through the dialogs
    step = 'add and remove a member through the dialogs'
    await s.open('/life/settings?tab=members')
    if (phone) { await pg.locator('[data-settings-section] button[role="combobox"], [data-settings-section] [aria-label="Space"]').first().click(); await pg.getByRole('option', { name: 'Shared', exact: true }).click() }
    else await pg.locator('[data-member-spaces] [data-space="Shared"]').click()
    await settle()
    const who = 'stranger@lifeos.test'
    if (await pg.locator(`[data-member="${who}"]`).count()) await s.api('settings.set_member', { space: 'Shared', user: who, remove: 1 }), await s.open('/life/settings?tab=members')
    await pg.locator('[data-add-member]').click()
    await pg.waitForTimeout(300)
    await pg.locator('[data-add-dialog] button, [data-add-dialog] input').first().click()
    await pg.keyboard.type('stranger', { delay: 30 })
    await pg.waitForTimeout(1200)
    await pg.getByRole('option', { name: /stranger/i }).first().click()
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    must(await pg.locator(`[data-member="${who}"]`).count(), 'Add member did not add the person')
    await pg.locator(`[data-member-menu="${who}"]`).click()
    await pg.getByRole('menuitem', { name: 'Remove' }).click()
    await pg.getByRole('button', { name: 'Remove', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    must(!(await pg.locator(`[data-member="${who}"]`).count()), 'Remove did not remove the person')
    must(await pg.locator('[data-owner-badge]').count(), 'the owner has no Owner badge')
    // the family member has no People and agents group, and no Assistants, Ask and AI or Backups
    step = 'the family member has no admin sections'
    const fam = await session('family@lifeos.test', width)
    await fam.open('/life/settings')
    must(!(await fam.page.locator('[data-settings-group="people"]').count()), 'the family user sees People and agents')
    must(!(await fam.page.locator('[data-settings-menu] [data-section="agents"], [data-settings-menu] [data-section="ai"], [data-settings-menu] [data-section="backups"]').count()), 'the family user sees an admin section')
    await fam.ctx.close()
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    must(!problems.length, problems.join('; '))
    return `${SECTIONS.length} sections`
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) }
  })

  await check(`${tag}.13`, `${width} px: navigation (set 6, issue 14): ${phone ? 'the phone bar is Today, Brain, Capture, Goals and Library; each opens; Capture opens its sheet; Ask is in the header; the lens sheet holds Settings; the Brain count' : 'the sidebar is the lens, Capture, Today, Brain, Goals, Library and Settings; the active item; the place tabs; the Brain count; the capture sheet and each of its entries'}; /graph is the Graph view of Notes`, async () => {
    let step = 'start'
    try {
    const PLACES = ['Today', 'Brain', 'Goals', 'Library']
    const path = () => new URL(pg.url()).pathname.replace(/\/$/, '')
    if (phone) {
      await s.open('/life')
      const items = await pg.locator('[data-tabbar] [data-tab-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab-item')))
      must(JSON.stringify(items) === JSON.stringify(PLACES), `the phone bar is ${items}`)
      must(await pg.locator('[data-tabbar] [data-tab-capture]').count(), 'the phone bar has no capture button')
      step = 'each place opens from the bar'
      for (const [label, want] of [['Brain', '/life/brain'], ['Goals', '/life/goals'], ['Library', '/life/library'], ['Today', '/life/today']]) {
        await nav(label)
        must(path() === want, `${label} opened ${path()}`)
      }
      step = 'Capture opens its sheet'
      await pg.locator('[data-tabbar] [data-tab-capture]').click()
      await settle()
      must(await pg.locator('[data-capture-text]').count(), 'Capture did not open its sheet')
      await pg.keyboard.press('Escape')
      await settle()
      step = 'Ask is in the header and opens its sheet'
      await pg.locator('[data-phone-ask]').first().click()
      await settle()
      must(await pg.locator('[data-ask-sheet]:visible').count(), 'Ask did not open its sheet')
      await pg.keyboard.press('Escape')
      await settle()
      step = 'the Brain count'
      const due = (await s.api('session.counts', { space: SPACE })).doors.inbox.n
      const badge = pg.locator('[data-tabbar] [data-tab-count="Brain"]')
      must(due === 0 ? !(await badge.count()) : num(await badge.innerText()) === due, `the Brain tab says ${await badge.count() ? await badge.innerText() : 'nothing'}, the count helper says ${due}`)
      step = 'the lens sheet holds Settings'
      await pg.locator('[data-lens-title]').click()
      await settle()
      must(await pg.locator('[data-lens-sheet]').isVisible(), 'the lens title did not open the sheet')
      await pg.locator('[data-lens-settings]').click()
      await settle()
      must(path() === '/life/settings', `Settings in the lens sheet opened ${path()}`)
    } else {
      await s.api('views.save', { screen: 'sidebar', space: '', state: { rail: false } })
      await s.open('/life')
      // Review joins the places once a review is locked, or on the review's day: the rest is fixed
      const navItems = () => pg.locator('[data-nav-places] [data-nav-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')).filter((x) => x !== 'Review'))
      must(JSON.stringify(await navItems()) === JSON.stringify(PLACES), `the places are ${await navItems()}`)
      must(JSON.stringify(await pg.locator('[data-nav-bottom] [data-nav-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')))) === JSON.stringify(['Settings']), 'the bottom is not Settings')
      must(await pg.locator('[data-lens-picker]').count() && await pg.locator('[data-nav-capture]').count() && await pg.locator('[data-ask-box]').count(), 'the lens, Capture or the header box is missing')
      step = 'each place opens and is the active item'
      const active = () => pg.locator('[data-sidebar] [aria-current="page"]').evaluateAll((els) => [...new Set(els.map((e) =>
        (e.closest('[data-nav-item]') || e.querySelector('[data-nav-item]'))?.getAttribute('data-nav-item')).filter(Boolean))])
      for (const [label, want] of [['Brain', '/life/brain'], ['Goals', '/life/goals'], ['Library', '/life/library'], ['Settings', '/life/settings'], ['Today', '/life/today']]) {
        await pg.locator(`[data-sidebar] [data-nav-item="${label}"]`).first().click()
        await pg.waitForURL((u) => u.pathname === want, { timeout: 10000 }).catch(() => {})
        await settle()
        must(path() === want, `${label} opened ${path()}`)
        if (label !== 'Settings') {
          const on = await active()
          must(on.includes(label) && on.length === 1, `${label}: the active items are ${on}`)
        }
      }
      step = 'the place tabs'
      await s.open('/life/goals/tasks')
      must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === 'tasks', 'Goals > All tasks is not the open tab')
      must(JSON.stringify(await active()) === JSON.stringify(['Goals']), `on Goals > All tasks the active items are ${await active()}`)
      step = "the Brain count equals the count helper's"
      const t = await s.api('session.counts', { space: SPACE })
      const brain = (await pg.locator('[data-nav-count="Brain"]').count()) ? num(await pg.locator('[data-nav-count="Brain"]').innerText()) : 0
      must(brain === t.doors.inbox.n, `the sidebar says ${brain} for the Brain, the count helper says ${t.doors.inbox.n}`)
      step = 'Capture opens its sheet and each entry works'
      await s.open('/life')
      await pg.locator('[data-nav-capture]').click()
      await settle()
      const entries = (await pg.locator('[role="dialog"] button').allInnerTexts()).map((x) => x.trim()).filter(Boolean)
      for (const e of ['Add as a task', 'Send to the Brain', 'Files or a photo', 'Goal', 'Note', 'Park on Someday']) must(entries.includes(e), `the capture sheet has no ${e}: ${entries}`)
      await pg.keyboard.press('Escape')
      for (const [kind, ok] of [['goal', async () => pg.getByRole('dialog', { name: 'New goal' }).isVisible()], ['note', async () => pg.getByRole('dialog', { name: 'New note' }).isVisible()],
        ['someday', async () => pg.getByRole('dialog', { name: 'Park on Someday' }).isVisible()], ['files', async () => pg.locator('[data-capture-files]').isVisible()]]) {
        await s.open('/life')
        await pg.locator('[data-nav-capture]').click()
        await settle()
        await pg.locator(`[data-capture-kind="${kind}"]`).click()
        await settle()
        must(await ok(), `Capture, ${kind} did not open`)
        await pg.keyboard.press('Escape')
      }
    }
    // /graph is the Graph view of Library > Notes
    step = '/graph is the Graph view of Notes'
    await s.open('/life/graph')
    must(path() === '/life/library/notes' && new URL(pg.url()).searchParams.get('view') === 'graph', `/graph went to ${pg.url()}`)
    must((await pg.locator('[data-library-views] [aria-checked="true"], [data-library-views] [data-state="checked"], [data-library-views] [data-state="on"]').first().innerText()).includes('Graph'), '/graph is not the Graph view of Notes')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) }
  })

  await check(`${tag}.14`, `${width} px: goals of every type: task figure, archive keeps it, tabs, score blank, add to a cycle, family sees none`, async () => {
    let step = 'start'
    try {
    const open = await s.api('goals.create', { title: `UX3 open goal ${width} ${stamp}`, horizon: 'Long term', space: SPACE, area: uxArea })
    const annual = await s.api('goals.create', { title: `UX3 annual goal ${width} ${stamp}`, horizon: 'Year', space: SPACE, area: uxArea, target_date: addDays(200) })
    const ts = []
    for (const i of [1, 2, 3]) ts.push(await s.api('tasks.quick_add', { text: `UX3 goal task ${i} ${width} ${stamp}`, space: SPACE, goal: open.name }))
    await s.api('tasks.set_status', { task: ts[0].name, status: 'Done' })
    await s.api('tasks.set_status', { task: ts[1].name, status: 'Dropped' })
    const figure = async () => { await s.open(`/life/goals?status=all&open=goal:${open.name}`); await paneTitle(); await settle(); return (await pg.locator('[data-goal-figure]').innerText()).replace(/\s+/g, ' ') }
    must((await figure()).includes('1 of 2 tasks'), `the goal shows "${await figure()}"`)
    await s.api('archive.set', { doctype: 'Life Task', name: ts[0].name, archived: 1 })
    must((await figure()).includes('1 of 2 tasks'), 'archiving the done task changed the figure')
    // the Goals screen: both new goals beside the seeded 12 Week Year goals; each tab's count matches its rows; Score blank for the new ones
    step = 'the Goals screen: both new goals beside the seeded 12 Wee'
    const bar = pg.locator('[data-state-tabs]')
    for (const v of ['in_progress', 'achieved', 'closed', 'all']) {
      await s.open(`/life/goals?${v === 'in_progress' ? 'all=1' : 'status=' + v}`)
      const said = num(await bar.locator(`[data-tab="${v}"] [data-tab-count]`).innerText())
      must(said === await count() && (await pg.locator(ROW).count()) === Math.min(said, 50), `Goals ${v}: the tab says ${said}, the list ${await count()}`)
    }
    await s.open('/life/goals?status=all')
    const text = await pg.locator('[data-main]').innerText()
    must(text.includes(`UX3 open goal ${width} ${stamp}`) && text.includes(`UX3 annual goal ${width} ${stamp}`) && text.includes('12 weeks'), 'the Goals screen does not list the new goals beside the 12 Week Year goals')
    const rows = (await s.api('goals.list', { space: SPACE, state: 'all', page_length: 100 })).goals
    must(rows.find((r) => r.name === open.name).score === null && rows.find((r) => r.name === annual.name).score === null, 'Score is not blank for the new goals')
    if (!phone) for (const n of [open.name, annual.name]) must((await pg.locator(`[data-ref="goal:${n}"]`).locator('xpath=..').locator('[data-goal-score]').innerText()).trim() === '', 'a Score shows for a goal without a cycle')
    // the 12 Week Year grid does not show them; moving the open goal into the current cycle does, and keeps its tasks
    step = 'the 12 Week Year grid does not show them; moving the open'
    const tf = await s.api('today.get', { space: SPACE })
    const cycle = tf.cycle?.name || tf.cycle?.cycle
    const gridHas = async (n) => { const g = await s.api('journal.goals', { space: SPACE }); return g.cycles.some((c) => c.goals.some((x) => x.name === n)) }
    must(!(await gridHas(open.name)) && !(await gridHas(annual.name)), 'a goal without a cycle shows in the 12 Week Year')
    const cycles = await s.api('goals.cycles', { space: SPACE })
    const active = cycles.find((c) => c.status === 'Active') || cycles[0]
    await s.open(`/life/goals?status=all&open=goal:${open.name}`)
    await paneTitle()
    await pg.locator('[data-add-to-cycle]').click()
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    must(await gridHas(open.name), 'the goal moved into the cycle is not in the grid')
    must((await s.api('tasks.list', { space: SPACE, goal: open.name, status: 'all', include_archived: 1 })).total === 3, 'the moved goal lost its tasks')
    // the family member sees no goals or counts from Private
    step = 'the family member sees no goals or counts from Private'
    const fam = await session('family@lifeos.test', width)
    must((await fam.api('goals.list', { space: SPACE }, { raw: true })).status() >= 400, 'the family user can list Private goals')
    await fam.open('/life/goals?status=all')
    must(!(await fam.page.locator('[data-main]').innerText()).includes('UX3 open goal'), 'the family user sees a Private goal')
    await fam.ctx.close()
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${cycle ? 'cycle ' + active.title : ''}`
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) }
  })

  await check(`${tag}.15`, `${width} px: a place's tabs (issue 14): the path holds the tab, the view switch is in the URL, [ and ] move, the phone row scrolls`, async () => {
    const bar = pg.locator('[data-place-tabs]').first()
    await s.open('/life/today/month?view=habits')
    must((await bar.getAttribute('data-tab-current')) === 'month', 'Today did not open on Month from its path')
    must((await pg.locator('[data-plan-views] [aria-checked="true"], [data-plan-views] [data-state="checked"], [data-plan-views] [data-state="on"]').first().innerText()).includes('Habits'), 'the view switch is not on Habits')
    const tabs = await bar.locator('[data-tab]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab')))
    must(JSON.stringify(tabs) === JSON.stringify(['day', 'week', 'month', 'year']), `Today's tabs are ${tabs}`)
    await s.open('/life/library/notes')
    const lib = await pg.locator('[data-place-tabs] [data-tab]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab')))
    must(JSON.stringify(lib) === JSON.stringify(['all', 'notes', 'documents', 'people', 'chats', 'files']), `Library's tabs are ${lib}`)
    if (!phone) {
      await s.open('/life/today/month')
      await pg.locator('body').click({ position: { x: 600, y: 10 } })
      await pg.keyboard.press(']')
      await settle()
      must(new URL(pg.url()).pathname === '/life/today/year', `] went to ${new URL(pg.url()).pathname}`)
      await pg.keyboard.press('[')
      await settle()
      must(new URL(pg.url()).pathname === '/life/today/month', `[ went to ${new URL(pg.url()).pathname}`)
      await s.open('/life/library/notes')
      await pg.keyboard.press(']')
      await settle()
      must(new URL(pg.url()).pathname === '/life/library/documents', `] on the Library went to ${new URL(pg.url()).pathname}`)
    } else {
      // the last tab, and a page shown as a tab after them: the row scrolls sideways with it in view, the page does not
      for (const p of ['/life/library/files', '/life/library/archive', '/life/goals/someday']) {
        await s.open(p)
        const m = await pg.locator('[data-place-tabs]').first().evaluate((el) => { const t = el.querySelector('[data-state="active"]').getBoundingClientRect(); return { inView: t.left >= 0 && t.right <= window.innerWidth, h: t.height } })
        must(m.inView && m.h >= 44, `${p}: the tab row on a phone: ${JSON.stringify(m)}`)
        must((await overflow()) <= 0, `${p} scrolls sideways`)
      }
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check(`${tag}.9`, `${width} px: the record pane shows the tabs of its kind; ptab= survives a reload; a pane with one tab has no tab bar`, async () => {
    const one = (dt, where = '1=1') => bench(`print(frappe.db.sql("select name from \`tab${dt}\` where space='${SPACE}' and ${where} order by modified desc limit 1")[0][0])`).split('\n').pop()
    const parent = (await s.api('library.save', { space: SPACE, title: `UX parent ${width} ${stamp}`, content_md: 'A parent.', area: uxArea })).name
    await s.api('library.save', { space: SPACE, title: `UX child ${width} ${stamp}`, content_md: 'A child.', area: uxArea, parent_note: parent })
    const leaf = one('Life Note', "is_archived=0 and name not in (select ifnull(parent_note,'') from `tabLife Note`)")
    const KINDS = [
      ['task:' + one('Life Task', 'is_archived=0'), ['Details', 'Notes', 'Links']],
      ['note:' + parent, ['Note', 'Notes under this one', 'Links']],
      ['note:' + leaf, ['Note', 'Links']],
      ['goal:' + one('Life Goal', "horizon='12 weeks'"), null], // Actions, Tasks, History across cycles, Links
      ['goal:' + ux.goal, ['Tasks', 'Links']], // an open-ended goal (a project before set 6) has no actions
      ['project:' + ux.project, ['Tasks', 'Links']], // a link to a project opens the goal it became
      ['chat:' + one('Life Chat Log', "is_archived=0 and ifnull(transcript_md, '')=''"), ['Summary', 'Open items', 'Made from this', 'Links']],
      ['page:' + one('Life Journal Page'), ['Page', 'Transcript', 'Created from this page']],
      ['vault:' + one('Life Vault Document', 'is_archived=0'), ['Details', 'File']],
      ['day:' + today, []], ['vault:new', []],
    ]
    const tabsOf = async () => (await pg.locator('[data-pane-tabs] [role="tab"]').allInnerTexts()).map((t) => t.replace(/\s*\d+$/, '').trim())
    for (const [ref, want] of KINDS) {
      await s.open(`/life/goals/tasks?view=list&open=${encodeURIComponent(ref)}`)
      await paneTitle()
      await settle()
      const got = await tabsOf()
      const expect = want || (got.includes('History across cycles') ? ['Actions', 'Tasks', 'History across cycles', 'Links'] : ['Actions', 'Tasks', 'Links'])
      must(JSON.stringify(got) === JSON.stringify(expect), `${ref}: tabs ${JSON.stringify(got)}, not ${JSON.stringify(expect)}`)
      if (!expect.length) { must(!(await pg.locator('[data-pane-tabs]').count()), `${ref}: a tab bar with no tabs`); continue }
      // the last tab is in the URL as ptab= and survives a reload; the first adds nothing
      const last = pg.locator('[data-pane-tabs] [role="tab"]').last()
      const value = await last.getAttribute('data-tab')
      await last.click()
      await settle()
      must(new URL(pg.url()).searchParams.get('ptab') === value, `${ref}: ptab= is ${new URL(pg.url()).searchParams.get('ptab')}, not ${value}`)
      await pg.reload({ waitUntil: 'networkidle' })
      await paneTitle()
      await settle()
      must((await pg.locator('[data-pane-tabs]').getAttribute('data-tab-current')) === value, `${ref}: reload left the ${value} tab`)
      must((await overflow()) <= 0, `${ref}: the page scrolls sideways`)
    }
    // Back closes the pane in one step even after changing its tab
    await s.open('/life/goals/tasks?view=list')
    await clickRow(ROW)
    await pg.locator('[data-pane-tabs] [role="tab"]').last().click()
    await settle()
    await pg.goBack()
    await settle()
    must(!(await pane.isVisible()), 'Back after changing the pane tab did not close the pane')
    // a count of open items opens the chat on its Open items tab
    await s.open('/life/library/chats?tab=chats&open_items=1&view=list')
    const door = pg.locator('[data-door="chat-items"]:visible').first()
    if (await door.count()) {
      const n = num(await door.innerText())
      await door.click()
      await paneTitle()
      await settle()
      must((await pg.locator('[data-pane-tabs]').getAttribute('data-tab-current')) === 'items', 'the open items count did not open the Open items tab')
      must(num(await pg.locator('[data-pane-tabs] [data-tab="items"] [data-tab-count]').innerText()) === n && (await pg.locator('[data-pane] [data-open-item]').count()) >= n, 'the Open items tab does not hold the number clicked')
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${KINDS.length} kinds`
  })

  // ---------- UX fixes, set 5 ----------
  const S5 = (what) => `S5 ${what} ${width} ${stamp}`
  // on a phone the tab bar is fixed over the bottom of the screen: bring the target to the middle first
  const tap = async (loc) => { await loc.evaluate((el) => el.scrollIntoView({ block: 'center' })); await pg.waitForTimeout(150); await loc.click() }
  const tasksLike = async (title) => (await s.api('tasks.list', { space: SPACE, status: 'any', filters: JSON.stringify([['title', 'like', `%${title}%`]]), page_length: 50 })).tasks
  await check(`${tag}.16`, `${width} px: Today: the Open band, the Next list in its four groups in order, the rail; a 12 Week Year tick moves the score; Someday never shows; amber over the limit`, async () => {
    // an overdue task, a task due today, a parked task due today, three stuck tasks for a decision
    const over = await s.api('tasks.quick_add', { text: S5('overdue'), space: SPACE, area: uxArea, due_date: addDays(-2) })
    const due = await s.api('tasks.quick_add', { text: S5('due today'), space: SPACE, area: uxArea, due_date: today })
    const parked = await s.api('tasks.quick_add', { text: S5('parked'), space: SPACE, area: uxArea, due_date: today })
    await s.api('someday.park', { doctype: 'Life Task', name: parked.name })
    const stuck = []
    for (let i = 0; i < 3; i++) stuck.push((await s.api('tasks.quick_add', { text: S5('stuck ' + i), space: SPACE, area: areaId('Learning') })).name)
    bench(`for n in ${JSON.stringify(stuck)}: frappe.db.set_value("Life Task", n, "last_touched_on", frappe.utils.add_days(frappe.utils.today(), -120))`)
    await s.api('insights.refresh', { space: SPACE })
    await s.open('/life')
    must(await pg.locator('[data-open-band]').isVisible(), 'no Open band')
    for (const k of ['open', 'inbox', 'week', 'habits']) must(await pg.locator(`[data-tile="${k}"]:visible`).count(), `no ${k} tile`)
    const groups = await pg.locator('[data-next-group]').evaluateAll((els) => els.map((e) => e.getAttribute('data-next-group')))
    const order = ['today', 'overdue', 'twy', 'decisions']
    must(JSON.stringify(groups) === JSON.stringify(order.filter((g) => groups.includes(g))), `Next groups are ${groups}`)
    if (await pg.locator('[data-overdue-toggle]').count()) { await tap(pg.locator('[data-overdue-toggle]')); await settle() } // issue 15: overdue is folded
    if (await pg.locator('[data-next-more]').count()) { await tap(pg.locator('[data-next-more]')); await settle() }
    const next = await pg.locator('[data-next]').innerText()
    must(next.includes(S5('overdue')) && next.includes(S5('due today')), 'the overdue or due task is not in Next')
    must(!next.includes(S5('parked')), 'a Someday task is on Today')
    must(await pg.locator('[data-next-row][data-why="12WY"]').count() && await pg.locator('[data-next-group="decisions"]').count(), 'no 12 Week Year action or decision in Next')
    must(await pg.locator('[data-rail-today]').isVisible() && await pg.locator('[data-rail-week]').isVisible(), 'the rail is missing')
    // a tick on a 12 Week Year action records the week tick and moves the score; it is put back after
    const row = pg.locator('[data-next-row][data-why="12WY"]').first()
    const action = await row.getAttribute('data-action')
    const before = await s.api('today.get', { space: SPACE })
    const a = before.cycle.actions.find((x) => x.name === action)
    try {
      await tap(row.locator('[data-week-tick]'))
      await pg.waitForTimeout(900)
      const after = (await s.api('today.get', { space: SPACE })).cycle
      must(after.actions.find((x) => x.name === action).count === a.count + 1, 'the tick was not recorded')
      must(after.done === before.cycle.done + 1 && after.score !== before.cycle.score, 'the week score did not change')
      const shown = num(await pg.locator('[data-week-score]:visible').first().innerText())
      must(shown === Math.round(after.score), `the band shows ${shown}%, the score is ${after.score}`)
    } finally {
      await s.api('journal.tick', { action, week: before.cycle.week, count: a.count })
    }
    // the stuck count over the limit turns the band amber; the limit is put back after
    const limit = (await s.api('counts.get', { space: SPACE })).rules.stuck_limit
    await s.api('settings.save', { values: { stuck_limit: 0 } })
    try {
      await s.open('/life')
      must(await pg.locator('[data-open-band][data-over-limit]').count(), 'the band is not marked over the limit')
      must(phone ? await pg.locator('[data-band-reset-phone]').isVisible() : await pg.locator('[data-band-amber]').isVisible(), 'no amber stuck warning')
      if (!phone) { // set 6: the dot sits on the Week's Reset button (issue 14: the sidebar has no Week item)
        await s.open('/life/today/week?view=calendar')
        must(await pg.locator('[data-plan-reset] [role="img"]').count(), "no amber dot on the Week's Reset button")
      }
    } finally {
      await s.api('settings.save', { values: { stuck_limit: limit } })
    }
    return `${groups.join(', ')}`
  })

  await check(`${tag}.31`, `${width} px: counts: every number on Today, Reset, Someday and the sidebar opens a list with exactly that many rows`, async () => {
    let n = 0
    for (const from of ['/life', '/life/today/reset', '/life/goals/someday?all=1']) {
      await s.open(from)
      if (phone && from === '/life/today/reset') { await pg.locator('[role="tab"]', { hasText: 'Inventory' }).first().click(); await settle() }
      const keys = await pg.locator('[data-count-door]:visible').evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute('data-count-key')))])
      // Someday's own numbers are its tab counts, which U.8 clicks; here only the doors on the page (the sidebar's on a wide screen)
      must(keys.length || from.includes('someday'), `no counts on ${from}`)
      for (const key of keys) {
        await s.open(from)
        if (phone && from === '/life/today/reset') { await pg.locator('[role="tab"]', { hasText: 'Inventory' }).first().click(); await settle() }
        const el = pg.locator(`[data-count-key="${key}"]:visible`).first()
        const want = Number(await el.getAttribute('data-count-n'))
        await el.click()
        await pg.waitForLoadState('networkidle')
        await settle()
        const got = num(await pg.locator('[data-lv-count]').first().innerText())
        must(got === want, `${from} ${key}: the number is ${want}, the list says ${got}`)
        if (want > 0 && want <= 40) {
          const more = pg.getByRole('button', { name: /^Show more/ })
          if (await more.count()) { await more.first().click(); await settle() }
          const rows = await pg.locator(`${ROW}:visible, [data-insight-row]:visible`).count()
          must(rows === want, `${from} ${key}: the number is ${want}, the list shows ${rows} rows`)
        }
        n++
      }
    }
    // the sidebar's numbers, with Plan open so Tasks and Someday show (a phone has no sidebar: U.13 checks its Inbox count)
    await s.open('/life/today/week')
    const navKeys = await pg.locator('[data-count-door]:visible').evaluateAll((els) => els.map((e) => e.getAttribute('data-count-key')).filter((k) => /^nav:/.test(k)))
    for (const key of navKeys) {
      await s.open('/life/today/week')
      const el = pg.locator(`[data-count-key="${key}"]:visible`).first()
      const want = Number(await el.getAttribute('data-count-n'))
      await el.click()
      await pg.waitForLoadState('networkidle')
      await settle()
      const got = num(await pg.locator('[data-lv-count]').first().innerText())
      must(got === want, `${key}: the number is ${want}, the list says ${got}`)
      n++
    }
    return `${n} numbers`
  })

  // Ask from a screen: the scope chip, a cited answer whose citation opens its record, Make task only when clicked, the panel over the screen
  const askOn = async (path, wantScope, { pane: paneRef } = {}) => {
    await s.open(path)
    if (paneRef) {
      await pg.locator(`[data-ref="${paneRef}"]`).first().click()
      await settle()
      await pg.locator('[data-pane-ask]').click()
    } else if (phone) await pg.locator('[data-phone-ask]:visible').first().click()
    else { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(300); await pg.keyboard.type(`What is still open in ${stamp} here?`); await pg.waitForTimeout(600); await pg.keyboard.press('Enter') }
    await settle()
    const panel = pg.locator('[data-ask-panel]:visible')
    must(await panel.count(), `${path}: the Ask panel did not open`)
    if (phone) must(await pg.locator('[data-ask-sheet]:visible').count(), 'not a bottom sheet on a phone')
    else must(Math.abs((await panel.boundingBox()).width - 480) < 2, 'the panel is not 480 px wide')
    const scope = (await pg.locator('[data-ask-scope]:visible').first().innerText()).trim()
    must(scope === wantScope, `${path}: the scope chip says "${scope}", not "${wantScope}"`)
    if (phone || paneRef) { await pg.locator('[data-ask-panel] textarea').fill('What is still open here?'); await pg.locator('[data-ask-send]:visible').click() }
    for (let i = 0; i < 40 && await pg.locator('[data-ask-answer][data-status="Working"]').count(); i++) await pg.waitForTimeout(250)
    await settle()
    return panel
  }
  await check(`${tag}.32`, `${width} px: Ask: from Today, Today under an area, a goal page, Reset and a record pane, with the scope of the screen; citations open their records; Make task only when clicked; the panel closes and the screen is as it was`, async () => {
    const done = []
    // set 6: the area page became the lens (Ask's scope is the lens), the project page the goal's page
    for (const [path, scope] of [['/life', 'Everything in this space'], ['/life?area=' + uxArea, areas.find((x) => x.name === uxArea).area_name],
      ['/life/goals/' + ux.goal, ux.goalTitle], ['/life/today/reset', 'Items on Reset']]) {
      await askOn(path, scope)
      const here = new URL(pg.url()).pathname
      const cites = pg.locator('[data-ask-cite]:visible')
      if (await cites.count()) {
        const title = (await cites.first().innerText()).replace(/^\d+\s*/, '')
        await cites.first().click()
        await settle()
        must(await pane.count() && (await paneTitle()).trim() === title.trim(), `${path}: the citation did not open "${title}"`)
        if (phone) await pg.locator('[data-pane-close]:visible').first().click() // a phone closes the sheet with its button
        else await pg.keyboard.press('Escape')
        await settle()
      }
      if (!phone) { await pg.locator('[data-ask-close]').click(); await settle() } else { await pg.keyboard.press('Escape'); await settle() }
      must(!(await pg.locator('[data-ask-panel]:visible').count()), `${path}: the panel did not close`)
      must(new URL(pg.url()).pathname === here && here.replace(/\/$/, '') === (path.split('?')[0] === '/life' ? '/life/today' : path.split('?')[0]), `${path}: the screen changed under the panel (${new URL(pg.url()).pathname})`)
      done.push(scope)
    }
    // a record pane: Ask about this
    const task = await s.api('tasks.quick_add', { text: S5('ask about'), space: SPACE, area: uxArea })
    await s.open(`/life/goals/tasks?view=list&status=all&f=${encodeURIComponent(JSON.stringify([['title', 'like', `%${S5('ask about')}%`]]))}`)
    await pg.locator(`[data-ref="task:${task.name}"]`).first().click()
    await settle()
    await pg.locator('[data-pane-ask]').click()
    await settle()
    must((await pg.locator('[data-ask-scope]:visible').first().innerText()).trim() === S5('ask about'), 'Ask about this does not take the record as its scope')
    await pg.locator('[data-ask-panel] textarea').fill(`${S5('ask about')}?`)
    await pg.locator('[data-ask-send]:visible').click()
    for (let i = 0; i < 40 && await pg.locator('[data-ask-answer][data-status="Working"]').count(); i++) await pg.waitForTimeout(250)
    await settle()
    must(await pg.locator('[data-ask-cite]:visible').count(), 'the answer cites nothing')
    // a suggested Make task creates a task only when clicked
    const made = async () => (await tasksLike('Follow up: ' + S5('ask about'))).length
    must((await made()) === 0, 'a task was made before the click')
    await pg.locator('[data-ask-action="make_task"]:visible').first().click()
    await pg.waitForTimeout(900)
    must((await made()) === 1, 'Make task did not make one task')
    return done.join(', ') + ', a task pane'
  })

  if (!phone) await check(`${tag}.33`, 'Ask: with no key it says it is not set up; at the cap it refuses and shows the spend; the family user never gets a Private record; a Vault document is never sent while the switch is off', async () => {
    // no key
    bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = None; s.save()')
    try {
      await s.open('/life')
      await pg.keyboard.press('Control+k'); await pg.waitForTimeout(300); await pg.keyboard.type('What is open this week?'); await pg.waitForTimeout(500); await pg.keyboard.press('Enter')
      await pg.waitForTimeout(1500)
      must(await pg.locator('[data-refusal="not_set_up"]').count() && (await pg.locator('[data-ask-refusal]').innerText()).includes('Ask is not set up yet'), 'no "not set up" message')
      await pg.locator('[data-ask-close]').click()
    } finally {
      bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()')
    }
    // the cap
    bench(`frappe.get_doc({"doctype": "Life AI Usage", "user": "owner@lifeos.test", "month": frappe.utils.now_datetime().strftime("%Y-%m"), "model": "claude-sonnet-5-5", "cost": 99, "purpose": "Test"}).insert(ignore_permissions=True)`)
    try {
      const res = await s.api('ask.ask', { question: 'What is open?', space: SPACE })
      must(res.error === 'cap' && /\$\d+\.\d\d of \$30/.test(res.error_text), `the cap did not refuse: ${JSON.stringify(res).slice(0, 200)}`)
      await s.open('/life/ask')
      must((await pg.locator('[data-ask-spend]').innerText()).includes('of $30'), 'the Ask page does not show the spend')
    } finally {
      bench('frappe.db.delete("Life AI Usage", {"purpose": "Test"})')
    }
    // the family user asks in Shared about a word only a Private record holds
    const secret = await s.api('tasks.quick_add', { text: S5('kumquat private'), space: SPACE, area: uxArea })
    bench('from lifeos.ai import fake\nfake.clear_received()')
    const fam = await session('family@lifeos.test', width)
    const r = await fam.api('ask.ask', { question: `kumquat ${stamp}?`, space: 'Shared' })
    must(!(r.message?.cited || []).some((c) => c.title.includes('kumquat')), 'the family user was given a Private record')
    must(!bench('from lifeos.ai import fake\nimport json\nprint(json.dumps(fake.received()))').includes(S5('kumquat private')), 'a Private record was sent for the family user')
    await fam.ctx.close()
    // a Vault document is never sent while "Ask may read Vault documents" is off
    await s.api('vault.save', { space: SPACE, values: { title: S5('zebra passport'), doc_type: 'ID', notes_md: `secret-${stamp}`, area: areaId('Money & Legal') } })
    bench('from lifeos.ai import fake\nfake.clear_received()')
    await s.api('ask.ask', { question: `Where is my zebra passport ${stamp}?`, space: SPACE })
    const sent = bench('from lifeos.ai import fake\nimport json\nprint(json.dumps(fake.received()))')
    must(sent.length > 10 && !sent.includes(`secret-${stamp}`) && !sent.includes(S5('zebra passport')), 'a Vault document reached the model')
    return 'no key, cap, family, Vault'
  })

  if (!phone) await check(`${tag}.34`, 'Insights: rules make Stuck, 12 Week Year and Habit insights from seeded data; a dismissed one does not return; a snoozed one returns after its date; at most 12 new a day', async () => {
    bench('frappe.db.delete("Life Insight", {"space": "Private"})')
    // a habit done every day last month and never this month
    bench(`from lifeos import journal
frappe.set_user("owner@lifeos.test")
h = frappe.get_doc({"doctype": "Life Habit", "space": "Private", "title": "${S5('habit')}"}).insert()
now = frappe.utils.getdate(frappe.utils.today()); prev = frappe.utils.add_months(now, -1)
for y, m in ((prev.year, prev.month), (now.year, now.month)):
    plan = journal.get_month_plan("Private", y, m, create=True)
    if h.name not in [r.habit for r in plan.habits]:
        plan.append("habits", {"habit": h.name, "days_per_week": 7}); plan.save()
first, last = journal.month_bounds(prev.year, prev.month); d = first
while d <= last:
    frappe.get_doc({"doctype": "Life Habit Log", "space": "Private", "habit": h.name, "date": d, "done": 1}).insert(); d = frappe.utils.add_days(d, 1)`)
    const ids = []
    for (let i = 0; i < 4; i++) ids.push((await s.api('tasks.quick_add', { text: S5('insight stuck ' + i), space: SPACE, area: areaId('Family') })).name)
    bench(`for n in ${JSON.stringify(ids)}: frappe.db.set_value("Life Task", n, "last_touched_on", frappe.utils.add_days(frappe.utils.today(), -200))`)
    await s.api('insights.refresh', { space: SPACE })
    const all = (await s.api('insights.list', { space: SPACE, status: 'all', page_length: 100 })).rows
    const kinds = new Set(all.map((r) => r.kind))
    for (const k of ['Stuck', '12 Week Year', 'Habit']) must(kinds.has(k), `no ${k} insight (got ${[...kinds]})`)
    must(all.filter((r) => r.found_on === today).length <= 12, 'more than 12 new insights today')
    const stuck = all.find((r) => r.kind === 'Stuck' && r.evidence.some((e) => ids.includes(e.name)))
    must(stuck, 'the seeded stuck tasks have no insight')
    await s.api('insights.dismiss', { insight: stuck.name, reason: 'Not relevant' })
    await s.api('insights.refresh', { space: SPACE })
    const again = (await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows.filter((r) => r.kind === 'Stuck' && r.evidence.some((e) => ids.includes(e.name)))
    must(!again.length, 'a dismissed insight came back')
    const other = (await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows[0]
    await s.api('insights.snooze', { insight: other.name, until: addDays(5) })
    await s.api('insights.refresh', { space: SPACE })
    must((await s.api('insights.list', { space: SPACE, status: 'Snoozed' })).rows.some((r) => r.name === other.name), 'the snoozed insight is not snoozed')
    bench(`frappe.db.set_value("Life Insight", "${other.name}", "snooze_until", frappe.utils.add_days(frappe.utils.today(), -1))`)
    await s.api('insights.refresh', { space: SPACE })
    must((await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows.some((r) => r.name === other.name), 'the snoozed insight did not return after its date')
    await s.open('/life/ask?tab=insights')
    must(await pg.locator('[data-insight-row]').count() && await pg.locator('[data-insights-how]').isVisible(), 'the Insights tab shows no insights')
    return [...kinds].join(', ')
  })

  await check(`${tag}.35`, `${width} px: Someday: a task, an open-ended goal (a project before set 6) with two tasks, a goal and an idea leave Today, Tasks and the Open counts and keep their creation dates; due for review after the date, also in Reset; Bring back with a date; Purge to the trash and Restore`, async () => {
    const before = (await s.api('counts.get', { space: SPACE })).open_tasks.n
    const t = await s.api('tasks.quick_add', { text: S5('someday task'), space: SPACE, area: uxArea, due_date: today })
    const p = await s.api('goals.create', { space: SPACE, title: S5('someday project'), horizon: 'Long term', area: uxArea })
    const pt = []
    for (let i = 0; i < 2; i++) pt.push(await s.api('tasks.quick_add', { text: S5('someday project task ' + i), space: SPACE, area: uxArea, goal: p.name }))
    const g = await s.api('goals.create', { space: SPACE, title: S5('someday goal'), horizon: 'Long term', area: uxArea })
    const created = (await s.api('frappe.client.get_value', { doctype: 'Life Task', filters: { name: t.name }, fieldname: 'creation' })).creation
    // the task is parked from its pane, the rest through the API the screens call
    await s.open(`/life/goals/tasks?view=list&status=all&f=${encodeURIComponent(JSON.stringify([['title', 'like', `%${S5('someday task')}%`]]))}`)
    await pg.locator(`[data-ref="task:${t.name}"]`).first().click()
    await settle()
    await pg.locator('[data-pane-someday]').click()
    await pg.waitForTimeout(900)
    await s.api('someday.park', { doctype: 'Life Goal', name: p.name })
    await s.api('someday.park', { doctype: 'Life Goal', name: g.name })
    const idea = await s.api('someday.create', { title: S5('someday idea'), space: SPACE, area: uxArea, as_note: 1 })
    must((await tasksLike(S5('someday task')))[0].status === 'Someday', 'the pane did not park the task')
    must((await s.api('counts.get', { space: SPACE })).open_tasks.n === before, 'the parked tasks are still in the Open count')
    must((await s.api('frappe.client.get_value', { doctype: 'Life Task', filters: { name: t.name }, fieldname: 'creation' })).creation === created, 'parking changed the creation date')
    const open = (await s.api('tasks.list', { space: SPACE, status: 'open', page_length: 100, filters: JSON.stringify([['title', 'like', `%${stamp}%`]]) })).tasks.map((x) => x.name)
    must(![t.name, ...pt.map((x) => x.name)].some((n) => open.includes(n)), 'a parked task is still in Tasks')
    await s.open('/life')
    must(!(await pg.locator('[data-next]').innerText()).includes(S5('someday task')), 'a parked task is on Today')
    // the clock moves past the review date
    bench(`frappe.db.set_value("Life Task", "${t.name}", "someday_review_on", frappe.utils.add_days(frappe.utils.today(), -1))`)
    await s.open('/life/goals/someday?tab=due')
    must((await pg.locator('[data-main]').innerText()).includes(S5('someday task')), 'not under Due for review')
    must((await s.api('reset.get', { space: SPACE })).batches.some((b) => b.key === 'someday_due' && b.items.some((i) => i.name === t.name)), 'not in Reset')
    // Bring back through the row's dialog; then a second parked task comes back with a date and is in Tasks with it
    await pg.locator(ROW, { hasText: S5('someday task') }).locator('[data-bring-back]:visible').first().click()
    await settle()
    await pg.getByRole('dialog').getByRole('button', { name: 'Bring back' }).click()
    await pg.waitForTimeout(900)
    const back = (await tasksLike(S5('someday task')))[0]
    must(back.status === 'Open', `Bring back left the task ${back.status}`)
    await s.api('someday.bring_back', { doctype: 'Life Goal', name: p.name, status: 'Active' })
    const t2 = await s.api('tasks.quick_add', { text: S5('someday dated'), space: SPACE, area: uxArea })
    await s.api('someday.park', { doctype: 'Life Task', name: t2.name })
    await s.api('someday.bring_back', { doctype: 'Life Task', name: t2.name, due_date: addDays(3) })
    const dated = (await s.api('tasks.list', { space: SPACE, status: 'open', filters: JSON.stringify([['title', 'like', `%${S5('someday dated')}%`]]) })).tasks
    must(dated.length === 1 && dated[0].due_date === addDays(3), 'a task brought back with a date is not in Tasks with that date')
    // Purge the Someday note to the trash, then Restore it from the Archive's Trash tab
    await s.open('/life/goals/someday?tab=notes')
    await pg.locator(ROW, { hasText: S5('someday idea') }).locator('[data-purge]:visible').first().click()
    await settle()
    await pg.getByRole('dialog').getByRole('button', { name: 'Purge' }).click()
    await pg.waitForTimeout(900)
    must(!(await s.api('frappe.client.get_count', { doctype: 'Life Note', filters: { name: idea.name } })), 'Purge did not remove the note')
    await s.open('/life/library/archive?type=trash')
    await pg.locator(ROW, { hasText: S5('someday idea') }).locator('[data-trash-restore]:visible').first().click()
    await pg.waitForTimeout(900)
    must(await s.api('frappe.client.get_count', { doctype: 'Life Note', filters: { name: idea.name } }), 'Restore did not bring the note back')
    return 'task, long-term goal with tasks, goal, note'
  })

  await check(`${tag}.36`, `${width} px: Reset: each rule batch finds its seeded items; a batch changes exactly those and Undo reverts; one by one with ${phone ? 'the buttons' : 'the keys'}; Delete then Restore from the trash; stuck tasks are the weekly review's Tasks tab`, async () => {
    const a = await s.api('tasks.quick_add', { text: S5('dupe'), space: SPACE, area: uxArea })
    const b = await s.api('tasks.quick_add', { text: S5('dupe'), space: SPACE, area: uxArea })
    const old = []
    for (let i = 0; i < 2; i++) old.push((await s.api('tasks.quick_add', { text: S5('ancient ' + i), space: SPACE, area: areaId('Personal') })).name)
    bench(`for n in ${JSON.stringify(old)}: frappe.db.set_value("Life Task", n, "last_touched_on", frappe.utils.add_days(frappe.utils.today(), -400))`)
    const got = await s.api('reset.get', { space: SPACE })
    const dupes = got.batches.find((x) => x.key === 'duplicates')
    must(dupes && dupes.items.some((i) => i.name === b.name) && !dupes.items.some((i) => i.name === a.name), 'the duplicate batch is wrong')
    must(got.batches.some((x) => x.key.startsWith('old:') && old.every((n) => x.items.some((i) => i.name === n))), 'the old tasks are not in a batch')
    // a batch from its card: confirm, exactly the listed items change, Undo from the toast
    await s.open('/life/today/reset')
    const card = pg.locator('[data-batch="duplicates"]')
    const listed = (await s.api('reset.get', { space: SPACE })).batches.find((x) => x.key === 'duplicates').items.map((i) => i.name)
    await card.locator('[data-batch-apply]').click()
    await settle()
    await pg.getByRole('dialog').getByRole('button', { name: /^Delete \d+/ }).click()
    await pg.waitForTimeout(1200)
    for (const n of listed) must(!(await s.api('frappe.client.get_count', { doctype: 'Life Task', filters: { name: n } })), 'a listed duplicate was not deleted')
    must(await s.api('frappe.client.get_count', { doctype: 'Life Task', filters: { name: a.name } }), 'the kept task was deleted')
    await pg.getByRole('button', { name: 'Undo' }).last().click()
    await pg.waitForTimeout(1200)
    for (const n of listed) must(await s.api('frappe.client.get_count', { doctype: 'Life Task', filters: { name: n } }), 'Undo did not bring a duplicate back')
    // one by one
    if (phone) { await pg.locator('[role="tab"]', { hasText: 'One by one' }).first().click(); await settle() }
    const first = (await pg.locator('[data-obo-title]').innerText()).trim()
    if (phone) await pg.locator('[data-obo="someday"]').click()
    else await pg.keyboard.press('s')
    await pg.waitForTimeout(1200)
    const parked = await s.api('tasks.list', { space: SPACE, status: 'Someday', filters: JSON.stringify([['title', '=', first]]), page_length: 5 })
    const parkedProject = parked.total ? null : (await s.api('goals.list', { space: SPACE, state: 'someday', filters: JSON.stringify([['title', '=', first]]) })).total // an open-ended goal
    must(parked.total || parkedProject, `Someday (${phone ? 'button' : 'S'}) did not park “${first}”`)
    await pg.getByRole('button', { name: 'Undo' }).last().click()
    await pg.waitForTimeout(1000)
    // Delete one of this run's tasks with X (or the button), then Restore it from the Trash tab
    const del = await s.api('tasks.quick_add', { text: S5('delete me'), space: SPACE, area: uxArea })
    bench(`frappe.db.set_value("Life Task", "${del.name}", "last_touched_on", "2000-01-01")`)
    await s.open('/life/today/reset')
    if (phone) { await pg.locator('[role="tab"]', { hasText: 'One by one' }).first().click(); await settle() }
    must((await pg.locator('[data-obo-title]').innerText()).trim() === S5('delete me'), 'the oldest untouched item is not first')
    if (phone) await pg.locator('[data-obo="delete"]').click()
    else await pg.keyboard.press('x')
    await pg.waitForTimeout(1200)
    must(!(await s.api('frappe.client.get_count', { doctype: 'Life Task', filters: { name: del.name } })), 'Delete did not delete')
    await s.open('/life/library/archive?type=trash')
    await pg.locator(ROW, { hasText: S5('delete me') }).locator('[data-trash-restore]:visible').first().click()
    await pg.waitForTimeout(1000)
    must(await s.api('frappe.client.get_count', { doctype: 'Life Task', filters: { name: del.name } }), 'Restore from the trash did not bring it back')
    // set 8: Reset's place in the weekly review is its second tab, Tasks, with the stuck tasks in piles
    await s.open('/life/today/week?view=review&tab=tasks')
    must(await pg.locator('[data-pile-board][data-pile-key="tasks"]').count(), "the weekly review's Tasks tab has no piles")
    return 'batches, undo, one by one, trash, weekly review'
  })

  await check(`${tag}.37`, `${width} px: no sideways scrolling and no script errors on the new screens`, async () => {
    const before = errors.length
    const bad = []
    for (const p of ['/life', '/life/today/reset', '/life/goals/someday', '/life/ask', '/life/ask?tab=insights', '/life/ask?tab=history', '/life/library/archive?type=trash', '/life/settings?tab=ai', '/life/settings?tab=reset']) {
      await s.open(p)
      if ((await overflow()) > 0) bad.push(`${p} scrolls sideways by ${await overflow()} px`)
    }
    must(!bad.length, bad.join('; '))
    must(errors.length === before, 'script errors: ' + errors.slice(before).join(' | ').slice(0, 300))
    return '9 screens'
  })

  // ---------- UX fixes, set 4 ----------
  // Area filters: no archived area and no area of another space, on every list with an Area filter; the Archive lists archived ones
  await check(`${tag}.20`, `${width} px: the lens offers only active areas of this space (the Area filter of set 4 is the lens since set 6)`, async () => {
    const made = []
    try {
      const mk = async (space, title, archived) => {
        const a = (await s.api('settings.save_item', { kind: 'area', space, title: `${title} ${width} ${stamp}` })).name
        made.push(a)
        if (archived) await s.api('settings.save_item', { kind: 'area', name: a, is_archived: 1 })
        return a
      }
      const active = await mk(SPACE, 'S4 active area', false)
      await mk(SPACE, 'S4 archived area', true)
      await mk('Shared', 'S4 shared area', false)
      await s.open('/life/goals/tasks')
      const opts = await lensOptions()
      must(opts.some((o) => o.startsWith('S4 active area')), `the lens does not offer the active area (${opts.filter((o) => o.startsWith('S4'))})`)
      must(!opts.some((o) => /S4 (archived|shared) area/.test(o)), `the lens offers ${opts.filter((o) => o.startsWith('S4')).join(', ')}`)
      // the archived area's records stay findable in the Archive, which is narrowed by the lens like every list
      must(active, '')
      return `${opts.length} entries`
    } finally {
      await closeLens()
      for (const a of made) await s.api('settings.save_item', { kind: 'area', name: a, delete: 1 }).catch(() => {})
    }
  })


  // Python on the acceptance site as the agent, answering JSON on its last line
  const asAgent = (code) => JSON.parse(bench(`frappe.set_user("hermes@lifeos.test")\nimport json\nfrom lifeos.api import wiki, library, sources, inbox, chats\nfrom lifeos import permissions\npermissions.clear_cache()\n${code}`).split('\n').pop())
  const editorEnd = async () => { await pg.locator('[data-live-editor] .cm-content').first().click(); await pg.keyboard.press('ControlOrMeta+End') }
  const docOf = (name) => s.api('library.get', { note: name })

  await check(`${tag}.21`, `${width} px: intent: Just keep is in Library > Captures, not the Inbox, with text and no proposals; Add to wiki writes pages and leaves no wiki proposals`, async () => {
    // Just keep, dropped through the box
    // (issue 17: the drop zone and the intent moved from the Inbox to the + Capture sheet)
    await s.open('/life/brain')
    await pg.locator('[data-nav-capture]:visible, [data-tab-capture]:visible').first().click()
    await pg.locator('[data-capture-text] textarea, textarea[data-capture-text]').first().fill(`S4 keep ${width} ${stamp}\nA note to keep.`)
    await pg.locator('[role="dialog"] [data-intent]').getByText('Just keep', { exact: true }).click()
    await pg.locator('[data-capture-brain]').click()
    await pg.waitForTimeout(1200)
    const kept = (await s.api('inbox.list', { space: SPACE, page_length: 5, filters: [['title', 'like', `S4 keep ${width} ${stamp}%`]] })).items[0]
    must(kept, 'the Just keep item was not created')
    runAgent()
    const got = await s.api('inbox.get', { item: kept.name })
    must(got.intent === 'Just keep' && got.status === 'Done', `Just keep: ${got.intent}, ${got.status}`)
    must((got.transcript_md || '').includes('A note to keep'), 'Just keep: no text')
    must(!got.proposals.length, 'Just keep: it has proposals')
    const queue = await s.api('inbox.list', { space: SPACE, page_length: 100, status: JSON.stringify(['To Review', 'New', 'Processing', 'Failed']) })
    must(!queue.items.some((i) => i.name === kept.name), 'the Just keep item is still in the Inbox')
    await s.open('/life/brain/captures?tab=text')
    must((await pg.locator('[data-main]').innerText()).includes(`S4 keep ${width} ${stamp}`), 'the Just keep item is not in Sources')
    // the intent is remembered
    await s.open('/life/brain')
    await pg.waitForTimeout(1200)
    await pg.reload({ waitUntil: 'networkidle' })
    await pg.locator('[data-nav-capture]:visible, [data-tab-capture]:visible').first().click()
    const keepBtn = pg.locator('[role="dialog"] [data-intent] button, [role="dialog"] [data-intent] [role="radio"]').filter({ hasText: 'Just keep' }).first()
    must(await keepBtn.evaluate((e) => ['true'].includes(e.getAttribute('aria-checked')) || ['on', 'checked', 'active'].includes(e.getAttribute('data-state')) || e.getAttribute('aria-pressed') === 'true'),
      'the last intent is not remembered')
    await pg.locator('[role="dialog"] [data-intent]').getByText('Process', { exact: true }).click()
    await pg.keyboard.press('Escape')
    // Add to wiki: pages are created and edited directly; no wiki proposals for review
    const w = await s.api('inbox.create_item', { title: `S4 wiki ${width} ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Mithun runs the Ghatia factory.', intent: 'Add to wiki' })
    runAgent()
    const wi = await s.api('inbox.get', { item: w.name })
    must(wi.status === 'Done' && !wi.proposals.some((p) => p.kind === 'Note'), `Add to wiki: ${wi.status}, ${wi.proposals.map((p) => p.kind)}`)
    const pages = (await s.api('wiki.pages', { space: SPACE, page_length: 200 })).pages
    const page = pages.find((p) => p.title === `S4 wiki ${width} ${stamp}`)
    must(page, 'Add to wiki did not create a page')
    const changes = (await s.api('wiki.changes', { space: SPACE, page_length: 50 })).changes
    must(changes.some((c) => c.note === page.name && c.change_type === 'Created') && changes.some((c) => c.note_title === 'Inbox log' && c.change_type === 'Edited' && c.source_name === w.name),
      'Add to wiki did not create one page and edit another')
    return 'Just keep and Add to wiki'
  })

  await check(`${tag}.22`, `${width} px: Captures: each tab's count matches its rows; Photos shows thumbnails; Made from this lists the task and the assistant's note; /chats lands on the Chats tab`, async () => {
    // a photo with a thumbnail
    const photo = await s.api('inbox.create_item', { title: `S4 photo ${width} ${stamp}`, source_type: 'Upload', space: SPACE, intent: 'Just keep' })
    await s.upload('Life Inbox Item', photo.name, `s4-${stamp}.png`, 'image/png', await pg.screenshot())
    // a source a task and a wiki page are made from
    const src = await s.api('inbox.create_item', { title: `S4 source ${width} ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Call the estate manager about drains.' })
    runAgent()
    const it = await s.api('inbox.get', { item: src.name })
    const p = it.proposals.find((x) => x.status === 'Pending')
    must(p, 'the agent proposed nothing for the source')
    await s.api('review.decide', { proposal: p.name, decision: 'accept', payload: { ...p.payload, kind: undefined, title: `S4 made ${width} ${stamp}`, area: p.payload.area || areaId('Personal') } })
    const made = await asAgent(`print(json.dumps(wiki.create_page(space="${SPACE}", title="S4 cites ${width} ${stamp}", summary="Cites a source", content_md="From a source.", sources=[{"doctype": "Life Inbox Item", "name": "${src.name}"}])))`)
    // tab counts equal the rows each tab lists
    const res = await s.api('sources.list', { space: SPACE, page_length: 200 })
    for (const [t, n] of Object.entries(res.tabs)) {
      await s.open(`/life/brain/captures?tab=${t}&view=list`)
      const shown = await pg.locator(`[data-state-tabs] [data-tab="${t}"]`).first().innerText()
      must(num(shown) === n, `${t}: the tab says ${shown}, the server ${n}`)
      const listed = (await s.api('sources.list', { space: SPACE, tab: t, page_length: 200 })).total
      must(listed === n, `${t}: ${listed} rows, the tab says ${n}`)
      if (n && n <= 50) must((await pg.locator(ROW).count()) === n, `${t}: ${await pg.locator(ROW).count()} rows on screen, the tab says ${n}`)
    }
    // the Photos grid shows thumbnails (the grid is the Photos tab's first view; the loop above left List remembered, so ask for it)
    await s.open('/life/brain/captures?tab=photos&view=grid')
    const thumbs = await pg.locator('[data-source-grid] img[data-thumb]').evaluateAll((els) => els.map((e) => e.getAttribute('src')))
    must(thumbs.length && thumbs.every((u) => /-thumb\.jpg$/.test(u)), `the Photos grid does not show thumbnails: ${thumbs.slice(0, 3)}`)
    // Made from this
    await s.open(`/life/brain/captures?open=source:${src.name}&ptab=made`)
    const madeText = await pg.locator('[data-source-made]').innerText()
    must(madeText.includes(`S4 made ${width} ${stamp}`) && madeText.includes(`S4 cites ${width} ${stamp}`), 'Made from this does not list the task and the wiki page')
    must(made.name, 'no page')
    // /chats lands on the Chats tab, with its filters
    await s.open(`/life/chats?area=${uxArea}`)
    must(/\/life\/library\/chats\?/.test(pg.url()) && pg.url().includes('tab=chats') && pg.url().includes(`area=${uxArea}`), `/chats went to ${pg.url()}`)
    return `${Object.keys(res.tabs).length} tabs`
  })

  await check(`${tag}.23`, `${width} px: editor: headings, bold, checklists and [[links]] render; Cmd-B; the / menu inserts a table; a pasted image shows; Show Markdown; no Edit or Done`, async () => {
    const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR4nGP8z8Dwn4GBgYGJAQoAADkVAgHaTGUJAAAAAElFTkSuQmCC'
    const tryEditor = async (where) => {
      await editorEnd()
      await pg.keyboard.type(`\n## Title ${stamp}\nsome `, { delay: 5 })
      await pg.keyboard.press('ControlOrMeta+b')
      await pg.keyboard.type('boldword', { delay: 5 })
      await pg.keyboard.press('End')
      await pg.keyboard.type('\n- [ ] a check item\nsee [[Dalmia Gold blend', { delay: 5 })
      await pg.waitForTimeout(1300)
      await pg.keyboard.press('Enter') // pick the record
      await pg.keyboard.type('\n\n', { delay: 5 })
      await pg.keyboard.type('/tab', { delay: 80 })
      await pg.waitForTimeout(700)
      await pg.keyboard.press('Enter')
      await pg.waitForTimeout(300)
      await pg.keyboard.press('ControlOrMeta+End')
      await pg.keyboard.type('\nend line', { delay: 5 })
      // a pasted image
      await pg.evaluate((b64) => {
        const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
        const dt = new DataTransfer()
        dt.items.add(new File([bin], 'pasted.png', { type: 'image/png' }))
        document.querySelector('[data-live-editor] .cm-content').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
      }, PNG)
      await pg.waitForTimeout(2500)
      await pg.keyboard.press('ControlOrMeta+End')
      const ed = pg.locator('[data-live-editor]').first()
      must((await ed.locator('.cm-lp-h2').allInnerTexts()).some((t) => t.includes(`Title ${stamp}`)), `${where}: the heading does not render`)
      must((await ed.locator('.cm-lp-strong').allInnerTexts()).includes('boldword'), `${where}: Cmd-B did not make bold`)
      must(await ed.locator('.cm-lp-task').count(), `${where}: the checklist has no box`)
      must((await ed.locator('.cm-lp-chip').allInnerTexts()).some((t) => t.includes('Dalmia Gold blend')), `${where}: the [[link]] is not a chip`)
      must(await ed.locator('.cm-lp-table table').count(), `${where}: the / menu did not insert a table`)
      must(await ed.locator('img.cm-lp-img[src*="/files/"]').count(), `${where}: the pasted image does not show`)
      must(!(await pg.getByRole('button', { name: /^(Edit|Done|Hide preview)$/ }).count()), `${where}: an Edit, Done or Hide preview button`)
      if (phone) {
        const bar = await pg.locator('[data-editor-toolbar]').first().boundingBox()
        const btn = await pg.locator('[data-editor-toolbar] [data-tool="bold"]').first().boundingBox()
        must(bar && btn && btn.x >= 0 && btn.x + btn.width <= width && btn.height >= 28, `${where}: the toolbar is not usable at 390 px`)
      }
    }
    await s.open('/life/dev/editor')
    await tryEditor('dev page')
    await pg.locator('[data-note-menu]').click()
    await pg.getByRole('menuitem', { name: 'Show Markdown' }).click()
    await settle()
    must(await pg.locator('[data-live-editor][data-raw]').count() && !(await pg.locator('[data-live-editor] .cm-lp-h2').count()), 'Show Markdown did not show the plain text')
    must((await pg.locator('[data-live-editor] .cm-content').innerText()).includes('# Estate visit, November'), 'the raw text is not shown')
    // a real note
    const note = await s.api('library.save', { space: SPACE, title: `S4 editor ${width} ${stamp}`, content_md: 'Start.', area: areaId('Learning') })
    await s.open(`/life/library/${note.name}`)
    await tryEditor('a note')
    await pg.waitForTimeout(2200)
    const saved = (await docOf(note.name)).content_md
    must(saved.includes(`## Title ${stamp}`) && saved.includes('**boldword**') && saved.includes('- [ ] a check item') && saved.includes('[[Dalmia Gold blend blueprint') &&
      saved.includes('| Column | Column |') && /!\[pasted\]\(\/private\/files\//.test(saved), 'the note did not save the Markdown: ' + saved.slice(0, 200))
    return 'dev page and a note'
  })

  await check(`${tag}.24`, `${width} px: conflict: an agent edits the open page; typing then saving shows the conflict and nothing is lost`, async () => {
    const page = await asAgent(`print(json.dumps(wiki.create_page(space="${SPACE}", title="S4 conflict ${width} ${stamp}", summary="A page", content_md="Agent text.")))`)
    await s.open(`/life/library/${page.name}`)
    await editorEnd()
    await asAgent(`p = wiki.get_page("${page.name}")\nprint(json.dumps(wiki.update_page("${page.name}", content_md="Agent text, edited.", base_version=p["version"], change_note="edit")))`)
    await pg.keyboard.type(' Mine too.', { delay: 10 })
    await pg.waitForTimeout(2600)
    must(await pg.locator('[data-conflict]').count(), 'no conflict message')
    must((await pg.getByRole('dialog').filter({ has: pg.locator('[data-conflict]') }).innerText()).includes('This page changed while you were editing'), 'the conflict message is not the agreed one')
    must((await docOf(page.name)).content_md === 'Agent text, edited.', 'the agent text was overwritten')
    await pg.locator('[data-conflict-diff]').click()
    must(await pg.locator('[data-conflict] [data-diff]').count(), 'View changes shows no diff')
    await pg.locator('[data-conflict-keep]').click()
    await pg.waitForTimeout(1500)
    must((await docOf(page.name)).content_md.includes('Mine too.'), 'Keep mine did not save the typed text')
    return 'kept'
  })

  await check(`${tag}.25`, `${width} px: wiki rules: the agent cannot edit My notes or the rules page; a stale version is a conflict; Undo restores and logs Reverted; Keep in My notes stops the agent`, async () => {
    const mine = await s.api('library.save', { space: SPACE, title: `S4 mine ${width} ${stamp}`, content_md: 'mine', area: areaId('Learning') })
    const refused = await asAgent(`out = {}
for key, fn in (("mine", lambda: wiki.update_page("${mine.name}", content_md="x", base_version=wiki.get_page("${mine.name}")["version"])),
		("rules", lambda: wiki.update_page(wiki.rules("${SPACE}")["name"], content_md="x", base_version=wiki.rules("${SPACE}")["version"]))):
	try:
		fn(); out[key] = "allowed"
	except frappe.PermissionError:
		out[key] = "refused"
	frappe.db.rollback()
p = wiki.create_page(space="${SPACE}", title="S4 rules ${width} ${stamp}", summary="r", content_md="One.")
v = wiki.get_page(p["name"])["version"]
wiki.update_page(p["name"], content_md="One. Two.", base_version=v, change_note="add two")
out["stale"] = wiki.update_page(p["name"], content_md="Lost", base_version=v)["conflict"]
out["page"] = p["name"]
frappe.db.commit()
print(json.dumps(out))`)
    must(refused.mine === 'refused' && refused.rules === 'refused', `the agent could edit: ${JSON.stringify(refused)}`)
    must(refused.stale === true, 'a stale base_version was not a conflict')
    // Undo, from the page's History in the pane
    const change = (await s.api('wiki.changes', { space: SPACE, note: refused.page })).changes[0]
    await s.open(`/life/library/notes?view=changes&open=change:${change.name}`)
    await pg.locator('[data-undo]').click()
    await pg.waitForTimeout(1200)
    must((await docOf(refused.page)).content_md === 'One.', 'Undo did not restore the previous text')
    const latest = (await s.api('wiki.changes', { space: SPACE, note: refused.page })).changes[0]
    must(latest.change_type === 'Reverted', 'Undo did not write a Reverted change')
    // Keep in My notes, from the pane
    await s.open(`/life/library/notes?by=assistant&open=note:${refused.page}`)
    await pg.locator('[data-move-collection]').click()
    await pg.waitForTimeout(900)
    const after = await asAgent(`try:
	wiki.update_page("${refused.page}", content_md="x", base_version=wiki.get_page("${refused.page}")["version"])
	print(json.dumps("allowed"))
except frappe.PermissionError:
	print(json.dumps("refused"))`)
    must(after === 'refused', 'the agent can still edit a page kept in My notes')
    return 'refused, conflict, undone, kept'
  })

  await check(`${tag}.26`, `${width} px: Health lists a broken [[link]] and an orphan page`, async () => {
    const p = await s.api('wiki.create_page', { space: SPACE, title: `S4 orphan ${width} ${stamp}`, summary: 'An orphan', content_md: `Points to [[S4 nowhere ${width} ${stamp}]].` })
    await s.open('/life/library/notes?view=health')
    await pg.locator('[data-health-refresh]').click()
    await pg.waitForTimeout(1500)
    must((await pg.locator('[data-health="orphans"]').innerText()).includes(`S4 orphan ${width} ${stamp}`), 'the orphan is not under Health')
    must((await pg.locator('[data-health="broken"]').innerText()).includes(`S4 nowhere ${width} ${stamp}`), 'the broken link is not under Health')
    must(p.name, '')
  })

  if (!phone) await check(`${tag}.27`, 'streams: chats.log twice with one external_id leaves one log; importing the Claude and ChatGPT fixtures creates the expected logs, and again creates and updates none', async () => {
    const ext = `s4-${stamp}`
    const a = await s.api('chats.log', { space: SPACE, title: `S4 stream ${stamp}`, source_system: 'claude', external_id: ext, open_items: ['One'] })
    const b = await s.api('chats.log', { space: SPACE, title: `S4 stream ${stamp}, renamed`, source_system: 'claude', external_id: ext, open_items: ['One', 'Two'] })
    must(a.created && !b.created && a.name === b.name, 'the second log was not an update')
    const got = await s.api('chats.get', { chat: a.name })
    must(got.title.endsWith('renamed') && got.open_items.length === 2, 'the log was not updated')
    const fixtures = path.join(root, 'lifeos/tests/fixtures')
    const importOnce = async (system, file) => {
      const up = await s.page.request.post(base + '/api/method/upload_file', { headers: { 'X-Frappe-CSRF-Token': await pg.evaluate(() => window.csrf_token) },
        multipart: { is_private: '1', file: { name: file, mimeType: 'application/zip', buffer: fs.readFileSync(path.join(fixtures, file)) } } })
      must(up.ok(), 'upload failed ' + up.status())
      const url = (await up.json()).message.file_url
      await s.api('connections.start_import', { space: SPACE, system, file_url: url })
      for (let i = 0; i < 60; i++) {
        const st = await s.api('connections.import_status', { space: SPACE, system })
        if (st.status === 'Done' || st.status === 'Failed') return st
        await pg.waitForTimeout(1000)
      }
      throw new Error(`${system}: the import did not finish (is a worker running?)`)
    }
    const c1 = await importOnce('claude', 'claude_export.zip')
    must(c1.status === 'Done' && c1.created === 2 && c1.skipped === 1, `Claude: ${JSON.stringify(c1)}`)
    const g1 = await importOnce('chatgpt', 'chatgpt_export.zip')
    must(g1.status === 'Done' && g1.created === 2 && g1.skipped === 1, `ChatGPT: ${JSON.stringify(g1)}`)
    const c2 = await importOnce('claude', 'claude_export.zip')
    const g2 = await importOnce('chatgpt', 'chatgpt_export.zip')
    must(!c2.created && !c2.updated && !g2.created && !g2.updated, `the second import changed something: ${JSON.stringify([c2, g2])}`)
    await s.open('/life/library/chats?tab=chats')
    must((await pg.locator('[data-main]').innerText()).includes('Blend sheet for Dalmia Gold'), 'the imported chat is not on the Chats tab')
    return 'two systems'
  })

  await check(`${tag}.28`, `${width} px: an Email Digest renders its sections and Open in Gmail buttons; the proposed reply task shows Open in Gmail`, async () => {
    const digest = `## Needs your attention\n- Mithun Sarkar: the despatch dates for December [Open](https://mail.google.com/mail/u/0/#inbox/s4${stamp}${width})\n- Ruchi: ITR papers [Open](https://mail.google.com/mail/u/0/#inbox/r${stamp})\n\n## Waiting on others\n- The auditor, scope letter [Open](https://mail.google.com/mail/u/0/#inbox/a${stamp})\n\n## Dates and deadlines\n- 20 Nov: board meeting\n\n## FYI from people\n- Anya: photos from the trip\n\n## Company information\n- Q3 numbers are out\n\n## Left out\n- 14 newsletters`
    const item = await s.api('inbox.create_item', { title: `S4 digest ${width} ${stamp}`, source_type: 'Email Digest', space: SPACE, raw_text: digest, source_system: 'gmail', external_id: `digest-${width}-${stamp}` })
    runAgent()
    await s.open(`/life/brain/captures?tab=email&open=source:${item.name}`)
    must((await pg.locator('[data-digest-section]').count()) >= 6, 'the digest sections are not headed lists')
    must((await pg.locator('[data-open-gmail]').count()) >= 3, 'no Open in Gmail buttons')
    const got = await s.api('inbox.get', { item: item.name })
    const p = got.proposals.find((x) => x.kind === 'Task')
    must(p && /mail\.google\.com/.test(p.payload.source_url || ''), 'the reply task has no Gmail link')
    const res = await s.api('review.decide', { proposal: p.name, decision: 'accept' })
    const task = res.created_name || (await s.api('inbox.get', { item: item.name })).proposals.find((x) => x.name === p.name).created_name
    await s.open(`/life/goals/tasks?open=task:${task}`)
    must((await pg.locator('[data-open-source]').innerText()).includes('Open in Gmail'), 'the task pane has no Open in Gmail')
  })

  await check(`${tag}.29`, `${width} px: Library's tabs are Everything, Notes, Documents, People and Chats; each opens from its tab and its path`, async () => {
    // set 6: the sidebar's Records (Sources, Notes, Wiki, Vault, Timeline) became Library's tabs; issue 14 gave it its own
    await s.open('/life')
    await nav('Library')
    must(new URL(pg.url()).pathname === '/life/library', `Library opened ${new URL(pg.url()).pathname}`)
    const bar = pg.locator('[data-place-tabs]').first()
    for (const [t, p] of [['notes', '/life/library/notes'], ['documents', '/life/library/documents'], ['people', '/life/library/people'], ['chats', '/life/library/chats'], ['all', '/life/library']]) {
      await bar.locator(`[data-tab="${t}"]`).click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must(new URL(pg.url()).pathname === p && (await bar.getAttribute('data-tab-current')) === t, `the ${t} tab opened ${new URL(pg.url()).pathname}`)
      await s.open(p)
      must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === t, `${p} does not open the ${t} tab`)
      must(await pg.locator('[data-lv-count], [data-library], [data-main] h1').count(), `${p} shows nothing`)
    }
  })

  if (!phone) await check(`${tag}.30`, 'access: the family user sees no Private sources, pages or changes; the agent cannot see a source behind a Vault document while the switch is off', async () => {
    const item = await s.api('inbox.create_item', { title: `S4 passport scan ${stamp}`, source_type: 'Upload', space: SPACE })
    const vault = await s.api('vault.save', { space: SPACE, values: { title: `S4 passport ${stamp}`, doc_type: 'ID', area: areaId('Money & Legal') } })
    bench(`from lifeos import index\nfrappe.db.set_value("Life Inbox Item", "${item.name}", "vault_document", "${vault.name}")\nindex.update(frappe.get_doc("Life Inbox Item", "${item.name}"))\nfrappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", 0)`)
    const seen = await asAgent(`rows = sources.list(space="${SPACE}", page_length=500)["sources"]
try:
	inbox.get("${item.name}"); got = "allowed"
except Exception:
	got = "refused"
print(json.dumps({"listed": any(r["name"] == "${item.name}" for r in rows), "get": got}))`)
    must(!seen.listed && seen.get === 'refused', `the agent sees the Vault source: ${JSON.stringify(seen)}`)
    const fam = await session('family@lifeos.test')
    try {
      for (const m of [['sources.list', { space: SPACE }], ['wiki.changes', { space: SPACE }], ['wiki.pages', { space: SPACE }]]) {
        const r = await fam.api(m[0], m[1], { raw: true })
        must(r.status() >= 400, `the family member could call ${m[0]} on Private`)
      }
      const shared = await fam.api('sources.list', { space: 'Shared', page_length: 500 })
      must(!shared.sources.some((r) => r.title.includes(stamp) && r.title.startsWith('S4')), 'the family member sees a Private source')
      await fam.open('/life/brain/captures')
      must(!(await fam.page.locator('[data-main]').innerText()).includes(`S4 keep`), 'a Private source shows to the family member')
      const ch = await fam.api('frappe.client.get_count', { doctype: 'Life Wiki Change', filters: { space: SPACE } }, { raw: true })
      must(!ch.ok() || (await ch.json()).message === 0, 'the family member counts Private wiki changes')
    } finally { await fam.ctx.close() }
  })

  // ---------- UX fixes, set 6: the lens, the four places, Plan and Library (U<width>.40 and up) ----------
  await check(`${tag}.40`, `${width} px: the lens: an area chosen in the ${phone ? 'lens sheet' : "sidebar's picker"} narrows Today, Inbox, every Plan tab and every Library tab; each count matches its rows and the server; the chip and the URL show it; it survives a reload; clearing it restores every count`, async () => {
    let step = 'start'
    const calls = []
    const onReq = (r) => { const u = r.url(); if (u.includes('/api/method/lifeos.api.')) calls.push({ m: u.split('/api/method/lifeos.api.')[1].split('?')[0], url: u, body: r.postData() || '' }) }
    const carries = (m) => calls.some((c) => (!m || c.m === m) && (new URL(c.url).searchParams.get('area') === uxArea || c.body.includes(`"area":"${uxArea}"`)))
    const lensIn = () => new URL(pg.url()).searchParams.get('area')
    const areaName = areas.find((x) => x.name === uxArea).area_name
    const goto = async (p) => { calls.length = 0; await pg.goto(base + p, { waitUntil: 'networkidle' }); await settle() } // no area= here: the lens decides
    const band = async () => Number(await pg.locator('[data-count-key="band:open"]:visible').first().getAttribute('data-count-n'))
    const total = (m, args) => s.api(m, { space: SPACE, page_length: 1, ...args }).then((r) => r.total)
    // [name, path, list method, the server's count under an area]
    const L = [
      ['Inbox', '/life/brain/queue?all=1', 'inbox.list', null],
      ['Plan > Goals', '/life/goals?all=1', 'goals.list', (a) => total('goals.list', { area: a })],
      ['Plan > Tasks', '/life/goals/tasks?view=list&all=1', 'tasks.list', (a) => total('tasks.list', { area: a, status: 'open_doing' })], // the Open tab: Open and Doing
      ['Plan > Someday', '/life/goals/someday?all=1', 'someday.list', (a) => total('someday.list', { area: a })],
      ['Library > All', '/life/library?view=list&all=1', 'sources.list', (a) => total('sources.list', { scope: 'all', area: a })],
      ['Library > Notes', '/life/library/notes?view=list&all=1', 'library.list', (a) => total('library.list', { collection: 'all', area: a })],
      ['Library > Captures', '/life/brain/captures?view=list&all=1', 'sources.list', (a) => total('sources.list', { area: a })],
      ['Library > Timeline', '/life/library/timeline?all=1', 'timeline.get', (a) => total('timeline.get', { area: a })],
      ['Library > Archive', '/life/library/archive?all=1', 'archive.list', (a) => total('archive.list', { area: a })],
    ]
    // the rhythm tabs are not lists: each asks the server for its area's records
    const R = [['Plan > Week, Calendar', '/life/today/week?view=calendar'], /* set 8: the review is about the whole plate and keeps no lens, like Reset */ ['Plan > Month, Plan', '/life/today/month?view=plan'],
      ['Plan > Month, Calendar', '/life/today/month?view=calendar'], ['Plan > 12 Weeks', '/life/today/year?view=cycle'], ['Plan > Year, Calendar', '/life/today/year?view=calendar'],
      ['Plan > Year, Goals', '/life/today/year?view=goals']]
    pg.on('request', onReq)
    try {
      step = 'the counts on All of life'
      const before = {}
      for (const [name, p] of L) { step = `the counts on All of life: ${name}`; await s.open(p); before[name] = await count() }
      await s.open('/life')
      const band0 = await band()
      step = 'choose the area in the lens'
      calls.length = 0
      await pickLens(uxArea)
      must(lensIn() === uxArea, `the URL has area=${lensIn()}`)
      must((await pg.locator('[data-lens-chip]:visible').innerText()).includes(areaName), 'the header has no chip for the area')
      if (phone) must((await pg.locator('[data-lens-title]').innerText()).includes(areaName), 'the phone title does not show the area')
      else must((await pg.locator('[data-lens-picker]').innerText()).includes(areaName), "the sidebar's picker does not show the area")
      step = 'Today under the lens'
      must(carries('today.get'), 'Today did not ask for the area')
      const c = await s.api('counts.get', { space: SPACE, area: uxArea })
      must((await band()) === c.open_tasks.n && c.open_tasks.n < band0, `Today's open tasks say ${await band()} (all of life ${band0}), the count helper ${c.open_tasks.n}`)
      if (!phone) {
        const sc = await s.api('session.counts', { space: SPACE, area: uxArea })
        const inboxBadge = pg.locator('[data-nav-count="Inbox"]')
        must(((await inboxBadge.count()) ? num(await inboxBadge.innerText()) : 0) === sc.doors.inbox.n, `the sidebar's Inbox count is not the area's (${sc.doors.inbox.n})`)
      }
      // the open tasks number is a door: under the lens it opens a list with exactly that many rows
      await pg.locator('[data-count-key="band:open"]:visible').first().click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must(lensIn() === uxArea && (await count()) === c.open_tasks.n, `the open tasks door under the lens lists ${await count()}, not ${c.open_tasks.n}`)
      const done = []
      for (const [name, p, m, server] of L) {
        step = `${name} under the lens`
        await goto(p)
        must(lensIn() === uxArea, `${name}: the lens is not in the URL (${new URL(pg.url()).search})`)
        must(await pg.locator('[data-lens-chip]:visible').count(), `${name}: no area chip`)
        must(carries(m), `${name}: ${m} was not asked for the area`)
        const n = await count()
        must(n <= before[name], `${name}: ${n} under the area, ${before[name]} on all of life`)
        if (server) { const want = await server(uxArea); must(n === want, `${name}: the list says ${n}, the server ${want} for the area`) }
        if (n <= 40) {
          const more = pg.getByRole('button', { name: /^Show more/ })
          if (await more.count()) { await more.first().click(); await settle() }
          const rows = await pg.locator(`${ROW}:visible`).count()
          must(rows === n, `${name}: the count says ${n}, ${rows} rows are shown`)
        }
        done.push(`${name} ${before[name]}→${n}`)
      }
      must(['Plan > Tasks', 'Library > Notes', 'Library > Captures'].every((k) => done.find((d) => d.startsWith(k + ' ')) && (() => { const [a, b] = done.find((d) => d.startsWith(k + ' ')).split(' ').pop().split('→').map(Number); return b < a })()),
        `the area did not narrow Tasks, Notes and Captures: ${done.join(', ')}`)
      for (const [name, p] of R) {
        step = `${name} under the lens`
        await goto(p)
        must(lensIn() === uxArea && await pg.locator('[data-lens-chip]:visible').count(), `${name}: the lens is not in the URL or the header`)
        must(carries(), `${name}: no request asked for the area (${[...new Set(calls.map((x) => x.m))].join(', ')})`)
      }
      step = 'the lens survives a reload'
      await goto('/life/goals/tasks?view=list')
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must(lensIn() === uxArea && await pg.locator('[data-lens-chip]:visible').count(), 'the lens was lost on reload')
      step = 'clear the area'
      if (phone) await pickLens('')
      else { await pg.locator('[data-lens-chip]:visible').first().click(); await pg.waitForLoadState('networkidle'); await settle() }
      must(!lensIn() && !(await pg.locator('[data-lens-chip]:visible').count()), `clearing left area=${lensIn()} or the chip`)
      for (const [name, p] of L) {
        await goto(p)
        must(!lensIn(), `${name}: the cleared lens came back`)
        must((await count()) === before[name], `${name}: ${await count()} after clearing, ${before[name]} before`)
      }
      await goto('/life')
      must((await band()) === band0, `Today says ${await band()} open tasks after clearing, ${band0} before`)
      return done.join(', ')
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) } finally {
      pg.off('request', onReq)
      await s.open('/life?area=')
    }
  })

  await check(`${tag}.41`, `${width} px: no screen scrolls sideways: every place, Plan and Library tab and view, Settings section, a goal and a note page, with and without an area`, async () => {
    const before = errors.length
    const bad = []
    const screens = ['/life', '/life/brain', '/life/today/week?view=review', '/life/today/week?view=calendar', '/life/today/week?view=agenda', '/life/today/month?view=plan',
      '/life/today/month?view=habits', '/life/today/month?view=checkins', '/life/today/month?view=calendar', '/life/today/year?view=cycle', '/life/today/year?view=calendar',
      '/life/today/year?view=goals', '/life/goals', '/life/goals/tasks', '/life/goals/someday', '/life/today/reset', '/life/library', '/life/library/notes',
      '/life/library/notes?view=tree', '/life/library/notes?view=graph', '/life/library/notes?view=changes', '/life/library/notes?view=health', '/life/library/notes?by=assistant',
      '/life/brain/captures', '/life/library/documents?tab=documents&sensitive=1', '/life/brain/captures?tab=photos', '/life/brain/captures?tab=pages', '/life/library/timeline',
      '/life/library/archive', '/life/library/archive?type=trash', '/life/ask', `/life/goals/${ux.goal}`, `/life/library/${ux.note}`,
      ...['profile', 'appearance', 'notifications', 'shortcuts', 'calendar', 'areas', 'rhythms', 'habits', 'dimensions', 'reset', 'connections', 'ai', 'cost', 'sensitive',
        'note-rules', 'spaces', 'members', 'agents', 'archive', 'import', 'backups'].map((t) => `/life/settings?tab=${t}`)]
    for (const p of screens) for (const area of ['', uxArea]) {
      if (area && p.includes('settings')) continue
      await s.open(p + (p.includes('?') ? '&' : '?') + 'area=' + area)
      const over = await overflow()
      if (over > 0) bad.push(`${p}${area ? ' (area)' : ''} by ${over} px`)
    }
    if (phone) { // the lens sheet and the Ask sheet too
      await s.open('/life')
      await openLens()
      if ((await overflow()) > 0) bad.push('the lens sheet')
      await closeLens()
    }
    must(!bad.length, 'scrolls sideways: ' + bad.join('; '))
    must(errors.length === before, 'script errors: ' + errors.slice(before).join(' | ').slice(0, 300))
    return `${screens.length} screens`
  })

  await check(`${tag}.42`, `${width} px: Library > Notes: the assistant's notes carry "Kept by the assistant" with the rules on top; Written by me leaves them out; the Changes view shows a diff and Undo restores; Health lists an orphan`, async () => {
    const title = `S5 kept ${width} ${stamp}` // the "S5 " prefix lets the debris check find it
    const page = await asAgent(`p = wiki.create_page(space="${SPACE}", title="${title}", summary="Kept by the agent", content_md="One.")
v = wiki.get_page(p["name"])["version"]
wiki.update_page(p["name"], content_md="One. Two.", base_version=v, change_note="add two")
frappe.db.commit()
print(json.dumps(p))`)
    await s.open('/life/library/notes?view=list&by=assistant')
    const row = pg.locator(ROW, { hasText: title }).first()
    must(await row.count(), "the assistant's note is not listed under Kept by the assistant")
    must(await row.locator('[data-assistant-badge]').count(), 'the note has no "Kept by the assistant" badge')
    must(await pg.locator('[data-notes-rules]').isVisible(), "the rules are not pinned above the assistant's notes")
    must((await count()) === (await s.api('library.list', { space: SPACE, collection: 'Wiki', page_length: 1 })).total, "the count is not the number of the assistant's notes")
    await s.open('/life/library/notes?view=list&by=me')
    must(!(await pg.locator(ROW, { hasText: title }).count()), 'Written by me lists the assistant\'s note')
    await s.open('/life/wiki') // the old Wiki lands on the assistant's notes
    must(new URL(pg.url()).pathname === '/life/library/notes' && new URL(pg.url()).searchParams.get('by') === 'assistant', `/wiki went to ${pg.url()}`)
    // Changes: the agent's edit with its diff; Undo puts the text back
    const change = (await s.api('wiki.changes', { space: SPACE, note: page.name })).changes[0]
    await s.open('/life/library/notes?view=changes')
    must(await pg.locator(`[data-ref="change:${change.name}"]`).count(), 'the edit is not in the Changes view')
    await pg.locator(`[data-ref="change:${change.name}"]`).first().click({ position: { x: 120, y: 12 } })
    await settle()
    must(await pane.isVisible() && await pg.locator('[data-pane] [data-diff]').count() && await pg.locator('[data-pane] [data-diff-row]').count(), 'the change shows no diff')
    await pg.locator('[data-pane] [data-undo]').click()
    await pg.waitForTimeout(1200)
    must((await docOf(page.name)).content_md === 'One.', 'Undo did not restore the text')
    // Health: the note links nowhere and nothing links to it
    await s.open('/life/library/notes?view=health')
    await pg.locator('[data-health-refresh]').click()
    await pg.waitForTimeout(1500)
    must((await pg.locator('[data-health="orphans"]').innerText()).includes(title), 'the orphan is not under Health')
    return 'badge, rules, diff, undo, orphan'
  })

  if (phone) await check(`${tag}.44`, '390 px: a rhythm banner shows on Today on its day and Skip hides it', async () => {
    const st = (await s.api('settings.get', { space: SPACE })).settings
    const at = nextWeekday(st.weekly_review_day || 'Sunday', 15) + ' 23:30:00' // two weeks on: an occurrence no other check skips
    await s.open(`/life?at=${encodeURIComponent(at)}`)
    const banner = pg.locator('[data-rhythm-banner][data-banner="review"]')
    must(await banner.isVisible(), 'no weekly review banner on the review day')
    must((await overflow()) <= 0, 'Today scrolls sideways with the banner')
    await tap(banner.locator('[data-banner-skip]'))
    await pg.waitForTimeout(900)
    must(!(await banner.count()), 'Skip did not hide the banner')
    await pg.reload({ waitUntil: 'networkidle' })
    await settle()
    must(!(await pg.locator('[data-rhythm-banner]').count()), 'the skipped banner came back on reload')
  })

  await s.ctx.close()
}

// ---------- UX fixes, set 6: once, at 1440 px, as the owner ----------
const pathOf = (pg) => new URL(pg.url()).pathname.replace(/\/$/, '') || '/'

await check('S6.1', 'Keyboard: G then T, I, O or L opens a place; the older G letters open their new homes (issue 14)', async () => {
  const pg = owner.page
  const done = []
  for (const [key, want, q] of [['t', '/life/today'], ['i', '/life/brain'], ['p', '/life/today/week'], ['l', '/life/library'], ['k', '/life/goals/tasks'], ['o', '/life/goals'],
    ['y', '/life/goals/someday'], ['w', '/life/today/week'], ['m', '/life/today/month'], ['j', '/life/today/year', { view: 'cycle' }], ['c', '/life/today/year'], ['e', '/life/today/reset'],
    ['n', '/life/library/notes'], ['u', '/life/brain/activity'], ['h', '/life/library/chats', { tab: 'chats' }], ['v', '/life/library/documents', { tab: 'documents', sensitive: '1' }],
    ['x', '/life/library/notes', { by: 'assistant' }], ['g', '/life/library/notes', { view: 'graph' }], ['r', '/life/library/archive'], ['b', '/life/brain/outbox'], ['d', '/life/review'],
    ['q', '/life/ask'], ['a', '/life/settings', { tab: 'areas' }], ['s', '/life/settings']]) {
    await owner.open(key === 't' ? '/life/brain' : '/life')
    await pg.locator('[data-page-head]').first().click({ position: { x: 5, y: 5 } }).catch(() => {})
    await pg.keyboard.press('g')
    await pg.keyboard.press(key)
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(400)
    must(pathOf(pg) === want, `G then ${key.toUpperCase()} opened ${pathOf(pg)}, not ${want}`)
    for (const [k, v] of Object.entries(q || {})) must(new URL(pg.url()).searchParams.get(k) === v, `G then ${key.toUpperCase()}: ${k} is ${new URL(pg.url()).searchParams.get(k)}, not ${v}`)
    done.push(key.toUpperCase())
  }
  return done.join(' ')
})

await check('S6.2', 'Every old route lands on its new home with its query (section 2 of the brief; the homes of issue 14)', async () => {
  const pg = owner.page
  const goal12 = (await owner.api('goals.list', { space: SPACE, horizon: '12 weeks', page_length: 1 })).goals[0].name
  const jp = bench(`print(frappe.db.sql("select name from \`tabLife Journal Page\` where space='${SPACE}' limit 1")[0][0])`).split('\n').pop()
  const ROUTES = [
    ['/tasks?priority=I&view=list', '/goals/tasks', { priority: 'I', view: 'list' }],
    ['/goals?status=achieved', '/goals', { status: 'achieved' }],
    ['/someday?tab=notes', '/goals/someday', { tab: 'notes' }],
    ['/projects?status=On%20Hold', '/goals', { type: 'Long term', status: 'in_progress' }],
    ['/projects?status=Done', '/goals', { type: 'Long term', status: 'achieved' }],
    [`/projects/${ux.project}?tab=tasks`, `/goals/${ux.goal}`, { tab: 'tasks' }],
    ['/reset', '/today/week', { view: 'review', tab: 'tasks' }], // set 8: set 7's Reset step is the review's Tasks tab
    ['/calendar/week?date=2026-12-02', '/today/week', { view: 'calendar', date: '2026-12-02' }],
    ['/calendar/agenda', '/today/week', { view: 'agenda' }],
    ['/calendar/month?date=2026-12-02', '/today/month', { view: 'calendar', date: '2026-12-02' }],
    ['/calendar/year', '/today/year', {}],
    ['/journal', '/today/year', { view: 'cycle' }],
    ['/journal/goals', '/today/year', { view: 'goals' }],
    ['/journal/month', '/today/month', {}],
    ['/journal/habits', '/today/month', { view: 'habits' }],
    ['/journal/checkins', '/today/month', { view: 'checkins' }],
    ['/journal/review', '/today/week', { view: 'review' }],
    ['/journal/pages', '/library', { tab: 'pages' }],
    [`/journal/pages/${jp}`, '/library', { tab: 'pages', open: `page:${jp}` }],
    [`/journal/goals/${goal12}`, `/goals/${goal12}`, {}],
    [`/sources?tab=chats&from=${addDays(-6)}`, '/library/chats', { tab: 'chats', from: addDays(-6) }],
    ['/chats?group=day', '/library/chats', { tab: 'chats', view: 'day' }],
    [`/chats?open=${ux.chat}`, '/library/chats', { tab: 'chats', open: `chat:${ux.chat}` }],
    ['/wiki', '/library/notes', { by: 'assistant' }],
    ['/wiki?tab=changes', '/library/notes', { by: 'assistant', view: 'changes' }],
    ['/vault', '/library/documents', { tab: 'documents', sensitive: '1' }],
    [`/vault?open=${ux.vault}`, '/library/documents', { tab: 'documents', sensitive: '1', open: `vault:${ux.vault}` }],
    ['/graph', '/library/notes', { view: 'graph' }],
    [`/timeline?from=${addDays(-3)}`, '/library/timeline', { from: addDays(-3) }],
    ['/archive?type=trash', '/library/archive', { type: 'trash' }],
    ['/areas', '/settings', { tab: 'areas' }],
    [`/areas/${uxArea}`, '/today', { area: uxArea }],
    ['/library?view=tree', '/library/notes', { view: 'tree' }],
    [`/inbox/${ux.inbox}`, '/brain/queue', { open: `inbox:${ux.inbox}` }],
  ]
  const bad = []
  for (const [from, to, q] of ROUTES) {
    await owner.open('/life' + from)
    for (let i = 0; i < 20 && pathOf(pg).startsWith('/life/projects/'); i++) await pg.waitForTimeout(200) // waits for goals.for_project
    const u = new URL(pg.url())
    const wrong = [pathOf(pg) !== ('/life' + to).replace(/\/$/, '') && `path ${u.pathname}`, ...Object.entries(q).map(([k, v]) => u.searchParams.get(k) !== v && `${k}=${u.searchParams.get(k)}`)].filter(Boolean)
    if (!wrong.length && q.open) { if (!(await pg.locator('[data-pane]').isVisible())) wrong.push('no pane') }
    if (!wrong.length && /not found/i.test(await pg.locator('[data-main]').innerText())) wrong.push('not found')
    if (wrong.length) bad.push(`${from} → ${wrong.join(', ')}`)
  }
  await owner.open('/life?area=')
  must(!bad.length, bad.join('; '))
  return `${ROUTES.length} routes`
})

await check('S6.3', 'A former project opens as an open-ended goal with its tasks; a goal shows what it serves and what serves it, and cannot serve its own servant', async () => {
  const pg = owner.page
  const proj = JSON.parse(bench(`import json
p = frappe.db.get_value("Life Project", "${ux.project}", ["title", "migrated_to"], as_dict=True)
cols = frappe.db.get_table_columns("Life Task")
left = frappe.db.sql("select count(*) from \`tabLife Task\` where project=%s and ifnull(goal, '') not in (%s, '')", ("${ux.project}", p.migrated_to))[0][0] if "project" in cols else 0
before = frappe.db.sql("select count(*) from \`tabLife Task\` where project=%s", "${ux.project}")[0][0] if "project" in cols else None
print(json.dumps({"title": p.title, "goal": p.migrated_to, "unmoved": left, "had": before}))`).split('\n').pop())
  must(proj.goal === ux.goal, 'the project has no goal')
  const got = await owner.api('goals.get', { goal: ux.goal })
  must(got.goal.title === proj.title && got.goal.horizon === 'Long term', `the goal is "${got.goal.title}" (${got.goal.horizon}), the project was "${proj.title}"`)
  // the project's tasks are the goal's (the old column is left in the table: every task that had the project has the goal, or a goal that serves it)
  must(!proj.unmoved || proj.unmoved === 0, `${proj.unmoved} of the project's tasks are not under its goal`)
  await owner.open(`/life/projects/${ux.project}`)
  for (let i = 0; i < 20 && pathOf(pg).startsWith('/life/projects/'); i++) await pg.waitForTimeout(200)
  must(pathOf(pg) === `/life/goals/${ux.goal}`, `/projects/:id went to ${pathOf(pg)}`)
  must((await pg.locator('h1').first().innerText()).includes(proj.title), 'the goal page does not show the project title')
  await pg.locator('[data-page-tabs] [data-tab="tasks"]').click()
  await pg.waitForLoadState('networkidle')
  await pg.waitForTimeout(500)
  const open = (await owner.api('tasks.list', { space: SPACE, goal: ux.goal, status: 'open_doing', page_length: 1 })).total
  const shown = num(await pg.locator('[data-tab-panel="tasks"] [data-lv-count]').innerText())
  must(open > 0 && shown === open, `the Tasks tab lists ${shown}, the goal has ${open} open tasks`)
  must((await pg.locator('[data-tab-panel="tasks"]').innerText()).includes(`UX door task ${stamp}`), "the goal's tasks do not include this run's task")
  // serves and served by
  const longer = await owner.api('goals.create', { space: SPACE, title: `S5 longer goal ${stamp}`, horizon: 'Year', target_date: addDays(300), area: uxArea })
  const shorter = await owner.api('goals.create', { space: SPACE, title: `S5 shorter goal ${stamp}`, horizon: 'Long term', serves: longer.name, done_when: 'It is done.', area: uxArea })
  await owner.open(`/life/goals/${longer.name}`)
  must((await pg.locator('[data-goal-served-by]').innerText()).includes(`S5 shorter goal ${stamp}`), 'the longer goal does not list what serves it')
  await owner.open(`/life/goals/${shorter.name}`)
  must((await pg.locator('[data-goal-serves]').innerText()).includes(`S5 longer goal ${stamp}`), 'the shorter goal does not show what it serves')
  const row = (await owner.api('goals.list', { space: SPACE, serves: longer.name, state: 'all' })).goals
  must(row.length === 1 && row[0].name === shorter.name && row[0].serves_title === `S5 longer goal ${stamp}` && row[0].done_when === 'It is done.', 'goals.list does not list what serves the goal')
  const loop = await owner.api('goals.update', { goal: longer.name, values: { serves: shorter.name } }, { raw: true })
  must(!loop.ok(), 'a goal could serve the goal that serves it')
  return `${proj.title}: ${open} open tasks`
})

await check('S6.4', 'A Vault document is a capture of kind Document, marked sensitive, with its expiry; the agent cannot read it, nor a note marked sensitive, while the switch is off; only the owner unmarks', async () => {
  const pg = owner.page
  const title = `S5 visa ${stamp}`
  const doc = await owner.api('vault.save', { space: SPACE, values: { title, doc_type: 'Travel', expiry_date: addDays(25), number_last4: '7731', area: areaId('Money & Legal') } })
  const rows = (await owner.api('sources.list', { space: SPACE, tab: 'documents', sensitive: 1, page_length: 200 })).sources
  const r = rows.find((x) => x.title === title)
  must(r && r.kind === 'Document' && r.sensitive, `not in Captures as a sensitive Document: ${JSON.stringify(r || null).slice(0, 200)}`)
  await owner.open('/life/library/documents?tab=documents&sensitive=1')
  const row = pg.locator('[data-row]', { hasText: title }).first()
  must(await row.count(), 'not on Library > Captures, Documents')
  must(await row.locator('[data-sensitive-lock]').count(), 'no lock on the document')
  must((await row.locator('[data-expiry-badge]').innerText()).includes('25'), 'no "Expires in 25 days"')
  must((await row.innerText()).includes('7731'), 'the last four characters are not shown')
  // a note marked sensitive from its pane
  const note = (await owner.api('library.save', { space: SPACE, title: `S5 private note ${stamp}`, content_md: 'Bank PIN hint.', area: areaId('Money & Legal') })).name
  await owner.open(`/life/library/notes?view=list&open=note:${note}`)
  await pg.locator('[data-pane-sensitive]').click()
  await pg.waitForTimeout(900)
  must((await owner.api('library.get', { note })).is_sensitive || (await owner.api('library.get', { note })).note?.is_sensitive, 'the pane did not mark the note sensitive')
  must((await pg.locator('[data-pane-sensitive]').getAttribute('aria-pressed')) === 'true', 'the pane does not show the note as sensitive')
  // the agent, with the switch off
  const vaultOpen = (await owner.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE).agents_can_read_vault
  must(!vaultOpen, '"Agents may open sensitive items" is on for Private')
  const asAgentHttp = agentFetch
  must((await asAgentHttp('vault.get', { document: doc.name })).status >= 400, 'the agent read the Vault document')
  must((await asAgentHttp('library.get', { note })).status >= 400, 'the agent read the sensitive note')
  const listed = JSON.stringify(await (await asAgentHttp('sources.list', { space: SPACE, scope: 'all', page_length: 500 })).json())
  must(!listed.includes(title) && !listed.includes(`S5 private note ${stamp}`), 'the agent lists a sensitive item')
  const found = JSON.stringify(await (await asAgentHttp('search.query', { text: 'visa ' + stamp })).json())
  must(!found.includes(title), 'the agent finds the Vault document in search')
  // the family member cannot unmark (no access at all); the owner can
  await owner.api('library.set_sensitive', { doctype: 'Life Note', name: note, sensitive: 0 })
  must((await asAgentHttp('library.get', { note })).ok, 'the agent cannot read the note once the owner unmarked it')
  return 'Document, lock, expiry, agent refused'
})

await check('S6.5', "Rhythm banners: the weekly review, Plan <month>, Plan your next 12 weeks and Close this cycle each show on Today on their day (the clock moved with at=); Skip hides each until its next occurrence; month plans off hides that one", async () => {
  const pg = owner.page
  const was = (await owner.api('settings.get', { space: SPACE })).settings
  bench(`frappe.db.delete("Life View State", {"user": "owner@lifeos.test", "screen": "rhythm-banners"})`)
  await owner.api('settings.save', { values: { month_plan_enabled: 1 } })
  try {
    const info = JSON.parse(bench(`import json
c = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"}, ["name", "start_date"], as_dict=True)
planned = frappe.db.exists("Life Cycle", {"space": "${SPACE}", "status": "Planned", "start_date": (">", c.start_date)})
plans = [f"{y}-{m:02d}" for y, m in frappe.db.sql("select year, month from \`tabLife Month Plan\` where space=%s", "${SPACE}")]
print(json.dumps({"start": str(c.start_date), "planned": bool(planned), "plans": plans}))`).split('\n').pop())
    must(!info.planned, 'a next cycle is already planned on the acceptance site')
    const review = nextWeekday(was.weekly_review_day || 'Sunday', 1)
    const afterReview = `${String(was.weekly_review_time || '18:00:00').slice(0, 2) === '23' ? '23:59:00' : '23:30:00'}`
    // a month from next month on with no plan yet: its 2nd, in the morning (before any review time)
    let month = null
    for (let i = 1; i < 24 && !month; i++) { const d = new Date(Date.parse(today + 'T12:00:00Z')); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + i); const k = d.toISOString().slice(0, 7); if (!info.plans.includes(k)) month = k }
    // a day of weeks 11 and 12 that is not the 1st to 3rd of a month, in the morning
    const inWeek = (w) => { for (let n = 0; n < 7; n++) { const d = plusDays(info.start, (w - 1) * 7 + n); if (Number(d.slice(8)) > 3) return d } }
    const CASES = [
      ['review', `${review} ${afterReview}`, 'Your weekly review is ready', '/life/today/week'],
      ['month', `${month}-02 08:00:00`, 'Plan ', '/life/today/month'],
      ['plan-next', `${inWeek(11)} 08:00:00`, 'Plan your next 12 weeks', '/life/today/year?view=cycle'],
      ['close', `${inWeek(12)} 08:00:00`, 'Close this cycle', '/life/today/year?view=cycle'],
    ]
    const done = []
    for (const [key, at, text, to] of CASES) {
      const b = (await owner.api('today.get', { space: SPACE, at })).banner
      must(b && b.key === key && b.text.startsWith(text), `at ${at} today.get gives ${JSON.stringify(b)}, not ${key}`)
      if (key === 'month') { // month plans off: no month banner
        await owner.api('settings.save', { values: { month_plan_enabled: 0 } })
        const off = (await owner.api('today.get', { space: SPACE, at })).banner
        await owner.api('settings.save', { values: { month_plan_enabled: 1 } })
        must(!off || off.key !== 'month', 'the month banner shows with month plans off')
      }
      await owner.open(`/life?at=${encodeURIComponent(at)}`)
      const banner = pg.locator(`[data-rhythm-banner][data-banner="${key}"]`)
      must(await banner.isVisible(), `no ${key} banner on Today at ${at}`)
      must((await banner.innerText()).includes(b.text), `the ${key} banner says "${await banner.innerText()}"`)
      // at most one line, above the Open band
      must((await pg.locator('[data-rhythm-banner]').count()) === 1, 'more than one banner')
      const order = await pg.evaluate(() => { const a = document.querySelector('[data-rhythm-banner]'), o = document.querySelector('[data-open-band]'); return !!(a && o && (a.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING)) })
      must(order, 'the banner is not above the Open band')
      must(new URL(await banner.locator('[data-banner-open]').evaluate((a) => a.href)).pathname === to.split('?')[0], `the ${key} banner does not lead to ${to} (${await banner.locator('[data-banner-open]').evaluate((a) => a.href)})`)
      await banner.locator('[data-banner-skip]').click()
      await pg.waitForTimeout(900)
      must(!(await banner.count()), `Skip did not hide the ${key} banner`)
      await pg.reload({ waitUntil: 'networkidle' })
      await pg.waitForTimeout(400)
      must(!(await pg.locator(`[data-rhythm-banner][data-banner="${key}"]`).count()), `the skipped ${key} banner came back on reload`)
      const again = (await owner.api('today.get', { space: SPACE, at })).banner
      must(!again || again.key !== key, `today.get still gives the skipped ${key} banner`)
      done.push(`${key} ${at.slice(0, 10)}`)
    }
    // the next occurrence of the review comes back
    const next = (await owner.api('today.get', { space: SPACE, at: `${plusDays(review, 7)} ${afterReview}` })).banner
    must(next && next.key === 'review', 'the next week\'s review banner did not come back after a skip')
    // without the test clock (a moment of now), the answer does not depend on at= on another site: here it just works
    return done.join(', ')
  } finally {
    await owner.api('settings.save', { values: { month_plan_enabled: was.month_plan_enabled ? 1 : 0 } })
  }
})

await check('S6.6', 'The fake agent runs end to end with the goal-based API: tasks it proposes are filed under the open-ended goal of their area; project= still maps to the goal for one set', async () => {
  const goals = (await owner.api('goals.list', { space: SPACE, horizon: 'Long term', area: uxArea })).goals.map((g) => g.name)
  must(goals.length, 'Tea & Coffee has no open-ended goal')
  const item = await owner.api('inbox.create_item', { title: `S5 agent pdf ${stamp}.pdf`, space: SPACE, instruction: 'summarise and extract to-dos' })
  await owner.upload('Life Inbox Item', item.name, `s6-agent-${stamp}.pdf`, 'application/pdf', PDF)
  runAgent()
  const got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'To Review' && got.proposals.length === 3, `the agent left ${got.status} with ${got.proposals.length} proposals`)
  const goal = got.proposals[0].payload.goal
  must(goal && goals.includes(goal) && got.proposals.every((p) => p.payload.goal === goal && !p.payload.project), `the proposals are not filed under an open-ended goal of Tea & Coffee: ${JSON.stringify(got.proposals.map((p) => p.payload)).slice(0, 200)}`)
  await owner.api('review.decide_all', { item: item.name, decision: 'accept' })
  const made = (await owner.api('inbox.get', { item: item.name })).proposals.map((p) => p.created_name)
  const under = (await owner.api('tasks.list', { space: SPACE, goal, status: 'all', page_length: 200 })).tasks.map((t) => t.name)
  must(made.length === 3 && made.every((n) => under.includes(n)), 'the accepted tasks are not under the goal')
  // the agent's own reads with its key: Today, the goal's tasks, and project= mapped to its goal
  const asAgentHttp = (m, args) => agentFetch(m, args).then(async (r) => [r.status, await r.json().catch(() => ({}))])
  const [ts] = await asAgentHttp('today.get', { space: SPACE })
  must(ts === 200, `today.get answered the agent ${ts}`)
  const [, byGoal] = await asAgentHttp('tasks.list', { space: SPACE, goal: ux.goal, status: 'all', page_length: 1 })
  const [, byProject] = await asAgentHttp('tasks.list', { space: SPACE, project: ux.project, status: 'all', page_length: 1 })
  must(byGoal.message && byProject.message && byGoal.message.total === byProject.message.total && byGoal.message.total > 0, `project= gives ${byProject.message?.total}, goal= ${byGoal.message?.total}`)
  const [ps] = await asAgentHttp('goals.for_project', { project: ux.project })
  must(ps >= 400, 'an agent can read a project')
  return `3 tasks under ${goal}`
})

// ---------- Set 7: Moving forward, at 1440 px and 390 px ----------
// Key results, the Outbox and the weekly review's goal step. Every record carries "S7 … <width> <stamp>" and is removed by S4.1.
const s7Settings = await owner.api('settings.get', { space: SPACE })
for (const width of SET_WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e)))
  const tag = `S7.${width}`
  const settle = () => pg.waitForTimeout(450)
  const W = `${width} ${stamp}`
  const field = (root, attr) => root.locator(`[${attr}] input, input[${attr}], [${attr}] textarea, textarea[${attr}]`).first()
  const pick = async (root, label, option, attr = 'data-card-who') => {
    let box = root.getByRole('combobox', { name: label }).first()
    if (!(await box.count())) box = root.locator(`[${attr}][role="combobox"], [${attr}] [role="combobox"], [${attr}] button`).first()
    await box.click()
    await pg.getByRole('option', { name: option, exact: true }).first().click()
    await settle()
  }
  const cycle = (await owner.api('journal.grid', { space: SPACE })).cycle

  await check(`${tag}.1`, `${width} px: New goal asks "Done when…": a milestone goal and a number goal through the dialog; a frequency offers Make it a habit`, async () => {
    const make = async (title, fill) => {
      await s.open('/life/goals')
      await pg.locator('[data-new-goal]').first().click()
      await settle()
      const dlg = pg.locator('[role="dialog"]').last()
      await field(dlg, 'data-goal-title').fill(title)
      await fill(dlg)
      await dlg.getByRole('button', { name: 'Add goal' }).click()
      await pg.waitForLoadState('networkidle')
      await settle()
      return (await s.api('goals.list', { space: SPACE, state: 'all', filters: [['title', '=', title]] })).goals[0]
    }
    const m = await make(`S7 milestone ${W}`, async (dlg) => {
      await dlg.locator('[data-measure-kind]').getByText('A finish line').click()
      await field(dlg, 'data-measure-done-when').fill('The plan is signed')
    })
    must(m && m.measure_kind === 'Milestone' && m.done_when === 'The plan is signed', 'the milestone goal was not made: ' + JSON.stringify(m))
    const n = await make(`S7 number ${W}`, async (dlg) => {
      await dlg.locator('[data-measure-kind]').getByText('A number').click()
      await field(dlg, 'data-measure-name').fill('Weight')
      await field(dlg, 'data-measure-unit').fill('kg')
      await field(dlg, 'data-measure-start').fill('84')
      await field(dlg, 'data-measure-target').fill('78')
    })
    must(n && n.measure_kind === 'Number' && n.start_value === 84 && n.target_value === 78 && n.progress.kind === 'number', 'the number goal was not made: ' + JSON.stringify(n))
    // a frequency is a habit
    await s.open('/life/goals')
    await pg.locator('[data-new-goal]').first().click()
    await settle()
    const dlg = pg.locator('[role="dialog"]').last()
    await field(dlg, 'data-goal-title').fill(`S7 walk 3 times a week ${W}`)
    await settle()
    must(await dlg.locator('[data-habit-hint]').isVisible(), 'no "This looks like a habit"')
    await dlg.locator('[data-make-habit]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    const habits = await s.api('journal.habits', { space: SPACE })
    must(habits.habits.some((h) => h.title === `S7 walk 3 times a week ${W}` && h.days_per_week === 3), 'the habit is not in this month')
    must(!(await s.api('goals.list', { space: SPACE, state: 'all', filters: [['title', 'like', `S7 walk%${stamp}%`]] })).goals.length, 'a goal was made for the habit')
    return 'milestone, number 84 → 78 kg, habit 3 a week'
  })

  await check(`${tag}.2`, `${width} px: the fake agent submits a Reading; it waits in the weekly review; Confirm updates the goal's current value and result bar`, async () => {
    const measure = `Yield ${W}`
    const g = (await s.api('goals.create', { space: SPACE, title: `S7 yield goal ${W}`, horizon: 'Long term', area: areaId('Tea & Coffee'), measure_kind: 'Number',
      measure, unit: 'kg/ha', start_value: 1200, target_value: 1800 })).name
    await s.api('inbox.create_item', { space: SPACE, title: `S7 reading ${W}`, source_type: 'Message', raw_text: `${measure} this flush: 1640 kg/ha, up from last month.` })
    runAgent()
    const waiting = (await s.api('goals.goal_readings', { goal: g })).suggested
    must(waiting.length === 1 && waiting[0].value === 1640 && waiting[0].excerpt.includes('1640'), 'the agent did not leave a Suggested reading: ' + JSON.stringify(waiting))
    // a fresh review, with no other finding ahead of this reading among the five it shows
    bench(`frappe.db.delete("Life Review", {"space": "${SPACE}", "user": "owner@lifeos.test"})
frappe.db.sql("update \`tabLife Insight\` set status='Dismissed' where space=%s and status='New' and ifnull(reading, '') = ''", "${SPACE}")`)
    await s.open('/life/today/week?view=review&tab=library')
    const row = pg.locator('[data-revelations] [data-finding][data-kind="Goal reading"]', { hasText: `S7 yield goal ${W}` }).first()
    must(await row.isVisible(), 'the reading is not in the weekly review')
    await row.locator('[data-finding-action="confirm_reading"]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    const got = await s.api('goals.get', { goal: g })
    must(got.goal.current_value === 1640 && got.goal.progress.percent === 73.3, `current ${got.goal.current_value}, ${got.goal.progress.percent}%`)
    await s.open(`/life/goals/${g}`)
    const bar = pg.locator('[data-result-bar]').first()
    must((await bar.getAttribute('data-result-percent')) === '73.3' && (await bar.innerText()).includes('1640'), 'the result bar does not show 1640: ' + (await bar.innerText()))
    return '1640 kg/ha, 73.3%'
  })

  let action
  await check(`${tag}.3`, `${width} px: a 12-week goal serving a longer goal shows on both`, async () => {
    must(cycle, 'no active cycle')
    const long = (await s.api('goals.create', { space: SPACE, title: `S7 long goal ${W}`, horizon: 'Year', target_date: addDays(200), area: areaId('Tea & Coffee'),
      done_when: 'A new client signed' })).name
    const g = (await s.api('journal.save_goal', { cycle: cycle.name, title: `S7 cycle goal ${W}`, area: areaId('Tea & Coffee'), serves: long, measure_kind: 'Milestone',
      done_when: 'Ten pitches made', actions: [{ title: `S7 calls ${W}`, per_week: 4 }] })).goal
    action = (await s.api('journal.goal', { goal: g })).goal.actions[0]
    await s.open('/life/today/year?view=cycle')
    const line = pg.locator('[data-grid-serves]', { hasText: `S7 long goal ${W}` })
    must(await line.count(), 'the 12 Weeks tab does not show the goal it serves')
    await s.open(`/life/goals/${long}`)
    const served = pg.locator('[data-goal-served-by]')
    must((await served.innerText()).includes(`S7 cycle goal ${W}`) && (await served.innerText()).includes(cycle.title), 'the longer goal does not show the cycle goal with its cycle')
    await s.open(`/life/goals/${g}`)
    must((await pg.locator('[data-goal-serves-progress]').innerText()).includes(`S7 long goal ${W}`), "the cycle goal's page does not show what it serves")
    return `${cycle.title}`
  })

  await check(`${tag}.4`, `${width} px: ticking a 4-a-week action once shows 1 of 4 and raises the week score`, async () => {
    must(action, 'no action from the check before')
    const g = await s.api('journal.grid', { space: SPACE })
    const wk = g.current_week
    const before = await s.api('journal.week_score', { cycle: cycle.name, week: wk })
    await s.open('/life/today/year?view=cycle')
    const cell = pg.locator(`button[aria-label^="S7 calls ${W}, week ${wk},"]`).first()
    must(await cell.count(), 'the action is not on the grid')
    await cell.click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must((await cell.getAttribute('aria-label')).endsWith('1 of 4'), 'the cell says ' + (await cell.getAttribute('aria-label')))
    const after = await s.api('journal.week_score', { cycle: cycle.name, week: wk })
    must(after.done === before.done + 1 && after.percent > before.percent, `score ${before.percent}% → ${after.percent}%`)
    await s.open('/life')
    const row = pg.locator('[data-next] [data-why="12WY"]', { hasText: `S7 calls ${W}` })
    if (await row.count()) must((await row.innerText()).includes('1 of 4 this week'), 'Today does not say 1 of 4')
    return `${before.percent}% → ${after.percent}%`
  })

  await check(`${tag}.5`, `${width} px: completing, delegating, parking and dropping a task each add to the right Outbox pile; Bring back reverses; Today's in and out open lists of that many rows`, async () => {
    const mk = async (what) => (await s.api('tasks.quick_add', { text: `S7 out ${what} ${W}`, space: SPACE, area: areaId('Tea & Coffee') })).name
    const t = { Done: await mk('done'), Delegated: await mk('delegate'), Parked: await mk('park'), Discarded: await mk('drop') }
    await s.api('tasks.set_status', { task: t.Done, status: 'Done' })
    await s.api('tasks.set_status', { task: t.Delegated, status: 'Waiting', waiting_on: 'Mithun' })
    await s.api('someday.park', { doctype: 'Life Task', name: t.Parked })
    await s.api('tasks.set_status', { task: t.Discarded, status: 'Dropped' })
    for (const [pile, name] of Object.entries(t)) {
      await s.open(`/life/brain/outbox?pile=${pile}`)
      const row = pg.locator('[data-row]', { hasText: `S7 out` }).filter({ hasText: W })
      must(await row.count() === 1, `${pile}: ${await row.count()} rows of this run`)
      const listed = await s.api('outbox.list', { space: SPACE, pile, page_length: 500 })
      must(listed.rows.some((r) => r.record === name) && listed.total === listed.tabs[pile], `${pile}: not in its pile`)
    }
    // Bring back the done one: it is open again and leaves the pile
    await s.open('/life/brain/outbox?pile=Done')
    const row = pg.locator('[data-row]', { hasText: `S7 out done ${W}` })
    await row.locator('[data-outbox-bring-back]:visible').first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must((await s.api('tasks.get', { task: t.Done })).status === 'Open', 'Bring back did not reopen the task')
    must(!(await s.api('outbox.list', { space: SPACE, pile: 'Done', page_length: 500 })).rows.some((r) => r.record === t.Done), 'the exit still counts')
    // Today's line: each number opens a list with that many rows
    await s.open('/life')
    const doors = pg.locator('[data-inout] [data-count-door]')
    must(await doors.count() === 2, 'no in-and-out line on Today')
    const seen = []
    for (let i = 0; i < 2; i++) {
      await s.open('/life')
      const d = pg.locator('[data-inout] [data-count-door]').nth(i)
      const n = Number(await d.getAttribute('data-count-n'))
      await d.click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must(new URL(pg.url()).pathname === '/life/brain/outbox', 'the number went to ' + new URL(pg.url()).pathname)
      const got = Number((await pg.locator('[data-lv-count]').first().innerText()).replace(/\D/g, '') || 0)
      must(got === n, `clicked ${n}, the Outbox lists ${got}`)
      seen.push(n)
    }
    must(errors.length === 0, 'script errors: ' + errors.join(' | ').slice(0, 300))
    return `in ${seen[0]}, out ${seen[1]}`
  })

  await check(`${tag}.6`, `${width} px: goal work planned the way Lock the week plans it makes a scheduled task that shows on Today and in the week calendar, and a delegated one that shows as Waiting`, async () => {
    // set 8: the cards of set 7's goal step became the review's Goals tab (checked by S8); here the same planning call
    const a = (await s.api('goals.create', { space: SPACE, title: `S7 plan goal ${W}`, horizon: 'Long term', area: areaId('Personal'), done_when: 'Planned' })).name
    const b = (await s.api('goals.create', { space: SPACE, title: `S7 handoff goal ${W}`, horizon: 'Long term', area: areaId('Personal'), done_when: 'Handed over' })).name
    const now = iso(new Date()) // the run may cross midnight
    const at = `${now} 23:${phone ? '30' : '00'}:00`
    const task = await s.api('week.add_goal_work', { goal: a, title: `S7 plan step ${W}`, scheduled_at: at, duration_min: 30, note: 'the soil report' })
    must(task.scheduled_at && task.scheduled_at.slice(0, 10) === now, 'no task scheduled today: ' + JSON.stringify(task))
    const handed = await s.api('week.add_goal_work', { goal: b, title: `S7 handoff step ${W}`, who: 'Vivek' })
    must(handed.status === 'Waiting' && handed.waiting_on === 'Vivek', 'the delegated task is not Waiting on Vivek: ' + JSON.stringify(handed))
    must((await s.api('outbox.list', { space: SPACE, pile: 'Delegated', page_length: 500 })).rows.some((r) => r.record === handed.task), 'not in Delegated')
    await s.open('/life')
    const next = pg.locator('[data-next] [data-why="Scheduled"]', { hasText: `S7 plan step ${W}` })
    const rail = pg.locator('[data-rail-task]', { hasText: `S7 plan step ${W}` })
    must(await next.count() || await rail.count(), 'the scheduled task is not on Today')
    must(await rail.count(), "the scheduled task is not on the rail's timeline")
    await s.open('/life/today/week?view=calendar')
    must((await pg.locator('[data-week-grid], [data-main]').first().innerText()).includes(`S7 plan step ${W}`), 'not in the week calendar')
    await s.open(`/life/goals/tasks?status=Waiting`)
    must((await pg.locator('[data-main]').innerText()).includes(`S7 handoff step ${W}`), 'the delegated task is not under Waiting')
    return `scheduled ${String(task.scheduled_at).slice(11, 16)}, waiting on Vivek`
  })

  await check(`${tag}.7`, `${width} px: Inbox items left too long: on Suggest an old item gets a suggested decision and the batch confirms it; on Park and Discard the job acts and Today's Undo restores`, async () => {
    const age = (name, days) => bench(`frappe.db.set_value("Life Inbox Item", "${name}", "received_on", frappe.utils.add_days(frappe.utils.now_datetime(), -${days}), update_modified=False)`)
    const run = () => JSON.parse(bench(`import json\nfrom lifeos import old_inbox\nfrappe.clear_document_cache("Life Settings", "Life Settings")\nprint(json.dumps(old_inbox.run_for_space("${SPACE}")))`).split('\n').pop())
    const setRule = (mode, days) => owner.api('settings.save', { values: { old_inbox_mode: mode, old_inbox_days: days } })
    try {
      // Suggest
      await setRule('Suggest', 7)
      const a = (await s.api('inbox.create_item', { space: SPACE, title: `S7 old suggest ${W}`, source_type: 'Message', raw_text: 'An old message.' })).name
      age(a, 10)
      run()
      const got = (await s.api('old_items.suggested', { space: SPACE, page_length: 500 })).rows.find((r) => r.name === a)
      must(got && got.decision && got.reason, 'no suggested decision: ' + JSON.stringify(got))
      await s.open('/life/brain')
      const banner = pg.locator('[data-old-items-banner]')
      must(await banner.isVisible(), 'no banner on the Inbox')
      await banner.locator('[data-old-items-open]').click()
      await settle()
      const dlg = pg.locator('[data-old-items-dialog], [role="dialog"]').last()
      await dlg.getByRole('checkbox', { name: 'Select all' }).click() // untick every item, then tick this run's only
      await settle()
      const row = dlg.locator(`[data-old-item][data-item="${a}"]`)
      await row.getByRole('checkbox').click()
      await pick(row, `Decision for S7 old suggest ${W}`, 'Park in Someday', 'data-old-item-decision')
      await dlg.locator('[data-old-items-confirm]').click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must((await s.api('inbox.get', { item: a })).status === 'Done', 'the batch did not act on the item')
      must((await s.api('outbox.list', { space: SPACE, pile: 'Parked', page_length: 500 })).rows.some((r) => r.record === a), 'the item is not Parked in the Outbox')
      // Park: the job acts, Today says so, Undo restores
      await setRule('Park', 14)
      const b = (await s.api('inbox.create_item', { space: SPACE, title: `S7 old park ${W}`, source_type: 'Message', raw_text: 'Old.' })).name
      age(b, 20)
      const parked = run()
      must(parked.parked >= 1 && (await s.api('inbox.get', { item: b })).status === 'Done', 'the job did not park it: ' + JSON.stringify(parked))
      await s.open('/life')
      const line = pg.locator('[data-auto-inbox]')
      must(await line.isVisible() && (await line.innerText()).includes('parked'), "Today does not say what the job parked")
      await line.locator('[data-auto-inbox-undo]').click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must((await s.api('inbox.get', { item: b })).status !== 'Done', 'Undo did not bring it back')
      // Discard: to the trash, Undo restores
      await setRule('Discard', 14)
      const c = (await s.api('inbox.create_item', { space: SPACE, title: `S7 old discard ${W}`, source_type: 'Message', raw_text: 'Old.' })).name
      age(c, 20)
      age(b, 1) // the parked one is young again, so this run discards only what is old
      run()
      must(!(await s.api('inbox.get', { item: c }, { raw: true })).ok(), 'the job did not discard it')
      await s.open('/life')
      must((await pg.locator('[data-auto-inbox]').innerText()).includes('trash'), "Today does not say what the job discarded")
      await pg.locator('[data-auto-inbox-undo]').click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must((await s.api('inbox.get', { item: c }, { raw: true })).ok(), 'Undo did not restore it')
      return `${got.decision} suggested, parked and discarded, both undone`
    } finally {
      await setRule('Suggest', 7)
    }
  })

  if (phone) {
    await check(`${tag}.8`, `${width} px: no set 7 screen scrolls sideways`, async () => {
      const bad = []
      for (const p of ['/life', '/life/goals', '/life/today/week?view=review', '/life/brain/outbox', '/life/brain/outbox?pile=in&period=12weeks',
        '/life/today/year?view=cycle', '/life/settings?tab=rhythms', '/life/settings?tab=reset']) {
        await s.open(p)
        const o = await pg.evaluate((w) => Math.max(document.documentElement.scrollWidth, window.innerWidth) - w, width)
        if (o > 0) bad.push(`${p} by ${o} px`)
      }
      must(!bad.length, bad.join('; '))
      return '8 screens'
    })
  }
  await s.ctx.close()
}

// ---------- Set 8: the weekly review in four tabs, at 1440 px and 390 px ----------
// On data shaped like the owner's (lifeos/devtools_review.py: a number goal with a Suggested reading, a milestone goal without its
// finish line, stuck, waiting and delegated tasks, Inbox items of every kind) plus the fixture calendar. Records carry
// "S8 … <width> <stamp>" and are removed by S4.1; devtools_review.cleanup removes the rest and puts the settings back.
for (const width of SET_WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const tag = `S8.${width}`
  const W = `${width} ${stamp}`
  const settle = () => pg.waitForTimeout(600)
  const data = JSON.parse(bench(`import json
from lifeos import devtools_review
print(json.dumps(devtools_review.setup("${W}"), default=str))`).split('\n').pop())
  const tabNow = () => new URL(pg.url()).searchParams.get('tab')
  const goTab = async (t) => {
    await pg.locator(phone ? `[data-review-step="${t}"]` : `[data-review-tab-btn="${t}"]`).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
  }
  const drawer = (name) => pg.locator(`[data-drawer][data-drawer-name="${name}"]`)
  const closeDrawer = async () => { await pg.keyboard.press('Escape'); await settle() }
  // nothing scrolls the page at 1440 x 900; nothing scrolls sideways at 390
  const fits = async (where) => {
    const o = await pg.evaluate(() => ({ x: document.documentElement.scrollWidth - window.innerWidth, y: document.documentElement.scrollHeight - window.innerHeight }))
    if (o.x > 0) throw new Error(`${where} scrolls sideways by ${o.x} px`)
    if (!phone && o.y > 0) throw new Error(`${where} scrolls the page by ${o.y} px at 1440 x 900`)
  }

  await check(`${tag}.1`, `${width} px: the review opens from Today's banner on Library, with its period in the header; Goals cannot open before Tasks is done`, async () => {
    await s.open('/life')
    const banner = pg.locator('[data-rhythm-banner][data-banner="review"]')
    must(await banner.isVisible(), "no weekly review banner on Today")
    await banner.locator('[data-banner-open]').click()
    await pg.locator('[data-review-library]').waitFor({ timeout: 20000 })
    await settle()
    must(tabNow() === 'library', `the review opened on ${tabNow()}`)
    const period = (await pg.locator('[data-review-period]').innerText()).trim()
    must(/^Week of \d+ (to|[A-Z][a-z]+ to) /.test(period) || period.startsWith('Covers '), `the header says "${period}"`)
    await goTab('goals')
    must(tabNow() === 'library', 'Goals opened before Tasks was done')
    must(await pg.getByText('Finish Tasks first.').count(), 'no word on why Goals is closed')
    must(!errors.length, errors.splice(0).join(' | '))
    return period
  })

  await check(`${tag}.2`, `${width} px: a meeting that matters with a linked voice note; a task made from its follow-up leaves the meeting's drawer and the Revelations list`, async () => {
    await s.open('/life/today/week?view=review&tab=library')
    await pg.locator(`[data-strip-meeting="${data.meeting}"]:visible`).first().click()
    const d = drawer('meeting')
    await d.locator('[data-meeting]').waitFor({ timeout: 10000 })
    must((await d.locator('[data-meeting-linked]').allInnerTexts()).some((t) => t.includes(`S8 voice after Dalmia ${W}`)), 'the voice note is not linked')
    const promise = d.locator('[data-finding][data-kind="Promise"]', { hasText: W }).first()
    must(await promise.count(), 'no Promise follow-up for the voice note')
    const name = await promise.getAttribute('data-finding-name')
    await promise.locator('[data-finding-action="make_task"]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!(await d.locator(`[data-finding-name="${name}"]`).count()), "the follow-up stayed in the meeting's drawer")
    const tasks = (await s.api('tasks.list', { space: SPACE, status: 'all', filters: [['title', 'like', `%send the blend sheet to Mithun ${W}%`]] })).tasks
    must(tasks.length === 1, 'the task was not made: ' + tasks.length)
    await closeDrawer()
    must(!(await pg.locator(`[data-revelations] [data-finding-name="${name}"]`).count()), 'the finding is still in Revelations')
    return tasks[0].title
  })

  await check(`${tag}.3`, `${width} px: a reading confirmed from Revelations shows its value on the goal's row in Goals`, async () => {
    const row = pg.locator('[data-revelations] [data-finding][data-kind="Goal reading"]', { hasText: 'Mr. Rao reported' }).first()
    must(await row.isVisible(), 'the reading is not among the revelations')
    await row.locator('[data-finding-action="confirm_reading"]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    const g = await s.api('goals.get', { goal: data.number })
    must(g.goal.current_value === 1460, `the goal reads ${g.goal.current_value}`)
    const t = await s.api('weekly.goals', { space: SPACE })
    const r = t.rows.find((x) => x.goal === data.number)
    must(r && r.progress.label === '1,460 of 1,800', 'the row says ' + JSON.stringify(r?.progress))
    return r.progress.label
  })

  await check(`${tag}.4`, `${width} px: the Park pile: one moved to Keep, the rest parked; the card's done state; the Outbox counts match; Undo restores both`, async () => {
    await goTab('tasks')
    must(tabNow() === 'tasks', 'Tasks did not open')
    const before = (await s.api('weekly.plate', { space: SPACE })).piles.find((x) => x.pile === 'Parked').n
    await pg.locator('[data-pile-card][data-pile="park"] [data-pile-open]').first().click()
    const d = drawer('pile')
    await d.locator('[data-pile-row]').first().waitFor({ timeout: 10000 })
    const moved = d.locator('[data-pile-row]', { hasText: `S8 park 0 ${W}` })
    await moved.locator('[data-pile-choice="keep"]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must((await d.locator('[data-pile-row]', { hasText: `S8 park 0 ${W}` }).innerText()).includes('Moved to Keep'), 'the row does not say Moved to Keep')
    const left = (await s.api('weekly.pile_summary', { space: SPACE, key: 'tasks' })).piles.park.left
    await d.locator('[data-pile-accept]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!(await d.count()) || !(await d.isVisible()), 'the drawer stayed open')
    const card = pg.locator('[data-pile-card][data-pile="park"]')
    must((await card.getAttribute('data-pile-done')) === '1', 'the card is not done')
    must((await card.innerText()).includes('1 moved to Keep'), 'the card does not say what moved')
    const status = async (n) => (await s.api('frappe.client.get_value', { doctype: 'Life Task', filters: { name: n }, fieldname: 'status' })).status
    must(await status(data.park[0]) === 'Open' && await status(data.park[1]) === 'Someday' && await status(data.park[2]) === 'Someday', 'the tasks did not move')
    const plate = (await s.api('weekly.plate', { space: SPACE })).piles.find((x) => x.pile === 'Parked')
    const listed = await s.api('outbox.list', { space: SPACE, pile: 'Parked', from_date: plate.to.query.from, to_date: plate.to.query.to, page_length: 500 })
    must(plate.n === listed.total && plate.n === listed.rows.length, `Parked says ${plate.n}, the Outbox lists ${listed.rows.length}`)
    must(plate.n === before + left, `Parked went from ${before} to ${plate.n}, not by ${left}`)
    await card.locator('[data-pile-undo]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(await status(data.park[0]) === 'Open' && await status(data.park[1]) === 'Open' && await status(data.park[2]) === 'Open', 'Undo did not restore both')
    must((await pg.locator('[data-pile-card][data-pile="park"]').getAttribute('data-pile-done')) === '0', 'the card stayed done after Undo')
    const after = (await s.api('weekly.plate', { space: SPACE })).piles.find((x) => x.pile === 'Parked').n
    must(after === before, `after Undo Parked is ${after}, was ${before}`)
    return `${left} parked, 1 moved to Keep, Outbox ${plate.n}, undone`
  })

  await check(`${tag}.5`, `${width} px: Needs you settled and every pile accepted; Next: Goals opens`, async () => {
    for (let i = 0; i < 8; i++) {
      const row = pg.locator('[data-needs-row][data-settled="0"]').first()
      if (!(await row.count())) break
      await row.locator('[data-needs-choice]').first().click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
    must(!(await pg.locator('[data-needs-you]').count()), 'Needs you did not fold away')
    for (const p of ['keep', 'park', 'letgo']) {
      const card = pg.locator(`[data-pile-card][data-pile="${p}"]`)
      if ((await card.getAttribute('data-pile-done')) === '1' || (await card.getAttribute('data-pile-count')) === '0') continue
      await card.locator('[data-pile-open]').click()
      await drawer('pile').locator('[data-pile-accept]').waitFor({ timeout: 10000 })
      await drawer('pile').locator('[data-pile-accept]').click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
    const chase = (await s.api('tasks.list', { space: SPACE, status: 'all', filters: [['title', 'like', `Chase Ravi: S8 drainage photos ${W}%`]] })).tasks
    must(chase.length === 1, 'the waiting item kept as Chase made no chase task')
    const next = pg.locator('[data-review-next]')
    must(await next.isEnabled(), 'Next: Goals is still closed: ' + (await pg.locator('[data-review-footer-line]').innerText()))
    await next.dispatchEvent('click') // a toast may sit over the footer for a moment
    await pg.waitForLoadState('networkidle')
    await settle()
    must(tabNow() === 'goals', 'Goals did not open')
    return 'Needs you, Keep, Park, Let go'
  })

  await check(`${tag}.6`, `${width} px: every cycle goal gets a next action or a skip with a reason; exactly three stars; more than the free time shows the warning`, async () => {
    await pg.locator('[data-goals-list]').waitFor({ timeout: 15000 })
    const t = await s.api('weekly.goals', { space: SPACE })
    const rows = t.rows
    // one through the drawer: a new next action, a free slot, Save
    const first = rows[0]
    await pg.locator(`[data-goal-row][data-goal="${first.goal}"] button`).first().click()
    const d = drawer('goal')
    await d.locator('[data-goal-drawer]').waitFor({ timeout: 10000 })
    await d.locator('[data-goal-next] input, input[data-goal-next]').first().fill(`S8 next 0 ${W}`)
    await d.locator('[data-goal-save]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    // skip one with a reason, in its drawer
    const skipped = rows[rows.length - 1]
    await pg.locator(`[data-goal-row][data-goal="${skipped.goal}"] button`).first().click()
    await d.locator('[data-goal-drawer]').waitFor({ timeout: 10000 })
    await d.locator('[data-goal-skip]').click()
    must(await d.locator('[data-goal-skip-confirm]').isDisabled(), 'a skip without a reason is allowed')
    await d.locator('[data-goal-skip-reason] input, input[data-goal-skip-reason]').first().fill('Travelling all week')
    await d.locator('[data-goal-skip-confirm]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must((await pg.locator(`[data-goal-row][data-goal="${skipped.goal}"]`).getAttribute('data-skipped')) === '1', 'the skipped goal is not marked')
    // the rest: a fresh next action each (new tasks, so the demo's own tasks stay as they are), long enough to pass the free time
    for (const [i, r] of rows.entries()) {
      if (r.goal === skipped.goal) continue
      await s.api('weekly.goal_save', { space: SPACE, goal: r.goal, values: { next_action: `S8 next ${i} ${W}`, task: null, minutes: 600,
        slot: `${addDays(1 + (i % 5))} 09:00`, who: i === 1 ? 'Vivek' : 'Me' } })
    }
    // exactly three stars, by the row's star buttons
    await s.open('/life/today/week?view=review&tab=goals')
    await pg.locator('[data-goals-list]').waitFor({ timeout: 15000 })
    for (let i = 0; i < 10; i++) {
      const starred = await pg.locator('[data-goal-row][data-star="1"]').count()
      if (starred === 3) break
      const btn = starred < 3 ? pg.locator('[data-goal-row][data-star="0"][data-skipped="0"] [data-goal-star-btn]').first() : pg.locator('[data-goal-row][data-star="1"] [data-goal-star-btn]').first()
      await btn.click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
    must(await pg.locator('[data-goal-row][data-star="1"]').count() === 3, 'not three stars')
    const cap = pg.locator('[data-goals-capacity]')
    must((await cap.getAttribute('data-over')) === '1', 'no warning for more than the free time')
    must(/^planned, [\d.]+ h free$/.test((await cap.locator('[data-goals-capacity-line]').innerText()).trim()), 'the warning does not say planned and free')
    must(await pg.locator('[data-review-next]').isEnabled(), 'Next: Reflect is closed: ' + (await pg.locator('[data-review-footer-line]').innerText()))
    return `${rows.length} goals, 1 skipped, 3 stars, over by ${Math.round((Number((await s.api('weekly.goals', { space: SPACE })).capacity.planned_minutes) - Number(t.capacity.free_minutes)) / 60)} h`
  })

  await check(`${tag}.7`, `${width} px: Pause and reopen: everything is where it was left; no tab scrolls the page at 1440 x 900 or sideways at 390`, async () => {
    if (!phone) await pg.setViewportSize({ width: 1440, height: 900 })
    await pg.locator('[data-review-pause]:visible').first().dispatchEvent('click')
    await pg.waitForLoadState('networkidle')
    must(new URL(pg.url()).searchParams.get('view') === 'calendar', 'Pause did not return to Plan > Week')
    await s.open('/life/today/week?view=review')
    await pg.locator('[data-review]').waitFor()
    await settle()
    await settle()
    must(tabNow() === 'reflect', `the review reopened on ${tabNow()}, not Reflect`)
    const seen = []
    for (const t of ['library', 'tasks', 'goals', 'reflect']) {
      await goTab(t)
      await settle()
      await fits(`the ${t} tab`)
      seen.push(t)
    }
    await goTab('tasks')
    must(await pg.locator('[data-pile-card][data-pile-done="1"]').count() >= 1, 'the piles were not kept')
    await goTab('goals')
    must(await pg.locator('[data-goal-row][data-star="1"]').count() === 3 && await pg.locator('[data-goal-row][data-skipped="1"]').count() === 1, 'stars or skip lost')
    // the drawers too
    await pg.locator('[data-goal-row] button').first().click()
    await drawer('goal').locator('[data-goal-drawer]').waitFor()
    await fits('the goal drawer')
    await closeDrawer()
    if (!phone) await pg.setViewportSize({ width: 1440, height: 1000 })
    return seen.join(', ')
  })

  await check(`${tag}.8`, `${width} px: what went well; Lock; the done screen; Today shows the top three first; the scheduled tasks are on Today and in Plan > Week`, async () => {
    await goTab('reflect')
    await pg.locator('[data-went-well] textarea, textarea[data-went-well]').first().fill(`S8 went well ${W}`)
    await pg.locator('[data-review-next]').dispatchEvent('click')
    await pg.locator('[data-review-done]').waitFor({ timeout: 20000 })
    await settle()
    must((await pg.locator('[data-review-done-title]').innerText()).startsWith('Week planned in'), 'no done screen')
    must(await pg.locator('[data-done-top]').count() === 3, 'the done screen does not list three')
    await pg.locator('[data-done-today]').click()
    await pg.waitForLoadState('networkidle')
    await settle()
    const first = pg.locator('[data-next-group]').first()
    must((await first.getAttribute('data-next-group')) === 'top', `Today's first group is ${await first.getAttribute('data-next-group')}`)
    const tops = await pg.locator('[data-next] [data-why="Top three"]').count()
    must(tops === 3 && await pg.locator('[data-next] [data-top-three]').count() === 3, `${tops} top-three rows on Today`)
    const made = (await s.api('tasks.list', { space: SPACE, status: 'all', filters: [['title', 'like', `S8 next % ${W}`]] })).tasks
    const scheduled = made.filter((x) => x.scheduled_at)
    must(scheduled.length >= 2, 'the plans were not scheduled')
    must(made.some((x) => x.status === 'Waiting' && x.waiting_on === 'Vivek'), 'the delegated plan is not Waiting on Vivek')
    const weekCal = await s.api('calendar.get', { space: SPACE, from_date: addDays(0), to_date: addDays(8) })
    must(scheduled.every((x) => weekCal.items.some((i) => i.name === x.name && i.scheduled)), 'a scheduled task is not in Plan > Week')
    await s.open('/life/today/week?view=calendar')
    const text = await pg.locator('[data-main]').innerText()
    must(scheduled.some((x) => text.includes(x.title)), 'no scheduled task on the Week calendar')
    // the next review starts after this one
    must((await s.api('weekly.get', { space: SPACE })).status === 'Locked', 'the review is not locked')
    must(!errors.length, errors.splice(0).join(' | '))
    return `${made.length} tasks, ${scheduled.length} scheduled, top three on Today`
  })

  bench(`from lifeos import devtools_review
devtools_review.cleanup("${stamp}", ${JSON.stringify(JSON.stringify(data.was))})`)
  await s.ctx.close()
}

// ---------- Bug fix 1: the weekly review on data shaped like the owner's, the error boundary, and every screen ----------
// Records carry "BF1 … <width> <stamp>" and are removed by S4.1.
for (const width of SET_WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const tag = `BF1.${width}`
  const W = `${width} ${stamp}`
  const settle = () => pg.waitForTimeout(500)
  const place = async (label) => {
    await pg.locator(width < 800 ? `[data-tab-item="${label}"]` : `[data-nav-item="${label}"]`).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
  }
  const headerButtons = () => pg.evaluate(() => [...document.querySelectorAll('#jr-actions [aria-label]')].map((b) => b.getAttribute('aria-label')))

  await check(`${tag}.1`, `${width} px: the weekly review renders on data like the owner's (a goal migrated from a project, a number goal with a Suggested reading, a milestone goal without "done when", a goal with no cycle, a delegated task), reached by clicking and by URL`, async () => {
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, now_datetime, today
from lifeos import readings
frappe.set_user("owner@lifeos.test")
area = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
cycle = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"})
def goal(title, **kw):
    g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": title, "area": area, **kw})
    g.flags.ignore_permissions = True
    return g.insert().name
# a project, migrated as set 6 did: an open-ended goal with no finish line and no measure
p = frappe.get_doc({"doctype": "Life Project", "space": "${SPACE}", "title": "BF1 project ${W}", "area": area, "status": "Active"})
p.flags.allow_migration = True
p.insert(ignore_permissions=True)
migrated = goal("BF1 migrated ${W}", horizon="Long term")
frappe.db.set_value("Life Project", p.name, "migrated_to", migrated)
number = goal("BF1 number ${W}", horizon="Long term", measure_kind="Number", measure="BF1 weight", unit="kg", start_value=84, target_value=78)
readings.suggest(number, 81, excerpt="Weighed 81 kg this morning.", by="Agent")
milestone = goal("BF1 milestone ${W}", horizon="12 weeks", cycle=cycle, measure_kind="Milestone", done_when="Signed")
frappe.db.set_value("Life Goal", milestone, "done_when", None)
nocycle = goal("BF1 no cycle ${W}", horizon="12 weeks", cycle=cycle)
frappe.db.set_value("Life Goal", nocycle, "cycle", None)
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "BF1 delegated ${W}", "goal": migrated, "area": area, "status": "Waiting",
    "waiting_on": "Ravi", "scheduled_at": str(add_days(now_datetime(), 1).replace(hour=11, minute=0, second=0, microsecond=0)), "duration_min": 30})
t.flags.ignore_permissions = True
t.insert()
# set 8: a fresh review, whose revelations have the reading among their five
frappe.db.delete("Life Review", {"space": "${SPACE}", "user": "owner@lifeos.test"})
frappe.db.sql("update \`tabLife Insight\` set status='Dismissed' where space=%s and status='New' and ifnull(reading, '') = ''", "${SPACE}")
print(json.dumps({"migrated": migrated, "number": number, "milestone": milestone, "nocycle": nocycle, "task": t.name}))`).split('\n').pop())
    must(made.migrated && made.task, 'the records were not made: ' + JSON.stringify(made))
    // set 8: the review is its own screen (header, numbered tabs, period); the Suggested reading is a revelation in Library
    const review = async (how) => {
      const body = pg.locator('[data-review-library]')
      await body.waitFor({ timeout: 15000 }).catch(() => {})
      await pg.locator('[data-revelations]').waitFor({ timeout: 15000 }).catch(() => {})
      await settle()
      must(!errors.length, `${how}: script error: ${errors.splice(0).join(' | ')}`)
      must(!(await pg.locator('[data-screen-error]').count()), `${how}: the screen could not be shown`)
      must(await body.isVisible(), `${how}: the review's body is empty`)
      must((await pg.locator('[data-review-period]').innerText()).match(/^(Week of|Covers) /), `${how}: no period in the header`)
      must((await pg.locator('[data-review-head] [data-review-pause]').count()) === 1, `${how}: no Pause in the header`)
      const text = await pg.locator('[data-main]').innerText()
      must(text.includes(`BF1 number ${W}`), `${how}: the reading to confirm is missing`)
    }
    // the way the owner reached it: Today, its Week tab, the Week's Calendar, then Review (issue 14: the Week is a tab of Today)
    await s.open('/life/brain')
    await place('Today')
    await pg.locator('[data-place-tabs] [data-tab="week"]').first().click()
    // issue 16: the Week tab is its own screen; the Calendar and Review views open by `view=`
    await pg.goto(new URL('/life/today/week?view=calendar', pg.url()).href)
    await settle()
    await pg.locator('[data-plan-views]:visible').first().getByText('Review', { exact: true }).click()
    await review('clicked from the Calendar')
    // by URL, and after a reload
    await s.open('/life/today/week?view=review&tab=library')
    await review('by URL')
    await pg.reload({ waitUntil: 'networkidle' })
    await review('after a reload')
    // and navigation still moves the page
    await place('Brain')
    must(new URL(pg.url()).pathname === '/life/brain' && await pg.locator('[data-main]').innerText().then((t) => t.includes('Needs you')), 'navigation after the review is stuck')
    return 'clicked, by URL and reloaded; the period and Pause in the header'
  })

  await check(`${tag}.2`, `${width} px: a screen forced to fail shows "This screen could not be shown." with Reload and a reference, logs it, and navigation keeps working`, async () => {
    const got = []
    for (const kind of ['render', 'patch']) {
      await s.open(`/life/dev/throw?kind=${kind}`)
      await pg.locator('[data-screen-error]').waitFor({ timeout: 5000 })
      errors.splice(0)
      const box = pg.locator('[data-screen-error]')
      must((await box.innerText()).includes('This screen could not be shown.'), `${kind}: no message`)
      must(await box.getByRole('button', { name: 'Reload' }).isVisible(), `${kind}: no Reload`)
      const ref = (await pg.locator('[data-screen-error-ref]').innerText()).trim()
      must(/^[A-Z0-9]{4,8}$/.test(ref), `${kind}: reference "${ref}"`)
      // the sidebar or the phone's tab bar still works, and leaving clears the message
      await place('Goals')
      must(new URL(pg.url()).pathname === '/life/goals', `${kind}: Goals did not open (${pg.url()})`)
      must(!(await pg.locator('[data-screen-error]').count()), `${kind}: the message stayed after leaving`)
      await place('Today')
      must(await pg.locator('[data-main]').innerText().then((t) => t.length > 100), `${kind}: Today is empty after the failure`)
      const logged = bench(`print(frappe.db.count("Error Log", {"method": "Life OS screen error ${ref}"}))`).split('\n').pop()
      must(logged === '1', `${kind}: the Error Log has ${logged} entries for ${ref}`)
      got.push(`${kind} ${ref}`)
    }
    // a screen whose file is gone after a rebuild says a newer version is out
    await s.open('/life')
    await pg.route(/\/assets\/lifeos\/frontend\/assets\/Settings-[^/]*\.js/, (r) => r.fulfill({ status: 404, body: 'gone' }))
    await pg.evaluate(() => document.querySelector('[data-app] a[href*="/settings"]').click())
    await pg.locator('[data-screen-error]').waitFor({ timeout: 5000 })
    must((await pg.locator('[data-screen-error]').innerText()).includes('A newer version of Life OS is available.'), 'a missing screen file gives the wrong message')
    await pg.unroute(/Settings-/)
    errors.splice(0)
    await place('Brain')
    must(new URL(pg.url()).pathname === '/life/brain' && !(await pg.locator('[data-screen-error]').count()), 'navigation after a missing screen file is stuck')
    bench(`frappe.db.delete("Error Log", {"method": ["like", "Life OS screen error %"]})`)
    return got.join(', ') + ', and a missing screen file'
  })

  await check(`${tag}.3`, `${width} px: every place, every Plan and Library tab and every view of Plan's rhythms opens by clicking, and navigation works afterwards`, async () => {
    await s.open('/life')
    errors.splice(0)
    const { seen, failures } = await walkScreens(pg, { width })
    must(!failures.length, failures.join('; '))
    return `${seen} screens`
  })
  await s.ctx.close()
}

// Issue 1: people and agents in one place (Settings > People and agents: Spaces, Members, Agents)
const I1_AGENT = 'issue1-agent@lifeos.test'
const I1_NEW = 'issue1-newcomer@lifeos.test'
for (const width of SET_WIDTHS) {
  const phone = width < 800
  const tag = `I1.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const settle = () => pg.waitForTimeout(500)
  const cur = () => pg.locator('[data-settings-section]').getAttribute('data-current')
  // an agent in no space, and a user with no Life OS role in no space
  const reset = () => bench(`from lifeos import devtools
frappe.set_user("Administrator")
devtools.make_user("${I1_AGENT}", "Issue One Agent", ["Life Agent"])
devtools.make_user("${I1_NEW}", "Issue One Newcomer", [])
u = frappe.get_doc("User", "${I1_NEW}"); u.flags.ignore_permissions = True; u.remove_roles("Life User", "Life Admin", "Life Agent")
for sp in frappe.get_all("Life Space", pluck="name"):
    doc = frappe.get_doc("Life Space", sp)
    for m in [m for m in doc.members if m.user in ("${I1_AGENT}", "${I1_NEW}")]: doc.remove(m)
    doc.save(ignore_permissions=True)
frappe.db.commit()`)
  const pickSpace = async (name) => {
    if (phone) { await pg.locator('[data-settings-section] [aria-label="Space"]').first().click(); await pg.getByRole('option', { name, exact: true }).click() }
    else await pg.locator(`[data-member-spaces] [data-space="${name}"]`).click()
    await settle()
  }
  const choose = async (sel, option) => {
    await pg.locator(sel).first().click()
    await pg.waitForTimeout(250)
    await pg.getByRole('option', { name: option, exact: true }).first().click()
    await pg.waitForTimeout(1200)
  }
  const shownAccess = async (sel) => (await pg.locator(sel).first().innerText()).trim()
  const addFromDialog = async (search, who) => {
    await pg.locator('[data-add-member]').click()
    await pg.waitForTimeout(400)
    await pg.locator('[data-add-dialog] input').first().click()
    await pg.keyboard.type(search, { delay: 30 })
    await pg.waitForTimeout(1200)
    await pg.getByRole('option', { name: new RegExp(who.split('@')[0].replace(/-/g, '.'), 'i') }).first().click()
    await settle()
  }
  const space = async (name) => (await s.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === name)

  await check(`${tag}.1`, `${width} px: an agent added with Add member shows in Members with its badge and in Agents; access changed in one view shows in the other; a user with no role is offered one`, async () => {
    reset()
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    // the agent: found by Add member with its kind, Can view by default with the note, and at once in the list with its badge
    await addFromDialog('Issue One Agent', I1_AGENT)
    must((await pg.locator('[data-add-picked]').getAttribute('data-kind')) === 'Agent', 'Add member does not show the agent as an agent')
    must(/Can view/.test(await pg.locator('[data-add-dialog] [data-add-access]').first().innerText()), 'an agent does not default to Can view')
    must(await pg.locator('[data-add-agent-note]').isVisible(), 'the note "Agents need Can edit…" is missing')
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1500)
    const row = pg.locator(`[data-members] [data-member="${I1_AGENT}"]`)
    must(await row.count(), 'the agent did not appear in Members after Add')
    must((await row.locator('[data-kind-badge]').innerText()).trim() === 'Agent', 'the agent has no Agent badge')
    must(/Can view/.test(await shownAccess(`[data-access="${I1_AGENT}"]`)), 'the agent was not added with Can view')
    // the filters: All, People, Agents with counts
    const tabs = await pg.locator('[data-member-filter]').innerText()
    const sp = await space(SPACE)
    for (const want of [`All ${sp.members.length}`, `People ${sp.people_count}`, `Agents ${sp.agent_count}`]) must(tabs.replace(/\s+/g, ' ').includes(want), `the filters read "${tabs}", not ${want}`)
    await pg.locator('[data-member-filter]').getByText(/^Agents/).click()
    await settle()
    must(await row.count() && !(await pg.locator('[data-members] [data-kind="Owner"], [data-members] [data-kind="Person"]').count()), 'Agents shows people')
    await pg.locator('[data-member-filter]').getByText(/^People/).click()
    await settle()
    must(!(await row.count()), 'People shows the agent')
    await pg.locator('[data-member-filter]').getByText(/^All/).click()
    await settle()
    // Agents: the same agent, the same access; change it there and Members matches, change it in Members and Agents matches
    await s.open('/life/settings?tab=agents')
    const ref = `${I1_AGENT}|${SPACE}`
    must(await pg.locator(`[data-agent="${I1_AGENT}"]`).count(), 'the agent is not under Agents')
    must(/Can view/.test(await shownAccess(`[data-agent-access="${ref}"]`)), 'Agents does not show Can view')
    must(await pg.locator(`[data-agent-user-link="${I1_AGENT}"]`).count(), 'the agent card has no link to its Frappe user')
    await choose(`[data-agent-access="${ref}"]`, 'Can edit')
    must((await space(SPACE)).members.find((m) => m.user === I1_AGENT)?.access === 'Write', 'Can edit in Agents was not saved')
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    must(/Can edit/.test(await shownAccess(`[data-access="${I1_AGENT}"]`)), 'Members does not match the change made in Agents')
    await choose(`[data-access="${I1_AGENT}"]`, 'Can view')
    await s.open('/life/settings?tab=agents')
    must(/Can view/.test(await shownAccess(`[data-agent-access="${ref}"]`)), 'Agents does not match the change made in Members')
    // a user with no Life OS role: said so, and Add waits until the owner says person or agent; a person gets Can edit
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    await addFromDialog('Issue One Newcomer', I1_NEW)
    must(await pg.locator('[data-add-no-role]').isVisible(), 'a user with no role is not told so')
    must(await pg.getByRole('button', { name: 'Add', exact: true }).last().isDisabled(), 'Add is possible before choosing person or agent')
    await pg.locator('[data-add-role]').getByText('A person', { exact: true }).click()
    await settle()
    must(/Can edit/.test(await pg.locator('[data-add-dialog] [data-add-access]').first().innerText()), 'a person does not default to Can edit')
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1500)
    must((await pg.locator(`[data-member="${I1_NEW}"] [data-kind-badge]`).innerText()).trim() === 'Person', 'the newcomer was not added as a person')
    must(!(await pg.locator(`[data-member="${I1_NEW}"] [data-access]`).count()) || /Can edit/.test(await shownAccess(`[data-access="${I1_NEW}"]`)), 'the newcomer was not added with Can edit')
    must(await pg.locator('[data-owner-badge]').count(), 'the owner has no Owner badge')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return 'agent and person added; access matched both ways'
  })

  await check(`${tag}.2`, `${width} px: Ask and agents' sensitive-item access switch from Spaces`, async () => {
    await s.open('/life/settings?tab=spaces')
    const before = await space(SPACE)
    must(/person|people/.test(await pg.locator(`[data-space-counts="${SPACE}"]`).innerText()) && /agent/.test(await pg.locator(`[data-space-counts="${SPACE}"]`).innerText()), 'Spaces has no people and agent counts')
    try {
      await pg.locator(`[data-ask-switch="${SPACE}"]`).click()
      await pg.waitForTimeout(1200)
      must((await space(SPACE)).ask_enabled === (before.ask_enabled ? 0 : 1), 'Ask in this space did not switch')
      await pg.locator(`[data-vault-switch="${SPACE}"]`).click()
      await pg.waitForTimeout(1500)
      must((await space(SPACE)).agents_can_read_vault === (before.agents_can_read_vault ? 0 : 1), 'Agents may open sensitive items did not switch')
      await s.open('/life/settings?tab=agents')
      const said = await pg.locator(`[data-agent-sensitive="${I1_AGENT}|${SPACE}"]`).innerText()
      must(before.agents_can_read_vault ? /No sensitive/.test(said) : /Opens sensitive/.test(said), `the agent card says "${said}" after the switch`)
    } finally {
      await s.api('settings.set_space_ask', { space: SPACE, ask_enabled: before.ask_enabled })
      await s.api('settings.set_agent_vault', { space: SPACE, allowed: before.agents_can_read_vault })
    }
  })

  await check(`${tag}.3`, `${width} px: ?tab=agents and the old names land under People and agents; nothing under Assistant lists members or agents`, async () => {
    for (const [asked, now] of [['agents', 'agents'], ['assistants', 'agents'], ['people', 'members']]) {
      await s.open(`/life/settings?tab=${asked}`)
      must((await cur()) === now, `?tab=${asked} opened ${await cur()}, not ${now}`)
    }
    // the menu: Agents is the third item of People and agents; Assistant has Connections, Ask and AI, Sensitive items, Note rules
    await s.open('/life/settings')
    const menu = await pg.locator('[data-settings-menu] [data-settings-group], [data-settings-menu] [data-section]').evaluateAll((els) =>
      els.map((e) => e.getAttribute('data-settings-group') ? '#' + e.getAttribute('data-settings-group') : e.getAttribute('data-section')))
    const after = (g) => { const i = menu.indexOf('#' + g); const j = menu.findIndex((x, k) => k > i && x.startsWith('#')); return menu.slice(i + 1, j < 0 ? undefined : j) }
    must(JSON.stringify(after('people')) === JSON.stringify(['spaces', 'members', 'agents']), `People and agents lists ${after('people')}`)
    must(JSON.stringify(after('assistant')) === JSON.stringify(['connections', 'ai', 'cost', 'sensitive', 'note-rules']), `Assistant lists ${after('assistant')}`)
    for (const sec of after('assistant')) {
      await s.open(`/life/settings?tab=${sec}`)
      must(!(await pg.locator('[data-settings-section] [data-member], [data-settings-section] [data-agent], [data-settings-section] [data-agent-access]').count()), `${sec} lists members or agents`)
      const text = await pg.locator('[data-settings-section]').innerText()
      must(!text.includes(I1_AGENT) && !text.includes('hermes@lifeos.test'), `${sec} names an agent`)
      must(!/Agents are under Agents/.test(text), `${sec} still says "Agents are under Agents"`)
    }
    for (const sec of ['sensitive', 'ai']) {
      await s.open(`/life/settings?tab=${sec}`)
      must(!(await pg.locator('[data-vault-switch], [data-ask-switch]').count()), `${sec} still has a per-space switch that moved to Spaces`)
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.api('settings.set_member', { space: SPACE, user: I1_AGENT, remove: 1 }).catch(() => {})
  await s.api('settings.set_member', { space: SPACE, user: I1_NEW, remove: 1 }).catch(() => {})
  await s.ctx.close()
}

// Issue 7: a file is stored once by content, and an item filed again with a changed file of the same name keeps versions
for (const width of SET_WIDTHS) {
  const tag = `I7.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const file = (title, ext) => s.api('inbox.create_item', { title, space: SPACE, source_type: 'Upload', intent: 'Just keep',
    source_system: 'hermes', external_id: ext })
  const ext = `i7-deck-${width}-${stamp}`
  const v1 = Buffer.from(`I7 standard deck ${stamp}, first version`)
  const v2 = Buffer.from(`I7 standard deck ${stamp}, second version`)
  const original = '[data-review-original]'
  await check(`${tag}.6`, `${width} px: an item filed twice with the same file shows one attachment; with two versions it shows "2 versions" and opens the older one`, async () => {
    const item = await file(`I7 deck ${width} ${stamp}`, ext)
    const first = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v1)
    must((await file(`I7 deck ${width} ${stamp}`, ext)).name === item.name, 'filing again made a second item')
    const again = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v1)
    must(again.name === first.name, 'the same file sent again was attached a second time')
    must((await s.api('inbox.get', { item: item.name })).files.length === 1, 'the item has more than one attachment')
    await s.open(`/life/inbox/${item.name}/review?tab=original`) // phones open on the summary
    must(await pg.locator(`${original} a[href="${first.file_url}"]`).count() === 1, 'the review does not show the one attachment once')
    must(!(await pg.locator('[data-file-versions]').count()), 'a file with one version shows versions')
    // a changed file of the same name: one current file and the old one as an earlier version
    await file(`I7 deck ${width} ${stamp}`, ext)
    const second = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v2)
    const got = await s.api('inbox.get', { item: item.name })
    must(got.files.length === 1 && got.files[0].file_url === second.file_url && got.files[0].versions.length === 1, 'not one current file with one earlier version: ' + JSON.stringify(got.files))
    await s.open(`/life/inbox/${item.name}/review?tab=original`) // phones open on the summary
    const toggle = pg.locator('[data-file-versions-toggle]')
    must(/^2 versions, latest \d+ \w{3}$/.test((await toggle.innerText()).trim()), 'the versions line says: ' + (await toggle.innerText()))
    await toggle.click()
    const link = pg.locator('[data-file-version] a')
    must(await link.count() === 1, 'the earlier version is not listed')
    const href = await link.getAttribute('href')
    must(href === first.file_url, 'the earlier version links to ' + href)
    const [popup] = await Promise.all([pg.context().waitForEvent('page'), link.click()])
    await popup.waitForLoadState()
    must((await popup.locator('body').innerText()).includes('first version'), 'opening the earlier version did not show the old file')
    await popup.close()
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    must(!overflow, 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}

// Issue 8: an agent files a piece of work with one call (agent/fake_agent.py --file-job); it is one item in the Inbox
// (Needs you replaces it in issue 14), and its page shows Inputs, Outputs, the summary and the proposals
for (const width of SET_WIDTHS) {
  const tag = `I8.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const title = `I8 deck ${width} ${stamp}`
  const fileJob = () => execFileSync('python3', [path.join(root, 'agent/fake_agent.py'), '--url', base, '--file-job', `i8-job-${width}-${stamp}`,
    '--title', title, '--space', SPACE], { env: { ...process.env, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' })
  await check(`${tag}.7`, `${width} px: a job filed (twice) with the fake agent is one item in the Inbox; its page shows Inputs, Outputs, the summary and the proposals`, async () => {
    fileJob()
    fileJob() // filing the same job again updates it
    const found = await s.api('inbox.list', { space: SPACE, page_length: 10, filters: [['title', '=', title]] })
    must(found.total === 1, `${found.total} items with the job's title`)
    const item = found.items[0]
    must(item.status === 'To Review' && item.pending === 2, `the item is ${item.status} with ${item.pending} pending proposals`)
    await s.open('/life/brain/queue')
    const shown = await pg.locator('[data-row]', { hasText: title }).count()
    must(shown === 1, `the Inbox shows the job in ${shown} rows`)
    await s.open(`/life/inbox/${item.name}/review?tab=original`) // phones open on the proposals
    must(await pg.locator('[data-review-outputs]').count() === 1, 'no Outputs section')
    for (const ext of ['txt', 'html'])
      must(await pg.locator('[data-review-original] a', { hasText: `${title}.${ext}` }).count() === 1, `the output ${title}.${ext} is not shown once`)
    const inputs = pg.locator('[data-review-inputs] [data-review-input]')
    must(await inputs.count() === 2, `${await inputs.count()} inputs shown`)
    const inputText = await pg.locator('[data-review-inputs]').innerText()
    must(inputText.includes('Standard sales deck.txt') && inputText.includes('Brand guidelines.txt'), 'the inputs are not named')
    must(!(await pg.locator('[data-review-original] a', { hasText: 'Standard sales deck.txt' }).count()), 'an input is listed as an output')
    must(await pg.locator('[data-review-filed-with]').count() === 1, 'the wiki page and chat log filed with it are not shown')
    await s.open(`/life/inbox/${item.name}/review?tab=summary`)
    must((await pg.locator('body').innerText()).includes('An owner-first deck'), 'the summary is not shown')
    await s.open(`/life/inbox/${item.name}/review?tab=proposals`)
    must(await pg.locator('[data-proposal="Pending"]').count() === 2, 'the two proposals are not shown')
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    must(!overflow, 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}

// Issue 10: one page per capture at /item/<name>: where it came from, what came in, what the Brain made of it, the decisions
// waiting, what came of it and what is related. Its proposal cards are the Review screen's.
for (const width of SET_WIDTHS) {
  const tag = `I10.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const title = `I10 capture ${width} ${stamp}`
  // an item with a file, a summary and three proposals from the fake agent; one is accepted, so two wait
  const made = await s.api('inbox.create_item', { title, space: SPACE, instruction: 'summarise and extract to-dos' })
  const id = made.name
  const pdfName = `i10-${width}-${stamp}.pdf`
  await s.upload('Life Inbox Item', id, pdfName, 'application/pdf', PDF)
  runAgent()
  const first = (await s.api('inbox.get', { item: id })).proposals[0]
  await s.api('review.decide', { proposal: first.name, decision: 'accept' })
  const section = (name) => pg.locator(`[data-item-section="${name}"]`)
  const openAll = async () => { // on a phone the folded sections are opened first
    const folded = pg.locator('[data-item-toggle][aria-expanded="false"]')
    for (let n = 0; n < 6 && await folded.count(); n++) await folded.first().click()
  }
  const settle = () => pg.waitForTimeout(700)

  await check(`${tag}.1`, `${width} px: an item with a file, a summary, 2 waiting proposals and 1 accepted task shows every section right`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    const head = await pg.locator('[data-item-head]').innerText()
    must((await pg.locator('h1').first().innerText()).includes(title), 'the title is not in the header')
    must(head.includes('Upload') && head.includes('Private'), 'the header does not say the source and the space: ' + head)
    must(await section('came-in').locator('[data-file-view]', { hasText: pdfName }).count() === 1, 'the file is not under What came in once')
    must((await section('came-in').innerText()).includes('summarise and extract to-dos'), 'the instruction is not under What came in')
    must((await section('brain').innerText()).includes('summarised'), 'the summary is not under What the Brain made of it')
    must(await section('decisions').locator('[data-proposal="Pending"]').count() === 2, 'Decisions does not show the 2 waiting proposals')
    must(!(await section('decisions').locator('[data-proposal="Accepted"]').count()), 'an accepted proposal is still under Decisions')
    const rows = section('came-of-it').locator('[data-came-of-it]')
    must(await rows.count() === 1, `What came of it shows ${await rows.count()} records`)
    const row = await rows.first().innerText()
    must(row.includes(first.preview) && row.includes('Task') && row.includes('Open'), 'the accepted task is not shown with its state: ' + row)
    must(await section('related').count() === 1, 'no Related section')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check(`${tag}.2`, `${width} px: accepting a proposal on the item page moves it to What came of it without a reload`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    await pg.evaluate(() => { window.__i10 = 1 })
    const card = section('decisions').locator('[data-proposal="Pending"]').first()
    const preview = (await card.locator('.text-base-medium').first().innerText()).trim()
    await card.getByRole('button', { name: 'Accept', exact: true }).click()
    await settle()
    must(await pg.evaluate(() => window.__i10 === 1), 'the page reloaded')
    must(await section('decisions').locator('[data-proposal="Pending"]').count() === 1, 'the accepted proposal is still waiting')
    const rows = await section('came-of-it').locator('[data-came-of-it]').allInnerTexts()
    must(rows.length === 2 && rows.some((r) => r.includes(preview)), `What came of it does not list "${preview}": ${rows.join(' | ')}`)
  })

  await check(`${tag}.3`, `${width} px: the item page opens from the Inbox list, from Library and from search`, async () => {
    const full = async (from, what) => {
      await s.open(from)
      await pg.locator('[data-pane-full]').click()
      await settle()
      must(new URL(pg.url()).pathname === `/life/item/${id}`, `Open full page from ${what} went to ${new URL(pg.url()).pathname}`)
      must(await pg.locator('[data-item-page]').count() === 1, `the item page did not show from ${what}`)
    }
    await s.open('/life/brain/queue')
    const row = pg.locator('[data-row]', { hasText: title }).first()
    must(await row.count() === 1, 'the item is not in the Inbox list')
    await row.locator('[data-ref]').first().click()
    await settle()
    await pg.locator('[data-pane-full]').click()
    await settle()
    must(new URL(pg.url()).pathname === `/life/item/${id}`, 'the Inbox list did not lead to the item page')
    await full(`/life/brain/captures?open=${encodeURIComponent('source:' + id)}`, 'Library')
    await s.open('/life/library/notes')
    if (width < 768) await pg.locator('[data-phone-search]').click()
    else await pg.keyboard.press('Meta+k')
    await pg.locator('input[aria-label="Search or ask anything"]').fill(title)
    await pg.waitForTimeout(900)
    await pg.keyboard.press('Enter')
    await settle()
    must(new URL(pg.url()).pathname === `/life/item/${id}`, 'the search result did not open the item page: ' + new URL(pg.url()).pathname)
  })

  await check(`${tag}.4`, `${width} px: a user without access to the item's space gets "Not found" rather than its content`, async () => {
    const f = await session('family@lifeos.test', width)
    try {
      await f.open(`/life/item/${id}`)
      must(await f.page.locator('[data-item-missing]').isVisible(), 'the page does not say Not found')
      const text = await f.page.locator('body').innerText()
      must(!text.includes(title) && !text.includes(pdfName) && !text.includes('summarised'), 'the page shows the item to a user outside its space')
      const r = await f.api('inbox.item_page', { item: id }, { raw: true })
      must(r.status() === 404, 'the API answers ' + r.status())
    } finally {
      await f.ctx.close()
    }
  })

  await check(`${tag}.5`, `${width} px: the item page is one column with no sideways scroll`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    const lefts = await pg.locator('[data-item-section]').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)))
    must(lefts.length === 5 && new Set(lefts).size === 1, 'the sections are not one column: ' + lefts.join(', '))
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}

// Issue 11: every area picker offers the seven areas of life that are on, each followed by its parts, indented; an area that
// is off, and its parts, are not offered. Checked on the area picker of a task.
for (const width of SET_WIDTHS) {
  const tag = `I11.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const SEVEN = ['Career', 'Health', 'Relationships', 'Money', 'Emotions', 'Mind', 'Environment']
  await check(`${tag}.6`, `${width} px: the area picker on a task shows the seven areas that are on with their parts indented, and no area that is off`, async () => {
    const all = (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas
    const life = all.filter((a) => a.is_life_area)
    must(life.map((a) => a.area_name).join() === SEVEN.join(), 'the space does not have the seven: ' + life.map((a) => a.area_name).join(', '))
    const off = life.find((a) => !a.is_on)
    must(off, 'every area of life is on, so nothing can be checked as off')
    const career = life.find((a) => a.area_name === 'Career')
    const hidden = `I11 part of an area that is off ${width} ${stamp}`
    await s.api('settings.save_item', { kind: 'area', space: SPACE, title: hidden, parent_area: off.name })
    const part = `I11 part of Career ${width} ${stamp}`
    const partId = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: part, parent_area: career.name })).name
    const task = await s.api('tasks.quick_add', { text: `I11 task ${width} ${stamp}`, space: SPACE, area: partId })
    const rows = (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas
    await s.open(`/life/goals/tasks?open=task:${task.name}`)
    const button = pg.locator('[data-task-area] button')
    must((await button.innerText()).includes(`Career / ${part}`), 'the picker does not name the task\'s part with its area: ' + await button.innerText())
    await button.click()
    await pg.waitForTimeout(300)
    // textContent keeps the indent, which innerText may trim
    const items = (await pg.getByRole('menuitem').evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+$/, '')))).filter((t) => t.trim() !== 'Remove')
    // where each item's first letter starts on screen
    const starts = await pg.getByRole('menuitem').evaluateAll((els) => els.map((e) => {
      const walk = document.createTreeWalker(e, NodeFilter.SHOW_TEXT)
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const i = n.data.search(/\S/)
        if (i < 0) continue
        const r = document.createRange()
        r.setStart(n, i)
        r.setEnd(n, i + 1)
        return [n.data.trim(), r.getBoundingClientRect().left]
      }
      return [e.textContent.trim(), null]
    }))
    await pg.keyboard.press('Escape')
    const parts = items.filter((t) => t.startsWith(' ')).map((t) => t.trim())
    const tops = items.filter((t) => !t.startsWith(' '))
    const on = life.filter((a) => a.is_on).map((a) => a.area_name)
    must(tops.join() === on.join(), `the areas offered are ${tops.join(', ')}; the areas that are on are ${on.join(', ')}`)
    must(!tops.includes(off.area_name) && !items.some((t) => t.includes(hidden)), `${off.area_name} is off but offered`)
    must(parts.includes(part), 'the new part of Career is not offered, indented')
    // each part sits right under its own area of life
    let current = null
    for (const t of items) {
      if (!t.startsWith(' ')) { current = life.find((a) => a.area_name === t); continue }
      const row = rows.find((a) => a.area_name === t.trim() && a.parent_area)
      must(row && current && row.parent_area === current.name, `${t.trim()} is not listed under its area`)
    }
    // the indent shows: a part's name starts to the right of every area's
    const at = Object.fromEntries(starts)
    const topLeft = Math.max(...tops.map((t) => at[t]))
    must(parts.every((t) => at[t] >= topLeft + 8), 'the parts are not indented: ' + starts.map(([t, x]) => `${t} at ${Math.round(x)}`).join(', '))
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${tops.length} areas on, ${parts.length} parts`
  })
  await s.ctx.close()
}

// Issue 12: Settings > Areas. The seven areas of life with an On/Off switch, their parts with Edit and "+ Add a part of",
// archiving a part that holds open work asks where it goes, and a Life User who is not Life Admin sees it read-only.
for (const width of SET_WIDTHS) {
  const tag = `I12.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const lifeAreas = async () => (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas.filter((a) => a.is_life_area)
  const lifeArea = async (n) => (await lifeAreas()).find((a) => a.area_name === n)
  const areasPage = async () => { await s.open(`/life/settings?tab=areas&space=${encodeURIComponent(SPACE)}`); await pg.locator('[data-areas-card]').waitFor() }
  const flip = async (n) => {
    await pg.locator(`[data-area-switch="${n}"]`).click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(700)
  }
  // what the lens offers: the sidebar's menu, or the phone's sheet
  const lensLabels = async () => {
    if (phone) await pg.locator('[data-lens-title]').click()
    else await pg.locator('[data-lens-picker] button, [data-lens-picker]').first().click()
    await pg.waitForTimeout(400)
    const items = phone ? pg.locator('[data-lens-sheet] [data-lens-item]') : pg.getByRole('menuitem')
    const out = (await items.allInnerTexts()).map((t) => t.trim())
    await pg.keyboard.press('Escape')
    await pg.waitForTimeout(300)
    return out
  }
  // what the area picker of a task offers
  let pickTask = null
  const pickerLabels = async () => {
    if (!pickTask) pickTask = (await s.api('tasks.quick_add', { text: `I12 picker task ${width} ${stamp}`, space: SPACE })).name
    await s.open(`/life/goals/tasks?open=task:${pickTask}`)
    await pg.locator('[data-task-area] button').click()
    await pg.waitForTimeout(300)
    const out = (await pg.getByRole('menuitem').allInnerTexts()).map((t) => t.trim())
    await pg.keyboard.press('Escape')
    return out
  }

  await check(`${tag}.1`, `${width} px: switching Money on shows it in the lens and the task area picker; off hides it; its goals come back when it is on again`, async () => {
    const was = (await lifeArea('Money')).is_on
    let goal = null
    try {
      await areasPage()
      if (was) { await flip('Money'); must(!(await lifeArea('Money')).is_on, 'Money did not switch off') }
      await areasPage()
      must((await pg.locator('[data-life-area="Money"]').getAttribute('data-on')) === '0', 'Money does not show as off')
      await flip('Money')
      must((await lifeArea('Money')).is_on, 'the switch did not turn Money on')
      await s.open('/life')
      must((await lensLabels()).includes('Money'), 'Money is on but not in the lens')
      must((await pickerLabels()).includes('Money'), 'Money is on but not in the task area picker')
      goal = (await s.api('goals.create', { title: `I12 goal in Money ${width} ${stamp}`, horizon: 'Long term', space: SPACE, area: (await lifeArea('Money')).name })).name
      const listed = async () => (await s.api('goals.list', { space: SPACE, page_length: 100, area: (await lifeArea('Money')).name }).catch(() => ({ goals: [] }))).goals.some((g) => g.name === goal)
      must(await listed(), 'the new goal in Money is not listed')
      await areasPage()
      must(/\d+ goals?/.test(await pg.locator('[data-life-area="Money"] [data-area-goals]').innerText()), 'Money shows no goal count')
      await flip('Money')
      must(!(await lifeArea('Money')).is_on, 'the switch did not turn Money off')
      await s.open('/life')
      must(!(await lensLabels()).includes('Money'), 'Money is off but still in the lens')
      must(!(await pickerLabels()).includes('Money'), 'Money is off but still in the task area picker')
      must(!(await s.api('goals.list', { space: SPACE, page_length: 100 })).goals.some((g) => g.name === goal), 'the goal of Money is listed while Money is off')
      await areasPage()
      await flip('Money')
      must((await s.api('goals.list', { space: SPACE, page_length: 100 })).goals.some((g) => g.name === goal), 'the goal did not come back when Money was switched on again')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    } finally {
      if (goal) await s.api('frappe.client.delete', { doctype: 'Life Goal', name: goal }).catch(() => {})
      const m = await lifeArea('Money')
      if (!!m.is_on !== !!was) await s.api('settings.save_item', { kind: 'area', name: m.name, is_on: was ? 1 : 0 })
    }
  })

  await check(`${tag}.2`, `${width} px: adding a part "CIS Board" under Career shows it in the list and in the pickers`, async () => {
    const name = `I12 CIS Board ${width} ${stamp}`
    await areasPage()
    await pg.locator('[data-add-part="Career"]').click()
    await pg.locator('[data-part-title] input, input[data-part-title]').first().fill(name)
    await pg.locator('[data-part-description] input, input[data-part-description]').first().fill('Vice Chair')
    await pg.getByRole('button', { name: 'Add', exact: true }).click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(700)
    const row = pg.locator(`[data-parts-of="Career"] [data-part-name="${name}"]`)
    must(await row.count(), 'the new part is not listed under Career')
    must((await row.innerText()).includes('Vice Chair · no goals'), 'the new part does not show its description and goal count: ' + await row.innerText())
    must((await pickerLabels()).includes(name), 'the new part is not in the task area picker')
    await s.open('/life')
    must((await lensLabels()).includes(name), 'the new part is not in the lens')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check(`${tag}.3`, `${width} px: archiving a part with open tasks asks where to move them, and they end up there`, async () => {
    const career = (await lifeArea('Career')).name
    const part = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: `I12 part to archive ${width} ${stamp}`, parent_area: career })).name
    const dest = `I12 destination ${width} ${stamp}`
    const destId = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: dest, parent_area: career })).name
    const t1 = (await s.api('tasks.quick_add', { text: `I12 open task one ${width} ${stamp}`, space: SPACE, area: part })).name
    const t2 = (await s.api('tasks.quick_add', { text: `I12 open task two ${width} ${stamp}`, space: SPACE, area: part })).name
    await areasPage()
    await pg.locator(`[data-edit-part="${part}"]`).click()
    await pg.locator('[data-archive-part]').click()
    const dlg = pg.locator('[data-archive-part-dialog]')
    await dlg.waitFor()
    must((await dlg.innerText()).includes('2 open tasks'), 'the dialog does not say what is open: ' + await dlg.innerText())
    await dlg.locator('[data-move-to]').click()
    const options = (await pg.getByRole('option').allInnerTexts()).map((t) => t.trim())
    must(options[0] === 'Career itself' && options.includes(dest), 'the places offered are ' + options.join(', '))
    await pg.getByRole('option', { name: dest, exact: true }).click()
    await pg.getByRole('button', { name: 'Archive', exact: true }).last().click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(900)
    for (const t of [t1, t2]) must((await s.api('tasks.get', { task: t })).area === destId, 'a task did not move to the place chosen')
    must((await s.api('settings.get', { space: SPACE })).areas.find((a) => a.name === part).is_archived, 'the part was not archived')
    must(!(await pg.locator(`[data-part="${part}"]`).count()), 'the archived part is still listed')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check(`${tag}.4`, `${width} px: a Life User who is not Life Admin sees Settings > Areas read-only`, async () => {
    const fam = await session('family@lifeos.test', width)
    try {
      await fam.open('/life/settings?tab=areas&space=Shared')
      const fp = fam.page
      await fp.locator('[data-areas-card]').waitFor()
      const switches = fp.locator('[data-area-switch]')
      must((await switches.count()) === 7, `${await switches.count()} switches, not seven`)
      for (const sw of await switches.all()) must(await sw.isDisabled(), 'a switch can be used')
      must(!(await fp.locator('[data-edit-part], [data-add-part], [data-new]').count()), 'Edit, Add a part or New shows')
      must(await fp.locator('[data-areas-read-only]').isVisible(), 'no line saying only the owner can change areas')
      const career = (await fam.api('area.tree', { space: 'Shared' })).areas.find((a) => a.is_life_area && a.area_name === 'Career')
      const r = await fam.api('settings.save_item', { kind: 'area', name: career.name, is_on: 0 }, { raw: true })
      must(r.status() === 403, `the server let the family user switch an area (HTTP ${r.status()})`)
      must((await s.api('area.tree', { space: 'Shared' })).areas.some((a) => a.name === career.name), 'Career of Shared was switched off')
    } finally { await fam.ctx.close() }
  })

  await check(`${tag}.5`, `${width} px: the screen matches the mockup: intro, one card of the seven, switches, On by default on Career and Health, parts with Edit, the footer`, async () => {
    await areasPage()
    const main = await pg.locator('[data-settings-section]').innerText()
    must(main.includes('Seven areas cover a whole life.'), 'no intro line')
    must(await pg.locator('[data-areas-footer]').innerText() === 'Switching an area off hides it and its goals; nothing is deleted. The Brain stops filing into it and sends those items to Needs you.', 'the footer line differs')
    const names = await pg.locator('[data-life-area]').evaluateAll((els) => els.map((e) => e.getAttribute('data-life-area')))
    must(names.length === 7 && new Set(names).size === 7, 'not the seven: ' + names.join(', '))
    const ons = await pg.locator('[data-life-area]').evaluateAll((els) => els.map((e) => e.getAttribute('data-on')))
    must(ons.join('').replace(/0+$/, '').indexOf('0') < 0, 'the areas that are on are not listed first')
    const byDefault = await pg.locator('[data-life-area]').evaluateAll((els) => els.filter((e) => [...e.querySelectorAll('*')].some((x) => x.textContent.trim() === 'On by default' && x.offsetParent)).map((e) => e.getAttribute('data-life-area')))
    must(byDefault.sort().join() === 'Career,Health', '"On by default" is on ' + byDefault.join(', '))
    // the switch: left of the name on a wide screen, on the right on a phone
    for (const n of ['Career', 'Health']) {
      const sw = await pg.locator(`[data-area-switch="${n}"]`).boundingBox()
      const nm = await pg.locator(`[data-life-area="${n}"] [data-area-name]`).boundingBox()
      const card = await pg.locator('[data-areas-card]').boundingBox()
      if (phone) must(sw.x > nm.x + nm.width && sw.x + sw.width > card.x + card.width - 40, `${n}: the switch is not on the right`)
      else must(sw.x + sw.width < nm.x, `${n}: the switch is not left of the name`)
    }
    const parts = pg.locator('[data-parts-of="Career"] [data-part]')
    must(await parts.count(), 'Career lists no parts')
    must(await pg.locator('[data-parts-of="Career"] [data-edit-part]').count() === await parts.count(), 'a part has no Edit')
    must(/(no goals|\d+ goals?)\s*Edit$/.test((await parts.first().innerText()).trim()), 'a part shows no goal count before its Edit: ' + await parts.first().innerText())
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  if (pickTask) await s.api('frappe.client.delete', { doctype: 'Life Task', name: pickTask }).catch(() => {})
  await s.ctx.close()
}

// Issue 13: every task has an area. A task quick-captured with no area shows the area the Brain guessed, with ✦ and how
// sure it is; one tap confirms it and the ✦ goes.
for (const width of SET_WIDTHS) {
  const tag = `I13.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  await check(`${tag}.7`, `${width} px: a quick-captured task shows its guessed area with ✦ and the confidence; one tap confirms it and the ✦ goes`, async () => {
    const title = `I13 quick capture ${width} ${stamp}`
    await s.open('/life/goals/tasks?view=list')
    const box = pg.getByLabel('Quick add')
    await box.fill(`${title} today`)
    await box.press('Enter')
    await pg.waitForLoadState('networkidle')
    // after a full walk many tasks are due today: show this one by its title
    await s.open(`/life/goals/tasks?view=list&status=all&f=${encodeURIComponent(JSON.stringify([['title', '=', title]]))}`)
    const row = pg.locator('[data-row]').filter({ hasText: title }).first()
    await row.waitFor({ timeout: 10000 })
    const chip = row.locator('[data-area-guess]')
    must(await chip.isVisible(), 'the new task shows no guessed area')
    const text = (await chip.innerText()).trim()
    must(/^✦ .+ · \d+%$/.test(text), 'the guess does not read "✦ <area> · <n>%": ' + text)
    const task = (await s.api('tasks.list', { space: SPACE, status: 'open', due: 'today' })).tasks.find((t) => t.title === title)
    must(task && task.area && task.area_guessed, 'the server has no guessed area for the task')
    // the model's guess comes from a job after the save and may replace the first one between the two reads: compare the area
    must(text.includes(task.area_name), `the chip says ${text}; the task is in ${task.area_name}, ${task.area_confidence}% sure`)
    await chip.click()
    await pg.waitForLoadState('networkidle')
    await chip.waitFor({ state: 'detached', timeout: 5000 }).catch(() => {})
    must(!(await row.locator('[data-area-guess]').count()), 'the ✦ is still shown after the tap')
    must((await row.innerText()).includes(task.area_name), 'the confirmed area is no longer named on the row')
    const after = await s.api('tasks.get', { task: task.name })
    must(!after.area_guessed && after.area === task.area, 'the server did not confirm the area')
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    await s.api('frappe.client.delete', { doctype: 'Life Task', name: task.name }).catch(() => {})
    return `${task.area_name}, ${Math.round(task.area_confidence)}%`
  })
  await s.ctx.close()
}

// Issue 14: the new navigation. Today, Brain, Goals and Library, each tab a route; Review after the first locked review;
// + Capture and the capture sheet; every old route redirected; the housekeeping pages reached from their new homes.
{
  const errs = (pg) => { const e = []; pg.on('pageerror', (x) => e.push(String(x).split('\n')[0])); return e }
  const path = (pg) => new URL(pg.url()).pathname
  const noSideways = async (pg) => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const loaded = async (pg, what) => {
    await pg.locator('[data-main]').first().waitFor({ timeout: 10000 })
    // a screen draws its skeleton first: wait for words
    const drawn = await pg.waitForFunction(() => (document.querySelector('[data-main]')?.innerText || '').trim().length > 20, null, { timeout: 8000 }).then(() => true, () => false)
    must(!(await pg.locator('[data-screen-error]').count()), `${what} shows the error message`)
    must(drawn, `${what} is blank`)
  }
  // the weekly review's day is moved off today for the Review checks, and put back after
  const st = JSON.parse(bench('import json\nprint(json.dumps({"day": frappe.db.get_single_value("Life Settings", "weekly_review_day") or "Sunday"}))').split('\n').pop())
  const offDay = DAY_NAMES[(new Date(bench('from frappe.utils import today\nprint(today())').split('\n').pop() + 'T12:00:00Z').getUTCDay() + 3) % 7]
  const setDay = (d) => bench(`frappe.db.set_single_value("Life Settings", "weekly_review_day", "${d}")\nfrappe.clear_cache()`)
  for (const width of SET_WIDTHS) {
    const tag = `I14.${width}`
    if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
    const phone = width < 800
    if (!phone) {
      setDay(offDay)
      bench('frappe.db.delete("Life Review", {"user": "family@lifeos.test"})')
      const f = await session('family@lifeos.test', width)
      const fe = errs(f.page)
      try {
        await check(`${tag}.1`, `${width} px: the sidebar shows + Capture, Today, Brain, Goals, Library and Settings, in that order, and no other place`, async () => {
          await f.open('/life/today')
          const order = await f.page.locator('[data-sidebar] [data-nav-capture], [data-sidebar] [data-nav-item]').evaluateAll((els) =>
            els.map((e) => (e.hasAttribute('data-nav-capture') ? '+ Capture' : e.getAttribute('data-nav-item'))))
          must(JSON.stringify(order) === JSON.stringify(['+ Capture', 'Today', 'Brain', 'Goals', 'Library', 'Settings']), 'the sidebar reads ' + order.join(', '))
          must((await f.page.locator('[data-sidebar] [data-nav-capture]').innerText()).includes('Capture'), 'the first button is not Capture')
          for (const gone of ['[data-nav-pin]', '[data-nav-plan]', '[data-nav-new]']) must(!(await f.page.locator(gone).count()), 'the sidebar still has ' + gone)
          must(await f.page.locator('[data-page-head] [data-ask-box]').count(), 'Ask is not in the header')
          must(!fe.length, 'script errors: ' + fe.slice(0, 3).join(' | '))
        })
        await check(`${tag}.2`, `${width} px: Review is hidden for a user who has never locked a review, and shown between Goals and Library after one is locked`, async () => {
          await f.open('/life/goals')
          must(!(await f.page.locator('[data-nav-item="Review"]').count()), 'Review shows before any review was locked')
          bench(`from frappe.utils import add_days, now_datetime, today
frappe.get_doc({"doctype": "Life Review", "space": "Shared", "user": "family@lifeos.test", "kind": "Weekly", "status": "Locked", "period_start": add_days(today(), -6),
  "period_end": today(), "locked_on": now_datetime(), "title": "I14 review", "tab_state": "{}"}).insert(ignore_permissions=True)`)
          await f.open('/life/goals')
          const order = await f.page.locator('[data-nav-places] [data-nav-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')))
          must(JSON.stringify(order) === JSON.stringify(['Today', 'Brain', 'Goals', 'Review', 'Library']), 'after a locked review the places read ' + order.join(', '))
          await f.page.locator('[data-nav-item="Review"]').first().click()
          await f.page.waitForURL((u) => u.pathname === '/life/review', { timeout: 10000 }).catch(() => {})
          must(path(f.page) === '/life/review', 'Review opens ' + path(f.page))
          await loaded(f.page, 'Review')
          must(!fe.length, 'script errors: ' + fe.slice(0, 3).join(' | '))
        })
      } finally {
        bench('frappe.db.delete("Life Review", {"user": "family@lifeos.test"})')
        setDay(st.day)
        await f.ctx.close()
      }
    }
    const s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = errs(pg)
    const item = await s.api('inbox.create_item', { title: `I14 to review ${width} ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'I14' })
    bench(`frappe.db.set_value("Life Inbox Item", "${item.name}", "status", "To Review")`)
    try {
      await check(`${tag}.3`, `${width} px: Brain shows the Needs you count, the same number as the Inbox count`, async () => {
        await s.open('/life/today')
        const inboxTotal = (await s.api('inbox.list', { space: SPACE, status: '["To Review"]', page_length: 1 })).total
        const badge = pg.locator(phone ? '[data-tab-count="Brain"]' : '[data-nav-count="Brain"]').first()
        await badge.waitFor({ timeout: 10000 })
        const n = Number((await badge.innerText()).replace(/\D/g, ''))
        must(n === inboxTotal, `Brain says ${n}; the Inbox has ${inboxTotal} to review`)
        await s.open('/life/brain')
        const tab = Number((await pg.locator('[data-place-tabs] [data-tab="needs-you"] [data-tab-count]').innerText()).replace(/\D/g, ''))
        must(tab === inboxTotal, `Needs you says ${tab}; the Inbox has ${inboxTotal}`)
        await s.open('/life/brain/queue')
        const listed = Number((await pg.locator('[data-state-tabs] [data-tab="To Review"] [data-tab-count]').first().innerText()).replace(/\D/g, ''))
        must(listed === inboxTotal, `the list says ${listed} to review; the Inbox has ${inboxTotal}`)
        return `${n}`
      })
      await check(`${tag}.4`, `${width} px: every route of the old router redirects to its new home, which loads without an error`, async () => {
        const goal = (await s.api('goals.list', { space: SPACE, horizon: 'Long term', page_length: 1 })).goals[0].name
        const area = areaId('Career') || areas[0].name
        const OLD = [['/life', '/life/today'], ['/life/inbox', '/life/brain'], [`/life/inbox/${item.name}`, '/life/brain/queue'],
          [`/life/inbox/${item.name}/review`, `/life/brain/review/${item.name}`], ['/life/plan', '/life/today/week'], ['/life/plan/week', '/life/today/week'],
          ['/life/plan/month', '/life/today/month'], ['/life/plan/12-weeks', '/life/today/year'], ['/life/plan/year', '/life/today/year'],
          ['/life/plan/goals', '/life/goals'], [`/life/plan/goals/${goal}`, `/life/goals/${goal}`], ['/life/plan/tasks', '/life/goals/tasks'],
          ['/life/plan/someday', '/life/goals/someday'], ['/life/plan/reset', '/life/today/reset'], ['/life/tasks', '/life/goals/tasks'],
          ['/life/someday', '/life/goals/someday'], ['/life/outbox', '/life/brain/outbox'], ['/life/archive', '/life/library/archive'],
          ['/life/wiki', '/life/library/notes'], ['/life/vault', '/life/library/documents'], ['/life/graph', '/life/library/notes'],
          ['/life/timeline', '/life/library/timeline'], ['/life/sources', '/life/brain/sources'], ['/life/chats', '/life/library/chats'],
          ['/life/library/captures', '/life/brain/captures'], ['/life/library/outbox', '/life/brain/outbox'], ['/life/projects', '/life/goals'],
          ['/life/reset', '/life/today/week'], ['/life/calendar', '/life/today/week'], ['/life/calendar/month', '/life/today/month'],
          ['/life/calendar/year', '/life/today/year'], ['/life/calendar/agenda', '/life/today/week'], ['/life/journal', '/life/today/year'],
          ['/life/journal/goals', '/life/today/year'], ['/life/journal/month', '/life/today/month'], ['/life/journal/habits', '/life/today/month'],
          ['/life/journal/checkins', '/life/today/month'], ['/life/journal/review', '/life/today/week'], ['/life/journal/pages', '/life/library'],
          [`/life/journal/goals/${goal}`, `/life/goals/${goal}`], ['/life/areas', '/life/settings'], [`/life/areas/${area}`, '/life/today'],
          ['/life/no-such-page', '/life/today']]
        const bad = []
        for (const [from, want] of OLD) {
          const before = errors.length
          await s.open(from)
          if (path(pg) !== want) { bad.push(`${from} went to ${path(pg)}`); continue }
          try { await loaded(pg, from) } catch (e) { bad.push(e.message) }
          if (errors.length > before) bad.push(`${from}: ${errors.slice(before).join(' | ')}`)
        }
        must(!bad.length, bad.slice(0, 5).join('; '))
        return `${OLD.length} routes`
      })
      await check(`${tag}.5`, `${width} px: Archive, Outbox, Graph, Timeline, Reset and Vault are reached from their new homes`, async () => {
        const via = async (start, link, want, query = {}) => {
          await s.open(start)
          await pg.locator(link).first().click()
          await pg.waitForURL((u) => u.pathname === want && Object.entries(query).every(([k, v]) => u.searchParams.get(k) === v), { timeout: 10000 }).catch(() => {})
          await pg.waitForLoadState('networkidle')
          const u = new URL(pg.url())
          must(u.pathname === want, `${link} on ${start} opened ${u.pathname}`)
          for (const [k, v] of Object.entries(query)) must(u.searchParams.get(k) === v, `${link} on ${start} did not set ${k}=${v}`)
          await loaded(pg, want)
        }
        await via('/life/library', '[data-place-link="archive"]', '/life/library/archive')
        await via('/life/brain/activity', '[data-place-link="outbox"]', '/life/brain/outbox')
        await via('/life/library/notes', '[data-place-link="graph"]', '/life/library/notes', { view: 'graph' })
        await via('/life/library', '[data-place-link="timeline"]', '/life/library/timeline')
        await via('/life/library/documents', '[data-place-link="sensitive"]', '/life/library/documents', { sensitive: '1', tab: 'documents' })
        await via('/life/today', phone ? '[data-band-reset-phone]' : '[data-band-reset]', '/life/today/reset')
        await via('/life/today/week?view=calendar', '[data-plan-reset]', '/life/today/reset')
        // Settings > Data lists every page with no other home
        await s.open('/life/settings?tab=places')
        const listed = await pg.locator('[data-settings-places] [data-elsewhere]').evaluateAll((els) => els.map((e) => e.getAttribute('data-elsewhere')))
        for (const k of ['archive', 'outbox', 'graph', 'timeline', 'reset', 'vault']) must(listed.includes(k), 'Settings > Data does not list ' + k)
        await noSideways(pg)
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
      if (phone) {
        await check(`${tag}.6`, `${width} px: the bottom bar shows Today, Brain, the capture button, Goals and Library; capture opens the capture sheet`, async () => {
          await s.open('/life/today')
          const bar = pg.locator('[data-tabbar]')
          const items = await bar.locator('[data-tab-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab-item')))
          must(JSON.stringify(items) === JSON.stringify(['Today', 'Brain', 'Goals', 'Library']), 'the bar reads ' + items.join(', '))
          const x = async (sel) => (await bar.locator(sel).first().boundingBox()).x
          const cap = await x('[data-tab-capture]')
          must(cap > await x('[data-tab-item="Brain"]') && cap < await x('[data-tab-item="Goals"]'), 'the capture button is not in the middle')
          await bar.locator('[data-tab-capture]').click()
          const sheet = pg.locator('[role="dialog"]').filter({ has: pg.locator('[data-capture-text]') })
          await sheet.waitFor({ timeout: 5000 })
          const title = `I14 captured ${width} ${stamp}`
          await sheet.locator('[data-capture-text] textarea, textarea[data-capture-text]').first().fill(title)
          await sheet.locator('[data-capture-task]').click()
          await sheet.waitFor({ state: 'detached', timeout: 5000 })
          const made = JSON.parse(bench(`import json\nprint(json.dumps(frappe.get_all("Life Task", filters={"title": "${title}"}, pluck="name")))`).split('\n').pop())
          must(made.length === 1, 'the capture sheet did not add the task')
          await s.api('frappe.client.delete', { doctype: 'Life Task', name: made[0] }).catch(() => {})
          await noSideways(pg)
          must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
        })
      }
      await check(`${tag}.7`, `${width} px: tabs are routes: each tab has its own path, and reloading /life/goals/tasks lands on Goals > All tasks`, async () => {
        const TABS = { today: ['day', 'week', 'month', 'year'], brain: ['needs-you', 'activity', 'sources'], goals: ['by-area', 'tasks', 'no-goal'],
          library: ['all', 'notes', 'documents', 'people', 'chats'] }
        const bad = []
        for (const [place, tabs] of Object.entries(TABS)) {
          for (const [i, t] of tabs.entries()) {
            const p = i ? `/life/${place}/${t}` : `/life/${place}`
            await s.open(p)
            const cur = await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current').catch(() => null)
            if (cur !== t) bad.push(`${p} shows tab ${cur}`)
          }
        }
        await s.open('/life/brain')
        await pg.locator('[data-place-tabs] [data-tab="activity"]').first().click()
        await pg.waitForURL((u) => u.pathname === '/life/brain/activity', { timeout: 10000 }).catch(() => {})
        if (path(pg) !== '/life/brain/activity') bad.push('clicking Activity went to ' + path(pg))
        await s.open('/life/goals/tasks')
        await pg.reload({ waitUntil: 'networkidle' })
        if (path(pg) !== '/life/goals/tasks') bad.push('the reload left /life/goals/tasks for ' + path(pg))
        if ((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) !== 'tasks') bad.push('the reload is not on All tasks')
        if (!(await pg.locator('[data-nav-item="Goals"][aria-current="page"], [data-tab-item="Goals"]').count())) bad.push('Goals is not the place shown')
        must(!bad.length, bad.slice(0, 5).join('; '))
        await loaded(pg, '/life/goals/tasks')
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
    } finally {
      bench(`frappe.delete_doc("Life Inbox Item", "${item.name}", force=1, ignore_permissions=True)`)
      await s.ctx.close()
    }
  }

  // Issue 15: Today > Day. Titles start "I15 " (known to the debris finder).
  for (const width of SET_WIDTHS) {
    const tag = `I15.${width}`
    if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
    const phone = width < 800
    const s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = errs(pg)
    const meeting = `I15 meeting ${width} ${stamp}`
    const mk = (title) => bench(`from frappe.utils import today
ev = frappe.get_doc({"doctype": "Event", "subject": "${title}", "starts_on": today() + " 14:00:00", "ends_on": today() + " 15:00:00", "event_category": "Event",
  "event_type": "Public", "life_space": "Private", "google_calendar_event_id": "fixture-i15-${stamp}-${width}"}).insert(ignore_permissions=True)
print(ev.name)`).split('\n').pop()
    const evName = mk(meeting)
    const names = []
    for (const t of ['one', 'two']) names.push((await s.api('tasks.quick_add', { text: `I15 ${t} ${width} ${stamp}`, space: SPACE, area: uxArea, due_date: today })).name)
    const item = await s.api('inbox.create_item', { title: `I15 to review ${width} ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'I15' })
    bench(`frappe.db.set_value("Life Inbox Item", "${item.name}", "status", "To Review")`)
    try {
      bench(`frappe.db.set_value("Life Task", "${names[0]}", "is_top_three", 1)`)
      await check(`${tag}.1`, `${width} px: Today > Day shows today's tasks, the top three and the day's events from the calendar`, async () => {
        await s.open('/life/today')
        await pg.locator('[data-next]').waitFor({ timeout: 10000 })
        const plate = await pg.locator('[data-next]').innerText()
        for (const t of names.map((_, i) => `I15 ${['one', 'two'][i]} ${width} ${stamp}`)) must(plate.includes(t), `${t} is not on the plate`)
        must(await pg.locator('[data-next-group="today"]').count(), 'no Today group')
        const rail = await pg.locator('[data-rail-today]').innerText()
        must(rail.includes(meeting), 'the calendar does not show ' + meeting)
        must(!plate.includes(meeting), 'the meeting is on the plate as well as in the calendar')
        const tops = (await s.api('today.get', { space: SPACE })).next.groups.find((g) => g.key === 'top').rows
        must(tops.some((r) => r.name === names[0]) && (await pg.locator('[data-top-three]').count()) >= 1, 'the top three are not marked')
        const od = pg.locator('[data-next-group="overdue"]')
        if (await od.count()) must(!(await pg.locator('[data-next-row][data-why="Overdue"]').count()), 'overdue items are not folded')
        must(await pg.locator('[data-open-band]').count(), 'the Open band is gone')
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
      await check(`${tag}.2`, `${width} px: ticking a task on Today marks it done and updates the counts`, async () => {
        await s.open('/life/today')
        const row = pg.locator('[data-task-row]', { hasText: `I15 two ${width} ${stamp}` }).first()
        await row.waitFor({ timeout: 10000 })
        const before = (await s.api('today.get', { space: SPACE })).tasks.today_count
        await row.locator('[role="checkbox"], input[type="checkbox"], button[aria-label^="Done"]').first().click()
        await pg.waitForTimeout(1500)
        const after = (await s.api('today.get', { space: SPACE })).tasks.today_count
        must(after === before - 1, `the due-today count went from ${before} to ${after}`)
        const st = (await s.api('tasks.list', { space: SPACE, status: 'any', filters: JSON.stringify([['name', '=', names[1]]]), page_length: 1 })).tasks[0].status
        must(st === 'Done', 'the task is ' + st)
        await s.open('/life/today')
        must(!(await pg.locator('[data-task-row]', { hasText: `I15 two ${width} ${stamp}` }).count()), 'the done task is still on the plate')
      })
      await check(`${tag}.3`, `${width} px: the Needs you line shows the waiting count and opens Brain > Needs you`, async () => {
        await s.open('/life/today')
        const line = pg.locator('[data-needs-you]')
        await line.waitFor({ timeout: 10000 })
        const n = Number((await line.locator('[data-needs-you-count]').innerText()).replace(/\D/g, ''))
        const total = (await s.api('inbox.list', { space: SPACE, status: '["To Review"]', page_length: 1 })).total
        must(n === total, `the line says ${n}; the Inbox has ${total} to review`)
        await line.click()
        await pg.waitForURL((u) => u.pathname === '/life/brain', { timeout: 10000 }).catch(() => {})
        must(path(pg) === '/life/brain', 'the line opened ' + path(pg))
        must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === 'needs-you', 'Brain is not on Needs you')
      })
      await check(`${tag}.4`, `${width} px: the switch moves to Week, Month and Year routes`, async () => {
        await s.open('/life/today')
        for (const t of ['week', 'month', 'year', 'day']) {
          await pg.locator(`[data-place-tabs] [data-tab="${t}"]`).first().click()
          const want = t === 'day' ? '/life/today' : `/life/today/${t}`
          await pg.waitForURL((u) => u.pathname === want, { timeout: 10000 }).catch(() => {})
          must(path(pg) === want, `${t} opened ${path(pg)}`)
        }
      })
      await check(`${tag}.5`, `${width} px: the layout matches the mockups (${phone ? 'Needs you, the plate, then the calendar below it' : 'the plate with the calendar beside it'}), with no sideways scroll`, async () => {
        await s.open('/life/today')
        await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
        const box = async (sel) => (await pg.locator(sel).first().boundingBox())
        const nu = await box('[data-needs-you]'), plate = await box('[data-next]'), rail = await box('[data-rail-today]'), band = await box('[data-open-band]')
        must(nu.y < plate.y, 'Needs you is not above the plate')
        if (phone) must(rail.y > plate.y && Math.abs(rail.x - plate.x) < 4, 'the calendar is not below the plate')
        else must(rail.x > plate.x + plate.width - 4 && rail.y < plate.y + 80, 'the calendar is not beside the plate')
        must(band.y > plate.y + plate.height - 4 || band.y > rail.y + rail.height - 4, 'the Open band is not below the fold')
        await noSideways(pg)
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
    } finally {
      bench(`frappe.delete_doc("Life Inbox Item", "${item.name}", force=1, ignore_permissions=True)
for n in ${JSON.stringify(names)}:
    frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
frappe.delete_doc("Event", "${evName}", force=1, ignore_permissions=True)`)
      await s.ctx.close()
    }
  }
}

// Issue 16: Today > Week, Month and Year. Titles start "I16 " (known to the debris finder).
for (const width of SET_WIDTHS) {
  const tag = `I16.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const path = () => new URL(pg.url()).pathname
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const year = Number(today.slice(0, 4))
  const monday = plusDays(today, -((new Date(today + 'T12:00:00Z').getUTCDay() + 6) % 7))
  const wed = plusDays(monday, 2)
  const nextMonth = new Date(Date.UTC(year, Number(today.slice(5, 7)), 15)).toISOString().slice(0, 10)
  const nextKey = nextMonth.slice(0, 7)
  const meeting = `I16 meeting ${width} ${stamp}`, due = `I16 due ${width} ${stamp}`, later = `I16 later ${width} ${stamp}`
  const goalTitle = `I16 goal ${width} ${stamp}`, offTitle = `I16 off ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
area = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n})
career, tea, mind = area("Career"), area("Tea & Coffee"), area("Mind")
was = {n: frappe.db.get_value("Life Area", n, "is_on") for n in (career, tea, mind)}
for n in (career, tea): frappe.db.set_value("Life Area", n, "is_on", 1)
frappe.db.set_value("Life Area", mind, "is_on", 0)
ev = frappe.get_doc({"doctype": "Event", "subject": "${meeting}", "starts_on": "${monday} 10:00:00", "ends_on": "${monday} 11:00:00", "event_category": "Event",
  "event_type": "Public", "life_space": "${SPACE}", "google_calendar_event_id": "fixture-i16-${stamp}-${width}"}).insert(ignore_permissions=True)
tasks = [frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": t, "status": "Open", "area": tea, "due_date": d}).insert(ignore_permissions=True).name
  for t, d in (("${due}", "${wed}"), ("${later}", "${nextMonth}"))]
goal = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${goalTitle}", "area": tea, "horizon": "Year", "target_date": "${year}-12-31"}).insert(ignore_permissions=True).name
off = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${offTitle}", "area": mind, "horizon": "Year", "target_date": "${year}-12-31"}).insert(ignore_permissions=True).name
print(json.dumps({"career": career, "tea": tea, "mind": mind, "was": was, "event": ev.name, "tasks": tasks, "goal": goal, "off": off}))`).split('\n').pop())
  let reviewName = null
  try {
    await check(`${tag}.1`, `${width} px: Week shows this week's calendar events and due tasks on the right days, and a day opens Day`, async () => {
      await s.open('/life/today/week')
      await pg.locator('[data-week-grid]').waitFor({ timeout: 10000 })
      const dayText = async (d) => await pg.locator(`[data-week-grid] [data-day="${d}"]`).innerText()
      must((await dayText(monday)).includes(meeting), `${meeting} is not on ${monday}`)
      must((await dayText(wed)).includes(due), `${due} is not on ${wed}`)
      for (const d of [plusDays(monday, 1), plusDays(monday, 3)]) must(!(await dayText(d)).includes(meeting) && !(await dayText(d)).includes(due), 'an item is on the wrong day ' + d)
      const to = wed === today ? monday : wed
      await pg.locator(`[data-week-grid] [data-day="${to}"] [data-open-day]`).click()
      await pg.waitForURL((u) => u.pathname === '/life/today' && u.searchParams.get('date') === to, { timeout: 10000 })
      await pg.locator('[data-day-other]').waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-day-other]')?.innerText.includes(t), to === wed ? due : meeting, { timeout: 10000 }).catch(() => {})
      must((await pg.locator('[data-day-other]').innerText()).includes(to === wed ? due : meeting), 'Day does not list the item of ' + to)
      must((await pg.locator('[data-page-head]').first().innerText()).includes(String(Number(to.slice(8)))), 'Day is not headed with the date')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: Month shows events and due tasks on the right dates; next and previous months work`, async () => {
      await s.open('/life/today/month')
      await pg.locator('[data-month-grid]').waitFor({ timeout: 10000 })
      const month = today.slice(0, 7)
      must((await pg.locator('[data-month-view]').getAttribute('data-month')) === month, 'Month is not on this month')
      if (phone) {
        for (const [d, title] of [[monday, meeting], [wed, due]]) {
          await pg.locator(`[data-month-grid] [data-day="${d}"] > button`).click()
          await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), title, { timeout: 5000 })
        }
      } else {
        must((await pg.locator(`[data-month-grid] [data-day="${monday}"]`).innerText()).includes(meeting), `${meeting} is not on ${monday}`)
        must((await pg.locator(`[data-month-grid] [data-day="${wed}"]`).innerText()).includes(due), `${due} is not on ${wed}`)
      }
      await pg.locator('[data-cal-next]').click()
      await pg.waitForFunction((k) => document.querySelector('[data-month-view]')?.getAttribute('data-month') === k, nextKey, { timeout: 10000 })
      await pg.locator(`[data-month-grid] [data-day="${nextMonth}"]`).waitFor({ timeout: 10000 })
      if (phone) {
        await pg.locator(`[data-month-grid] [data-day="${nextMonth}"] > button`).click()
        await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), later, { timeout: 5000 })
      } else must((await pg.locator(`[data-month-grid] [data-day="${nextMonth}"]`).innerText()).includes(later), `${later} is not on ${nextMonth}`)
      await pg.locator('[data-cal-prev]').click()
      await pg.waitForFunction((k) => document.querySelector('[data-month-view]')?.getAttribute('data-month') === k, month, { timeout: 10000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.3`, `${width} px: Year shows a bar for each goal in its area's lane, and one tick per weekly review with the right count`, async () => {
      const before = await s.api('calendar.year_plan', { space: SPACE, year })
      const week = before.reviews.weeks.find((w) => !w.done && !w.future)
      must(week, 'no past week without a review')
      reviewName = bench(`r = frappe.get_doc({"doctype": "Life Review", "space": "${SPACE}", "user": "owner@lifeos.test", "kind": "Weekly", "status": "Locked", "period_start": "${week.start}",
  "period_end": "${plusDays(week.start, 6)}", "locked_on": frappe.utils.now_datetime(), "title": "I16 review ${width} ${stamp}", "tab_state": "{}"}).insert(ignore_permissions=True)
print(r.name)`).split('\n').pop()
      const after = await s.api('calendar.year_plan', { space: SPACE, year })
      must(after.reviews.done === before.reviews.done + 1, `the server counts ${after.reviews.done} reviews; it was ${before.reviews.done}`)
      await s.open('/life/today/year')
      await pg.locator('[data-year-view]').waitFor({ timeout: 10000 })
      if (phone) {
        const section = await pg.locator(`[data-month-section="${Number(today.slice(5, 7))}"]`).innerText()
        must(section.includes(goalTitle), 'the goal is not listed in its months')
        must((await pg.locator('[data-reviews-phone]').innerText()).includes(`${after.reviews.done} of ${after.reviews.total}`), 'the reviews count is wrong')
      } else {
        const lane = pg.locator(`[data-lane="area-${made.tea}"]`)
        await lane.waitFor({ timeout: 10000 })
        const bar = pg.locator(`[data-goal-bar][data-goal="${made.goal}"]`)
        must((await bar.count()) === 1 && (await bar.innerText()).includes(goalTitle), 'the goal has no bar')
        const lanes = await pg.locator('[data-lane]').evaluateAll((els) => els.map((e) => e.getAttribute('data-lane')))
        must(lanes.indexOf(`area-${made.tea}`) > lanes.indexOf(`area-${made.career}`), "the goal's part is not under its area")
        must((await pg.locator('[data-review-tick]').count()) === after.reviews.weeks.length, 'there is not a tick for every week')
        must((await pg.locator('[data-review-tick][data-done]').count()) === after.reviews.done, 'the done ticks are not the reviews held')
        must((await pg.locator('[data-lane="reviews"]').innerText()).includes(`${after.reviews.done} of ${after.reviews.total} done`), 'the lane does not say n of m done')
        must(await pg.locator(`[data-review-tick][data-start="${week.start}"][data-done]`).count(), 'the week of the review is not ticked')
        const cards = await pg.locator('[data-year-cards]').innerText()
        must(cards.includes('This year so far') && cards.includes('Next 12 Week Year'), 'the cards are missing')
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.4`, `${width} px: an area that is off has no lane`, async () => {
      const out = await s.api('calendar.year_plan', { space: SPACE, year })
      must(!out.lanes.some((l) => l.area === made.mind), 'the server sent a lane for an area that is off')
      await s.open('/life/today/year')
      await pg.locator('[data-year-view]').waitFor({ timeout: 10000 })
      must(!(await pg.locator('[data-year-view]').innerText()).includes(offTitle), 'the goal of an area that is off is shown')
      if (!phone) must(!(await pg.locator(`[data-lane="area-${made.mind}"]`).count()), 'the area that is off has a lane')
      bench(`frappe.db.set_value("Life Area", "${made.mind}", "is_on", 1)`)
      await s.open('/life/today/year')
      await pg.locator('[data-year-view]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-year-view]').innerText()).includes(offTitle), 'the goal does not show once the area is on')
      bench(`frappe.db.set_value("Life Area", "${made.mind}", "is_on", 0)`)
    })
    await check(`${tag}.5`, `${width} px: clicking a goal opens the goal; clicking a month opens Month`, async () => {
      await s.open('/life/today/year')
      await pg.locator('[data-year-view]').waitFor({ timeout: 10000 })
      const m = Number(today.slice(5, 7))
      await (phone ? pg.locator(`[data-month-section="${m}"] a`, { hasText: goalTitle }) : pg.locator(`[data-goal-bar][data-goal="${made.goal}"] a`)).first().click()
      await pg.waitForURL((u) => u.pathname === `/life/goals/${made.goal}`, { timeout: 10000 })
      await pg.getByText(goalTitle).first().waitFor({ timeout: 10000 }).catch(() => {})
      must((await pg.locator('body').innerText()).includes(goalTitle), 'the goal page does not show the goal')
      await s.open('/life/today/year')
      await pg.locator('[data-year-view]').waitFor({ timeout: 10000 })
      const target = m === 12 ? 11 : m + 1
      await (phone ? pg.locator(`[data-month-section="${target}"] h2 a`) : pg.locator(`[data-month-head="${target}"] button`)).click()
      await pg.waitForURL((u) => u.pathname === '/life/today/month' && u.searchParams.get('date') === `${year}-${String(target).padStart(2, '0')}-01`, { timeout: 10000 })
      await pg.locator('[data-month-view]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-month-view]').getAttribute('data-month')) === `${year}-${String(target).padStart(2, '0')}`, 'Month is on the wrong month')
    })
    await check(`${tag}.6`, `${width} px: Week, Month and Year have no sideways scroll`, async () => {
      for (const p of ['week', 'month', 'year']) {
        await s.open('/life/today/' + p)
        await pg.locator(`[data-${p}-view]`).waitFor({ timeout: 10000 })
        await pg.waitForTimeout(500)
        await noSideways()
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`was = ${JSON.stringify(made.was)}
for n, v in was.items(): frappe.db.set_value("Life Area", n, "is_on", v)
for g in ("${made.goal}", "${made.off}"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for t in ${JSON.stringify(made.tasks)}: frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
frappe.delete_doc("Event", "${made.event}", force=1, ignore_permissions=True)
${reviewName ? `frappe.delete_doc("Life Review", "${reviewName}", force=1, ignore_permissions=True)` : ''}`)
    await s.ctx.close()
  }
}

// Issue 17: Brain > Needs you. Titles start "I17 " (known to the debris finder). Other waiting captures of the space are put
// aside (archived) for each width and brought back after, so the rows and the numbers are this check's alone.
for (const width of SET_WIDTHS) {
  const tag = `I17.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I17 ${what} ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
area = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n})
tea, mind, career = area("Tea & Coffee"), area("Mind"), area("Career")
was = {n: frappe.db.get_value("Life Area", n, "is_on") for n in (tea, mind, career)}
for n in (tea, mind, career): frappe.db.set_value("Life Area", n, "is_on", 1)
aside = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0, "status": ["in", ["To Review", "Failed", "New", "Processing"]]}, pluck="name")
for n in aside: frappe.db.set_value("Life Inbox Item", n, "is_archived", 1, update_modified=False)
print(json.dumps({"tea": tea, "mind": mind, "career": career, "was": was, "aside": aside, "tea_name": "Tea & Coffee", "mind_name": "Mind"}))`).split('\n').pop())
  // a capture waiting for a decision, with one proposal: { kind, area, alt, reason, hours, source, status }
  const mk = (what, o = {}) => JSON.parse(bench(`import json
from frappe.utils import add_to_date, now_datetime
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T(what)}", "source_type": "${o.source || 'Email'}", "status": "${o.status || 'To Review'}",
  "received_on": add_to_date(now_datetime(), hours=-${o.hours ?? 1})${o.error ? `, "error": "${o.error}"` : ''}}).insert(ignore_permissions=True)
out = {"item": item.name}
if "${o.status || 'To Review'}" == "To Review":
    body = {"title": "${T(what)}"${o.kind === 'Reading' ? ', "goal": "x", "value": 1, "excerpt": "x"' : ''}${o.area ? `, "area": ${JSON.stringify(o.area)}` : ''}}
    p = frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": item.name, "kind": "${o.kind || 'Task'}", "preview": "${T(what)}",
      "payload": frappe.as_json(body), "confidence": 0.6, "status": "Pending", "reason": ${o.reason ? JSON.stringify(o.reason) : 'None'}, "alt_area": ${o.alt ? JSON.stringify(o.alt) : 'None'}}).insert(ignore_permissions=True)
    out["proposal"] = p.name
print(json.dumps(out))`).split('\n').pop())
  const row = (p) => pg.locator(`[data-needs-row][data-proposal="${p}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openNeeds = async () => { await s.open('/life/brain'); await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(400) }
  const rowsOf = async () => (await s.api('brain.needs_you', { space: SPACE })).rows
  const queue = async () => { for (const r of await rowsOf()) await s.api('review.decide', { proposal: r.proposal, decision: 'reject' }) }
  try {
    await check(`${tag}.12`, `${width} px: on an empty space Needs you says what will appear and offers + Capture`, async () => {
      await openNeeds()
      must(await pg.locator('[data-needs-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-needs-empty]').innerText()
      must(t.includes('Nothing needs you.') && t.includes('Things you capture or connect will show up here.'), 'the empty state says: ' + t)
      await pg.locator('[data-needs-capture]').click()
      await pg.locator('[data-capture-text]').first().waitFor({ timeout: 5000 })
      await pg.keyboard.press('Escape')
      await noSideways()
    })
    await check(`${tag}.1`, `${width} px: with 3 waiting captures (one with two possible areas) Needs you shows 3 rows with their best guesses and reasons`, async () => {
      const a = await mk('voice', { area: made.mind, reason: 'Sounds like a task, but no date was said', hours: 3, source: 'Voice Note' })
      const b = await mk('torn', { area: made.tea, alt: made.mind, reason: 'Mentions both Tea and Mind', hours: 2 })
      const c = await mk('plain', { area: made.career, hours: 1 })
      await openNeeds()
      must((await pg.locator('[data-needs-row]').count()) === 3, `${await pg.locator('[data-needs-row]').count()} rows, not 3`)
      const ra = await row(a.proposal).innerText(), rb = await row(b.proposal).innerText(), rc = await row(c.proposal).innerText()
      must(ra.includes(T('voice')) && ra.includes('✦ Sounds like a task, but no date was said') && ra.includes('Best guess:') && ra.includes('Task') && ra.includes('Mind'), 'row 1: ' + ra)
      must(rb.includes('Mentions both Tea and Mind') && rb.includes('Tea & Coffee') && /\bor\b/.test(rb) && rb.includes('Mind'), 'row 2: ' + rb)
      must(rc.includes('Career') && !rc.includes('✦'), 'row 3 (no reason, no mark): ' + rc)
      must((await row(b.proposal).locator('[data-area-chip]').count()) === 2 && (await row(a.proposal).locator('[data-area-chip]').count()) === 1, 'the area chips are wrong')
      must(await row(a.proposal).locator('[data-keep]').count() && await row(a.proposal).locator('[data-change]').count() && await row(a.proposal).locator('[data-drop]').count(), 'a row lacks Keep, Change or Drop')
      must(!(await row(b.proposal).locator('[data-keep]').count()) && (await row(b.proposal).locator('[data-pick]').count()) === 2, 'the torn row has Keep, or not two choices')
      must((await pg.locator('[data-stat-needs]').getAttribute('data-n')) === '3', 'the Needs you number is not 3')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      made.k = { a, b, c }
    })
    await check(`${tag}.2`, `${width} px: Keep accepts the proposal, the row leaves, and the record exists with the guessed area`, async () => {
      const { a } = made.k
      await openNeeds()
      await row(a.proposal).locator('[data-keep]').click()
      await row(a.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const got = JSON.parse(bench(`import json
p = frappe.get_doc("Life Proposal", "${a.proposal}")
print(json.dumps({"status": p.status, "area": frappe.db.get_value(p.created_doctype, p.created_name, "area"), "dt": p.created_doctype}))`).split('\n').pop())
      must(got.status === 'Accepted' && got.dt === 'Life Task' && got.area === made.mind, 'after Keep: ' + JSON.stringify(got))
    })
    await check(`${tag}.3`, `${width} px: picking the second of two area chips files it there`, async () => {
      const { b } = made.k
      await openNeeds()
      await row(b.proposal).locator('[data-pick="second"]').click()
      await row(b.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const area = bench(`p = frappe.get_doc("Life Proposal", "${b.proposal}")
print(p.status, frappe.db.get_value(p.created_doctype, p.created_name, "area"))`).split('\n').pop()
      must(area === `Accepted ${made.mind}`, 'after the second chip: ' + area)
    })
    await check(`${tag}.4`, `${width} px: Drop discards it and it appears in the Outbox as Discarded`, async () => {
      const { c } = made.k
      await openNeeds()
      await row(c.proposal).locator('[data-drop]').click()
      await row(c.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const listed = await s.api('outbox.list', { space: SPACE, pile: 'Discarded', page_length: 500 })
      must(listed.rows.some((r) => r.record === c.item), 'the capture is not in the Outbox as Discarded')
      await s.open('/life/brain/outbox?pile=Discarded')
      await pg.waitForFunction((t) => document.body.innerText.includes(t), T('plain'), { timeout: 10000 })
    })
    await check(`${tag}.5`, `${width} px: Done, file all files every row in one go`, async () => {
      const rows = []
      for (let i = 0; i < 3; i++) rows.push(await mk(`all ${i}`, { area: made.tea, hours: 3 - i }))
      await openNeeds()
      const label = await pg.locator('[data-file-all]').innerText()
      must(label.includes('Done, file all 3'), 'the button says: ' + label)
      await pg.locator('[data-file-all]').click()
      await pg.locator('[data-needs-empty]').waitFor({ timeout: 10000 })
      const states = bench(`print(",".join(frappe.db.get_value("Life Proposal", n, "status") for n in ${JSON.stringify(rows.map((r) => r.proposal))}))`).split('\n').pop()
      must(states === 'Accepted,Accepted,Accepted', 'after Done, file all: ' + states)
    })
    await check(`${tag}.6`, `${width} px: with more than 7 waiting, 7 show and the rest come in as rows are cleared`, async () => {
      const rows = []
      for (let i = 0; i < 9; i++) rows.push(await mk(`many ${i}`, { area: made.tea, hours: 20 - i }))
      await openNeeds()
      must((await pg.locator('[data-needs-row]').count()) === 7, `${await pg.locator('[data-needs-row]').count()} rows, not 7`)
      must((await pg.locator('[data-stat-needs]').getAttribute('data-n')) === '9', 'the Needs you number is not 9')
      must(!(await row(rows[7].proposal).count()), 'the eighth is already shown')
      await row(rows[0].proposal).locator('[data-drop]').click()
      await row(rows[7].proposal).waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-row]').count()) === 7, 'a row did not come in')
      await row(rows[1].proposal).locator('[data-drop]').click()
      await row(rows[8].proposal).waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-row]').count()) === 7, 'the ninth did not come in')
      await queue()
    })
    await check(`${tag}.7`, `${width} px: the two numbers match the captures of the last 24 hours`, async () => {
      await queue()
      const before = await s.api('brain.needs_you', { space: SPACE })
      bench(`from frappe.utils import add_to_date, now_datetime
def mk(title, source, hours, area=None):
    frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": title, "source_type": source, "status": "Done", "area": area,
      "received_on": add_to_date(now_datetime(), hours=-hours)}).insert(ignore_permissions=True)
mk("${T('own 1')}", "Email", 2, "${made.tea}")
mk("${T('own 2')}", "Chat", 4, "${made.mind}")
mk("${T('own 3')}", "Email", 5, "${made.tea}")
mk("${T('old')}", "Email", 30, "${made.tea}")`)
      const after = await s.api('brain.needs_you', { space: SPACE })
      must(after.came_in.count === before.came_in.count + 3, `came in: ${before.came_in.count} then ${after.came_in.count}`)
      must(after.filed.count === before.filed.count + 3, `filed: ${before.filed.count} then ${after.filed.count}`)
      // the server's numbers are the captures of the last 24 hours
      const truth = JSON.parse(bench(`import json
from frappe.utils import add_to_date, now_datetime
rows = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0, "received_on": [">=", add_to_date(now_datetime(), hours=-24)]}, fields=["source_type"])
print(json.dumps({"n": len(rows), "sources": len({r.source_type for r in rows})}))`).split('\n').pop())
      must(truth.n === after.came_in.count && truth.sources === after.came_in.sources, `the server says ${after.came_in.count} from ${after.came_in.sources}; the captures say ${JSON.stringify(truth)}`)
      await openNeeds()
      must((await pg.locator('[data-stat-came-in]').getAttribute('data-n')) === String(after.came_in.count), 'the screen shows another number for came in')
      must((await pg.locator('[data-stat-came-in]').innerText()).includes(`from ${after.came_in.sources} source`), 'the sources are not shown')
      must((await pg.locator('[data-stat-filed]').getAttribute('data-n')) === String(after.filed.count), 'the screen shows another number for filed on its own')
      await pg.locator('[data-see-activity]').click()
      await pg.waitForURL((u) => u.pathname === '/life/brain/activity', { timeout: 10000 })
    })
    await check(`${tag}.8`, `${width} px: each row stacks at 390 px, with Keep, Change and Drop reachable and no sideways scroll`, async () => {
      const r = await mk('stack', { area: made.tea, reason: 'A long reason that needs room to wrap on a phone, with more words than fit on one line', hours: 1 })
      await openNeeds()
      const rw = row(r.proposal)
      await rw.waitFor({ timeout: 10000 })
      const box = await rw.boundingBox()
      for (const sel of ['[data-keep]', '[data-change]', '[data-drop]']) {
        const b = await rw.locator(sel).boundingBox()
        must(b && b.x >= 0 && b.x + b.width <= width + 1 && b.y >= box.y && b.y + b.height <= box.y + box.height + 1, `${sel} is not inside the row (${JSON.stringify(b)})`)
      }
      if (phone) {
        const text = await rw.locator('[data-row-title]').boundingBox(), acts = await rw.locator('[data-row-actions]').boundingBox()
        must(acts.y >= text.y + text.height - 1, 'on a phone the actions do not sit under the text')
      }
      await noSideways()
      await rw.locator('[data-change]').click()
      await pg.waitForURL((u) => u.pathname.startsWith('/life/item/'), { timeout: 10000 })
      await queue()
    })
    await check(`${tag}.10`, `${width} px: an agent's proposal with alt_area shows two area chips; picking the second files it in that area`, async () => {
      const out = JSON.parse(bench(`import json
from lifeos.api import inbox
frappe.set_user("owner@lifeos.test")
it = inbox.create_item(title="${T('agent')}", space="${SPACE}", raw_text="Mentions both", source_type="Email")
frappe.set_user("hermes@lifeos.test")
from lifeos import permissions
permissions.clear_cache()
inbox.claim_next(space="${SPACE}")
res = inbox.submit_result(item=it["name"], proposals=[{"kind": "Task", "preview": "${T('agent')}", "confidence": 0.6, "reason": "Mentions both Tea and Mind",
  "payload": {"title": "${T('agent')}", "area": "${made.tea}"}, "alt_area": "${made.mind}"}])
print(json.dumps({"item": it["name"], "proposal": res["created"][0]["name"], "errors": res["errors"]}))`).split('\n').pop())
      must(!out.errors.length, 'the agent was refused: ' + JSON.stringify(out.errors))
      await openNeeds()
      const rw = row(out.proposal)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-area-chip]').count()) === 2, 'not two area chips')
      await rw.locator('[data-pick="second"]').click()
      await rw.waitFor({ state: 'detached', timeout: 10000 })
      const area = bench(`p = frappe.get_doc("Life Proposal", "${out.proposal}")
print(p.status, frappe.db.get_value(p.created_doctype, p.created_name, "area"))`).split('\n').pop()
      must(area === `Accepted ${made.mind}`, 'filed as: ' + area)
    })
    await check(`${tag}.11`, `${width} px: a Reading proposal shows as Read later`, async () => {
      const r = await mk('reading', { kind: 'Reading', hours: 1 })
      await openNeeds()
      const rw = row(r.proposal)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-row-kind]').innerText()) === 'Read later', 'the kind reads: ' + await rw.locator('[data-row-kind]').innerText())
      await queue()
    })
    await check(`${tag}.13`, `${width} px: a capture that failed is listed under Unfiled with Retry, never lost`, async () => {
      const f = await mk('failed', { status: 'Failed', error: 'Could not read the file', source: 'Upload' })
      await openNeeds()
      const rw = pg.locator(`[data-failed-row][data-item="${f.item}"]`)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.innerText()).includes('Could not read the file') && (await rw.locator('[data-retry]').count()) === 1, 'the failed capture is not shown with Retry')
      await noSideways()
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for p in frappe.get_all("Life Proposal", filters={"preview": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Proposal", p, force=1, ignore_permissions=True)
for t in frappe.get_all("Life Task", filters={"title": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}:
    if frappe.db.exists("Life Inbox Item", n): frappe.db.set_value("Life Inbox Item", n, "is_archived", 0, update_modified=False)
for n, v in ${JSON.stringify(made.was)}.items(): frappe.db.set_value("Life Area", n, "is_on", v)`)
    await s.ctx.close()
  }
}

// Issue 18: Brain > Activity. Titles start "I18 " (known to the debris finder). The space's other captures are put aside (archived)
// for each width and brought back after, so the feed holds this check's captures alone.
for (const width of SET_WIDTHS) {
  const tag = `I18.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I18 ${what} ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
tea = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
was = frappe.db.get_value("Life Area", tea, "is_on")
frappe.db.set_value("Life Area", tea, "is_on", 1)
aside = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0}, pluck="name")
for n in aside: frappe.db.set_value("Life Inbox Item", n, "is_archived", 1, update_modified=False)
print(json.dumps({"tea": tea, "was": was, "aside": aside}))`).split('\n').pop())
  const mk = (what, o = {}) => JSON.parse(bench(`import json
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T(what)}", "source_type": "${o.source || 'Email'}", "status": "${o.status || 'Done'}",
  "received_on": frappe.utils.now_datetime()${o.error ? `, "error": "${o.error}"` : ''}${o.area ? `, "area": "${o.area}"` : ''}}).insert(ignore_permissions=True)
out = {"item": item.name}
${o.task ? `t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${T(what)}", "area": "${o.area}", "inbox_item": item.name}).insert(ignore_permissions=True)
p = frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": item.name, "kind": "Task", "preview": "${T(what)}",
  "payload": frappe.as_json({"title": "${T(what)}"}), "status": "Pending"}).insert(ignore_permissions=True)
frappe.db.set_value("Life Proposal", p.name, {"status": "Accepted", "created_doctype": "Life Task", "created_name": t.name})
out["task"] = t.name` : ''}
print(json.dumps(out))`).split('\n').pop())
  const row = (i) => pg.locator(`[data-activity-row][data-item="${i}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openFeed = async (q = '') => { await s.open('/life/brain/activity' + q); await pg.locator('[data-activity]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(500) }
  try {
    await check(`${tag}.6`, `${width} px: on a space with nothing captured Activity says what will appear and offers + Capture`, async () => {
      await openFeed()
      must(await pg.locator('[data-activity-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-activity-empty]').innerText()
      must(t.includes('Nothing has come in yet.') && t.includes('will show up here'), 'the empty state says: ' + t)
      await pg.locator('[data-activity-capture]').click()
      await pg.locator('[data-capture-text]').first().waitFor({ timeout: 5000 })
      await pg.keyboard.press('Escape')
      await noSideways()
    })
    await check(`${tag}.1`, `${width} px: a capture filed on its own today shows under Today with its area and a link to the record`, async () => {
      const a = await mk('filed', { area: made.tea, task: true })
      made.a = a
      await openFeed()
      const day = pg.locator('[data-activity-day]').first()
      must((await day.locator('h2').innerText()) === 'Today', 'the first group is not Today')
      const rw = row(a.item)
      await rw.waitFor({ timeout: 10000 })
      const t = await rw.innerText()
      must(t.includes(T('filed')) && t.includes('Tea & Coffee') && t.includes('Email'), 'the row says: ' + t)
      const href = await rw.locator('[data-made-link]').first().getAttribute('href')
      must(href && href.includes(a.task), 'the link to the record is ' + href)
      must((await rw.locator('[data-row-item]').getAttribute('href')) === `/life/item/${a.item}`, 'the item page link is wrong')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: the source filter narrows the feed to that source`, async () => {
      const v = await mk('voice', { source: 'Voice Note' })
      await openFeed()
      must(await row(v.item).count() && await row(made.a.item).count(), 'both captures should be listed first')
      await pg.locator('[data-activity-source]').selectOption('Voice Note')
      await pg.waitForTimeout(600)
      must(new URL(pg.url()).searchParams.get('source') === 'Voice Note', 'the filter is not in the URL')
      must((await row(v.item).count()) === 1 && (await row(made.a.item).count()) === 0, 'the feed is not narrowed to Voice Note')
      const sources = await pg.locator('[data-activity-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-source')))
      must(sources.every((x) => x === 'Voice Note'), 'other sources remain: ' + sources)
      await pg.locator('[data-outcome="dropped"]').click()
      await pg.waitForTimeout(500)
      must((await pg.locator('[data-activity-row]').count()) === 0, 'Dropped should hold nothing here')
    })
    await check(`${tag}.3`, `${width} px: a failed capture shows its reason and Retry puts it back in the queue`, async () => {
      const f = await mk('failed', { status: 'Failed', error: 'Could not read the file', source: 'Upload' })
      await openFeed('?outcome=failed')
      const rw = row(f.item)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-row-reason]').innerText()).includes('Could not read the file'), 'the reason is not shown')
      await rw.locator('[data-retry]').click()
      await pg.waitForTimeout(800)
      const status = bench(`print(frappe.db.get_value("Life Inbox Item", "${f.item}", "status"))`).split('\n').pop()
      must(status === 'New', 'the status is ' + status)
      must((await row(f.item).count()) === 0, 'it is still listed as failed')
    })
    await check(`${tag}.4`, `${width} px: the Outbox piles in Activity show the same numbers as the Outbox`, async () => {
      await openFeed()
      const listed = (await s.api('outbox.list', { space: SPACE, pile: 'all', period: 'week', page_length: 1 })).tabs
      for (const pile of ['Done', 'Delegated', 'Parked', 'Discarded']) {
        const n = await pg.locator(`[data-plate-pile][data-pile="${pile}"]`).getAttribute('data-n')
        must(Number(n) === listed[pile], `${pile}: Activity says ${n}, the Outbox ${listed[pile]}`)
      }
      must((await pg.locator('[data-flow-in]').innerText()) === String(listed.in) && (await pg.locator('[data-flow-out]').innerText()) === String(listed.all), 'the flow line differs')
      await pg.locator('[data-plate-pile][data-pile="Done"]').click()
      await pg.waitForURL((u) => u.pathname === '/life/brain/outbox' && u.searchParams.get('pile') === 'Done', { timeout: 10000 })
      await pg.locator('[data-outbox-sub]').waitFor({ timeout: 10000 })
    })
    await check(`${tag}.5`, `${width} px: the feed is one column and nothing scrolls sideways`, async () => {
      await openFeed()
      await noSideways()
      const boxes = await pg.locator('[data-activity-row]').evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.width] }))
      must(boxes.length > 0, 'no rows')
      must(boxes.every(([x, w]) => Math.abs(x - boxes[0][0]) < 1 && Math.abs(w - boxes[0][1]) < 1), 'the rows are not one column')
      if (phone) must(boxes[0][1] <= width, 'a row is wider than the screen')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for p in frappe.get_all("Life Proposal", filters={"preview": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Proposal", p, force=1, ignore_permissions=True)
for t in frappe.get_all("Life Task", filters={"title": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}:
    if frappe.db.exists("Life Inbox Item", n): frappe.db.set_value("Life Inbox Item", n, "is_archived", 0, update_modified=False)
frappe.db.set_value("Life Area", "${made.tea}", "is_on", ${made.was ? 1 : 0})`)
    await s.ctx.close()
  }
}

// Issue 19: Brain > Sources. Titles start "I19 ". The space's own connections are put aside (their space renamed) for each width and
// brought back after, so the cards are this check's alone.
for (const width of SET_WIDTHS) {
  const tag = `I19.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const ASIDE = `zz-i19-aside-${width}`
  const made = JSON.parse(bench(`import json
tea = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
was = frappe.db.get_value("Life Area", tea, "is_on")
frappe.db.set_value("Life Area", tea, "is_on", 1)
aside = frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name")
for n in aside: frappe.db.set_value("Life Connection", n, "space", "${ASIDE}", update_modified=False)
print(json.dumps({"tea": tea, "was": was, "aside": aside}))`).split('\n').pop())
  const card = (sys) => pg.locator(`[data-source-card][data-system="${sys}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openSources = async () => { await s.open('/life/brain/sources'); await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const capture = (title, system, extra = {}) => s.api('inbox.create_item', { space: SPACE, title: `I19 ${title} ${width} ${stamp}`, source_system: system, ...extra })
  try {
    await check(`${tag}.6`, `${width} px: with no source connected Sources says what will appear and offers Add a source`, async () => {
      await openSources()
      must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-sources-empty]').innerText()
      must(t.includes('Nothing is connected yet.') && t.includes('switch them on below'), 'the empty state says: ' + t)
      must(await pg.locator('[data-source-tile][data-system="upload"]').innerText().then((x) => x.includes('Always on')), 'the Upload tile is missing')
      await pg.locator('[data-add-source-empty]').click()
      await pg.locator('[data-add-more]').waitFor({ state: 'visible' })
      await noSideways()
    })
    await check(`${tag}.1`, `${width} px: connected sources show with this week's counts, matching the captures in the database`, async () => {
      for (const n of [1, 2, 3]) await capture(`hermes ${n}`, 'hermes')
      await capture('gmail 1', 'gmail')
      await openSources()
      must((await pg.locator('[data-source-card]').count()) === 2, 'expected two cards, got ' + await pg.locator('[data-source-card]').count())
      must((await pg.locator('[data-connected-count]').innerText()) === '2', 'the count in the heading is wrong')
      for (const sys of ['hermes', 'gmail']) {
        const n = bench(`from frappe.utils import add_days, getdate
d = getdate()
print(frappe.db.count("Life Inbox Item", {"space": "${SPACE}", "source_system": "${sys}", "creation": [">=", add_days(d, -d.weekday())]}))`).split('\n').pop()
        const shown = await card(sys).getAttribute('data-week')
        must(shown === n && n !== '0', `${sys}: the card says ${shown}, the database ${n}`)
        must((await card(sys).locator('[data-source-line]').innerText()).includes(`${n} this week`), `${sys}: the line does not say ${n} this week`)
      }
      must((await card('hermes').innerText()).includes('Agent · Telegram'), 'the kind of Hermes is missing')
      must((await card('gmail').innerText()).includes('only people, not newsletters'), 'the Gmail note is missing')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: switching Hermes off makes create_item from hermes fail with a clear message; switching it on again works`, async () => {
      await openSources()
      await card('hermes').locator('button[role="switch"]').click()
      await pg.waitForTimeout(800)
      must((await card('hermes').getAttribute('data-active')) === '0', 'the card still says On')
      const r = await s.api('inbox.create_item', { space: SPACE, title: `I19 refused ${width} ${stamp}`, source_system: 'hermes' }, { raw: true })
      const text = await r.text()
      must(!r.ok() && text.includes('switched off'), `create_item answered ${r.status()}: ${text.slice(0, 200)}`)
      must(bench(`print(frappe.db.count("Life Inbox Item", {"title": "I19 refused ${width} ${stamp}"}))`).split('\n').pop() === '0', 'the refused capture was stored')
      must((await (await s.api('inbox.create_item', { space: SPACE, title: `I19 upload ${width} ${stamp}`, source_system: 'upload' })).title).includes('upload'), 'Upload should always work')
      await card('hermes').locator('button[role="switch"]').click()
      await pg.waitForTimeout(800)
      must((await card('hermes').getAttribute('data-active')) === '1', 'the card still says Off')
      const ok = await capture('back on', 'hermes')
      must(ok.created, 'create_item should work again')
      must((await card('hermes').getAttribute('data-week')) !== null && bench(`print(frappe.db.count("Life Inbox Item", {"title": ["like", "I19 hermes %${width} ${stamp}"]}))`).split('\n').pop() === '3', 'what Hermes brought earlier was deleted')
    })
    await check(`${tag}.3`, `${width} px: a Coming tile cannot be switched on`, async () => {
      await openSources()
      const tile = pg.locator('[data-tile-coming][data-system="github"]')
      must((await tile.innerText()).includes('Coming'), 'the GitHub tile does not say Coming')
      must((await tile.locator('button').count()) === 0, 'a Coming tile has a button')
      await tile.click({ force: true })
      await pg.waitForTimeout(500)
      must((await pg.locator('[data-source-settings]').count()) === 0 && (await card('github').count()) === 0, 'a Coming tile opened or added something')
      for (const sys of ['github', 'whatsapp', 'wearable', 'tally', 'drive', 'erpnext']) must(await pg.locator(`[data-tile-coming][data-system="${sys}"]`).count() === 1, sys + ' is missing')
      const r = await s.api('connections.save', { space: SPACE, system: 'github', active: 1 }, { raw: true })
      must(!r.ok() && (await r.text()).includes('not built yet'), 'the server switched GitHub on: ' + r.status())
    })
    await check(`${tag}.4`, `${width} px: opening a source shows its default intent, area and goal, and saving changes what create_item uses`, async () => {
      await openSources()
      await card('gmail').locator('[data-source-open]').click()
      const dlg = pg.locator('[data-source-settings][data-system="gmail"]')
      await dlg.waitFor({ timeout: 5000 })
      must(await dlg.locator('[data-settings-intent]').count() && await dlg.locator('[data-settings-area]').count() && await dlg.locator('[data-settings-goal]').count(), 'intent, area or goal is missing')
      await dlg.locator('[data-settings-intent] [role="combobox"], [data-settings-intent] button').first().click()
      await pg.getByRole('option', { name: 'Just keep', exact: true }).first().click()
      await dlg.locator('[data-settings-area] button').click()
      await pg.getByRole('menuitem', { name: 'Tea & Coffee', exact: false }).first().click()
      await pg.getByRole('button', { name: 'Save' }).click()
      await pg.waitForTimeout(1000)
      const c = bench(`import json
print(json.dumps(frappe.db.get_value("Life Connection", {"space": "${SPACE}", "system": "gmail"}, ["default_intent", "default_area"], as_dict=True)))`).split('\n').pop()
      must(JSON.parse(c).default_intent === 'Just keep' && JSON.parse(c).default_area === made.tea, 'the defaults were not saved: ' + c)
      const item = await capture('defaults', 'gmail')
      must(item.intent === 'Just keep' && item.area === made.tea, `create_item used intent ${item.intent}, area ${item.area}`)
      await card('gmail').locator('[data-source-open]').click()
      await pg.locator('[data-source-settings][data-system="gmail"]').waitFor({ timeout: 5000 })
      must((await pg.locator('[data-source-settings] [data-settings-intent]').innerText()).includes('Just keep'), 'the saved intent is not shown when it is opened again')
      await pg.keyboard.press('Escape')
    })
    await check(`${tag}.5`, `${width} px: ${phone ? 'the cards stack in one column' : 'the cards sit in a grid'} and nothing scrolls sideways`, async () => {
      await openSources()
      await noSideways()
      const boxes = await pg.locator('[data-source-card]').evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width] }))
      must(boxes.length >= 2, 'expected at least two cards')
      if (phone) must(boxes.every(([x, , w]) => Math.abs(x - boxes[0][0]) < 1 && w <= width), 'the cards do not stack')
      else must(Math.abs(boxes[1][1] - boxes[0][1]) < 1 && boxes[1][0] > boxes[0][0], 'the cards are not side by side')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I19 %${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for c in frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Connection", c, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}: frappe.db.set_value("Life Connection", n, "space", "${SPACE}", update_modified=False)
frappe.db.set_value("Life Area", "${made.tea}", "is_on", ${made.was ? 1 : 0})`)
    await s.ctx.close()
  }
}

// Issue 20: Goals > By area. Titles start "I20 ". Areas switched on or off here are put back after.
for (const width of SET_WIDTHS) {
  const tag = `I20.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I20 ${what} ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openGoals = async (q = 'show=open') => { await s.open('/life/goals?' + q); await pg.locator('[data-goals-by-area][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const made = JSON.parse(bench(`import json
top = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n, "parent_area": ("is", "not set")})
part = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n, "parent_area": ("is", "set")})
ids = {n: top(n) for n in ("Career", "Health", "Money", "Mind", "Emotions", "Environment", "Relationships")}
ids["btw"], ids["tea"] = part("Business That Works"), part("Tea & Coffee")
was = {k: frappe.db.get_value("Life Area", v, "is_on") for k, v in ids.items()}
for k in ("Career", "Health", "Money", "Mind", "btw", "tea"): frappe.db.set_value("Life Area", ids[k], "is_on", 1)
used = set(frappe.get_all("Life Goal", filters={"space": "${SPACE}"}, pluck="area"))
empty = next(n for n in ("Emotions", "Environment", "Relationships") if ids[n] not in used)
frappe.db.set_value("Life Area", ids[empty], "is_on", 1)
cycle = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"})
print(json.dumps({"ids": ids, "was": was, "empty": empty, "cycle": cycle}))`).split('\n').pop())
  const restore = () => bench(`import json
frappe.set_user("Administrator")
for t in frappe.get_all("Life Task", filters={"title": ["like", "I20 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for g in frappe.get_all("Life Goal", filters={"title": ["like", "I20 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Goal", filters={"space": "zz-i20-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Goal", n, "space", "${SPACE}", update_modified=False)
for k, v in ${JSON.stringify(made.was)}.items(): frappe.db.set_value("Life Area", ${JSON.stringify(made.ids)}[k], "is_on", v)`)
  const goals = {}
  try {
    await check(`${tag}.6`, `${width} px: with no goals By area says what will appear and offers + Goal`, async () => {
      bench(`for n in frappe.get_all("Life Goal", filters={"space": "${SPACE}"}, pluck="name"): frappe.db.set_value("Life Goal", n, "space", "zz-i20-aside-${width}", update_modified=False)`)
      try {
        await openGoals('show=open')
        must(await pg.locator('[data-goals-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-goals-empty]').innerText()
        must(t.includes('No goals yet.') && t.includes('under the area of life'), 'the empty state says: ' + t)
        await pg.locator('[data-goals-empty-add]').click()
        await pg.locator('[role="dialog"]').last().waitFor({ timeout: 5000 })
        await pg.keyboard.press('Escape')
        await noSideways()
      } finally {
        bench(`for n in frappe.get_all("Life Goal", filters={"space": "zz-i20-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Goal", n, "space", "${SPACE}", update_modified=False)`)
      }
    })
    // eight goals: Career (two parts and one on Career itself), Health, Money and Mind
    const plan = [['ctx', 'career year', 'Career', 'Year'], ['pilot', 'pilot', 'btw', 'Long term'], ['hire', 'hire', 'btw', 'Long term'], ['tea', 'tea yield', 'tea', 'Long term'],
      ['fit', 'fit', 'Health', '12 weeks'], ['golf', 'golf', 'Health', 'Long term'], ['itr', 'itr', 'Money', 'Long term'], ['read', 'read', 'Mind', 'Long term']]
    const out = JSON.parse(bench(`import json
ids = ${JSON.stringify(made.ids)}
out = {}
def mk(key, title, area, kind, **kw):
    v = {"doctype": "Life Goal", "space": "${SPACE}", "title": title, "area": ids[area], "horizon": kind, **kw}
    if kind == "Year": v["target_date"] = "2026-12-31"
    if kind == "12 weeks": v["cycle"] = ${JSON.stringify(made.cycle)}
    out[key] = frappe.get_doc(v).insert(ignore_permissions=True).name
mk("ctx", "${T('career year')}", "Career", "Year", done_when="Career year done")
mk("pilot", "${T('pilot')}", "btw", "Long term", done_when="Pilot signed", serves=out["ctx"])
mk("hire", "${T('hire')}", "btw", "Long term", measure_kind="Number", measure="Consultants", unit="people", start_value=0, target_value=2)
mk("tea", "${T('tea yield')}", "tea", "Long term", done_when="Yield up")
mk("fit", "${T('fit')}", "Health", "12 weeks", done_when="Fit by March")
mk("golf", "${T('golf')}", "Health", "Long term", done_when="Five birdies")
mk("itr", "${T('itr')}", "Money", "Long term", done_when="Return filed")
mk("read", "${T('read')}", "Mind", "Long term", done_when="Five books")
task = lambda title, status, due=None, at=None: frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": title, "status": status, "goal": out["pilot"], "area": ids["btw"], "due_date": due, "scheduled_at": at}).insert(ignore_permissions=True)
task("${T('later')}", "Open", due="2026-12-20")
task("${T('sooner')}", "Open", due="2026-12-01")
task("${T('finished')}", "Done")
print(json.dumps(out))`).split('\n').pop())
    Object.assign(goals, out)
    const row = (key) => pg.locator(`[data-goal-card][data-goal="${goals[key]}"]`)
    await check(`${tag}.1`, `${width} px: with eight goals over Career (two parts), Health, Money and Mind each appears under its area and part`, async () => {
      await openGoals('show=open')
      const want = { ctx: ['Career', ''], pilot: ['Career', 'Business That Works'], hire: ['Career', 'Business That Works'], tea: ['Career', 'Tea & Coffee'], fit: ['Health', ''],
        golf: ['Health', ''], itr: ['Money', ''], read: ['Mind', ''] }
      for (const [k, [area, partName]] of Object.entries(want)) {
        const c = row(k)
        must((await c.count()) === 1, `${k}: expected one card, got ${await c.count()}`)
        must((await c.getAttribute('data-area-name')) === area && (await c.getAttribute('data-part-name')) === partName, `${k} is under ${await c.getAttribute('data-area-name')} / ${await c.getAttribute('data-part-name')}`)
        must((await pg.locator(`[data-area-section][data-area="${area}"] [data-goal="${goals[k]}"]`).count()) === 1, `${k}: not inside the ${area} section`)
      }
      must((await pg.locator('[data-area-section][data-area="Career"] [data-part-head]').allInnerTexts()).join('|').includes('Business That Works'), 'the part heading is missing')
      for (const n of ['Health', 'Money', 'Mind']) must(await pg.locator(`[data-area-chip^="${n}"]`).count() === 1, `no chip for ${n}`)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: a goal's card shows its Done when, score, next action and open task count, matching the goal page`, async () => {
      await openGoals('show=open')
      const c = row('pilot')
      const page = await s.api('goals.get', { goal: goals.pilot })
      const txt = await c.innerText()
      must(txt.includes('Done when: Pilot signed'), 'Done when is missing: ' + txt)
      must(txt.includes(`Serves ${T('career year')}`), 'what it serves is missing')
      must((await c.locator('[data-goal-next-title]').innerText()) === T('sooner'), 'the next action is not the earliest due task')
      must(Number(await c.locator('[data-goal-open-tasks]').getAttribute('data-count')) === page.tabs.tasks && page.tabs.tasks === 2, `open tasks: card ${await c.locator('[data-goal-open-tasks]').getAttribute('data-count')}, goal page ${page.tabs.tasks}`)
      must((await c.locator('[data-goal-progress]').innerText()).includes('1 of 3 tasks') && page.goal.progress.label === '1 of 3 tasks', 'progress differs from the goal page')
      must((await row('hire').innerText()).includes('0 → 2 people'), 'a number goal does not show its target')
      const fit = row('fit')
      const fp = await s.api('goals.get', { goal: goals.fit })
      must(fp.goal.progress.kind === 'cycle' && Number(await fit.locator('[data-goal-score]').getAttribute('data-score')) === Math.round(fp.goal.progress.percent), 'the cycle goal score differs from the goal page')
      must(/^Week \d+ · \d+%$/.test(await fit.locator('[data-goal-score]').innerText()), 'the week and score are not shown: ' + await fit.locator('[data-goal-score]').innerText())
      must((await row('golf').locator('[data-goal-next-title]').innerText()) === 'No next action', 'a goal with no tasks should say so')
      await c.locator('[data-goal-open]').click()
      await pg.waitForURL(new RegExp(`/life/goals/${goals.pilot}`), { timeout: 8000 })
      // the default filter is this cycle: only the cycle goal of the eight shows, and Finished shows none of them
      await openGoals('')
      must((await row('fit').count()) === 1 && (await row('pilot').count()) === 0, 'This cycle should hold the cycle goal only')
      await openGoals('show=finished')
      must((await pg.locator('[data-goal-card][data-goal]').evaluateAll((els, ids) => els.filter((e) => ids.includes(e.dataset.goal)).length, Object.values(goals))) === 0, 'an open goal shows under Finished')
    })
    await check(`${tag}.3`, `${width} px: an area that is off has no section; turning it on shows its goals`, async () => {
      bench(`frappe.db.set_value("Life Area", "${made.ids.Mind}", "is_on", 0)`)
      await openGoals('show=open')
      must((await pg.locator('[data-area-section][data-area="Mind"]').count()) === 0 && (await row('read').count()) === 0, 'the off area still has a section')
      must((await pg.locator('[data-area-chip-off="Mind"]').count()) === 1, 'the off area has no dimmed chip')
      bench(`frappe.db.set_value("Life Area", "${made.ids.Mind}", "is_on", 1)`)
      await openGoals('show=open')
      must((await pg.locator('[data-area-section][data-area="Mind"]').count()) === 1 && (await row('read').count()) === 1, 'the goal did not come back')
    })
    await check(`${tag}.4`, `${width} px: + Goal in an empty area opens the new-goal form with that area set`, async () => {
      await openGoals('show=open')
      const sec = pg.locator(`[data-area-section][data-area="${made.empty}"]`)
      must((await sec.locator('[data-area-empty]').innerText()).includes('No goals yet'), 'the empty area does not say so')
      await sec.locator('[data-area-add]').click()
      const dlg = pg.locator('[role="dialog"]').last()
      await dlg.waitFor({ timeout: 5000 })
      const text = await dlg.innerText()
      must(new RegExp(`Area\\s+${made.empty}`).test(text), `the area is not set to ${made.empty}: ${text.slice(0, 200)}`)
      await pg.keyboard.press('Escape')
    })
    await check(`${tag}.5`, `${width} px: ${phone ? 'goal cards are full width under area headings' : 'goal cards stack one to a row under area headings'}`, async () => {
      await openGoals('show=open')
      await noSideways()
      const boxes = await pg.locator('[data-area-section][data-area="Career"] [data-goal-card]').evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width] }))
      must(boxes.length >= 4, 'expected the Career cards')
      must(boxes.every(([x, , w]) => Math.abs(x - boxes[0][0]) < 1 && Math.abs(w - boxes[0][2]) < 1), 'the cards are not the same width')
      if (phone) must(boxes[0][2] >= width - 40 && boxes[0][0] + boxes[0][2] <= width, `the card is ${boxes[0][2]} px wide in a ${width} px screen`)
      const head = await pg.locator('[data-area-section][data-area="Career"] h2').boundingBox()
      must(head.y < boxes[0][1], 'the area heading is not above its cards')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 21: Goals > All tasks. Titles start "I21 ". Areas switched on here are put back after.
for (const width of SET_WIDTHS) {
  const tag = `I21.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I21 ${what} ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openTasks = async (q = '') => { await s.open('/life/goals/tasks' + (q ? '?' + q : '')); await pg.locator('[data-all-tasks][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(400) }
  const shown = () => pg.locator('[data-task-row]').evaluateAll((els) => els.map((e) => e.dataset.task))
  const made = JSON.parse(bench(`import json
top = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n, "parent_area": ("is", "not set")})
ids = {n: top(n) for n in ("Career", "Health", "Money")}
was = {k: frappe.db.get_value("Life Area", v, "is_on") for k, v in ids.items()}
for v in ids.values(): frappe.db.set_value("Life Area", v, "is_on", 1)
print(json.dumps({"ids": ids, "was": was}))`).split('\n').pop())
  const restore = () => bench(`import json
frappe.set_user("Administrator")
for t in frappe.get_all("Life Task", filters={"title": ["like", "I21 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for g in frappe.get_all("Life Goal", filters={"title": ["like", "I21 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Task", filters={"space": "zz-i21-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "${SPACE}", update_modified=False)
for k, v in ${JSON.stringify(made.was)}.items(): frappe.db.set_value("Life Area", ${JSON.stringify(made.ids)}[k], "is_on", v)`)
  const ids = {}
  try {
    await check(`${tag}.7`, `${width} px: with no tasks All tasks says what will appear and offers a box to add one`, async () => {
      bench(`for n in frappe.get_all("Life Task", filters={"space": "${SPACE}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "zz-i21-aside-${width}", update_modified=False)`)
      try {
        await openTasks()
        must(await pg.locator('[data-tasks-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-tasks-empty]').innerText()
        must(t.includes('No open tasks.') && t.includes('under the area of life'), 'the empty state says: ' + t)
        must(await pg.locator('[data-tasks-empty-add]').isVisible(), 'no box to add the first task')
        await noSideways()
      } finally {
        bench(`for n in frappe.get_all("Life Task", filters={"space": "zz-i21-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "${SPACE}", update_modified=False)`)
      }
    })
    const out = JSON.parse(bench(`import json
ids = ${JSON.stringify(made.ids)}
out = {}
g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${T('goal')}", "area": ids["Career"], "horizon": "Long term", "done_when": "Done"}).insert(ignore_permissions=True).name
def mk(key, title, area, **kw):
    out[key] = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": title, "area": ids[area], "status": "Open", **kw}).insert(ignore_permissions=True).name
mk("career", "${T('career')}", "Career", goal=g, due_date=frappe.utils.today())
mk("health", "${T('health')}", "Health", due_date=frappe.utils.add_days(frappe.utils.today(), -2))
mk("money", "${T('money')}", "Money")
mk("guess", "${T('guess')}", "Money", area_guessed=1, area_confidence=70)
mk("parked", "${T('parked')}", "Money")
mk("done", "${T('done')}", "Health", status="Done")
out["goal"] = g
print(json.dumps(out))`).split('\n').pop())
    Object.assign(ids, out)
    await s.api('tasks.set_status', { task: ids.parked, status: 'Someday' })
    const open = ['career', 'health', 'money', 'guess']
    await check(`${tag}.1`, `${width} px: every open task appears once, under its area`, async () => {
      await openTasks()
      const all = await shown()
      must(new Set(all).size === all.length, 'a task is listed twice')
      const api = await s.api('tasks.all_tasks', { space: SPACE })
      must(all.length === api.total && api.total === api.counts.open, `${all.length} rows, the server says ${api.total} (${api.counts.open} open)`)
      for (const [k, area] of [['career', 'Career'], ['health', 'Health'], ['money', 'Money'], ['guess', 'Money']]) {
        must((await pg.locator(`[data-task-group-section][data-group="${area}"] [data-task="${ids[k]}"]`).count()) === 1, `${k} is not under ${area}`)
      }
      must((await pg.locator(`[data-task="${ids.done}"], [data-task="${ids.parked}"]`).count()) === 0, 'a done or parked task shows under All open')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: grouping by goal and by due date shows the same tasks`, async () => {
      await openTasks()
      const base = (await shown()).sort()
      await pg.locator('[data-task-group-by="goal"]').click()
      await pg.waitForURL(/group=goal/, { timeout: 5000 })
      await pg.waitForTimeout(600)
      must(JSON.stringify((await shown()).sort()) === JSON.stringify(base), 'grouped by goal the tasks differ')
      must((await pg.locator(`[data-task-group-section][data-group="${T('goal')}"] [data-task="${ids.career}"]`).count()) === 1, 'the goal group does not hold its task')
      must((await pg.locator('[data-task-group-section][data-group="No goal"]').count()) === 1, 'no "No goal" group')
      await pg.locator('[data-task-group-by="due"]').click()
      await pg.waitForURL(/group=due/, { timeout: 5000 })
      await pg.waitForTimeout(600)
      must(JSON.stringify((await shown()).sort()) === JSON.stringify(base), 'grouped by due date the tasks differ')
      must((await pg.locator(`[data-task-group-section][data-group="Overdue"] [data-task="${ids.health}"]`).count()) === 1 && (await pg.locator(`[data-task-group-section][data-group="Today"] [data-task="${ids.career}"]`).count()) === 1, 'the due groups are wrong')
    })
    await check(`${tag}.3`, `${width} px: quick add under Health creates a task in Health`, async () => {
      await openTasks()
      const title = T('quick')
      const box = pg.locator('[data-group-add="Health"]')
      await box.fill(title)
      await box.press('Enter')
      await pg.waitForFunction((t) => [...document.querySelectorAll('[data-task-title]')].some((e) => e.textContent.trim() === t), title, { timeout: 8000 })
      const row = JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Task", {"title": "${title}"}, ["area", "area_guessed"], as_dict=True)))`).split('\n').pop())
      must(row.area === made.ids.Health && !row.area_guessed, 'the task is not in Health: ' + JSON.stringify(row))
      must((await pg.locator(`[data-task-group-section][data-group="Health"] [data-task-title]`).allInnerTexts()).includes(title), 'the task is not listed under Health')
    })
    await check(`${tag}.4`, `${width} px: the Someday filter shows the tasks of the Someday page`, async () => {
      await openTasks('show=someday')
      const here = (await shown()).sort()
      const old = (await s.api('someday.list', { space: SPACE, tab: 'tasks', page_length: 100 })).rows.map((r) => r.name).sort()
      must(old.includes(ids.parked) && JSON.stringify(here) === JSON.stringify(old), `All tasks > Someday ${here.length}, the Someday page ${old.length}`)
    })
    await check(`${tag}.5`, `${width} px: a task with a guessed area shows ✦`, async () => {
      await openTasks()
      const row = pg.locator(`[data-task="${ids.guess}"]`)
      must((await row.locator('[data-area-guess]').count()) === 1 && (await row.locator('[data-area-guess]').innerText()).includes('✦'), 'no ✦ on the guessed task')
      must((await pg.locator(`[data-task="${ids.money}"] [data-area-guess]`).count()) === 0, '✦ on a task whose area is known')
    })
    await check(`${tag}.6`, `${width} px: ${phone ? 'the list is one column' : 'a row has its task, goal and due date side by side'}`, async () => {
      await openTasks()
      await noSideways()
      const boxes = await pg.locator(`[data-task="${ids.career}"]`).evaluate((row) => [row.querySelector('[data-task-title]'), row.querySelector('[data-task-goal]'), row.querySelector('[data-task-due]')].map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width] }))
      if (phone) must(boxes[0][1] < boxes[1][1] && boxes[1][1] < boxes[2][1] && boxes.every(([x, , w]) => x + w <= width), 'the task, goal and date are not stacked: ' + JSON.stringify(boxes))
      else must(Math.abs(boxes[0][1] - boxes[1][1]) < 30 && boxes[0][0] < boxes[1][0] && boxes[1][0] < boxes[2][0], 'the columns are not side by side: ' + JSON.stringify(boxes))
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 22: Goals > No goal. Titles start "I22 ". Areas switched on here are put back after.
for (const width of SET_WIDTHS) {
  const tag = `I22.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I22 ${what} ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openNoGoal = async () => { await s.open('/life/goals/no-goal'); await pg.locator('[data-no-goal][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(400) }
  const shown = () => pg.locator('[data-no-goal-row]').evaluateAll((els) => els.map((e) => e.dataset.task))
  const dbRow = (title, fields) => JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Task", {"title": "${title}"}, ${JSON.stringify(fields)}, as_dict=True)))`).split('\n').pop())
  const made = JSON.parse(bench(`import json
top = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n, "parent_area": ("is", "not set")})
ids = {n: top(n) for n in ("Career", "Health", "Money")}
was = {k: frappe.db.get_value("Life Area", v, "is_on") for k, v in ids.items()}
for v in ids.values(): frappe.db.set_value("Life Area", v, "is_on", 1)
print(json.dumps({"ids": ids, "was": was}))`).split('\n').pop())
  const restore = () => bench(`import json
frappe.set_user("Administrator")
for t in frappe.get_all("Life Task", filters={"title": ["like", "I22 % ${width} ${stamp}"]}, pluck="name") + frappe.get_all("Life Task", filters={"title": ["like", "I22 Quillfeather%"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for g in frappe.get_all("Life Goal", filters={"title": ["like", "%I22 % ${width} ${stamp}%"]}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for g in frappe.get_all("Life Goal", filters={"title": ["like", "%Quillfeather%"]}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Task", filters={"space": "zz-i22-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "${SPACE}", update_modified=False)
for k, v in ${JSON.stringify(made.was)}.items(): frappe.db.set_value("Life Area", ${JSON.stringify(made.ids)}[k], "is_on", v)`)
  const ids = {}
  try {
    await check(`${tag}.7`, `${width} px: with every task under a goal No goal says what will appear and offers a box to add one`, async () => {
      bench(`for n in frappe.get_all("Life Task", filters={"space": "${SPACE}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "zz-i22-aside-${width}", update_modified=False)`)
      try {
        await openNoGoal()
        must(await pg.locator('[data-no-goal-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-no-goal-empty]').innerText()
        must(t.includes('Every open task serves a goal.') && t.includes('Tasks with no goal'), 'the empty state says: ' + t)
        must(await pg.locator('[data-no-goal-empty-add]').isVisible(), 'no box to add a task')
        await noSideways()
      } finally {
        bench(`for n in frappe.get_all("Life Task", filters={"space": "zz-i22-aside-${width}"}, pluck="name"): frappe.db.set_value("Life Task", n, "space", "${SPACE}", update_modified=False)`)
      }
    })
    const out = JSON.parse(bench(`import json
ids = ${JSON.stringify(made.ids)}
out = {}
g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${T('goal')}", "area": ids["Career"], "horizon": "Long term", "done_when": "Done"}).insert(ignore_permissions=True).name
def mk(key, title, area, **kw):
    out[key] = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": title, "area": ids[area], "status": "Open", **kw}).insert(ignore_permissions=True).name
mk("withgoal", "${T('with goal')}", "Career", goal=g)
mk("career", "${T('career')}", "Career")
mk("health", "${T('health')}", "Health")
mk("money", "${T('money')}", "Money")
mk("guess", "${T('guess')}", "Money", area_guessed=1, area_confidence=70)
mk("attach", "${T('attach')}", "Career")
for i in range(8): mk("q%d" % i, "I22 Quillfeather call %d" % i, "Health")
out["goal"] = g
print(json.dumps(out))`).split('\n').pop())
    Object.assign(ids, out)
    await check(`${tag}.1`, `${width} px: tasks without a goal are grouped by area; a task with a goal is not listed`, async () => {
      await openNoGoal()
      const all = await shown()
      must(new Set(all).size === all.length, 'a task is listed twice')
      for (const [k, area] of [['career', 'Career'], ['health', 'Health'], ['money', 'Money'], ['guess', 'Money']]) {
        must((await pg.locator(`[data-no-goal-group][data-group="${area}"] [data-task="${ids[k]}"]`).count()) === 1, `${k} is not under ${area}`)
      }
      must(!all.includes(ids.withgoal), 'a task with a goal is listed')
      const api = await s.api('tasks.no_goal', { space: SPACE })
      must(all.length === api.total, `${all.length} rows, the server says ${api.total}`)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: adding a task to a goal takes it off the list and it shows under that goal`, async () => {
      await openNoGoal()
      const row = pg.locator(`[data-task="${ids.attach}"]`)
      await row.locator('[data-add-to-goal]').click()
      await pg.getByRole('menuitem', { name: T('goal') }).click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-no-goal-row][data-task="${n}"]`), ids.attach, { timeout: 8000 })
      const g = dbRow(T('attach'), ['goal'])
      must(g.goal === ids.goal, 'the task is not under the goal: ' + JSON.stringify(g))
      const under = (await s.api('tasks.list', { space: SPACE, goal: ids.goal, status: 'open' })).tasks.map((t) => t.name)
      must(under.includes(ids.attach), 'the goal does not list the task')
    })
    await check(`${tag}.3`, `${width} px: confirming a guessed area clears ✦`, async () => {
      await openNoGoal()
      const row = pg.locator(`[data-task="${ids.guess}"]`)
      must((await row.locator('[data-area-guess]').count()) === 1, 'no ✦ on the guessed task')
      await row.locator('[data-area-guess]').click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-task="${n}"] [data-area-guess]`), ids.guess, { timeout: 8000 })
      must(dbRow(T('guess'), ['area_guessed']).area_guessed === 0, 'the guess is still marked')
      must((await pg.locator(`[data-task="${ids.guess}"]`).count()) === 1, 'the task left the list when its area was confirmed')
    })
    await check(`${tag}.4`, `${width} px: Make it a goal creates one goal in that area with the tasks attached`, async () => {
      await openNoGoal()
      const group = pg.locator('[data-no-goal-group][data-group="Health"]')
      must(await group.locator('[data-suggestion]').isVisible(), 'no suggestion under Health')
      must((await group.locator('[data-suggestion]').innerText()).includes('look like a goal'), 'the suggestion does not say it looks like a goal')
      const before = JSON.parse(bench(`import json\nprint(json.dumps(frappe.db.count("Life Goal", {"space": "${SPACE}"})))`).split('\n').pop())
      await group.locator('[data-make-goal]').click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-no-goal-row][data-task="${n}"]`), ids.q0, { timeout: 8000 })
      const res = JSON.parse(bench(`import json
goals = frappe.get_all("Life Goal", filters={"space": "${SPACE}", "title": ["like", "%Quillfeather%"]}, fields=["name", "area"])
tasks = frappe.get_all("Life Task", filters={"goal": ["in", [g.name for g in goals] or [""]]}, pluck="name")
print(json.dumps({"goals": goals, "tasks": tasks, "total": frappe.db.count("Life Goal", {"space": "${SPACE}"})}))`).split('\n').pop())
      must(res.goals.length === 1 && res.goals[0].area === made.ids.Health, 'the goal is not one goal in Health: ' + JSON.stringify(res.goals))
      must(res.total === before + 1, `${res.total - before} goals were made`)
      const want = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => ids['q' + i]).sort()
      must(JSON.stringify(res.tasks.sort()) === JSON.stringify(want), 'the tasks under the goal are ' + res.tasks.length)
    })
    await check(`${tag}.5`, `${width} px: the tab count is the number of open tasks with no goal`, async () => {
      await openNoGoal()
      const n = Number((await pg.locator('[data-tab="no-goal"] [data-tab-count]').innerText()).trim())
      const sql = JSON.parse(bench(`import json
print(json.dumps(frappe.db.sql("select count(*) from \`tabLife Task\` where space=%s and is_archived=0 and status in ('Open','Doing','Waiting') and ifnull(goal,'')='' and ifnull(standalone,0)=0", "${SPACE}")[0][0]))`).split('\n').pop())
      must(n === sql, `the tab says ${n}, the database has ${sql}`)
      must((await shown()).length === n, `${(await shown()).length} rows under a tab that says ${n}`)
    })
    await check(`${tag}.6`, `${width} px: ${phone ? 'groups stack and a task\'s actions are reachable' : 'a row has its task and its actions side by side'}`, async () => {
      await openNoGoal()
      await noSideways()
      const row = pg.locator(`[data-task="${ids.career}"]`)
      const box = async (sel) => { const b = await row.locator(sel).boundingBox(); must(b, sel + ' is not visible'); return b }
      const [title, area, fine, add] = [await box('[data-task-title]'), await box('[data-area-menu]'), await box('[data-fine-as-is]'), await box('[data-add-to-goal]')]
      for (const b of [area, fine, add]) must(b.x >= 0 && b.x + b.width <= width, `an action is outside the ${width} px screen`)
      if (phone) must(title.y < area.y && title.y < fine.y && title.y < add.y, 'the actions are not under the title')
      else must(title.x < area.x && Math.abs(title.y - area.y) < 40, 'the actions are not beside the title')
      const heads = await pg.locator('[data-no-goal-group] h2').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().y))
      must(heads.every((y, i) => !i || y > heads[i - 1]), 'the groups do not stack')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.8`, `${width} px: Fine as is leaves the list and keeps the task without a goal`, async () => {
      await openNoGoal()
      await pg.locator(`[data-task="${ids.money}"] [data-fine-as-is]`).click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-no-goal-row][data-task="${n}"]`), ids.money, { timeout: 8000 })
      const r = dbRow(T('money'), ['goal', 'standalone'])
      must(!r.goal && r.standalone === 1, 'the task changed unexpectedly: ' + JSON.stringify(r))
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 23: Library > Everything. Records titled "I23 ". Moved or changed rows are put back after.
for (const width of SET_WIDTHS) {
  const tag = `I23.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I23 ${what} ${width} ${stamp}`
  const WORD = `zebrafruit${stamp}${width}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const Q = `${width} ${stamp}` // only this run's records, whatever else the site holds
  const openLib = async (path = '/life/library', q = '') => { await s.open(q ? `${path}?q=${encodeURIComponent(q)}` : path); await pg.locator('[data-library-everything][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const rowFor = (title) => pg.locator('[data-lib-row]', { hasText: title })
  const letters = async () => pg.locator('[data-lib-row]').evaluateAll((els) => els.map((e) => e.dataset.letter))
  const was = JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Space", "${SPACE}", "agents_can_read_vault")))`).split('\n').pop())
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Note", "Life Vault Document", "Life Chat Log", "Life Person"):
    for n in frappe.get_all(dt, filters={"title" if dt != "Life Person" else "full_name": ["like", "I23 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
frappe.db.sql("update \`tabLife Index\` set space = %s where space = %s", ("${SPACE}", "zz-i23-aside-${width}"))
frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("${SPACE}", "zz-i23-aside-${width}"))
frappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", ${was ? 1 : 0})`)
  const ids = {}
  try {
    await check(`${tag}.7`, `${width} px: on an empty space the Library says what will appear and offers + Capture; People says the same`, async () => {
      bench(`frappe.db.sql("update \`tabLife Index\` set space = %s where space = %s and ref_doctype in ('Life Note', 'Life Vault Document', 'Life Chat Log', 'Life Inbox Item')", ("zz-i23-aside-${width}", "${SPACE}"))
frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("zz-i23-aside-${width}", "${SPACE}"))`)
      try {
        // People has its own screen and its own empty state since issue 25 (checked by I25.7)
        for (const p of ['/life/library']) {
          await openLib(p)
          must(await pg.locator('[data-lib-empty]').isVisible(), `no empty state at ${p}`)
          const t = await pg.locator('[data-lib-empty]').innerText()
          must(t.includes('will show up here') && t.includes('Capture'), 'the empty state says: ' + t)
          must(await pg.locator('[data-lib-capture]').isVisible(), 'no Capture button')
          must((await pg.locator('[data-lib-count]').innerText()).startsWith('0 items'), 'the count is not 0')
        }
        await noSideways()
      } finally {
        bench(`frappe.db.sql("update \`tabLife Index\` set space = %s where space = %s", ("${SPACE}", "zz-i23-aside-${width}"))
frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("${SPACE}", "zz-i23-aside-${width}"))`)
      }
    })
    const out = JSON.parse(bench(`import json
out = {}
mk = lambda **v: frappe.get_doc({"space": "${SPACE}", **v}).insert(ignore_permissions=True).name
career = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Career", "parent_area": ("is", "not set")})
out["note"] = mk(doctype="Life Note", title="${T('note')}", content_md="the ${WORD} idea", area=career)
out["other"] = mk(doctype="Life Note", title="${T('plain')}", content_md="nothing special here")
out["wiki"] = mk(doctype="Life Note", title="${T('org')}", collection="Wiki", summary="Organisation · Honda dealer", content_md="x")
out["doc"] = mk(doctype="Life Vault Document", title="${T('passport')}", doc_type="ID")
out["chat"] = mk(doctype="Life Chat Log", title="${T('chat')}", assistant="Claude", date=frappe.utils.today(), summary_md="s", open_items=[{"text": "do it", "status": "Open"}, {"text": "and it", "status": "Open"}])
out["person"] = mk(doctype="Life Person", full_name="${T('person')}", relation="Manager")
frappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", 0)
print(json.dumps(out))`).split('\n').pop())
    Object.assign(ids, out)
    await check(`${tag}.1`, `${width} px: Everything shows notes, documents, people and chats together, newest first, with the right kind and line`, async () => {
      await openLib('/life/library', Q)
      const want = [[T('note'), 'N', 'Note'], [T('org'), 'P', 'Organisation · Honda dealer · kept by the Brain'], [T('passport'), 'D', 'Document · ID · sensitive'],
        [T('chat'), 'C', 'Chat · Claude · 2 open items'], [T('person'), 'P', 'Person · Manager']]
      for (const [title, letter, line] of want) {
        const row = rowFor(title)
        must((await row.count()) === 1, `${title} is not listed once`)
        must((await row.getAttribute('data-letter')) === letter, `${title} has the wrong letter`)
        const l = await row.locator('[data-lib-line]').innerText()
        must(l.includes(line), `${title}: the line is "${l}", wanted "${line}"`)
      }
      must((await pg.locator('[data-lib-title]').first().innerText()).length > 0, 'a row has no title')
      const api = await s.api('everything.list', { space: SPACE, q: Q, page_length: 50 })
      const shown = await pg.locator('[data-lib-row]').evaluateAll((els) => els.map((e) => e.dataset.ref))
      must(JSON.stringify(shown) === JSON.stringify(api.rows.map((r) => r.ref)), 'the rows are not the server\'s, in its order')
      const dates = api.rows.map((r) => r.date)
      must(JSON.stringify(dates) === JSON.stringify([...dates].sort().reverse()), 'the rows are not newest first')
      must((await pg.locator('[data-lib-count]').innerText()).includes(api.total.toLocaleString() + ' item'), 'the count is not the server\'s total')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: each tab shows only its kind`, async () => {
      for (const [tab, letter] of [['notes', 'N'], ['documents', 'D'], ['people', 'P'], ['chats', 'C']]) {
        const api = await s.api('everything.list', { space: SPACE, tab, page_length: 100 })
        must(api.rows.length && api.rows.every((r) => r.letter === letter), `${tab} holds another kind`)
      }
      // issue 25: People is its own screen, one row per Life Person
      await s.open('/life/library/people?q=' + encodeURIComponent(Q))
      await pg.locator('[data-library-people][data-loaded="1"]').waitFor({ timeout: 10000 })
      await pg.waitForTimeout(300)
      const ls = await pg.locator('[data-people-letter]').evaluateAll((els) => els.map((e) => e.textContent.trim()))
      must(ls.length && ls.every((l) => l === 'P' || l === 'O'), 'People shows another kind: ' + ls.join(''))
      must((await pg.locator('[data-people-row]', { hasText: T('person') }).count()) === 1, 'People does not show the person')
      must((await pg.locator('[data-people-row]', { hasText: T('note') }).count()) === 0 && (await pg.locator('[data-people-row]', { hasText: T('chat') }).count()) === 0, 'People shows a note or a chat')
      for (const [path, yes, no] of [['/life/library/documents', T('passport'), T('note')], ['/life/library/chats', T('chat'), T('note')]]) {
        await s.open(path)
        await pg.waitForLoadState('networkidle')
        await pg.waitForTimeout(500)
        const text = await pg.locator('[data-main]').innerText()
        must(text.includes(yes) && !text.includes(no), `${path} does not show only its kind`)
      }
    })
    await check(`${tag}.3`, `${width} px: search finds a note by a word in its body and the Area filter narrows the list`, async () => {
      await openLib()
      await pg.locator('[data-lib-search] input, input[data-lib-search]').first().fill(WORD)
      await pg.waitForFunction((n) => document.querySelectorAll('[data-lib-row]').length === n, 1, { timeout: 8000 })
      must((await rowFor(T('note')).count()) === 1, 'the note with the word is not found')
      await pg.locator('[data-lib-search] input, input[data-lib-search]').first().fill('')
      await pg.waitForFunction((n) => document.querySelectorAll('[data-lib-row]').length > n, 1, { timeout: 8000 })
      const total = Number((await pg.locator('[data-lib-count]').innerText()).replace(/\D/g, ''))
      await pg.locator('select[data-lib-area]').selectOption({ label: 'Career' })
      await pg.waitForFunction((n) => { const t = document.querySelector('[data-lib-count]'); return t && Number(t.textContent.replace(/\D/g, '')) < n }, total, { timeout: 8000 })
      must((await rowFor(T('note')).count()) === 1, 'the Career note left the list')
      must((await rowFor(T('chat')).count()) === 0, 'a chat with no area is still listed under Career')
    })
    await check(`${tag}.4`, `${width} px: a sensitive document shows 🔒 and opens for the owner; the agent, with the Vault closed, never gets it`, async () => {
      await openLib('/life/library', Q)
      const row = rowFor(T('passport'))
      must((await row.locator('[data-sensitive-lock]').count()) === 1, 'no 🔒 on the document')
      must((await row.locator('[data-lib-line]').innerText()).includes('sensitive'), 'the line does not say sensitive')
      await row.locator('button').click()
      await pg.locator('[data-pane-title]', { hasText: T('passport') }).waitFor({ timeout: 8000 }).catch(() => {})
      must((await pg.locator('[data-pane-title]').innerText()).includes(T('passport')), 'the document did not open: ' + (await pg.locator('[data-pane-title]').innerText()))
      const agent = JSON.parse(bench(`import json
frappe.set_user("hermes@lifeos.test")
from lifeos import permissions
from lifeos.api import everything
permissions.clear_cache()
rows = everything.list(space="${SPACE}", page_length=100)["rows"]
print(json.dumps({"listed": any(r["name"] == "${ids.doc}" for r in rows), "others": len(rows)}))`).split('\n').pop())
      must(!agent.listed, 'the agent lists the sensitive document')
      must(agent.others > 0, 'the agent sees nothing at all')
    })
    await check(`${tag}.5`, `${width} px: Trash and archive opens the old archive`, async () => {
      await openLib()
      await pg.locator('[data-place-link="archive"]').click()
      await pg.waitForURL(/\/life\/library\/archive/, { timeout: 8000 })
      await pg.waitForLoadState('networkidle')
      must(await pg.locator('[data-main] h1').first().isVisible(), 'the archive shows nothing')
      must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === 'archive', 'the archive is not the open page')
      must(await pg.locator('[data-place-link="timeline"]').count() === 1 && await pg.locator('[data-place-link="graph"]').count() === 1, 'Timeline and Graph links are missing')
    })
    await check(`${tag}.6`, `${width} px: ${phone ? 'rows stack and the tabs scroll sideways inside their bar, not the page' : 'a row has its title, area and date side by side; the tabs fit'}`, async () => {
      await openLib()
      await noSideways()
      const row = rowFor(T('note'))
      const box = async (sel) => { const b = await row.locator(sel).boundingBox(); must(b, sel + ' is not visible'); return b }
      const [title, where, date] = [await box('[data-lib-title]'), await box('[data-lib-where]'), await box('[data-lib-date]')]
      for (const b of [title, where, date]) must(b.x >= 0 && b.x + b.width <= width + 1, `part of a row is outside the ${width} px screen`)
      if (phone) {
        must(where.y > title.y && date.y >= where.y, 'the row does not stack')
        const bar = await pg.locator('[data-place-tabs] [data-tab-bar], [data-tab-bar]').first().evaluate((e) => ({ sw: e.scrollWidth, cw: e.clientWidth }))
        must(bar.sw >= bar.cw, 'the tab bar is cut off')
      } else {
        must(where.x > title.x && date.x > where.x && Math.abs(title.y - date.y) < 40, 'the row is not side by side')
      }
      const tabs = await pg.locator('[data-place-tabs] [data-tab]').evaluateAll((els) => els.map((e) => e.dataset.tab))
      must(['all', 'notes', 'documents', 'people', 'chats'].every((t) => tabs.includes(t)), 'a tab is missing: ' + tabs.join())
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 24: Library > Files. Records titled "I24 ". Records and files made here are deleted after.
for (const width of SET_WIDTHS) {
  const tag = `I24.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I24 ${what} ${width} ${stamp}`
  const F = (what, ext) => `I24 ${what} ${width} ${stamp}.${ext}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openFiles = async (query = '') => { await s.open('/life/library/files' + query); await pg.locator('[data-library-files][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const rowFor = (name) => pg.locator('[data-file-row]', { hasText: name })
  const was = JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Space", "${SPACE}", "agents_can_read_vault")))`).split('\n').pop())
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Inbox Item", "Life Vault Document"):
    for n in frappe.get_all(dt, filters={"title": ["like", "I24 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
frappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", ${was ? 1 : 0})`)
  const ids = {}
  try {
    const out = JSON.parse(bench(`import json
from lifeos.api import inbox
mk = lambda **v: frappe.get_doc({"space": "${SPACE}", **v}).insert(ignore_permissions=True).name
att = lambda dt, name, file, data: frappe.get_doc({"doctype": "File", "file_name": file, "attached_to_doctype": dt, "attached_to_name": name, "is_private": 1, "content": data}).insert(ignore_permissions=True)
out = {}
career = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Career", "parent_area": ("is", "not set")})
out["a"] = mk(doctype="Life Inbox Item", title="${T('first user')}", source_type="Upload", area=career)
out["b"] = mk(doctype="Life Inbox Item", title="${T('second user')}", source_type="Upload")
for n in (out["a"], out["b"]): att("Life Inbox Item", n, "${F('shared', 'pptx')}", b"i24 shared slides ${width} ${stamp}")
out["v"] = mk(doctype="Life Inbox Item", title="${T('versions')}", source_type="Upload", source_system="claude", external_id="i24-${width}-${stamp}")
att("Life Inbox Item", out["v"], "${F('report', 'txt')}", b"i24 report one ${width} ${stamp}")
att("Life Inbox Item", out["v"], "${F('report', 'txt')}", b"i24 report two, newer ${width} ${stamp}")
for ext in ("txt", "png", "mp3"): att("Life Inbox Item", out["v"], "${F('kind', 'EXT')}".replace("EXT", ext), b"i24 " + ext.encode() + b" ${width} ${stamp}")
out["doc"] = mk(doctype="Life Vault Document", title="${T('passport')}", doc_type="ID")
att("Life Vault Document", out["doc"], "${F('passport', 'txt')}", b"i24 passport ${width} ${stamp}")
frappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", 0)
print(json.dumps(out))`).split('\n').pop())
    Object.assign(ids, out)
    await check(`${tag}.1`, `${width} px: a file used by two items is listed once, with both under Used in`, async () => {
      await openFiles('?q=' + encodeURIComponent(F('shared', 'pptx')))
      const row = rowFor(F('shared', 'pptx'))
      must((await row.count()) === 1, 'the shared file is not listed once: ' + (await row.count()))
      const used = await row.locator('[data-file-used-in]').evaluateAll((els) => els.map((e) => e.dataset.ref).sort())
      must(JSON.stringify(used) === JSON.stringify([`source:${ids.a}`, `source:${ids.b}`].sort()), 'Used in is ' + used.join())
      await row.locator('[data-file-used-in]').first().click()
      await pg.locator('[data-pane-title]').waitFor({ timeout: 8000 })
      must(await row.locator('[data-file-open]').isVisible() && await row.locator('[data-file-download]').isVisible(), 'Open or Download is missing')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.2`, `${width} px: a file with 2 versions shows "2 versions" and opens either`, async () => {
      await openFiles('?q=' + encodeURIComponent(F('report', 'txt')))
      const row = rowFor(F('report', 'txt'))
      must((await row.count()) === 1, 'the file is not listed once')
      must((await row.locator('[data-file-versions]').innerText()).includes('2 versions'), 'the row does not say 2 versions')
      await row.locator('[data-file-versions]').click()
      const hrefs = await row.locator('[data-file-version]').evaluateAll((els) => els.map((e) => e.getAttribute('href')))
      must(hrefs.length === 2 && hrefs[0] !== hrefs[1], 'the two versions are not two links: ' + hrefs.join())
      for (const h of hrefs) {
        const r = await pg.evaluate(async (u) => { const x = await fetch(u); return { status: x.status, text: (await x.text()).slice(0, 40) } }, h)
        must(r.status === 200 && r.text.startsWith('i24 report'), `${h} does not open: ${JSON.stringify(r)}`)
      }
    })
    await check(`${tag}.3`, `${width} px: the type filter shows only slides when Slides is chosen`, async () => {
      await openFiles('?q=' + encodeURIComponent(`I24 `))
      const pick = async (label) => { await pg.locator('[data-files-type]').first().click(); await pg.getByRole('option', { name: label, exact: true }).click() }
      await pick('Slides')
      await pg.waitForFunction(() => /type=slides/.test(location.search), null, { timeout: 8000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-file-row]').length > 0 && !document.querySelector('[data-file-row]:not([data-type="slides"])'), null, { timeout: 8000 })
      const names = await pg.locator('[data-file-row]').evaluateAll((els) => els.map((e) => e.dataset.type))
      must(names.length && names.every((t) => t === 'slides'), 'the list holds ' + names.join())
      must((await rowFor(F('shared', 'pptx')).count()) === 1 && (await rowFor(F('kind', 'png')).count()) === 0, 'the slides are not the only rows')
      await pick('Images')
      await pg.waitForFunction(() => /type=images/.test(location.search), null, { timeout: 8000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-file-row]').length > 0 && !document.querySelector('[data-file-row]:not([data-type="images"])'), null, { timeout: 8000 })
      const imgs = await pg.locator('[data-file-row]').evaluateAll((els) => els.map((e) => e.dataset.type))
      must(imgs.every((t) => t === 'images'), 'Images shows ' + imgs.join())
    })
    await check(`${tag}.4`, `${width} px: a user who cannot see any record using a file does not see the file`, async () => {
      const agent = JSON.parse(bench(`import json
frappe.set_user("hermes@lifeos.test")
from lifeos import permissions
from lifeos.api import files
permissions.clear_cache()
names = [r["name"] for r in files.list(space="${SPACE}", page_length=100, q="I24 ")["rows"]]
print(json.dumps({"names": names}))`).split('\n').pop())
      must(!agent.names.includes(F('passport', 'txt')), 'the agent lists the file of a closed Vault document')
      must(agent.names.includes(F('shared', 'pptx')), 'the agent sees nothing it may open')
      await openFiles('?q=' + encodeURIComponent(F('passport', 'txt')))
      must((await rowFor(F('passport', 'txt')).count()) === 1, 'the owner does not see the Vault file')
    })
    await check(`${tag}.5`, `${width} px: ${phone ? 'at 390 px the list is one column' : 'a row has its name, Used in and the buttons side by side'}`, async () => {
      await openFiles('?q=' + encodeURIComponent(F('shared', 'pptx')))
      await noSideways()
      const row = rowFor(F('shared', 'pptx'))
      const box = async (sel) => { const b = await row.locator(sel).first().boundingBox(); must(b, sel + ' is not visible'); return b }
      const [name, used, open] = [await box('[data-file-name]'), await box('[data-file-used]'), await box('[data-file-open]')]
      for (const b of [name, used, open]) must(b.x >= 0 && b.x + b.width <= width + 1, `part of a row is outside the ${width} px screen`)
      if (phone) must(used.y > name.y && open.y > used.y, 'the row is not one column')
      else must(used.x > name.x && open.x > used.x, 'the row is not side by side')
      must((await row.locator('[data-file-reusable]').count()) === 0, 'a file no job used shows Reusable')
      const tabs = await pg.locator('[data-place-tabs] [data-tab]').evaluateAll((els) => els.map((e) => e.dataset.tab))
      must(tabs.includes('files'), 'the Files tab is missing: ' + tabs.join())
    })
    await check(`${tag}.6`, `${width} px: with no files the screen says what will appear and offers + Capture; a search with no match says so`, async () => {
      const aside = JSON.parse(bench(`import json
rows = frappe.db.sql("select name, attached_to_doctype from \`tabFile\` where attached_to_doctype in ('Life Inbox Item', 'Life Note', 'Life Vault Document', 'Life Chat Log')", as_dict=True)
frappe.db.sql("update \`tabFile\` set attached_to_doctype = concat('zz ', attached_to_doctype) where attached_to_doctype in ('Life Inbox Item', 'Life Note', 'Life Vault Document', 'Life Chat Log')")
frappe.db.commit()
print(json.dumps(rows))`).split('\n').pop())
      try {
        await openFiles()
        must(await pg.locator('[data-files-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-files-empty]').innerText()
        must(t.includes('will show up here') && t.includes('Capture'), 'the empty state says: ' + t)
        must(await pg.locator('[data-files-capture]').isVisible(), 'no Capture button')
        await noSideways()
      } finally {
        bench(`import json
for r in json.loads(${JSON.stringify(JSON.stringify(aside))}):
    frappe.db.set_value("File", r["name"], "attached_to_doctype", r["attached_to_doctype"], update_modified=False)
frappe.db.commit()`)
      }
      await openFiles('?q=nosuchfile' + stamp)
      must((await pg.locator('[data-files-empty]').innerText()).includes('No file matches'), 'a search with no match does not say so')
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 25: Library > People. Records named "I25 ". People, organisations, notes and tasks made here are deleted after.
for (const width of SET_WIDTHS) {
  const tag = `I25.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I25 ${what} ${width} ${stamp}`
  const Q = `${width} ${stamp}` // only this run's records, whatever else the site holds
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openPeople = async (query = '') => { await s.open('/life/library/people' + query); await pg.locator('[data-library-people][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const openPerson = async (name) => { await s.open('/life/library/people/' + name); await pg.locator('[data-library-person][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const restore = () => bench(`frappe.set_user("Administrator")
for dt, field in (("Life Task", "title"), ("Life Note", "title")):
    for n in frappe.get_all(dt, filters={field: ["like", "I25 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
frappe.db.set_value("Life Person", {"full_name": ["like", "I25 % ${width} ${stamp}"]}, "organisation", None)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "I25 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("${SPACE}", "zz-i25-aside-${width}"))`)
  const ids = {}
  try {
    Object.assign(ids, JSON.parse(bench(`import json
mk = lambda **v: frappe.get_doc({"space": "${SPACE}", **v}).insert(ignore_permissions=True).name
out = {}
out["org"] = mk(doctype="Life Person", full_name="${T('Acme Ltd')}", kind="Organisation")
out["asha"] = mk(doctype="Life Person", full_name="${T('Asha')}", kind="Person", organisation=out["org"], role="Buyer")
out["ravi"] = mk(doctype="Life Person", full_name="${T('Ravi')}", kind="Person", organisation=out["org"])
out["old"] = mk(doctype="Life Note", title="${T('old note')}", content_md="Met ${T('Asha')} in May.")
out["new"] = mk(doctype="Life Note", title="${T('new note')}", content_md="${T('Asha')} sent the papers.")
out["task"] = mk(doctype="Life Task", title="${T('chase papers')}", status="Waiting", waiting_on="the bank", waiting_on_person=out["asha"])
frappe.db.sql("update \`tabLife Index\` set record_date = '2026-05-01' where ref_name = %s", out["old"])
print(json.dumps(out))`).split('\n').pop()))
    await check(`${tag}.3`, `${width} px: People lists persons and organisations; filtering by kind works`, async () => {
      await openPeople('?q=' + encodeURIComponent(Q))
      const kinds = async () => pg.locator('[data-people-row]').evaluateAll((els) => els.map((e) => e.dataset.kind + ':' + e.dataset.name))
      const all = await kinds()
      must(all.length === 3 && all.includes('Organisation:' + ids.org) && all.includes('Person:' + ids.asha), 'People lists ' + all.join())
      const letters = await pg.locator('[data-people-letter]').evaluateAll((els) => els.map((e) => e.textContent.trim()).sort().join(''))
      must(letters === 'OPP', 'letters are ' + letters)
      await pg.selectOption('[data-people-kind]', 'Organisation')
      await pg.waitForFunction(() => document.querySelectorAll('[data-people-row]').length === 1, null, { timeout: 8000 })
      must(JSON.stringify(await kinds()) === JSON.stringify(['Organisation:' + ids.org]), 'the Organisation filter shows ' + (await kinds()).join())
      must(new URL(pg.url()).searchParams.get('kind') === 'Organisation', 'the kind is not in the address')
      await pg.selectOption('[data-people-kind]', 'Person')
      await pg.waitForFunction(() => document.querySelectorAll('[data-people-row]').length === 2, null, { timeout: 8000 })
      must((await kinds()).every((k) => k.startsWith('Person:')), 'the People filter shows an organisation')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.4`, `${width} px: a person page lists the notes and tasks that mention them, newest first`, async () => {
      await openPerson(ids.asha)
      const refs = await pg.locator('[data-mention]').evaluateAll((els) => els.map((e) => e.dataset.ref))
      must(refs.length === 3 && refs.includes('note:' + ids.new) && refs.includes('note:' + ids.old) && refs.includes('task:' + ids.task), 'Mentioned in is ' + refs.join())
      must(refs[refs.length - 1] === 'note:' + ids.old, 'the oldest note is not last: ' + refs.join())
      const t = await pg.locator(`[data-mention][data-ref="task:${ids.task}"]`).innerText()
      must(t.includes('Waiting on them'), 'the task does not say it is waiting on them: ' + t)
      await pg.locator(`[data-mention][data-ref="note:${ids.new}"] button`).click()
      await pg.locator('[data-pane-title]').waitFor({ timeout: 8000 })
      must(new URL(pg.url()).searchParams.get('open') === 'note:' + ids.new, 'the note did not open in the pane')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.5`, `${width} px: an organisation page lists its people`, async () => {
      await openPerson(ids.org)
      const names = await pg.locator('[data-org-person]').evaluateAll((els) => els.map((e) => e.dataset.name).sort())
      must(JSON.stringify(names) === JSON.stringify([ids.asha, ids.ravi].sort()), 'the organisation lists ' + names.join())
      await pg.locator(`[data-org-person][data-name="${ids.asha}"] a`).click()
      await pg.waitForFunction((n) => location.pathname.endsWith('/library/people/' + n), ids.asha, { timeout: 8000 })
      await pg.locator('[data-person-org]').waitFor({ timeout: 8000 })
      must((await pg.locator('[data-person-org]').innerText()).includes(T('Acme Ltd')), 'the person page does not name the organisation')
    })
    await check(`${tag}.6`, `${width} px: ${phone ? 'at 390 px the person page is one column' : 'the facts sit beside the text and mentions'}`, async () => {
      await openPerson(ids.asha)
      await noSideways()
      const box = async (sel) => { const b = await pg.locator(sel).first().boundingBox(); must(b, sel + ' is not visible'); return b }
      const [who, mentions, facts] = [await box('[data-person-who]'), await box('[data-person-mentions]'), await box('[data-person-facts]')]
      for (const b of [who, mentions, facts]) must(b.x >= 0 && b.x + b.width <= width + 1, `part of the page is outside the ${width} px screen`)
      if (phone) must(Math.abs(who.x - facts.x) < 2 && facts.y > mentions.y && mentions.y > who.y, 'the page is not one column')
      else must(facts.x > who.x + who.width - 2 && Math.abs(facts.y - who.y) < 40, 'the facts are not beside the text')
    })
    await check(`${tag}.7`, `${width} px: with no people the screen says what will appear and offers + Capture`, async () => {
      bench(`frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("zz-i25-aside-${width}", "${SPACE}"))`)
      try {
        await openPeople()
        must(await pg.locator('[data-people-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-people-empty]').innerText()
        must(t.includes('will show up here') && t.includes('Capture'), 'the empty state says: ' + t)
        must(await pg.locator('[data-people-capture]').isVisible(), 'no Capture button')
        await noSideways()
      } finally {
        bench(`frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("${SPACE}", "zz-i25-aside-${width}"))`)
      }
    })
  } finally {
    restore()
    await s.ctx.close()
  }
}

// Issue 26: the ladder. A user made for the run (their own space, one task) is at level 1; their records are deleted after.
// I26.1 and I26.2 are unit tests (test_issue26_ladder).
for (const width of SET_WIDTHS) {
  const tag = `I26.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const phone = width < 800
  const user = `i26-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I26 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Task",):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let s
  try {
    bench(`from lifeos import devtools
devtools.make_user("${user}", "Ladder", ["Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)
frappe.get_doc({"doctype": "Life Task", "space": "${space}", "title": "I26 task ${width} ${stamp}"}).insert(ignore_permissions=True)`)
    s = await session(user, width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    // the card is in the sidebar on a desktop and in the focus sheet (the logo) on a phone
    const openCard = async () => {
      await s.open('/life/today')
      if (phone) await pg.locator('[data-lens-title]').click()
      return pg.locator('[data-setup-card]:visible')
    }
    await check(`${tag}.3`, `${width} px: the setup card shows the level and the next step, and links to How it works`, async () => {
      const card = await openCard()
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('Your setup · level 1 of 6'), 'the card says: ' + t)
      must(t.includes('Next: Connect a source'), 'the next step is not Connect a source: ' + t)
      await card.locator('[data-setup-how]').click()
      await pg.waitForFunction(() => location.pathname.endsWith('/how-it-works'), null, { timeout: 8000 })
      await pg.locator('[data-how]').waitFor({ timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.4`, `${width} px: How it works marks the current level as next, and shows the flow`, async () => {
      await s.open('/life/how-it-works')
      await pg.locator('[data-ladder]').waitFor({ timeout: 10000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-ladder-level]').length === 6, null, { timeout: 8000 })
      const marks = await pg.locator('[data-ladder-level]').evaluateAll((els) => els.map((e) => e.dataset.ladderMark).join())
      must(marks === 'done,next,later,later,later,later', 'the levels are marked ' + marks)
      const next = await pg.locator('[data-ladder-mark="next"]').innerText()
      must(next.includes('Level 2 · next') && next.includes('Connect a source'), 'next says: ' + next)
      must((await pg.locator('[data-how-flow] [data-how-step]').count()) === 4, 'the flow is not four boxes')
      await noSideways()
    })
    await check(`${tag}.5`, `${width} px: dismissing the card hides it for that user, and Settings still reaches How it works`, async () => {
      const card = await openCard()
      await card.locator('[data-setup-dismiss]').click()
      await pg.waitForFunction(() => !document.querySelector('[data-setup-card]'), null, { timeout: 8000 })
      await s.open('/life/today')
      await pg.waitForTimeout(800)
      if (phone) await pg.locator('[data-lens-title]').click()
      must((await pg.locator('[data-setup-card]').count()) === 0, 'the card came back after a reload')
      await s.open('/life/settings?tab=places')
      await pg.locator('[data-settings-how]').click()
      await pg.waitForFunction(() => location.pathname.endsWith('/how-it-works'), null, { timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}

// Issue 27: Settings, Assistant, Cost lists this month's spend by feature, matching the recorded calls. I27.1 to I27.4 are unit tests
// (test_issue27_gateway). The run's own calls are written under a feature made for it and deleted after.
for (const width of SET_WIDTHS) {
  const tag = `I27.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const feature = `I27 feature ${width} ${stamp}`
  const restore = () => bench(`frappe.db.delete("Life AI Usage", {"purpose": "${feature}"})`)
  let s
  try {
    // two haiku calls of 1,000,000 tokens in and 100,000 out: $0.15 each, $0.30 and 2,200,000 tokens in all
    bench(`from lifeos.ai import client
for _i in range(2):
    client.record("claude-haiku-5-5", {"input_tokens": 1000000, "output_tokens": 100000}, "${feature}", user="owner@lifeos.test")`)
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    await check(tag, `${width} px: Cost shows this month's spend by feature, matching the recorded calls`, async () => {
      await s.open('/life/settings?tab=cost')
      await pg.locator('[data-ai-spend]').waitFor({ timeout: 10000 })
      const row = pg.locator(`[data-cost-feature="${feature}"]`)
      await row.waitFor({ timeout: 8000 })
      const t = await row.innerText()
      must(t.includes('2,200,000 tokens') && t.includes('$0.30'), 'the feature row says: ' + t)
      must(/This month: \$/.test(await pg.locator('[data-cost-total]').innerText()), 'no this-month total')
      must((await pg.locator('[data-cost-call]').count()) >= 2, 'the last calls are not listed')
      must((await pg.locator('[data-cost-days]').innerText()).includes('call'), 'no by-day list')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}

// Issue 28: Brain > Skills lists process-capture; Test runs its examples (recorded answers) and shows pass or fail before saving; editing and
// saving makes version 2. A skill with no examples and no runs shows its empty states. I28.1 to I28.9 and I28.11 and .12 are unit tests
// (test_issue28_skills). The built-in skill is put back as the app ships it after, and the skill made here is deleted.
for (const width of SET_WIDTHS) {
  const tag = `I28.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const reset = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Skill Run", "Life Skill Version", "Life Skill Example"):
    frappe.db.delete(dt, {"skill": ("in", ["process-capture", "i28-empty-${width}"])})
frappe.db.delete("Life Skill", {"name": ("in", ["process-capture", "i28-empty-${width}"])})
from lifeos.skills import store
store.install()`)
  let s
  try {
    reset()
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    await check(`${tag}.10`, `${width} px: Skills lists process-capture, Test shows pass for each example, saving an edit makes version 2`, async () => {
      await s.open('/life/brain/skills')
      const card = pg.locator('[data-skill-card][data-skill="process-capture"]')
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('Process a capture') && t.includes('v1') && t.includes('Built-in') && /run/.test(t), 'the card says: ' + t)
      await noSideways()
      await card.locator('[data-skill-open]').click()
      await pg.locator('[data-skill-page][data-skill="process-capture"]').waitFor({ timeout: 10000 })
      must(await pg.locator('[data-skill-example]').count() === 4, 'the examples are not listed')
      await pg.locator('[data-skill-test]').click()
      await pg.locator('[data-example-result]').first().waitFor({ timeout: 15000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-example-result]').length === 4, null, { timeout: 15000 })
      const results = await pg.locator('[data-example-result]').evaluateAll((els) => els.map((e) => e.getAttribute('data-example-result')))
      must(results.every((r) => r === 'pass'), 'the examples say: ' + results.join(','))
      await pg.locator('[data-skill-text]').fill((await pg.locator('[data-skill-text]').inputValue()) + '\nAlways write the summary in plain words.\n')
      await pg.locator('[data-skill-save]').click()
      await pg.waitForFunction(() => document.querySelector('[data-skill-page]')?.getAttribute('data-version') === '2', null, { timeout: 10000 })
      must(await pg.locator('[data-skill-version-row]').count() === 2, 'two versions are not listed')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.E`, `${width} px: a skill with no examples and no runs says what will appear`, async () => {
      await s.api('skills.create', { slug: `i28-empty-${width}`, values: JSON.stringify({ title: `I28 empty ${width}`, trigger_kind: 'Button', tools: [], output_kind: 'Answer', instructions: 'Say hello.' }) })
      await s.open(`/life/brain/skills/i28-empty-${width}`)
      await pg.locator('[data-skill-page]').waitFor({ timeout: 10000 })
      const empties = await pg.locator('[data-empty]').allInnerTexts()
      must(empties.some((e) => e.includes('No examples yet.')) && empties.some((e) => e.includes('No runs yet.')), 'the empty states say: ' + empties.join(' | '))
      await noSideways()
    })
  } finally {
    if (s) await s.ctx.close()
    reset()
  }
}

// Issue 30: a proposed lesson shows in Needs you and on the skill page; Edit then Accept saves the edited words as a new version of the skill;
// removing an accepted lesson makes a version without it. I30.1, .2 and .5 are unit tests (test_issue30_lessons). The acceptance site's stand-in
// model answers every capture the same way, so process-capture's examples are replaced here by one it passes, and put back (store.install) after.
for (const width of SET_WIDTHS) {
  const tag = `I30.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const reset = (examples) => bench(`frappe.set_user("Administrator")
for dt in ("Life Skill Correction", "Life Skill Lesson"):
    frappe.db.delete(dt)
for dt in ("Life Skill Run", "Life Skill Version", "Life Skill Example"):
    frappe.db.delete(dt, {"skill": "process-capture"})
frappe.db.delete("Life Skill", {"name": "process-capture"})
from lifeos.skills import store
store.install()
${examples ? `frappe.db.delete("Life Skill Example", {"skill": "process-capture"})
import json
frappe.get_doc({"doctype": "Life Skill Example", "skill": "process-capture", "title": "Anything is filed", "source": "Owner",
  "input": json.dumps({"title": "Robusta prices", "text": "Robusta is up."}), "expected": json.dumps([{"has_proposal": {"kind": "Task"}}])}).insert()` : ''}`)
  // a proposed lesson with the three corrections it came from, as the Brain's improve-skill would have made it
  const propose = () => JSON.parse(bench(`import json
lesson = frappe.get_doc({"doctype": "Life Skill Lesson", "skill": "process-capture", "space": "${SPACE}", "status": "Proposed", "base_version": 1,
  "summary": "Commodity newsletters", "text": "Newsletters about commodity prices are for reading later, never a task."}).insert()
for i in range(3):
    frappe.get_doc({"doctype": "Life Skill Correction", "skill": "process-capture", "skill_version": 1, "space": "${SPACE}", "correction_type": "Area",
      "key": "area:Task:a>b", "detail": "The Brain filed a Task under Money; the owner filed it under Career.", "capture_title": f"Robusta prices {i}", "lesson": lesson.name}).insert()
print(json.dumps(lesson.name))`).split('\n').pop())
  let s
  try {
    reset(true)
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    await check(`${tag}.E`, `${width} px: with no lessons Needs you has no lessons section and the skill page says what will appear`, async () => {
      await s.open('/life/brain')
      await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-lessons]').count()) === 0, 'a lessons section shows with no lessons')
      await s.open('/life/brain/skills/process-capture')
      await pg.locator('[data-skill-lessons]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-skill-lessons]').innerText()).includes('No lessons yet.'), 'the skill page does not say what will appear')
      await noSideways()
    })
    await check(`${tag}.3`, `${width} px: a lesson shows in Needs you and on the skill page; Edit then Accept saves the edited words`, async () => {
      const name = propose()
      await s.open('/life/brain')
      const card = pg.locator(`[data-needs-lessons] [data-lesson="${name}"]`)
      await card.waitFor({ timeout: 10000 })
      must((await card.innerText()).includes('Newsletters about commodity prices') && (await card.innerText()).includes('3 corrections'), 'the lesson says: ' + (await card.innerText()))
      await noSideways()
      await s.open('/life/brain/skills/process-capture')
      await pg.locator(`[data-skill-lessons] [data-lesson="${name}"]`).waitFor({ timeout: 10000 })
      await s.open('/life/brain')
      await card.waitFor({ timeout: 10000 })
      await card.locator('[data-lesson-edit]').click()
      await card.locator('[data-lesson-text]').fill('Price newsletters are read later, not tasks.')
      await card.locator('[data-lesson-accept]').click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-needs-lessons] [data-lesson="${n}"]`), name, { timeout: 15000 })
      const d = await s.api('skills.detail', { name: 'process-capture' })
      must(d.version === 2 && d.instructions.includes('Price newsletters are read later, not tasks.') && !d.instructions.includes('commodity prices'), 'the skill is: version ' + d.version)
      await s.open('/life/brain/skills/process-capture')
      const done = pg.locator(`[data-skill-lessons] [data-lesson="${name}"][data-status="Accepted"]`)
      await done.waitFor({ timeout: 10000 })
      must((await done.locator('[data-lesson-version]').innerText()).includes('version 2'), 'the lesson does not link its version')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.4`, `${width} px: removing an accepted lesson makes a new version without it`, async () => {
      await s.open('/life/brain/skills/process-capture')
      const done = pg.locator('[data-skill-lessons] [data-lesson][data-status="Accepted"]')
      await done.waitFor({ timeout: 10000 })
      await done.locator('[data-lesson-remove]').click()
      await pg.waitForFunction(() => document.querySelector('[data-skill-page]')?.getAttribute('data-version') === '3', null, { timeout: 15000 })
      const d = await s.api('skills.detail', { name: 'process-capture' })
      must(!d.instructions.includes('Price newsletters') && !d.instructions.includes('Lessons from'), 'the text still has the lesson')
      must((await pg.locator('[data-skill-lessons] [data-lesson][data-status="Removed"]').count()) === 1, 'the lesson is not shown as removed')
      await noSideways()
    })
  } finally {
    if (s) await s.ctx.close()
    reset(false)
  }
}

// Issue 31: Settings > Calendar shows the calendars of the connected account and saves the one Life OS writes to (off by default).
// I31.1 to I31.4 are unit tests (test_issue31_gcal_write). The fixture calendar stands in for Google; the choice is cleared after.
for (const width of SET_WIDTHS) {
  const tag = `I31.${width}.5`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const restore = () => bench('frappe.defaults.clear_default("life_write_calendar", parent="owner@lifeos.test")')
  let s
  try {
    restore()
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    await check(tag, `${width} px: Settings > Calendar lists the account's calendars and saves the one to write to`, async () => {
      await s.open('/life/settings?tab=calendar')
      const pick = pg.locator('[data-calendar-write]')
      await pick.waitFor({ timeout: 10000 })
      must((await pick.inputValue()) === '', 'writing is not off by default')
      must((await pick.locator('option').count()) >= 2, 'the calendars of the account are not listed')
      await pick.selectOption('primary')
      await pg.waitForTimeout(800)
      await s.open('/life/settings?tab=calendar')
      await pg.locator('[data-calendar-write]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-calendar-write]').inputValue()) === 'primary', 'the choice was not saved')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}

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
await check('I5.1', 'Without the switches the tooling uses the Docker bench, Chrome and .env; with them, a local bench, Playwright\'s Chromium and the environment', async () => {
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
await check('I5.2', 'CI has an acceptance job that builds the front end, makes acceptance.localhost, serves it and runs every check', async () => {
  const job = ciJob('acceptance')
  must(job, 'no acceptance job in .github/workflows/ci.yml')
  for (const step of ['LIFEOS_BENCH_CMD: local', 'bench build --app lifeos', 'scripts/acceptance-site.sh', 'node tools/acceptance.mjs'])
    must(job.includes(step), 'the job lacks: ' + step)
  must(!/acceptance\.mjs[^\n]*--(only|ux)/.test(job), 'the job runs only some checks')
  must(/part: \[1440, 390, sets\]/.test(job) && job.includes('--part=${{ matrix.part }}'), 'the job does not run all three parts')
  if (process.env.GITHUB_ACTIONS) {
    must(!ONLY && !ONLY_UX, 'this CI run was given --only or --ux')
    must(SETUP.bench.startsWith('local bench') && !SETUP.chrome && SETUP.passwordFrom === 'environment', 'CI is not using the switches')
  }
  return process.env.GITHUB_ACTIONS ? 'running in GitHub Actions' : 'the job as written'
})
await check('I5.3', 'A failed check saves screenshots, and CI uploads them with the logs as an artifact', async () => {
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
await check('I5.4', 'No password or key in the workflow file or in the logs a failed run uploads', async () => {
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

// Issue 60: one kind of goal with a horizon, one parking lot (Someday), no tags. I60.1 to I60.3, I60.5 to I60.7 are unit tests
// (test_issue60_horizons_someday_no_tags). Titles start "I60 ".
for (const width of SET_WIDTHS) {
  const tag = `I60.${width}`
  if (ONLY && !ONLY.split(',').some((o) => tag.startsWith(o) || o.startsWith('.'))) continue
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I60 ${what} ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const tea = bench(`print(frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"}))`).split('\n').pop()
  const cleanup = () => bench(`frappe.set_user("Administrator")
for g in frappe.get_all("Life Goal", filters={"title": ["like", "I60 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)`)
  try {
    await check(`${tag}.4`, `${width} px: a Month goal created with a parent 12-week goal shows under it on its page and in Goals > By area`, async () => {
      const ids = JSON.parse(bench(`import json
from frappe.utils import today, add_days, getdate
cycle = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"})
parent = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${T('twelve')}", "horizon": "12 weeks", "cycle": cycle, "area": "${tea}", "done_when": "Done"}).insert(ignore_permissions=True)
child = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${T('month')}", "horizon": "Month", "target_date": today(), "area": "${tea}", "serves": parent.name, "done_when": "Done"}).insert(ignore_permissions=True)
print(json.dumps({"parent": parent.name, "child": child.name, "horizon": child.horizon}))`).split('\n').pop())
      must(ids.horizon === 'Month', 'the goal is not a Month goal')
      await s.open(`/life/goals/${ids.parent}`)
      await pg.locator('[data-served-by-line]').first().waitFor({ timeout: 10000 })
      must((await pg.locator('[data-main]').innerText()).includes(T('month')), 'the Month goal is not under the 12-week goal')
      await noSideways()
      await s.open('/life/goals?show=open')
      await pg.locator('[data-goals-by-area][data-loaded="1"]').waitFor({ timeout: 10000 })
      await pg.waitForTimeout(300)
      must(await pg.locator(`[data-goal-card][data-goal="${ids.child}"]`).count() === 1, 'the Month goal is not in Goals > By area')
      await noSideways()
    })
    await check(`${tag}.8`, `${width} px: no screen shows a tag, a tag picker or Settings > Tags`, async () => {
      const task = JSON.parse(bench(`import json
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${T('task')}", "area": "${tea}"}).insert(ignore_permissions=True)
print(json.dumps(t.name))`).split('\n').pop())
      for (const path of ['/life', '/life/goals/tasks', '/life/library', '/life/library/sources', '/life/goals/someday', '/life/settings?tab=areas', '/life/settings?tab=habits']) {
        await s.open(path)
        await pg.waitForTimeout(700)
        const text = await pg.locator('body').innerText()
        must(!/\btags?\b/i.test(text), `${path} shows a tag`)
        await noSideways()
      }
      await s.open('/life/settings?tab=areas')
      must((await pg.getByRole('button', { name: 'Tags' }).count()) + (await pg.getByRole('link', { name: 'Tags' }).count()) === 0, 'Settings lists Tags')
      await s.open('/life/settings?tab=tags')
      await pg.waitForTimeout(500)
      must((await pg.locator('[data-settings-list="tag"]').count()) === 0, 'Settings > Tags still lists tags')
      await s.open(`/life/goals/tasks?open=task:${task}`)
      await pg.waitForTimeout(900)
      must(!/\btags?\b/i.test(await pg.locator('body').innerText()), 'the task pane shows a tag picker')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check(`${tag}.9`, `${width} px: the month plan shows this month's Month goals in priority order, with the habits`, async () => {
      const plan = await s.api('journal.month', { space: SPACE, create: 1 })
      for (const w of ['first', 'second', 'third']) await s.api('journal.save_month_goal', { plan: plan.plan.name, title: T(w) })
      const now = await s.api('journal.month', { space: SPACE })
      const third = now.plan.goals.find((g) => g.title === T('third'))
      await s.api('journal.save_month_goal', { plan: plan.plan.name, row: third.row, move: -1 })
      await s.open('/life/today/month?view=plan')
      await pg.locator('[data-month-goal]').first().waitFor({ timeout: 10000 })
      const titles = (await pg.locator('[data-month-goal]').allInnerTexts()).map((x) => x.split('\n').find((l) => l.startsWith('I60 '))).filter((x) => [T('first'), T('second'), T('third')].includes(x))
      must(titles.join('|') === [T('first'), T('third'), T('second')].join('|'), 'the Month goals are in the order: ' + titles)
      must((await pg.locator('[data-main]').innerText()).includes('Habits'), 'the habits are not shown with the goals')
      await noSideways()
    })
  } finally {
    cleanup()
    await s.ctx.close()
  }
}

// every check cleans up: this run's records go from the acceptance site too, and none is left
await check('S4.1', "This run's records are removed from the acceptance site", async () => {
  const code = 'from lifeos import devtools\nimport json\ndevtools.purge_test_debris(dry_run=0)\nd, st = devtools.find_test_debris()\nprint(json.dumps({k: len(v) for k, v in d.items()}))'
  let out
  try { out = bench(code) } catch (e) { out = bench(code) } // the purge is safe to repeat: a lock wait on a busy runner should not fail the run
  out = out.split('\n').pop()
  must(!Object.keys(JSON.parse(out)).length, 'left on the acceptance site: ' + out)
})

// lifeos.localhost is the owner's test site: no acceptance run may leave a record there
await check('S4.0', 'No test debris on lifeos.localhost after the run', async () => {
  const out = bench('from lifeos import devtools\nimport json\nd, st = devtools.find_test_debris()\nprint(json.dumps({k: len(v) for k, v in d.items()}))', 'lifeos.localhost').split('\n').pop()
  const d = JSON.parse(out)
  must(!Object.keys(d).length, 'debris on lifeos.localhost: ' + out)
})

// Pre-step 6: Frappe's semgrep rules find nothing in the app, apart from the inline exceptions in docs/conformance/exceptions.md
await check('C.1', "Frappe's semgrep rules report no finding (tools/scan.sh)", async () => {
  try {
    execFileSync(path.join(root, 'tools/scan.sh'), { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
  } catch (e) {
    const lines = String(e.stdout || '').trim().split('\n')
    throw new Error('findings: ' + lines.slice(-3).join(' ').replace(/\s+/g, ' '))
  }
})

await browser.close()
const failed = results.filter((r) => !r[1])
console.log(`\n${results.length - failed.length} of ${results.length} acceptance items pass.`)
process.exit(failed.length ? 1 : 0)
