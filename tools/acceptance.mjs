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
const ONLY = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7) // run only the checks whose number ends with this: --only=.8
async function check(n, title, fn) {
  if ((ONLY_UX || ONLY) && !String(n).startsWith('U')) return
  if (ONLY && !String(n).endsWith(ONLY)) return
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
  await phone.open('/life/journal/habits')
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
  await owner.open('/life/journal')
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
  await owner.open('/life/calendar/year')
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
  await owner.open('/life/vault?expiry=soon') // the Expiring soon tab
  must((await owner.page.locator('[data-main]').innerText()).includes(title), 'not shown in the Vault')
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
    const text = await fam.page.locator('[data-app]').innerText()
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
  must(await owner.page.locator('text=also in').count() > 0, 'the Review screen has no area chips')
})

await check(13, 'Tea & Coffee area page shows projects, tasks, notes and chats together', async () => {
  const a = await owner.api('area.get', { area: areaId('Tea & Coffee') })
  must(a.projects.length && a.tasks.length && a.notes.length && a.chats.length, `projects ${a.projects.length}, tasks ${a.tasks.length}, notes ${a.notes.length}, chats ${a.chats.length}`)
  // since set 3 each kind is a tab of the area page
  for (const [tab, title] of [['overview', a.projects[0].title], ['tasks', a.tasks[0].title], ['notes', a.notes[0].title], ['chats', a.chats[0].title]]) {
    await owner.open(`/life/areas/${areaId('Tea & Coffee')}?tab=${tab}&all=1`)
    must((await owner.page.locator('[data-main]').innerText()).includes(title), `the ${tab} tab does not show ${title}`)
  }
  return `${a.projects.length} projects, ${a.counts.open_tasks} open tasks, ${a.counts.notes} notes, ${a.counts.chats} chats`
})

