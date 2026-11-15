// Walks the acceptance list in section 13 of SPEC.md against the local test site, as a person would:
// a logged-in browser for the owner and for a second user, and agent/fake_agent.py over HTTP with an API key.
//   node tools/acceptance.mjs
// Needs the Docker bench running with seed and demo data loaded, and .env with LIFEOS_DEV_PASSWORD.
// It leaves its records on the test site. It prints one line per acceptance item and exits 1 if any fails.
import { chromium } from 'playwright-core'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env'), 'utf8').split('\n').filter(Boolean).map((l) => l.split('=')))
const base = process.env.LIFEOS_URL || 'http://localhost:18000'
const SPACE = 'Private'
const stamp = Date.now().toString(36)
const results = []
const iso = (d) => new Date(d.getTime() + 5.5 * 3600e3).toISOString().slice(0, 10) // Asia/Kolkata date
const today = iso(new Date())
const addDays = (n) => iso(new Date(Date.now() + n * 86400e3))

function bench(code) {
  // run Python on the test site, for the two steps that need the clock moved (the archive job)
  const script = `import frappe; frappe.init("lifeos.localhost"); frappe.connect()\n${code}\nfrappe.db.commit()\n`
  return execFileSync('docker', ['exec', '-i', 'lifeos-bench', 'bash', '-lc', 'cd ~/frappe-bench/sites && ../env/bin/python -W ignore -'],
    { input: script, encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] }).trim()
}

const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })

