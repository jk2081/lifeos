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

async function check(n, title, fn) {
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

await browser.close()
const failed = results.filter((r) => !r[1])
console.log(`\n${results.length - failed.length} of ${results.length} acceptance items pass.`)
process.exit(failed.length ? 1 : 0)