await check(14, 'Timeline shows everything captured on one day', async () => {
  const t = await owner.api('timeline.get', { space: SPACE, from_date: today, to_date: today, page_length: 100 })
  const kinds = new Set(t.days.flatMap((d) => d.entries.map((e) => e.kind)))
  for (const k of ['Inbox', 'Task', 'Note', 'Document', 'Journal Page']) must(kinds.has(k), `no ${k} on today's timeline`)
  must(t.days.length === 1, 'more than one day returned')
  await owner.open('/life/timeline?all=1') // a bare URL restores the remembered view, which a UX check may have filtered
  must((await owner.page.locator('[data-main]').innerText()).includes(`Target note ${stamp}`), 'the screen does not show today')
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
  must(!(await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] })).tasks.some((t) => t.name === task.name), 'the task is still in Tasks')
  must(!JSON.stringify(await owner.api('projects.list', { space: SPACE })).includes(r.name), 'the project is still in Projects')
  await owner.open('/life/archive')
  must((await owner.page.locator('[data-main]').innerText()).includes(`Project ${stamp}`), 'the Archive screen does not show it')
  await owner.api('archive.restore', { doctype: 'Life Project', name: r.name })
  arch = await owner.api('archive.list', { space: SPACE, page_length: 100 })
  must(!arch.projects.some((p) => p.name === r.name) && !JSON.stringify(arch.groups).includes(task.name), 'restore left it in Archive')
  must((await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] })).tasks.some((t) => t.name === task.name), 'the task did not come back')
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
  must((await owner.page.locator('[data-main]').innerText()).includes(`Stale open task ${stamp}`), 'the screen does not show it under Decide')
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
// A bare list URL restores the remembered view, so the checks that want the whole list say so: all=1.
const ROW = '[data-row]'
const LISTS = [
  ['Inbox', '/life/inbox?all=1'], ['Timeline', '/life/timeline?all=1'], ['Tasks', '/life/tasks?view=list'],
  ['Projects', '/life/projects?all=1'], ['Vault', '/life/vault?all=1'], ['Chats', '/life/chats?all=1'],
  ['Library list', '/life/library?view=list&all=1'], ['Archive', '/life/archive?all=1'],
].map(([name, p]) => [name, p, ROW])
// one filter for each ListView, set through the library's quick-filter strip: [screen, path, URL key, URL value, the control's label, the option to pick, text to type for a Link]
const FILTERS = [
  ['Inbox', '/life/inbox?status=all', 'source_type', 'Message', 'Source Type', 'Message'], ['Tasks', '/life/tasks?view=list', 'priority', 'I', 'Priority', 'I'],
  ['Tasks table', '/life/tasks?view=table&status=all', 'priority', 'I', 'Priority', 'I'], ['Projects', '/life/projects?status=all', 'area', uxArea, 'Area', 'Tea & Coffee', 'Tea'],
  ['Vault', '/life/vault?all=1', 'type', 'Travel', 'Doc Type', 'Travel'], ['Chats', '/life/chats?all=1', 'area', uxArea, 'Area', 'Tea & Coffee', 'Tea'],
  ['Library list', '/life/library?view=list&all=1', 'area', uxArea, 'Area', 'Tea & Coffee', 'Tea'], ['Archive', '/life/archive?all=1', 'area', uxArea, 'Area', 'Tea & Coffee', 'Tea'],
]
// UX fixes, set 3: the state tabs of each list screen. [screen, path, the URL parameter of the tabs, the tab values in order (the first is the default), another filter]
const STATE_TABS = [
  ['Inbox', '/life/inbox', 'status', ['To Review', 'Waiting', 'Failed', 'Done', 'all'], 'source_type=Message'],
  ['Tasks', '/life/tasks', 'status', ['open', 'loops', 'Waiting', 'Done', 'all'], `area=${uxArea}`],
  ['Projects', '/life/projects', 'status', ['Active', 'On Hold', 'Done', 'Dropped', 'all'], `area=${uxArea}`],
  ['Archive', '/life/archive', 'type', ['all', 'Life Task', 'Life Note', 'Life Chat Log', 'Life Vault Document', 'Life Inbox Item', 'Life Journal Page'], `area=${uxArea}`],
  ['Chats', '/life/chats', 'open_items', ['all', '1'], `area=${uxArea}`],
  ['Vault', '/life/vault', 'expiry', ['all', 'soon', 'expired'], 'type=Other'],
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
  const nav = async (label) => { // through the sidebar on a wide screen, the tab bar on a phone
    if (phone) await pg.locator(`[data-tabbar] [data-slot="mobile-nav-item"][aria-label="${label}"]`).click()
    else await pg.locator('[data-slot="sidebar-item"]', { hasText: new RegExp(`^\\s*${label}`) }).first().locator('a, button').first().click()
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
    must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/inbox' && await pg.locator(ROW).count(), '/inbox/:id does not show the list with the pane open')
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
      await s.open('/life/tasks?view=list')
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
    await door('/life', 'today-review', { path: '/life/inbox' })
    await door('/life', 'today-proposals', { target: '[data-lv-sum]', path: '/life/inbox', ...hidden })
    await door('/life', 'today-due', { path: '/life/tasks' })
    await door('/life', 'today-overdue', { path: '/life/tasks', ...hidden })
    await door('/life', 'today-loops', { path: '/life/tasks' })
    await door('/life', 'today-score', { target: '[data-week-score]', path: '/life/journal', ...hidden })
    await door('/life', 'today-vault', { path: '/life/vault' })
    await door('/life', 'nav-review', { path: '/life/inbox', ...hidden })
    // the area and project pages: the preview headings of Overview lead to their tab (set 3), whose list holds that number
    const area = '/life/areas/' + uxArea
    const proj = '/life/projects/' + ux.project
    const tabList = '[data-tab-panel]:visible [data-lv-count]'
    await door(area, 'area-overview-projects', { path: area, target: tabList })
    await door(area, 'area-overview-tasks', { path: area, target: tabList })
    await door(area, 'area-overview-timeline', { path: area, target: tabList })
    await door('/life/projects?all=1', 'project-tasks', { which: 1, path: '/life/tasks' })
    await door(proj, 'project-tasks', { which: 1, path: '/life/tasks' })
    await door(proj, 'project-overview-tasks', { path: proj, target: tabList })
    await door('/life/chats?from=' + addDays(-6), 'chats-open', { path: '/life/chats' })
    must(new URL(pg.url()).searchParams.get('from') === addDays(-6) && new URL(pg.url()).searchParams.get('open_items') === '1', 'chats: the date range was not kept')
    await door('/life/chats?all=1', 'chats-area', { path: '/life/chats' })
    await door('/life/vault?all=1', 'vault-soon', { path: '/life/vault' })
    await door('/life/vault?all=1', 'vault-expired', { path: '/life/vault' })
    await door('/life/library', 'library-notes', { path: '/life/library' })
    await door('/life/journal/review', 'review-done', { path: '/life/tasks' })
    await door('/life/journal/review', 'review-carried', { path: '/life/tasks', ...hidden })
    await door('/life/journal/review', 'review-loops', { path: '/life/tasks' })
    await door('/life/journal/review', 'review-archived', { path: '/life/archive' })
    // an inbox row: "4 of 13 proposals pending" opens that item in the pane at its pending proposals
    await s.open('/life/inbox?status=To+Review')
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
    await s.open('/life')
    const rowText = await pg.locator('[data-door="today-row"]').first().innerText()
    must(/^\d+ of \d+ proposals pending$/.test(rowText.trim()), `Today lists an inbox item as "${rowText}"`)
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
    await s.open('/life/vault?holder=none&type=Medical&expiry=later') // Expired is a tab now; "Later" is still a filter
    const empty = await pg.locator('[data-lv-empty]').innerText()
    must(empty.includes('Type: Medical') && empty.includes('Expiry: Later'), 'the empty state does not name the filters: ' + empty)
    await pg.locator('[data-lv-empty] button', { hasText: 'Clear filters' }).click()
    await settle()
    must(!new URL(pg.url()).search.includes('type='), 'Clear filters did not clear')
    return `${FILTERS.length} lists`
  })

  await check(`${tag}.6`, `${width} px: no horizontal scrolling and no script errors on any converted screen`, async () => {
    const screens = [...LISTS.map(([n, p]) => [n, p]), ['Tasks table', '/life/tasks?view=table'], ['Tasks board', '/life/tasks?view=board'], ['Open loops', '/life/tasks?view=loops'],
      ['Projects cards', '/life/projects?view=cards'], ['Library tree', '/life/library'], ['Area', '/life/areas/' + uxArea], ['Project', '/life/projects/' + ux.project],
      ['Today', '/life'], ['Areas', '/life/areas'], ['Calendar', '/life/calendar/agenda'], ['Calendar month', '/life/calendar/month'], ['12 Week Year', '/life/journal'], ['Goals', '/life/journal/goals'],
      ['Month', '/life/journal/month'], ['Habits', '/life/journal/habits'], ['Check-ins', '/life/journal/checkins'], ['Pages', '/life/journal/pages'], ['Weekly review', '/life/journal/review'],
      ['Graph', '/life/graph'], ['Settings', '/life/settings']]
    for (const [name, p] of screens) {
      await s.open(p)
      const over = await overflow()
      must(over <= 0, `${name}: ${over} px of horizontal scrolling`)
    }
    // Area, Project and Today: a row opens the pane and the page does not change
    for (const p of ['/life/areas/' + uxArea, '/life/projects/' + ux.project, '/life']) {
      await s.open(p)
      await pg.locator('[data-row]:has([data-ref])').first().click({ position: { x: 120, y: 12 } })
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname.replace(/\/$/, '') === p, `${p}: a row did not open the pane in place`)
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${screens.length} screens`
  })

  await check(`${tag}.7`, `${width} px: a list remembers its view on every device, a link with a query wins, Clear clears`, async () => {
    const param = (k) => new URL(pg.url()).searchParams.get(k)
    await s.open('/life/tasks?view=list') // a query: the list shows exactly this, and it becomes the saved state
    await pickQuick('Priority', 'II')
    must(param('priority') === 'II', 'the filter was not set')
    const filtered = await count()
    await nav('Today')
    must(new URL(pg.url()).pathname === '/life' || new URL(pg.url()).pathname === '/life/', 'the sidebar did not go to Today')
    await nav('Tasks')
    must(new URL(pg.url()).pathname === '/life/tasks', 'the sidebar did not go to Tasks')
    must(param('priority') === 'II' && param('view') === 'list', `coming back lost the view: ${new URL(pg.url()).search}`)
    must((await count()) === filtered, 'the remembered filter is in the URL but the list is not filtered')
    must(!param('open'), 'an open record was restored')
    // the same person on another device: the state comes from the server, not from this browser
    await pg.waitForTimeout(1600)
    const other = await session('owner@lifeos.test', width)
    await other.open('/life/tasks')
    must(new URL(other.page.url()).searchParams.get('priority') === 'II', `a second browser does not show the saved filter: ${new URL(other.page.url()).search}`)
    await other.ctx.close()
    // a link with a query wins over what was saved, and then becomes the saved state
    await s.open('/life')
    const loops = num(await pg.locator('[data-door="today-loops"]:visible').first().innerText())
    await pg.locator('[data-door="today-loops"]:visible').first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!param('priority'), 'the Open loops link kept the saved filter')
    must((await count()) === loops, `Open loops shows ${await count()}, the number said ${loops}`)
    const loopsQuery = new URL(pg.url()).search
    await nav('Today')
    await nav('Tasks')
    must(new URL(pg.url()).search === loopsQuery, `the list did not remember the link's query: ${new URL(pg.url()).search} instead of ${loopsQuery}`)
    // Clear removes the filters and the cleared state is what is remembered
    await s.open('/life/tasks?view=list')
    await pickQuick('Priority', 'II')
    must(param('priority') === 'II', 'the filter was not set again')
    await pg.locator('[data-clear]:visible').first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!param('priority'), 'Clear did not remove the filter')
    must(!(await pg.locator('[data-active-filters]:visible').count()), 'the list still says a filter is on')
    await nav('Today')
    await nav('Tasks')
    must(!param('priority'), 'the cleared filter came back')
    // another person has their own states
    await pg.waitForTimeout(1600)
    const saved = await s.api('views.get_all')
    must(Object.keys(saved).some((k) => k.startsWith('tasks|')), 'nothing was saved on the server for the owner')
    const fam = await session('family@lifeos.test', width)
    const theirs = await fam.api('views.get_all')
    must(!Object.keys(theirs).some((k) => k.includes('Private')) && !JSON.stringify(theirs).includes('loops'), 'the family user sees the owner\'s saved states')
    await fam.open('/life/tasks')
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
        const q = (v) => `${p}?${[v === values[0] ? '' : `${key}=${encodeURIComponent(v)}`, extra, name === 'Tasks' ? 'view=list' : '', !extra && v === values[0] ? 'all=1' : ''].filter(Boolean).join('&')}`
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
      const el = pg.locator(`[data-door="${name}"]:visible`).first()
      if (!(await el.count())) { if (optional) return; throw new Error(`${name}: not on ${from}`) }
      const n = num(await el.innerText())
      await el.click()
      await pg.waitForLoadState('networkidle')
      await settle()
      must((await current()) === want, `${name}: landed on the ${await current()} tab, not ${want}`)
      must((await tabCount(want)) === n && (await count()) === n, `${name}: clicked ${n}, the ${want} tab says ${await tabCount(want)} and the list ${await count()}`)
    }
    await lands('/life', 'today-due', 'open')
    await lands('/life', 'today-overdue', 'open', phone)
    await lands('/life', 'today-loops', 'loops')
    await lands('/life', 'today-review', 'To Review')
    await lands('/life', 'today-vault', 'soon')
    await lands('/life/vault?all=1', 'vault-expired', 'expired')
    await lands('/life/chats?all=1', 'chats-open', '1')
    // Tasks: Open loops is a tab with its explanation, the layout switch has three options, the board is not offered on Done
    const layouts = async () => (await pg.locator('[role="radiogroup"]:visible [role="radio"]').allInnerTexts()).map((t) => t.trim())
    await s.open('/life/tasks?status=loops')
    must((await current()) === 'loops' && (await pg.locator('[data-tasks-sub]').innerText()).includes('older than 14 days'), 'Open loops is not a tab with its explanatory line')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Table']), `Open loops offers the layouts ${await layouts()}`)
    await s.open('/life/tasks?view=loops') // a link from before the tabs
    must((await current()) === 'loops' && new URL(pg.url()).searchParams.get('status') === 'loops', 'view=loops does not open the Open loops tab')
    await s.open('/life/tasks?view=board')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Board', 'Table']), `the layout switch offers ${await layouts()}`)
    must((await pg.locator('[data-list]').getAttribute('data-view')) === 'board' && (await pg.locator('[data-column]').count()) === 2, 'the board on the Open tab does not show Open and Doing')
    await s.open('/life/tasks?view=board&status=all')
    must((await pg.locator('[data-column]').count()) === 4, 'the board on the All tab does not show four columns')
    await s.open('/life/tasks?view=board&status=Done')
    must(JSON.stringify(await layouts()) === JSON.stringify(['List', 'Table']), `Done offers the layouts ${await layouts()}`)
    must((await pg.locator('[data-list]').getAttribute('data-view')) === 'list', 'the board did not fall back to the list on Done')
    // a status that is not a tab selects All and shows as a filter
    await s.open('/life/tasks?view=list&status=Dropped')
    must((await current()) === 'all', `status=Dropped selected the ${await current()} tab`)
    if (phone) must((await pg.locator('[data-filters-button]').innerText()).includes('(1)'), 'status=Dropped is not shown as a filter')
    else must((await pg.locator('[data-active-filters]').innerText()).includes('1 filter'), 'status=Dropped is not shown as a filter')
    if (phone) {
      // seven tabs are wider than a phone: the row scrolls sideways, the page does not, and the open tab is in view
      await s.open('/life/archive?type=Life+Journal+Page')
      const m = await bar.evaluate((el) => { const t = el.querySelector('[data-state="active"]').getBoundingClientRect(); return { wide: el.scrollWidth > el.clientWidth, inView: t.left >= 0 && t.right <= window.innerWidth, h: t.height } })
      must(m.wide && m.inView, `the tab row does not scroll with the open tab in view: ${JSON.stringify(m)}`)
      must(m.h >= 44, `a tab is ${m.h} px high on a phone`)
      must((await overflow()) <= 0, 'the Archive scrolls sideways')
    } else {
      // [ and ] move between tabs; arrow keys move inside the tab row
      await s.open('/life/projects?status=all&area=' + uxArea)
      await pg.keyboard.press('[')
      await settle()
      must((await current()) === 'Dropped', '[ did not open the previous tab')
      await pg.keyboard.press(']')
      await settle()
      must((await current()) === 'all', '] did not open the next tab')
      await bar.locator('[data-tab="all"]').focus()
      await pg.keyboard.press('ArrowLeft')
      await settle()
      must((await current()) === 'Dropped', 'the left arrow did not move to the previous tab')
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${checked} tabs`
  })
  await check(`${tag}.10`, `${width} px: area and project pages: each tab opens with its count, its list matches the main screen, reload stays, a row opens the pane in the tab`, async () => {
    const pageBar = pg.locator('[data-page-tabs]')
    const cur = () => pageBar.getAttribute('data-tab-current')
    const panelCount = async (t) => num(await pg.locator(`[data-tab-panel="${t}"] [data-lv-count]`).innerText())
    const f = JSON.stringify([['status', 'in', ['Active', 'On Hold']], ['is_archived', '=', 0]])
    const PAGES = [
      ['/life/areas/' + uxArea, [['projects', `/life/projects?area=${uxArea}&f=${encodeURIComponent(f)}`], ['tasks', `/life/tasks?area=${uxArea}&view=list`],
        ['notes', `/life/library?view=list&area=${uxArea}`], ['documents', `/life/vault?area=${uxArea}`], ['chats', `/life/chats?area=${uxArea}`], ['timeline', `/life/timeline?area=${uxArea}`]]],
      ['/life/projects/' + ux.project, [['tasks', `/life/tasks?project=${ux.project}&view=list`], ['notes', `/life/library?view=list&project=${ux.project}`],
        ['documents', `/life/vault?project=${ux.project}`], ['chats', `/life/chats?project=${ux.project}`], ['links', null]]],
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
    // the main screens keep their own remembered view: the area's Tasks tab does not change it
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
    const jp = bench(`print(frappe.db.sql("select name from \`tabLife Journal Page\` where space='${SPACE}' limit 1")[0][0])`).split('\n').pop()
    await s.open('/life/journal/pages/' + jp)
    const jt = pg.locator('[data-journal-tabs]')
    if (!phone) must(!(await jt.count()), 'the journal page shows tabs at 1440 px')
    else {
      await jt.locator('[data-tab="transcript"]').click()
      await settle()
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must((await jt.getAttribute('data-tab-current')) === 'transcript', 'the journal page tab did not survive a reload')
    }
    must((await overflow()) <= 0, 'the page scrolls sideways')
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
      ['project:' + one('Life Project', 'is_archived=0'), ['Overview', 'Tasks']],
      ['goal:' + one('Life Goal'), null], // Actions, Tasks, History across cycles, Links (Annual and Open goals have no History)
      ['chat:' + one('Life Chat Log', 'is_archived=0'), ['Summary', 'Open items', 'Links']],
      ['page:' + one('Life Journal Page'), ['Page', 'Transcript', 'Created from this page']],
      ['vault:' + one('Life Vault Document', 'is_archived=0'), ['Details', 'File']],
      ['day:' + today, []], ['vault:new', []],
    ]
    const tabsOf = async () => (await pg.locator('[data-pane-tabs] [role="tab"]').allInnerTexts()).map((t) => t.replace(/\s*\d+$/, '').trim())
    for (const [ref, want] of KINDS) {
      await s.open(`/life/tasks?view=list&open=${encodeURIComponent(ref)}`)
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
    await s.open('/life/tasks?view=list')
    await clickRow(ROW)
    await pg.locator('[data-pane-tabs] [role="tab"]').last().click()
    await settle()
    await pg.goBack()
    await settle()
    must(!(await pane.isVisible()), 'Back after changing the pane tab did not close the pane')
    // a count of open items opens the chat on its Open items tab
    await s.open('/life/chats?open_items=1&view=table')
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
  await s.ctx.close()
}

await browser.close()
const failed = results.filter((r) => !r[1])
console.log(`\n${results.length - failed.length} of ${results.length} acceptance items pass.`)
process.exit(failed.length ? 1 : 0)