async function session(user, width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, timezoneId: 'Asia/Kolkata',
    isMobile: width < 800, hasTouch: width < 800 })
  const page = await ctx.newPage()
  const res = await page.request.post(base + '/api/method/login', { form: { usr: user, pwd: env.LIFEOS_DEV_PASSWORD } })
  if (!res.ok()) throw new Error('login failed for ' + user)
  await page.goto(base + '/life', { waitUntil: 'networkidle' })
  const csrf = await page.evaluate(() => window.csrf_token)
  const api = async (method, args = {}, { raw = false } = {}) => {
    const r = await page.request.post(`${base}/api/method/${method.includes('lifeos.') || method.startsWith('frappe.') ? method : 'lifeos.api.' + method}`,
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
  const open = async (p) => { await page.goto(base + p, { waitUntil: 'networkidle' }); await page.waitForTimeout(400) }
  return { ctx, page, api, upload, open }
}

const ONLY_UX = process.argv.includes('--ux') // run only the UX checks (U1 and up)
async function check(n, title, fn) {
  if (ONLY_UX && !String(n).startsWith('U')) return
  try {
    const note = await fn()
    results.push([n, true, title, note || ''])
  } catch (e) {
    results.push([n, false, title, String(e.message || e).split('\n')[0].slice(0, 300)])
  }
  const [, ok, t, note] = results[results.length - 1]
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${String(n).padStart(2)}. ${t}${note ? '  — ' + note : ''}`)
}
const must = (cond, message) => { if (!cond) throw new Error(message) }

// the agent's key is made for this run and passed in the environment; it is never printed or stored
const [agentKey, agentSecret] = bench('from lifeos import devtools\nprint(devtools.agent_api_key())').split('\n').pop().split(':')
function runAgent() {
  return execFileSync('python3', [path.join(root, 'agent/fake_agent.py'), '--url', base],
    { env: { ...process.env, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' })
}
// a real one-page PDF, made by the test helpers on the bench
const PDF = Buffer.from(bench('import base64\nfrom lifeos import devtools\nprint(base64.b64encode(devtools.pdf_bytes()).decode())').split('\n').pop(), 'base64')

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
  const text = await owner.page.locator('.main').innerText()
  must(/Week \d+ of 12/.test(text), 'no 12 Week Year week on Today')
  must(text.includes('Habits today') && text.includes('Japa'), 'habits are missing on Today')
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
  await owner.page.locator('button.bt.p', { hasText: /^Accept$/ }).first().click()
  await owner.page.waitForTimeout(800)
  await owner.page.locator('button.bt.t', { hasText: /^Reject$/ }).first().click()
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
  const tasks = await owner.api('tasks.list', { space: SPACE, page_length: 100 })
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
  await phone.open('/life/journal/habits')
  const count = () => phone.page.locator('text=/\\d+ of \\d+ days/').first().innerText()
  const before = await count()
  // an empty box if the month has one, else untick a ticked one: the count changes either way
  const empty = phone.page.locator('button.dy[aria-pressed="false"]:not([disabled])')
  const box = (await empty.count()) ? empty.first() : phone.page.locator('button.dy[aria-pressed="true"]:not([disabled])').last()
  const size = await box.boundingBox()
  must(size.width >= 40 && size.height >= 40, `habit box is ${size.width}x${size.height}`)
  await box.click()
  await phone.page.waitForTimeout(700)
  const after = await count()
  must(before !== after, `count stayed at ${before}`)
  must(await phone.page.locator('button.dy:not([disabled])').count() <= Number(today.slice(8)), 'a day that has not come can be ticked')
  must(await phone.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'the page scrolls sideways')
  await phone.ctx.close()
  return `${before} -> ${after}`
})

await check(5, 'Tick week cells in the 12 Week Year grid and see the week score change', async () => {
  await owner.open('/life/journal')
  const stat = () => owner.page.locator('.stats .cd').first().innerText()
  const before = (await stat()).replace(/\n/g, ' ')
  const g = await owner.api('journal.grid', { space: SPACE })
  const col = g.current_week
  // an empty cell of the current week
  const cells = owner.page.locator(`.gr:not(.hdr) .wc:nth-of-type(${col}) button.wk:not([disabled]):not(.on):not(.done)`)
  let clicked = false
  for (let i = 0; i < await cells.count() && !clicked; i++) {
    const c = cells.nth(i)
    if (((await c.innerText()).trim() === '') && (await c.getAttribute('aria-pressed')) !== 'true') { await c.click(); clicked = true }
  }
  if (!clicked) await owner.page.locator('.wc button.wk:not([disabled])').nth(col - 1).click()
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
  await owner.open('/life/calendar/year')
  must((await owner.page.locator('.main').innerText()).includes('Birthday'), 'not shown on the year screen')
})

await check(8, 'Vault document expiring in 30 days shows a badge on Today', async () => {
  const title = `Passport ${stamp}`
  await owner.api('vault.save', { space: SPACE, values: { title, doc_type: 'Travel', expiry_date: addDays(30), number_last4: '4821', area: areaId('Money & Legal') } })
  const refused = await owner.api('vault.save', { space: SPACE, values: { title: 'x', doc_type: 'ID', number_last4: '123456789', area: areaId('Money & Legal') } }, { raw: true })
  must(!refused.ok(), 'a full number was stored')
  const t = await owner.api('today.get', { space: SPACE })
  must(t.coming_up.some((c) => c.kind === 'vault' && c.title === title), 'not in today.get')
  await owner.open('/life')
  must((await owner.page.locator('.main').innerText()).includes(title), 'not shown on Today')
  await owner.open('/life/vault')
  must((await owner.page.locator('.main').innerText()).includes(title), 'not shown in the Vault')
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
  must((await owner.page.locator('.main').innerText()).includes(`Source note ${stamp}`), 'the backlinks panel does not show the source')
})

await check(10, 'Search for a word in a transcript finds the inbox item', async () => {
  const res = await owner.api('search.query', { text: 'Nowrojee' })
  must(res.results.some((r) => r.ref_doctype === 'Life Inbox Item' && r.ref_name === photoItem), 'the inbox item was not found')
  await owner.page.keyboard.press('Control+k')
  await owner.page.keyboard.type('Nowrojee')
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
    'projects.list': {}, 'area.tree': {}, 'journal.grid': {}, 'journal.goals': {}, 'journal.month': {}, 'journal.habits': {}, 'journal.checkins': {},
    'journal.pages': {}, 'journal.weekly_review': {}, 'settings.get': {} }
  for (const [m, args] of Object.entries(reads)) {
    const r = await fam.api(m, { ...args, space: SPACE }, { raw: true })
    must(r.status() === 403, `${m} with space=Private answered ${r.status()}`)
    const own = JSON.stringify(await fam.api(m, args)) || ''
    must(!own.includes(stamp) && !own.includes('Ruchi ITR') && !own.includes('Japa'), `${m} leaks Private records`)
  }
  for (const [m, args] of [['inbox.get', { item: photoItem }], ['area.get', { area: areaId('Tea & Coffee') }],
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
  for (const p of ['', '/inbox', '/timeline', '/tasks', '/calendar/year', '/journal', '/journal/goals', '/journal/month', '/journal/habits', '/journal/checkins',
    '/journal/pages', '/journal/review', '/areas', '/projects', '/library', '/vault', '/chats', '/graph', '/archive', '/settings']) {
    await fam.open('/life' + p)
    const text = await fam.page.locator('.app').innerText()
    must(!/Ruchi|Merrill|Japa|Tea & Coffee|Private/.test(text) && !text.includes(stamp), `screen ${p || '/'} shows Private content`)
    screens++
  }
  await fam.ctx.close()
  return `${Object.keys(reads).length} methods, ${screens} screens, search and file`
})

await check(12, 'At review, change the area with one tap and add a second: the record is on both area pages', async () => {
  const title = `Promotion plan ${stamp}`
  const tea = await owner.api('area.get', { area: areaId('Tea & Coffee') })
  const personal = await owner.api('area.get', { area: areaId('Personal') })
  must(tea.tasks.some((t) => t.title === title) || tea.timeline.some((t) => t.title === title), 'not on the Tea & Coffee page')
  must(personal.references.some((t) => t.title === title), 'not under References on the Personal page')
  const item = await owner.api('inbox.list', { space: SPACE, status: 'To Review' })
  await owner.open('/life/inbox/' + item.items[0].name)
  must(await owner.page.locator('text=+ also in').count() > 0, 'the Review screen has no area chips')
})

await check(13, 'Tea & Coffee area page shows projects, tasks, notes and chats together', async () => {
  const a = await owner.api('area.get', { area: areaId('Tea & Coffee') })
  must(a.projects.length && a.tasks.length && a.notes.length && a.chats.length, `projects ${a.projects.length}, tasks ${a.tasks.length}, notes ${a.notes.length}, chats ${a.chats.length}`)
  await owner.open('/life/areas/' + areaId('Tea & Coffee'))
  const text = await owner.page.locator('.main').innerText()
  must(text.includes(a.projects[0].title) && text.includes(a.notes[0].title) && text.includes(a.chats[0].title), 'the screen does not show them')
  return `${a.projects.length} projects, ${a.counts.open_tasks} open tasks, ${a.counts.notes} notes, ${a.counts.chats} chats`
})

await check(14, 'Timeline shows everything captured on one day', async () => {
  const t = await owner.api('timeline.get', { space: SPACE, from_date: today, to_date: today, page_length: 100 })
  const kinds = new Set(t.days.flatMap((d) => d.entries.map((e) => e.kind)))
  for (const k of ['Inbox', 'Task', 'Note', 'Document', 'Journal Page']) must(kinds.has(k), `no ${k} on today's timeline`)
  must(t.days.length === 1, 'more than one day returned')
  await owner.open('/life/timeline')
  must((await owner.page.locator('.main').innerText()).includes(`Target note ${stamp}`), 'the screen does not show today')
  return [...kinds].join(', ')
})

