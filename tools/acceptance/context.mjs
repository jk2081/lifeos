// The state every acceptance check shares: the bench, the browser, the owner's session, the fake agent's key and the helpers
// (`check`, `must`, `session`, `bench`, dates). It is loaded once by tools/acceptance.mjs, after the acceptance site is ready;
// each place's file (today.mjs, brain.mjs, ...) imports what it needs from here.
import { chromium } from 'playwright-core'
import { walkScreens } from '../screen-walk.mjs'
import { resolveSetup, benchPython, MAC_CHROME } from '../acceptance-env.mjs'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const root = path.resolve(import.meta.dirname, '..', '..')
export const SETUP = resolveSetup()
export const env = { LIFEOS_DEV_PASSWORD: SETUP.password }
export const base = process.env.LIFEOS_URL || 'http://localhost:19000'
export const SITE = process.env.LIFEOS_SITE || 'acceptance.localhost'
if (SITE === 'lifeos.localhost') throw new Error('acceptance runs on its own site, never on lifeos.localhost')
export const GET_METHODS = new Set(JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/lib/getMethods.json'), 'utf8')))
export const queryParams = (args) => Object.fromEntries(Object.entries(args || {}).filter(([, v]) => v !== undefined && v !== null)
  .map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 1 : 0) : typeof v === 'object' ? JSON.stringify(v) : v]))
export const SPACE = 'Private'
export const stamp = Date.now().toString(36)
export const results = []
export const iso = (d) => new Date(d.getTime() + 5.5 * 3600e3).toISOString().slice(0, 10) // Asia/Kolkata date
export const today = iso(new Date())
export const addDays = (n) => iso(new Date(Date.now() + n * 86400e3))
export const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
// the first date at least `min` days from today that falls on the named weekday (YYYY-MM-DD)
export const nextWeekday = (name, min = 1) => { for (let n = min; ; n++) { const d = addDays(n); if (DAY_NAMES[new Date(d + 'T12:00:00Z').getUTCDay()] === name) return d } }
export const plusDays = (d, n) => new Date(Date.parse(d + 'T12:00:00Z') + n * 86400e3).toISOString().slice(0, 10)

export function bench(code, site = SITE) {
  // run Python on the acceptance site, for the steps that need the clock moved (the archive job)
  const script = `import frappe; frappe.init("${site}"); frappe.connect()\n${code}\nfrappe.db.commit()\n`
  return benchPython(script).trim()
}

// a journal page to open: the Brain's photo check makes one, and a place walked on its own makes this one
export const ensureJournalPage = () => bench(`r = frappe.db.sql("select name from \`tabLife Journal Page\` where space='${SPACE}' limit 1")
if not r:
    d = frappe.get_doc({"doctype": "Life Journal Page", "space": "${SPACE}", "page_date": frappe.utils.today(), "transcript_md": "A page for the checks."})
    d.flags.ignore_permissions = True
    d.insert()
    r = [[d.name]]
print(r[0][0])`).split('\n').pop()

export const browser = await chromium.launch({ executablePath: SETUP.chrome, headless: true })