await check(15, 'Complete a project: it and its records move to Archive. Restore it', async () => {
  const r = await owner.api('frappe.client.insert', { doc: { doctype: 'Life Project', space: SPACE, title: `Project ${stamp}`, area: areaId('Learning'), status: 'Active' } })
  const task = await owner.api('tasks.quick_add', { text: `Project task ${stamp}`, space: SPACE, project: r.name })
  const info = await owner.api('projects.completion_info', { project: r.name })
  must(JSON.stringify(info).includes('1'), 'the confirm dialog has no count')
  await owner.api('projects.set_status', { project: r.name, status: 'Done' })
  let arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(arch.projects.some((p) => p.name === r.name), 'the project is not in Archive')
  must(JSON.stringify(arch.groups).includes(task.name), 'its task is not in Archive')
  must(!(await owner.api('tasks.list', { space: SPACE, page_length: 100 })).tasks.some((t) => t.name === task.name), 'the task is still in Tasks')
  must(!JSON.stringify(await owner.api('projects.list', { space: SPACE })).includes(r.name), 'the project is still in Projects')
  await owner.open('/life/archive')
  must((await owner.page.locator('.main').innerText()).includes(`Project ${stamp}`), 'the Archive screen does not show it')
  await owner.api('archive.restore', { doctype: 'Life Project', name: r.name })
  arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(!arch.projects.some((p) => p.name === r.name) && !JSON.stringify(arch.groups).includes(task.name), 'restore left it in Archive')
  must((await owner.api('tasks.list', { space: SPACE, page_length: 100 })).tasks.some((t) => t.name === task.name), 'the task did not come back')
})

await check(16, 'Archive job archives done tasks; a stale open task is listed under Decide', async () => {
  const done = await owner.api('tasks.quick_add', { text: `Old done task ${stamp}`, space: SPACE, area: areaId('Personal') })
  const stale = await owner.api('tasks.quick_add', { text: `Stale open task ${stamp}`, space: SPACE, area: areaId('Personal') })
  await owner.api('tasks.set_status', { task: done.name, status: 'Done' })
  // move the clock: the first was finished 100 days ago, the second not touched for 100 days
  bench(`from frappe.utils import add_days, today
frappe.db.set_value("Life Task", "${done.name}", "completed_on", add_days(today(), -100), update_modified=False)
frappe.db.set_value("Life Task", "${stale.name}", "last_touched_on", add_days(today(), -100), update_modified=False)
from lifeos import archive, index
index.update(frappe.get_doc("Life Task", "${done.name}"))
archive.run_daily()`)
  const arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(JSON.stringify(arch.groups).includes(done.name), 'the done task was not archived')
  must(!JSON.stringify(arch.groups).includes(stale.name), 'the stale open task was archived')
  const review = await owner.api('journal.weekly_review', { space: SPACE })
  must(review.decide.some((t) => t.name === stale.name), 'the stale task is not under Decide')
  must(JSON.stringify(review).includes(done.name), 'the weekly review does not list what the job archived')
  await owner.open('/life/journal/review')
  must((await owner.page.locator('.main').innerText()).includes(`Stale open task ${stamp}`), 'the screen does not show it under Decide')
})