export async function session(user, width = 1440) {
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
  // Issue 46: `area=` is each page's own filter and is not carried; a path that names none opens on all of life, and the checks that
  // narrow by area name it.
  const open = async (p) => {
    const u = new URL(base + p)
    if (u.pathname.startsWith('/life') && !u.searchParams.has('area')) u.searchParams.set('area', '')
    await page.goto(u.toString(), { waitUntil: 'networkidle' }); await page.waitForTimeout(400)
  }
  return { ctx, page, api, upload, open }
}
// ---- which checks run -----------------------------------------------------------------------------------------------------
// `--only=TODAY` runs one place's checks, `--only=TODAY.3` one check, `--only=TODAY.3,BRAIN.7` several. `--part=today` runs one
// place (the unit of the parallel jobs in .github/workflows/ci.yml); without either, every place runs, one after another.
export { PLACES } from './places.mjs'
import { PLACES } from './places.mjs'
export const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7)
export const PART = (process.argv.find((a) => a.startsWith('--part=')) || '').slice(7)
if (PART && !PLACES.includes(PART)) throw new Error(`--part= takes one of ${PLACES.join(', ')}`)
export const WIDTHS = [1440, 390]
// a place is walked when --part names it, or --only names one of its checks, or neither is given
export const placeRuns = (place) => {
  if (PART) return PART === place
  if (ONLY) return ONLY.split(',').some((o) => o.split('.')[0].toUpperCase() === place.toUpperCase())
  return true
}
const wanted = (n) => !ONLY || ONLY.split(',').some((o) => String(n) === o.toUpperCase() || String(n).startsWith(o.toUpperCase() + '.'))
export async function check(n, title, fn) {
  if (!wanted(n)) return
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
export const must = (cond, message) => { if (!cond) throw new Error(message) }
// Issue 5: when a check fails, every page still open is saved to LIFEOS_FAIL_SHOTS (GitHub Actions uploads the folder)
export const FAIL_SHOTS = process.env.LIFEOS_FAIL_SHOTS
export async function failShots(n, dir = FAIL_SHOTS) {
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
export const pathOf = (pg) => new URL(pg.url()).pathname.replace(/\/$/, '') || '/'

// the agent's key is made for this run and passed in the environment; it is never printed or stored
export const [agentKey, agentSecret] = bench('from lifeos import devtools\nprint(devtools.agent_api_key())').split('\n').pop().split(':')
// the agent over HTTP with its key: GET for the methods that declare GET (frontend/src/lib/getMethods.json), POST for the rest,
// so a refusal is the permission rule and not the wrong HTTP method
export function agentFetch(m, args = {}) {
  const headers = { Authorization: `token ${agentKey}:${agentSecret}` }
  const url = `${base}/api/method/lifeos.api.${m}`
  if (GET_METHODS.has(`lifeos.api.${m}`)) return fetch(`${url}?${new URLSearchParams(args)}`, { headers })
  return fetch(url, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(args) })
}
export function runAgent() {
  return execFileSync('python3', [path.join(root, 'agent/fake_agent.py'), '--url', base],
    { env: { ...process.env, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' })
}
// a real one-page PDF, made by the test helpers on the bench
export const PDF = Buffer.from(bench('import base64\nfrom lifeos import devtools\nprint(base64.b64encode(devtools.pdf_bytes()).decode())').split('\n').pop(), 'base64')

// the Settings check adds and removes this person as a member; they exist on the acceptance site with no space
bench(`from lifeos import devtools\nfrappe.set_user("Administrator")\ndevtools.make_user("stranger@lifeos.test", "Stranger", ["Life User"])`)
// UX fixes, set 5: Ask and the AI insights use the fake model here, never the real API: the site config flag, and a key that
// starts with "fake-", which the client never sends anywhere. Insights start empty.
bench(`from frappe.installer import update_site_config
update_site_config("lifeos_fake_ai", 1)
s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()
frappe.db.delete("Life Insight"); frappe.db.delete("Life AI Usage")
# issue 56: new goals need a "Done when" by default; the older checks make goals without one, so it is off for them and I56 switches it on
frappe.db.set_single_value("Life Settings", "require_done_when", 0)
for sp in frappe.get_all("Life Space", pluck="name"): frappe.db.set_value("Life Space", sp, {"ask_enabled": 1, "ask_can_read_vault": 0})`)
// Earlier runs leave their records on the test site. Today lists only the 20 documents that expire soonest, so the vault
// documents of earlier runs are archived first; otherwise this run's document would not be among them.
bench(`from lifeos import archive
frappe.set_user("owner@lifeos.test")
for name in frappe.get_all("Life Vault Document", filters={"space": "${SPACE}", "is_archived": 0}, or_filters=[["title", "like", "UX permit %"], ["title", "like", "Passport m%"]], pluck="name"):
    archive.set_archived("Life Vault Document", name, True, "Manual")`)

export const owner = await session('owner@lifeos.test')
export const areas = (await owner.api('area.tree', { space: SPACE })).areas
export const areaId = (name) => areas.find((a) => a.area_name === name)?.name
export let photoItem, photoFile
export { chromium, walkScreens, resolveSetup, benchPython, MAC_CHROME, execFileSync, fs, os, path }