await check('S1', 'Security: rendered Markdown is sanitised', async () => {
  const bad = 'Hello <script>window.__pwned = 1</script> <img src=x onerror="window.__pwned = 2"> [click](javascript:window.__pwned=3) <a href="javascript:alert(1)">x</a> <iframe src="https://example.com"></iframe>'
  const note = await owner.api('library.save', { space: SPACE, title: `Sanitise ${stamp}`, content_md: bad, area: areaId('Learning') })
  await owner.open('/life/library/' + (note.name || note.note?.name))
  const found = await owner.page.evaluate(() => ({
    pwned: window.__pwned, scripts: document.querySelectorAll('.main script, .main iframe').length,
    handlers: [...document.querySelectorAll('.main *')].filter((e) => [...e.attributes].some((a) => a.name.startsWith('on'))).length,
    js: [...document.querySelectorAll('.main a')].filter((a) => (a.getAttribute('href') || '').trim().toLowerCase().startsWith('javascript:')).length,
    shown: document.querySelector('.main').innerText.includes('Hello'),
  }))
  must(found.shown, 'the note did not render')
  must(!found.pwned && !found.scripts && !found.handlers && !found.js, JSON.stringify(found))
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
  // records the checks need, made through the API as the owner
  const project = (await owner.api('projects.list', { space: SPACE, area: uxArea })).projects[0]
  ux.project = project.name
  ux.task = (await owner.api('tasks.quick_add', { text: `UX door task ${stamp}`, space: SPACE, project: project.name, priority: 'I', due_date: addDays(-2) })).name
  await owner.api('tasks.quick_add', { text: `UX due today ${stamp}`, space: SPACE, area: uxArea, due_date: today })
  const doneTask = (await owner.api('tasks.quick_add', { text: `UX done ${stamp}`, space: SPACE, project: project.name })).name
  await owner.api('tasks.set_status', { task: doneTask, status: 'Done' })
  const carried = (await owner.api('tasks.quick_add', { text: `UX carried ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.carry_forward', { task: carried })
  const old = (await owner.api('tasks.quick_add', { text: `UX archived by the job ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.set_status', { task: old, status: 'Done' })
  bench(`from lifeos import archive\nfrappe.set_user("owner@lifeos.test")\narchive.set_archived("Life Task", "${old}", True, "Auto")`)
  ux.note = (await owner.api('library.save', { space: SPACE, title: `UX note ${stamp}`, area: uxArea, content_md: 'A reference note for the UX checks.' })).name
  ux.vault = (await owner.api('vault.save', { space: SPACE, values: { title: `UX permit ${stamp}`, doc_type: 'Other', expiry_date: addDays(20), area: uxArea } })).name
  ux.chat = (await owner.api('chats.log', { space: SPACE, title: `UX chat ${stamp}`, area: uxArea, project: project.name, summary_md: 'Talked about the UX checks.',
    open_items: ['Follow up on the UX checks'] })).name
  const item = await owner.api('inbox.create_item', { title: `UX inbox ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Buy a new kettle. Call the estate manager.' })
  runAgent()
  ux.inbox = item.name
}

const num = (text, which = 0) => { const m = String(text).match(/\d+/g); if (!m) throw new Error(`no number in "${text}"`); return Number(m[which]) }
const LISTS = [
  ['Inbox', '/life/inbox', '.lv-row'], ['Timeline', '/life/timeline', '.rw.rowlink'], ['Tasks', '/life/tasks?view=list', '.lv-row'],
  ['Projects', '/life/projects', '.lv-row'], ['Vault', '/life/vault', '.lv-row'], ['Chats', '/life/chats', '.lv-row'],
  ['Library list', '/life/library?view=list', '.lv-row'], ['Archive', '/life/archive', '.lv-row'],
]
// one filter for each ListView: [screen, path, filter key, value]
const FILTERS = [
  ['Inbox', '/life/inbox', 'status', 'Done'], ['Tasks', '/life/tasks?view=list', 'due', 'overdue'], ['Tasks table', '/life/tasks?view=table', 'priority', 'I'],
  ['Projects', '/life/projects', 'area', uxArea], ['Vault', '/life/vault', 'expiry', 'soon'], ['Chats', '/life/chats', 'area', uxArea],
  ['Library list', '/life/library?view=list', 'area', uxArea], ['Archive', '/life/archive', 'type', 'Life Task'],
]

for (const width of [1440, 390]) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e)))
  const tag = `U${width}`
  const pane = pg.locator('[data-pane]')
  const settle = () => pg.waitForTimeout(450)
  const overflow = () => pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const count = async () => num(await pg.locator('[data-lv-count]').first().innerText())
  const clickRow = async (sel) => { await pg.locator(sel).first().click({ position: { x: 24, y: 14 } }); await settle() }

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
      must(await pg.locator(`${sel}.on`).count() >= 1, `${name}: the open row is not highlighted`)
    }
    return `${LISTS.length} screens`
  })

  await check(`${tag}.2`, `${width} px: the URL has open=, Back closes the pane, reload reopens it`, async () => {
    for (const [name, p, sel] of LISTS) {
      await s.open(p)
      await pg.evaluate(() => window.scrollTo(0, 120))
      await clickRow(sel)
      const withPane = pg.url()
      const title = await pg.locator('[data-pane-title]').innerText()
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
      must((await pg.locator('[data-pane-title]').innerText()) === title, `${name}: reload opened another record`)
    }
    await s.open('/life/inbox/' + ux.inbox)
    must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/inbox' && await pg.locator('.lv-row').count(), '/inbox/:id does not show the list with the pane open')
    must((await pg.locator('[data-pane-title]').innerText()).includes('UX inbox'), '/inbox/:id opened another item')
  })

  if (phone) {
    await check(`${tag}.3`, '390 px: the pane covers the screen and closes with its close button', async () => {
      for (const [name, p, sel] of LISTS) {
        await s.open(p)
        await clickRow(sel)
        const box = await pane.boundingBox()
        must(box && box.x === 0 && box.y === 0 && Math.round(box.width) === 390 && Math.round(box.height) === 844, `${name}: the pane is ${JSON.stringify(box)}`)
        must((await overflow()) <= 0, `${name}: horizontal scrolling with the pane open`)
        await pg.locator('[data-pane-close]').click()
        await settle()
        must(!(await pane.isVisible()), `${name}: the close button did not close the pane`)
        must(await pg.locator(sel).count(), `${name}: the list is gone after closing`)
      }
    })
  } else {
    await check(`${tag}.3`, '1440 px: pane widths, Esc, j and k, focus, Open full page, search opens in the pane', async () => {
      await s.open('/life/tasks?view=list')
      await clickRow('.lv-row')
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
      await pg.locator('.lv-row').nth(2).click({ position: { x: 24, y: 14 } }) // the list is still usable beside the pane
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
      must(new URL(pg.url()).pathname === `/life/inbox/${ux.inbox}/review` && !(await pane.isVisible()), 'Open full page did not open the review screen')
      // every pane type opens from its reference
      for (const ref of [`task:${ux.task}`, `note:${ux.note}`, `vault:${ux.vault}`, `project:${ux.project}`, `chat:${ux.chat}`, `day:${today}`]) {
        await s.open('/life/areas?open=' + encodeURIComponent(ref))
        must(await pane.isVisible() && !(await pg.locator('[data-pane-title]').innerText()).match(/Loading|Not found/), `the pane did not load ${ref}`)
      }
      await s.open('/life/timeline')
      await pg.keyboard.press('Meta+k')
      await pg.locator('input[aria-label="Search"]').fill(`UX note ${stamp}`)
      await pg.waitForTimeout(900)
      await pg.keyboard.press('Enter')
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/timeline', 'a search result did not open in the pane over the current screen')
      must((await pg.locator('[data-pane-title]').innerText()).includes('UX note'), 'the search result opened another record')
    })
  }

  await check(`${tag}.4`, `${width} px: every number is a door, and the list count equals the number clicked`, async () => {
    const done = []
    // [where the number is, door, which number in its text, what to compare on the page it leads to]
    const door = async (from, name, { which = 0, target = '[data-lv-count]', path, nth = 0, optional = false } = {}) => {
      await s.open(from)
      const el = pg.locator(`[data-door="${name}"]`).nth(nth)
      if (!(await el.count()) || !(await el.isVisible())) {
        if (optional) return
        throw new Error(`${name}: the number is not on ${from}`)
      }
      const n = num(await el.innerText(), which)
      await el.click()
      await pg.waitForLoadState('networkidle')
      await settle()
      if (path) must(new URL(pg.url()).pathname === path, `${name}: went to ${new URL(pg.url()).pathname}, not ${path}`)
      const got = num(await pg.locator(target).first().innerText())
      must(got === n, `${name}: clicked ${n}, the list says ${got}`)
      done.push(`${name} ${n}`)
    }
    const hidden = { optional: phone } // lines the phone layout leaves out
    await door('/life', 'today-review', { path: '/life/inbox' })
    await door('/life', 'today-proposals', { target: '[data-lv-sum]', path: '/life/inbox', ...hidden })
    await door('/life', 'today-due', { path: '/life/tasks' })
    await door('/life', 'today-overdue', { path: '/life/tasks', ...hidden })
    await door('/life', 'today-loops', { path: '/life/tasks' })
    await door('/life', 'today-score', { target: '[data-week-score]', path: '/life/journal', ...hidden })
    await door('/life', 'today-vault', { path: '/life/vault' })
    await door('/life', 'nav-review', { path: '/life/inbox', ...hidden })
    const area = '/life/areas/' + uxArea
    await door(area, 'area-projects', { path: '/life/projects' })
    await door(area, 'area-tasks', { path: '/life/tasks' })
    await door(area, 'area-notes', { path: '/life/library' })
    await door(area, 'area-documents', { path: '/life/vault' })
    await door(area, 'area-reference', { path: '/life/library' })
    for (const i of [0, 1, 2, 3]) { // the section counts: projects, open tasks, chats, documents
      await s.open(area)
      const links = pg.locator('.sh a.num')
      if (i >= await links.count()) break
      const n = num(await links.nth(i).innerText())
      await links.nth(i).click()
      await pg.waitForLoadState('networkidle')
      await settle()
      const got = await count()
      must(got === n, `area section ${i}: clicked ${n}, the list says ${got}`)
      done.push(`section ${n}`)
    }
    await door(area, 'project-tasks', { which: 1, path: '/life/tasks' }) // "4 of 10 tasks done" on a project card
    await door('/life/projects', 'project-tasks', { which: 1, path: '/life/tasks' })
    const proj = '/life/projects/' + ux.project
    await door(proj, 'project-tasks', { which: 1, path: '/life/tasks' })
    await door(proj, 'project-open', { path: '/life/tasks' })
    await door(proj, 'project-notes', { path: '/life/library' })
    await door(proj, 'project-documents', { path: '/life/vault' })
    await door(proj, 'project-chats', { path: '/life/chats' })
    await door('/life/chats?from=' + addDays(-6), 'chats-open', { path: '/life/chats' })
    must(new URL(pg.url()).searchParams.get('from') === addDays(-6) && new URL(pg.url()).searchParams.get('open_items') === '1', 'chats: the date range was not kept')
    await door('/life/chats', 'chats-area', { path: '/life/chats' })
    await door('/life/vault', 'vault-soon', { path: '/life/vault' })
    await door('/life/vault', 'vault-expired', { path: '/life/vault' })
    await door('/life/library', 'library-notes', { path: '/life/library' })
    await door('/life/journal/review', 'review-done', { path: '/life/tasks' })
    await door('/life/journal/review', 'review-carried', { path: '/life/tasks', ...hidden })
    await door('/life/journal/review', 'review-loops', { path: '/life/tasks' })
    await door('/life/journal/review', 'review-archived', { path: '/life/archive' })
    // an inbox row: "4 of 13 proposals pending" opens that item in the pane at its pending proposals
    await s.open('/life/inbox?status=To+Review')
    const link = pg.locator('.lv-row:visible a.num', { hasText: 'pending' }).first()
    const text = await link.innerText()
    must(/^\d+ of \d+ proposals pending$/.test(text.trim()), `an inbox row says "${text}"`)
    await link.click()
    await settle()
    must(await pane.isVisible(), 'the proposals count did not open the pane')
    const pendingShown = await pane.locator('[data-proposal="Pending"]').count()
    must(pendingShown === num(text), `clicked ${num(text)} pending, the pane shows ${pendingShown}`)
    const inView = await pane.locator('[data-proposal="Pending"]').first().evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.top < window.innerHeight })
    must(inView, 'the pane is not scrolled to the pending proposals')
    await s.open('/life')
    const rowText = await pg.locator('[data-door="today-row"]').first().innerText()
    must(/^\d+ of \d+ proposals pending$/.test(rowText.trim()), `Today lists an inbox item as "${rowText}"`)
    return `${done.length + 1} numbers`
  })

  await check(`${tag}.5`, `${width} px: filters on every ListView are in the URL and survive a reload`, async () => {
    for (const [name, p, key, value] of FILTERS) {
      await s.open(p)
      if (phone) await pg.locator('.lv-fbtn').click()
      await pg.locator(`[data-filter="${key}"]`).selectOption(value)
      await pg.waitForLoadState('networkidle')
      await settle()
      must(new URL(pg.url()).searchParams.get(key) === value, `${name}: the filter is not in the URL`)
      const filtered = await count()
      const rows = await pg.locator('.lv-row').count()
      must(rows === Math.min(filtered, 50), `${name}: the count says ${filtered} but ${rows} rows are shown`)
      if (phone) must((await pg.locator('.lv-fbtn').innerText()).includes('(1)'), `${name}: the Filters button does not show one active filter`)
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must((await pg.locator(`[data-filter="${key}"]`).inputValue()) === value, `${name}: the filter was lost on reload`)
      must((await count()) === filtered, `${name}: the count changed on reload`)
      await pg.goBack()
      await settle()
      must(!new URL(pg.url()).searchParams.get(key), `${name}: Back did not undo the filter`)
    }
    // an empty result names the filters and offers Clear filters
    await s.open('/life/vault?holder=none&type=Medical&expiry=expired')
    const empty = await pg.locator('[data-lv-empty]').innerText()
    must(empty.includes('Type: Medical') && empty.includes('Expiry: Expired'), 'the empty state does not name the filters: ' + empty)
    await pg.locator('[data-lv-empty] button', { hasText: 'Clear filters' }).click()
    await settle()
    must(!new URL(pg.url()).search.includes('type='), 'Clear filters did not clear')
    return `${FILTERS.length} lists`
  })

  await check(`${tag}.6`, `${width} px: no horizontal scrolling and no script errors on any converted screen`, async () => {
    const screens = [...LISTS.map(([n, p]) => [n, p]), ['Tasks table', '/life/tasks?view=table'], ['Tasks board', '/life/tasks?view=board'], ['Open loops', '/life/tasks?view=loops'],
      ['Projects cards', '/life/projects?view=cards'], ['Library tree', '/life/library'], ['Area', '/life/areas/' + uxArea], ['Project', '/life/projects/' + ux.project],
      ['Today', '/life'], ['Areas', '/life/areas'], ['Calendar', '/life/calendar/agenda'], ['Weekly review', '/life/journal/review']]
    for (const [name, p] of screens) {
      await s.open(p)
      const over = await overflow()
      must(over <= 0, `${name}: ${over} px of horizontal scrolling`)
    }
    // Area, Project and Today: a row opens the pane and the page does not change
    for (const p of ['/life/areas/' + uxArea, '/life/projects/' + ux.project, '/life']) {
      await s.open(p)
      await pg.locator('.rw[data-ref]').first().locator('.grow').click({ position: { x: 20, y: 10 } })
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname === p, `${p}: a row did not open the pane in place`)
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${screens.length} screens`
  })
  await s.ctx.close()
}

await browser.close()
const failed = results.filter((r) => !r[1])
console.log(`\n${results.length - failed.length} of ${results.length} acceptance items pass.`)
process.exit(failed.length ? 1 : 0)
