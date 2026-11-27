// Today: Day, Week, Month and Year, the lists' counts, rhythm banners, Reset and the first-run guide.
// Checks are numbered TODAY.<n> in the order they appear here; `node tools/acceptance.mjs --only=TODAY` runs this file's checks.
import { DAY_NAMES, PDF, SPACE, WIDTHS, addDays, areaId, areas, base, bench, browser, chatOff, chatOn, check, must, nextWeekday, owner, path, pathOf, plusDays, session, stamp, today } from './context.mjs'
import { ROW, num, ux, uxArea, uxKit } from './ux.mjs'
const DAY_SHORT = (d) => DAY_NAMES[new Date(d + 'T12:00:00Z').getUTCDay()].slice(0, 3)

await check('TODAY.1', 'Log in, open /life, Today is filled from seed data', async () => {
  const guest = await browser.newContext()
  const res = await guest.request.get(base + '/life', { maxRedirects: 0 })
  must(res.status() === 302 && (res.headers().location || '').includes('/login'), 'a guest is not sent to login')
  must((await guest.request.get(base + '/api/method/lifeos.api.today.get')).status() >= 400, 'a guest can call the API')
  await guest.close()
  await owner.open('/life?mode=goals') // the habits card is Goals' (issue 135)
  const text = await owner.page.locator('[data-main]').innerText()
  must(/Week \d+ of 12/.test(text), 'no 12 Week Year week on Today')
  await owner.page.locator('[data-card="habits"]').waitFor({ timeout: 10000 })
  const t = await owner.api('today.get', { space: SPACE })
  must(text.includes('Habits') && t.habits.length && (await owner.page.locator('[data-card="habits"] [data-stat-value]').innerText()).includes(`of ${t.habits.length}`), 'habits are missing on Today')
  must(t.cycle, 'today.get has no cycle')
  return `week ${t.cycle.week}, ${t.habits.length} habits, ${t.tasks.due} tasks due`
})

await check('TODAY.2', 'Add a birthday and see it on the calendar this year and next', async () => {
  const title = `Birthday ${stamp}`
  await owner.api('calendar.add_important_date', { space: SPACE, title, day: 12, month: 12, kind: 'Birthday' })
  for (const year of [2026, 2027]) {
    const cal = await owner.api('calendar.get', { space: SPACE, from_date: `${year}-12-01`, to_date: `${year}-12-31` })
    must(JSON.stringify(cal.items).includes(title), 'not on the calendar in ' + year)
    const y = await owner.api('calendar.year', { space: SPACE, year })
    must(JSON.stringify(y).includes(title), 'not on the year view in ' + year)
  }
  const plan = await owner.api('calendar.year_plan', { space: SPACE })
  must(JSON.stringify(plan.key_weeks).includes(title), 'not among the key dates of the year view')
})

await check('TODAY.3', 'Vault document expiring in 30 days shows on its day of the month calendar', async () => {
  const title = `Passport ${stamp}`
  await owner.api('vault.save', { space: SPACE, values: { title, doc_type: 'Travel', expiry_date: addDays(30), number_last4: '4821', area: areaId('Money & Legal') } })
  const refused = await owner.api('vault.save', { space: SPACE, values: { title: 'x', doc_type: 'ID', number_last4: '123456789', area: areaId('Money & Legal') } }, { raw: true })
  must(!refused.ok(), 'a full number was stored')
  const t = await owner.api('today.get', { space: SPACE })
  must(t.coming_up.some((c) => c.kind === 'vault' && c.title === title), 'not in today.get')
  await owner.open(`/life/today/month?mode=calendar&date=${addDays(30)}`) // issue 132: Today's Coming up is gone; the expiry is on the month's calendar, on its day
  await owner.page.locator('[data-month-grid]').waitFor({ timeout: 10000 })
  await owner.page.waitForFunction((t) => document.querySelector('[data-month-grid]')?.innerText.includes(t), title, { timeout: 10000 }).catch(() => {})
  must((await owner.page.locator('[data-month-grid]').innerText()).includes(title), 'not shown on the month calendar')
  // set 6: the Vault's documents are captures of kind Document, marked sensitive, with their expiry
  await owner.open('/life/library/documents?tab=documents&sensitive=1')
  const row = owner.page.locator('[data-row]', { hasText: title }).first()
  must(await row.count(), 'not shown in Library > Captures, Documents')
  must(await row.locator('[data-expiry-badge]').count() && await row.locator('[data-sensitive-lock]').count(), 'the document has no expiry badge or lock')
})

for (const width of WIDTHS) {
  const { S5, count, nav, overflow, pane, pg, phone, s, settle, tag, tap } = await uxKit(width)
  await check('TODAY.4', `${width} px: every number is a door, and the list count equals the number clicked`, async () => {
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

  await check('TODAY.5', `${width} px: Today: no Open band; Day Calendar lists the task due today and never a Someday task`, async () => {
    // an overdue task, a task due today, a parked task due today
    await s.api('tasks.quick_add', { text: S5('overdue'), space: SPACE, area: uxArea, due_date: addDays(-2) })
    await s.api('tasks.quick_add', { text: S5('due today'), space: SPACE, area: uxArea, due_date: today })
    const parked = await s.api('tasks.quick_add', { text: S5('parked'), space: SPACE, area: uxArea, due_date: today })
    await s.api('someday.park', { doctype: 'Life Task', name: parked.name })
    await s.open('/life/today?mode=calendar')
    await pg.locator('[data-day-timeline]').waitFor({ timeout: 10000 })
    must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is still on Today (issue 55)')
    await pg.waitForFunction((t) => document.querySelector('[data-day-timeline]')?.innerText.includes(t), S5('due today'), { timeout: 10000 })
    const text = await pg.locator('[data-day-timeline]').innerText()
    must(!text.includes(S5('parked')), 'a Someday task is on Today')
    must(await pg.locator('[data-next], [data-rail]').count() === 0, 'the old Next list or rail is still on Today')
    return 'due today is on the timeline'
  })

  await check('TODAY.6', `${width} px: counts: every number on Today, Reset, Someday and the sidebar opens a list with exactly that many rows`, async () => {
    let n = 0
    for (const from of ['/life', '/life/settings?tab=data', '/life/goals/someday?all=1']) {
      await s.open(from)
      if (phone && from === '/life/settings?tab=data') { await pg.locator('[role="tab"]', { hasText: 'Inventory' }).first().click(); await settle() }
      const keys = await pg.locator('[data-count-door]:visible').evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute('data-count-key')))])
      // Someday's own numbers are its tab counts, which U.8 clicks; here only the doors on the page (the sidebar's on a wide screen)
      must(keys.length || from.includes('someday') || (phone && from === '/life'), `no counts on ${from}`) // issue 132: Today's own list of counts is gone; a phone has no sidebar
      for (const key of keys) {
        await s.open(from)
        if (phone && from === '/life/settings?tab=data') { await pg.locator('[role="tab"]', { hasText: 'Inventory' }).first().click(); await settle() }
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

  if (!phone) await check('TODAY.7', 'Insights: rules make Stuck, 12 Week Year and Habit insights from seeded data; a dismissed one does not return; a snoozed one returns after its date; at most 12 new a day', async () => {
    bench('frappe.db.delete("Life Insight", {"space": "Private"})')
    // a habit done every day last month and never this month
    bench(`from lifeos.goals import cycles, habits
frappe.set_user("owner@lifeos.test")
h = frappe.get_doc({"doctype": "Life Habit", "space": "Private", "title": "${S5('habit')}"}).insert()
now = frappe.utils.getdate(frappe.utils.today()); prev = frappe.utils.add_months(now, -1)
habits.set_month_habits("Private", prev.year, prev.month, [{"habit": h.name, "days_per_week": 7}])
first, last = cycles.month_bounds(prev.year, prev.month); d = first
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
    await s.api('frappe.client.set_value', { doctype: 'Life Insight', name: stuck.name, fieldname: { status: 'Dismissed', dismiss_reason: 'Not relevant' } })
    await s.api('insights.refresh', { space: SPACE })
    const again = (await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows.filter((r) => r.kind === 'Stuck' && r.evidence.some((e) => ids.includes(e.name)))
    must(!again.length, 'a dismissed insight came back')
    const other = (await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows[0]
    await s.api('frappe.client.set_value', { doctype: 'Life Insight', name: other.name, fieldname: { status: 'Snoozed', snooze_until: addDays(5) } })
    await s.api('insights.refresh', { space: SPACE })
    must((await s.api('insights.list', { space: SPACE, status: 'Snoozed' })).rows.some((r) => r.name === other.name), 'the snoozed insight is not snoozed')
    bench(`frappe.db.set_value("Life Insight", "${other.name}", "snooze_until", frappe.utils.add_days(frappe.utils.today(), -1))`)
    await s.api('insights.refresh', { space: SPACE })
    must((await s.api('insights.list', { space: SPACE, status: 'New', page_length: 100 })).rows.some((r) => r.name === other.name), 'the snoozed insight did not return after its date')
    await s.open('/life/insights')
    must(await pg.locator('[data-insight-row]').count() && await pg.locator('[data-insights-how]').isVisible(), 'the Insights tab shows no insights')
    return [...kinds].join(', ')
  })

  await check('TODAY.8', `${width} px: Reset: each rule batch finds its seeded items; a batch changes exactly those and Undo reverts; one by one with ${phone ? 'the buttons' : 'the keys'}; Delete then Restore from the trash; stuck tasks are the weekly review's Tasks tab`, async () => {
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
    await s.open('/life/settings?tab=data')
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
    await s.open('/life/settings?tab=data')
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
    // the weekly review's second tab, Tasks, lists the stale tasks with Keep, Someday and Drop (issue 72)
    await s.open('/life/today/week?view=review&tab=tasks')
    must(await pg.locator('[data-stale-tasks]').count(), "the weekly review's Tasks tab has no stale tasks list")
    return 'batches, undo, one by one, trash, weekly review'
  })

  if (phone) await check('TODAY.9', '390 px: a rhythm banner shows on Today on its day and Skip hides it', async () => {
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

await check('TODAY.10', "Rhythm banners: the weekly review, Plan your next 12 weeks and Close this cycle each show on Today on their day (the clock moved with at=); Skip hides each until its next occurrence", async () => {
  const pg = owner.page
  const was = (await owner.api('settings.get', { space: SPACE })).settings
  bench(`frappe.db.delete("Life View State", {"user": "owner@lifeos.test", "screen": "rhythm-banners"})`)
  try {
    const info = JSON.parse(bench(`import json
c = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"}, ["name", "start_date"], as_dict=True)
planned = frappe.db.exists("Life Cycle", {"space": "${SPACE}", "status": "Planned", "start_date": (">", c.start_date)})
print(json.dumps({"start": str(c.start_date), "planned": bool(planned)}))`).split('\n').pop())
    must(!info.planned, 'a next cycle is already planned on the acceptance site')
    const review = nextWeekday(was.weekly_review_day || 'Sunday', 1)
    const afterReview = `${String(was.weekly_review_time || '18:00:00').slice(0, 2) === '23' ? '23:59:00' : '23:30:00'}`
    // a day of weeks 11 and 12, in the morning
    const inWeek = (w) => plusDays(info.start, (w - 1) * 7 + 2)
    const CASES = [
      ['review', `${review} ${afterReview}`, 'Your weekly review is ready', '/life/today/week'],
      ['plan-next', `${inWeek(11)} 08:00:00`, 'Plan your next 12 weeks', '/life/goals/cycles'],
      ['close', `${inWeek(12)} 08:00:00`, 'Close this cycle', '/life/goals/cycles'],
    ]
    const done = []
    for (const [key, at, text, to] of CASES) {
      const b = (await owner.api('today.get', { space: SPACE, at })).banner
      must(b && b.key === key && b.text.startsWith(text), `at ${at} today.get gives ${JSON.stringify(b)}, not ${key}`)
      await owner.open(`/life?at=${encodeURIComponent(at)}`)
      const banner = pg.locator(`[data-rhythm-banner][data-banner="${key}"]`)
      must(await banner.isVisible(), `no ${key} banner on Today at ${at}`)
      must((await banner.innerText()).includes(b.text), `the ${key} banner says "${await banner.innerText()}"`)
      // at most one line, above the list
      must((await pg.locator('[data-rhythm-banner]').count()) === 1, 'more than one banner')
      const order = await pg.evaluate(() => { const a = document.querySelector('[data-rhythm-banner]'), o = document.querySelector('[data-day-timeline], [data-dashboard]'); return !!(a && o && (a.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING)) })
      must(order, 'the banner is not above the day')
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
    bench(`frappe.db.delete("Life View State", {"user": "owner@lifeos.test", "screen": "rhythm-banners"})`)
  }
})


// Issue 16: Today > Week, Month and Year. Titles start "I16 " (known to the debris finder).
for (const width of WIDTHS) {
  const tag = `I16.${width}`
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
  // today's own cell and row carry the run's other items and the month cell shows three, so the fixtures go on days that are not today
  const meetDay = monday === today ? plusDays(monday, 1) : monday
  const dueDay = wed === today ? plusDays(monday, 3) : wed
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
ev = frappe.get_doc({"doctype": "Event", "subject": "${meeting}", "starts_on": "${meetDay} 10:00:00", "ends_on": "${meetDay} 11:00:00", "event_category": "Event",
  "event_type": "Public", "life_space": "${SPACE}", "google_calendar_event_id": "fixture-i16-${stamp}-${width}"}).insert(ignore_permissions=True)
tasks = [frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": t, "status": "Open", "area": tea, "due_date": d}).insert(ignore_permissions=True).name
  for t, d in (("${due}", "${dueDay}"), ("${later}", "${nextMonth}"))]
goal = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${goalTitle}", "area": tea, "horizon": "Year", "target_date": "${year}-12-31", "done_when": "Done"}).insert(ignore_permissions=True).name
off = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${offTitle}", "area": mind, "horizon": "Year", "target_date": "${year}-12-31", "done_when": "Done"}).insert(ignore_permissions=True).name
print(json.dumps({"career": career, "tea": tea, "mind": mind, "was": was, "event": ev.name, "tasks": tasks, "goal": goal, "off": off}))`).split('\n').pop())
  let reviewName = null
  try {
    await check('TODAY.11', `${width} px: Week shows this week's calendar events and due tasks on the right days, and a day opens Day`, async () => {
      await s.open('/life/today/week?mode=calendar')
      await pg.locator('[data-week-grid]').waitFor({ timeout: 10000 })
      const dayText = async (d) => await pg.locator(`[data-week-grid] [data-day="${d}"]`).innerText()
      must((await dayText(meetDay)).includes(meeting), `${meeting} is not on ${meetDay}`)
      must((await dayText(dueDay)).includes(due), `${due} is not on ${dueDay}`)
      for (const d of [plusDays(monday, 4), plusDays(monday, 5)]) must(!(await dayText(d)).includes(meeting) && !(await dayText(d)).includes(due), 'an item is on the wrong day ' + d)
      const to = dueDay === today ? meetDay : dueDay
      await pg.locator(`[data-week-grid] [data-day="${to}"] [data-open-day]`).click()
      await pg.waitForURL((u) => u.pathname === '/life/today' && u.searchParams.get('date') === to, { timeout: 10000 })
      await pg.locator('[data-day-timeline]').waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-day-timeline]')?.innerText.includes(t), to === dueDay ? due : meeting, { timeout: 10000 }).catch(() => {})
      must((await pg.locator('[data-day-timeline]').innerText()).includes(to === dueDay ? due : meeting), 'Day does not list the item of ' + to)
      must((await pg.locator('[data-page-head]').first().innerText()).includes(String(Number(to.slice(8)))), 'Day is not headed with the date')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('TODAY.12', `${width} px: Month shows events and due tasks on the right dates; next and previous months work`, async () => {
      await s.open('/life/today/month?mode=calendar')
      await pg.locator('[data-month-grid]').waitFor({ timeout: 10000 })
      const month = today.slice(0, 7)
      must((await pg.locator('[data-month-view]').getAttribute('data-month')) === month, 'Month is not on this month')
      if (phone) {
        for (const [d, title] of [[meetDay, 'meeting'], [dueDay, due]]) {
          await pg.locator(`[data-month-grid] [data-day="${d}"] > button`).click()
          await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), title, { timeout: 5000 })
        }
      } else {
        // a meeting is a count on its day, not its title (the key dates are named)
        const cell = await pg.locator(`[data-month-grid] [data-day="${meetDay}"]`).innerText()
        must(/\d meetings?/.test(cell) && !cell.includes(meeting), `${meetDay} does not count its meetings: ${cell.replace(/\n/g, ' | ')}`)
        must((await pg.locator(`[data-month-grid] [data-day="${dueDay}"]`).innerText()).includes(due), `${due} is not on ${dueDay}`)
      }
      await pg.locator('[data-cal-next]').click()
      await pg.waitForFunction((k) => document.querySelector('[data-month-view]')?.getAttribute('data-month') === k, nextKey, { timeout: 10000 })
      await pg.locator(`[data-month-grid] [data-day="${nextMonth}"]`).waitFor({ timeout: 10000 })
      if (phone) {
        await pg.locator(`[data-month-grid] [data-day="${nextMonth}"] > button`).click()
        await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), later, { timeout: 5000 })
      } else {
        // the next month's items load after its grid is drawn
        await pg.waitForFunction(([d, t]) => document.querySelector(`[data-month-grid] [data-day="${d}"]`)?.innerText.includes(t), [nextMonth, later], { timeout: 10000 }).catch(() => {})
        must((await pg.locator(`[data-month-grid] [data-day="${nextMonth}"]`).innerText()).includes(later), `${later} is not on ${nextMonth}`)
      }
      await pg.locator('[data-cal-prev]').click()
      await pg.waitForFunction((k) => document.querySelector('[data-month-view]')?.getAttribute('data-month') === k, month, { timeout: 10000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('TODAY.13', `${width} px: Year's Goals shows a goal under its area and the weekly reviews locked since setup`, async () => {
      const before = await s.api('calendar.year_plan', { space: SPACE })
      const week = before.reviews.weeks.find((w) => !w.done && w.start <= today)
      must(week, 'no week since setup without a review')
      reviewName = bench(`r = frappe.get_doc({"doctype": "Life Review", "space": "${SPACE}", "user": "owner@lifeos.test", "kind": "Weekly", "status": "Locked", "period_start": "${week.start}",
  "period_end": "${plusDays(week.start, 6)}", "locked_on": frappe.utils.now_datetime(), "title": "I16 review ${width} ${stamp}", "tab_state": "{}"}).insert(ignore_permissions=True)
print(r.name)`).split('\n').pop()
      const after = await s.api('calendar.year_plan', { space: SPACE })
      must(after.reviews.done === before.reviews.done + 1, `the server counts ${after.reviews.done} reviews; it was ${before.reviews.done}`)
      await s.open('/life/today/year?mode=goals')
      await pg.locator('[data-year-view] [data-dash-card]').first().waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-panel="goals"]')?.innerText.includes(t), goalTitle, { timeout: 10000 })
      must((await pg.locator('[data-card="reviews"]').innerText()).includes(`${after.reviews.done} of ${after.reviews.total}`), 'the Reviews locked card does not say ' + `${after.reviews.done} of ${after.reviews.total}`)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('TODAY.14', `${width} px: an area that is off has no goals on Year`, async () => {
      const out = await s.api('calendar.year_plan', { space: SPACE })
      must(!out.lanes.some((l) => l.area === made.mind), 'the server sent a lane for an area that is off')
      await s.open('/life/today/year?mode=goals')
      await pg.locator('[data-year-view] [data-dash-card]').first().waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-panel="goals"]')?.innerText.includes(t), goalTitle, { timeout: 10000 })
      must(!(await pg.locator('[data-year-view]').innerText()).includes(offTitle), 'the goal of an area that is off is shown')
      bench(`frappe.db.set_value("Life Area", "${made.mind}", "is_on", 1)`)
      await s.open('/life/today/year?mode=goals')
      await pg.locator('[data-year-view] [data-dash-card]').first().waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-year-view]')?.innerText.includes(t), offTitle, { timeout: 10000 })
      bench(`frappe.db.set_value("Life Area", "${made.mind}", "is_on", 0)`)
    })
    await check('TODAY.15', `${width} px: clicking a goal on Year's Goals opens the goal in the Drawer`, async () => {
      await s.open('/life/today/year?mode=goals')
      const row = pg.locator('[data-panel="goals"] [data-dash-row]', { hasText: goalTitle }).first()
      await row.waitFor({ timeout: 10000 })
      await row.locator('button').first().click()
      await pg.waitForFunction((g) => new URL(location.href).searchParams.get('open') === 'goal:' + g, made.goal, { timeout: 10000 })
      must(new URL(pg.url()).pathname === '/life/today/year', 'the goal took the page away')
      await pg.keyboard.press('Escape')
    })
    await check('TODAY.16', `${width} px: Week, Month and Year have no sideways scroll`, async () => {
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


// Issue 49: the first-run guide and the empty states on a brand-new site. I49.1 and I49.2 are unit tests (test_i49_first_run). A user made for
// the run, with a space of their own and nothing in it, stands for a new person's site. Titles start "I49 ".
for (const width of WIDTHS) {
  const tag = `I49.${width}`
  const phone = width < 800
  const user = `i49-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I49 ${width} ${stamp}`
  const zoneWas = bench('print(frappe.db.get_single_value("System Settings", "time_zone"))').split('\n').pop()
  const reset = () => bench(`frappe.defaults.clear_default("lifeos_onboarding", parent="${user}")`)
  const restore = () => bench(`frappe.set_user("Administrator")
frappe.db.set_single_value("System Settings", "time_zone", "${zoneWas}")
for dt in ("Life Task",):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos.tools import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  const keyWas = bench('from lifeos.ai import client\nprint(client.api_key() or "")').split('\n').pop()
  // the AI key as the check needs it: none, or a fake one (a key starting "fake-" is never sent anywhere)
  const keyIs = (v) => bench(`doc = frappe.get_doc("Life Settings")\ndoc.anthropic_api_key = ${v ? JSON.stringify(v) : 'None'}\ndoc.save()`)
  const fakeArea = (name) => bench(`from frappe.installer import update_site_config\nupdate_site_config("lifeos_fake_ai_area", "${name}")`)
  let one = null
  try {
    bench(`from lifeos.tools import devtools
devtools.make_user("${user}", "Newcomer", ["Life Admin", "Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)`)
    one = await session(user, width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    const stepKey = () => pg.locator('[data-guide]').getAttribute('data-step')
    const guideOpens = async () => { await one.open('/life'); await pg.locator('[data-guide]').waitFor({ timeout: 10000 }) }
    const path = () => new URL(pg.url()).pathname
    const STEP_KEYS = ['welcome', 'you', 'areas', 'brain', 'things', 'done']
    // a new person's site again: no tasks, only Career and Health on, no parts, no AI key, the guide not yet seen
    const fresh = ({ key = '', area = '' } = {}) => {
      bench(`frappe.set_user("Administrator")
for n in frappe.get_all("Life Task", filters={"space": "${space}"}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Action Log", {"space": "${space}"})
for n in frappe.get_all("Life Area", filters={"space": "${space}", "is_life_area": 0}, pluck="name"): frappe.delete_doc("Life Area", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Area", filters={"space": "${space}", "is_life_area": 1}, pluck="name"):
    frappe.db.set_value("Life Area", n, "is_on", 1 if frappe.db.get_value("Life Area", n, "area_name") in ("Career", "Health") else 0)
frappe.defaults.clear_default("lifeos_onboarding", parent="${user}")
frappe.db.set_value("User", "${user}", "preferred_name", None)
frappe.clear_cache()`)
      keyIs(key)
      fakeArea(area)
    }
    const toStep = async (key) => {
      for (let guard = 0; guard < 8 && await stepKey() !== key; guard++) {
        const was = await stepKey()
        await pg.locator('[data-guide-next]').click()
        await pg.waitForFunction((k) => document.querySelector('[data-guide]')?.dataset.step !== k, was, { timeout: 8000 })
      }
      must(await stepKey() === key, `could not reach ${key}`)
    }
    // open the guide on its first screen, with nothing left over from an earlier check
    const openGuide = async (key = 'welcome') => {
      await pg.evaluate(() => sessionStorage.clear())
      await guideOpens()
      await toStep(key)
    }
    const zoneTrigger = () => pg.locator('[data-guide-zone]').first()
    const pickZone = async (city) => {
      await zoneTrigger().click()
      await pg.getByRole('option', { name: new RegExp(`— ${city} `) }).first().click()
    }

    await check('TODAY.17', `${width} px: the first visit opens the guide; Start, Next, Skip and Done land on Today and the guide does not return`, async () => {
      fresh()
      await guideOpens()
      must(await stepKey() === 'welcome', 'the guide does not open on Welcome')
      must((await pg.locator('[data-guide-flow] li').count()) === 3, 'Welcome does not show Sources, Brain and Plan')
      for (const key of ['welcome', 'you', 'areas']) {
        must(await stepKey() === key, `expected the ${key} step, at ${await stepKey()}`)
        await pg.locator('[data-guide-next]').click()
        await pg.waitForFunction((k) => document.querySelector('[data-guide]')?.dataset.step !== k, key, { timeout: 8000 })
      }
      for (const key of ['brain', 'things']) {
        must(await stepKey() === key, `expected the ${key} step, at ${await stepKey()}`)
        await pg.locator('[data-guide-skip]').click()
        await pg.waitForFunction((k) => document.querySelector('[data-guide]')?.dataset.step !== k, key, { timeout: 8000 })
      }
      must(await stepKey() === 'done', 'the last step is not You are set up')
      await pg.locator('[data-guide-next]').click() // Done
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
      must(await pg.locator('[data-guide]').count() === 0, 'the guide is still open')
      await one.open('/life')
      await pg.waitForTimeout(1200)
      must(await pg.locator('[data-guide]').count() === 0, 'the guide came back after a reload')
      must((await one.api('onboarding.state')).done, 'the guide is not recorded as finished')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    if (phone) {
      reset()
      await check('TODAY.18', `${width} px: the guide shows one screen at a time and each screen fits the phone`, async () => {
        await guideOpens()
        for (const key of STEP_KEYS) {
          must(await stepKey() === key, `expected ${key}, at ${await stepKey()}`)
          must(await pg.locator('[data-guide-step]:visible').count() === 1, `${key}: more than one screen is shown`)
          must(!(await pg.evaluate(() => document.querySelector('[data-guide]').scrollWidth > window.innerWidth + 1)), `${key}: the screen scrolls sideways`)
          const box = await pg.locator('[data-guide-next]').boundingBox()
          must(box && box.x >= 0 && box.x + box.width <= width, `${key}: the Next button is off the screen`)
          if (key !== 'done') {
            await pg.locator('[data-guide-next]').click()
            await pg.waitForFunction((k) => document.querySelector('[data-guide]')?.dataset.step !== k, key, { timeout: 8000 })
          }
        }
        await pg.locator('[data-guide-close]').click()
        await pg.waitForFunction(() => !document.querySelector('[data-guide]'), null, { timeout: 8000 })
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
    }

    await check('TODAY.19', `${width} px: Today, Brain, Goals and Library on a fresh site each show their empty state with one action`, async () => {
      reset()
      for (const [p, sel] of [['/life/today?mode=calendar', '[data-timeline-empty]'], ['/life/brain', '[data-needs-empty]'], ['/life/goals', '[data-goals-empty]'], ['/life/library', '[data-lv-empty]']]) {
        await one.open(p)
        // the guide opens on a new site: close it to see the screen under it
        const g = pg.locator('[data-guide-close]')
        if (await g.count() || await g.waitFor({ timeout: 1500 }).then(() => true, () => false)) { await g.click(); await pg.waitForFunction(() => !document.querySelector('[data-guide]'), null, { timeout: 8000 }) }
        await pg.locator(sel).waitFor({ timeout: 10000 })
        const text = await pg.locator(sel).innerText()
        must(text.length > 20, `${p}: the empty state says ${JSON.stringify(text)}`)
        must(await pg.locator(`${sel} button, ${sel} a`).count() === 1, `${p}: the empty state has ${await pg.locator(`${sel} button, ${sel} a`).count()} actions`)
        await noSideways()
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.20', `${width} px: going through the guide sets what to call the person and the time zone, switches on a third area, adds a part and turns three typed things into tasks with areas`, async () => {
      fresh()
      await guideOpens()
      await pg.locator('[data-guide-next]').click() // Start
      await pg.locator('[data-guide-name] input, input[data-guide-name]').first().fill('Asha')
      await pickZone('Dubai')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'areas', null, { timeout: 8000 })
      must(await pg.locator('[data-guide-area][data-on="1"]').count() === 2, 'Career and Health are not the two areas on')
      await pg.locator('[data-guide-switch="Mind"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Mind"]')?.dataset.on === '1', null, { timeout: 8000 })
      await pg.locator('[data-guide-add-part="Career"]').click()
      await pg.locator('[data-guide-part-title] input, input[data-guide-part-title]').first().fill(`I49 part ${stamp}`)
      await pg.locator('[data-guide-part-add]').click()
      await pg.locator('[data-guide-area="Career"] [data-guide-part]').waitFor({ timeout: 8000 })
      await pg.locator('[data-guide-next]').click()
      await pg.locator('[data-guide-skip]').click() // the AI key: later
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'things', null, { timeout: 8000 })
      const things = [`I49 book the dentist ${stamp}`, `I49 pay the electricity bill ${stamp}`, `I49 read a chapter of my book ${stamp}`]
      for (const [i, t] of things.entries()) await pg.locator(`[data-guide-thing="${i}"] input, input[data-guide-thing="${i}"]`).first().fill(t)
      await pg.locator('[data-guide-next]').click()
      await pg.locator('[data-guide-task]').first().waitFor({ timeout: 10000 })
      must(await pg.locator('[data-guide-task]').count() === 3, 'three tasks were not made')
      const areas = await pg.locator('[data-guide-task-area]').allInnerTexts()
      must(areas.every((a) => a && a !== 'No area'), 'a task has no area: ' + areas.join())
      await pg.locator('[data-guide-next]').click() // on, to the end
      must(/3 areas, 1 part, 3 tasks/.test(await pg.locator('[data-guide-summary]').innerText()), 'the summary is ' + await pg.locator('[data-guide-summary]').innerText())
      await pg.locator('[data-guide-next]').click() // Done
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
      const out = JSON.parse(bench(`import json
doc = frappe.get_doc("User", "${user}")
on = frappe.get_all("Life Area", filters={"space": "${space}", "is_life_area": 1, "is_on": 1}, pluck="area_name")
tasks = frappe.get_all("Life Task", filters={"space": "${space}"}, fields=["title", "area"])
print(json.dumps({"name": doc.full_name, "call": doc.preferred_name, "zone": frappe.db.get_single_value("System Settings", "time_zone"), "on": sorted(on),
  "tasks": len(tasks), "unfiled": len([t for t in tasks if not t.area]),
  "part": frappe.db.exists("Life Area", {"space": "${space}", "area_name": "I49 part ${stamp}"}) is not None}))`).split('\n').pop())
      must(out.call === 'Asha' && out.name === 'Newcomer', `called ${out.call}, full name ${out.name}`)
      must(out.zone === 'Asia/Dubai', 'the time zone is ' + out.zone)
      must(out.on.join() === 'Career,Health,Mind', 'the areas on are ' + out.on.join())
      must(out.tasks === 3 && out.unfiled === 0, `tasks: ${out.tasks}, without an area: ${out.unfiled}`)
      must(out.part, 'the part was not made')
      must((await one.api('onboarding.state')).status === 'done', 'the guide is not recorded as done')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.21', `${width} px: after the guide the ladder card shows level 1 of 7 and the next step, the AI key`, async () => {
      await one.open('/life/today')
      if (phone) await pg.locator('[data-more-title]').click()
      const card = pg.locator('[data-setup-card]:visible')
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('level 1 of 7'), 'the card says: ' + t.replace(/\n/g, ' | '))
      must(/AI key/i.test(t), 'the next step is not the AI key: ' + t)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    // ---- issue 97: the guide's one layout, step by step. Every check starts from `fresh()` and opens the guide on the step it tests. ----
    // what each step looks like, measured in the page, once for each colour scheme
    const walked = {}
    const walk = async (scheme, key = '') => {
      if (walked[scheme]) return walked[scheme]
      fresh({ key })
      await pg.emulateMedia({ colorScheme: scheme })
      await openGuide()
      const out = []
      for (const k of STEP_KEYS) {
        await toStep(k)
        await pg.mouse.move(1, 1) // off the button, so no hover colour
        await pg.waitForTimeout(350)
        out.push({ key: k, ...(await pg.evaluate(() => {
          const g = document.querySelector('[data-guide]')
          const last = g.querySelector('[data-guide-step]').lastElementChild
          const foot = g.querySelector('[data-guide-footer]')
          const style = (el) => { const c = getComputedStyle(el); return `${c.borderTopWidth} ${c.borderTopColor} ${c.backgroundColor}` }
          const inputs = [...g.querySelectorAll('input, [role="combobox"]')].filter((e) => e.getBoundingClientRect().width).map(style)
          const clipped = [...g.querySelectorAll('*')].filter((e) => !e.children.length && e.clientWidth && e.scrollWidth > e.clientWidth + 1).map((e) => (e.textContent || e.tagName).slice(0, 30))
          const buttons = [...g.querySelectorAll('button')].map((b) => b.textContent.trim())
          return { gap: foot.getBoundingClientRect().top - last.getBoundingClientRect().bottom, primary: getComputedStyle(g.querySelector('[data-guide-next]')).backgroundColor,
            label: g.querySelector('[data-guide-next]').textContent.trim(), skip: !!g.querySelector('[data-guide-skip]'), inputs, clipped, buttons, text: g.innerText }
        })) })
      }
      walked[scheme] = out
      return out
    }

    await check('TODAY.31', `${width} px: on every step the footer sits under the content, within 48 px`, async () => {
      for (const m of await walk('light')) must(m.gap >= 0 && m.gap <= 48, `${m.key}: the footer is ${Math.round(m.gap)} px under the content`)
    })

    await check('TODAY.32', `${width} px: every step has the same primary button colour, and every text box and select the same border and background`, async () => {
      const all = await walk('light')
      must(new Set(all.map((m) => m.primary)).size === 1, 'the primary button colours differ: ' + [...new Set(all.map((m) => m.primary))].join(' | '))
      const styles = new Set(all.flatMap((m) => m.inputs))
      must(all.some((m) => m.inputs.length) && styles.size === 1, 'the input styles differ: ' + [...styles].join(' | '))
    })

    await check('TODAY.33', `${width} px: the primary button reads Start, Next, Next, Next, Next, Done and nothing reads Continue`, async () => {
      const all = await walk('light')
      must(all.map((m) => m.label).join() === 'Start,Next,Next,Next,Next,Done', 'the labels are ' + all.map((m) => m.label).join())
      must(!all.some((m) => m.buttons.includes('Continue')), 'a button reads Continue')
    })

    await check('TODAY.34', `${width} px: Skip is shown only where the step is optional and starts empty (the AI key, and what is on your mind)`, async () => {
      const skips = (await walk('light')).filter((m) => m.skip).map((m) => m.key)
      must(skips.join() === 'brain,things', 'Skip is on ' + skips.join())
    })

    await check('TODAY.35', `${width} px: Welcome shades none of its three cards`, async () => {
      fresh()
      await openGuide()
      const bgs = await pg.locator('[data-guide-card]').evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor))
      must(bgs.length === 3 && new Set(bgs).size === 1, 'the cards are shaded differently: ' + bgs.join(' | '))
    })

    await check('TODAY.36', `${width} px: You: the call-me field holds the first word of the full name, saving it leaves the full name, and the time zone reads as a place with its offset`, async () => {
      fresh()
      await openGuide('you')
      must(await pg.locator('[data-guide-name] input, input[data-guide-name]').first().inputValue() === 'Newcomer', 'the field is not the first word of the full name')
      must(await pg.getByText('What should we call you?').count() > 0, 'the field is not labelled "What should we call you?"')
      const zone = await zoneTrigger().innerText()
      must(zone.includes('Kolkata') && zone.includes('GMT+5:30') && zone.includes('India'), 'the time zone reads ' + zone)
      must(await zoneTrigger().evaluate((e) => e.scrollHeight <= e.clientHeight), 'the time zone text is clipped')
      await pg.locator('[data-guide-name] input, input[data-guide-name]').first().fill('Jai')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'areas', null, { timeout: 8000 })
      const s = await one.api('onboarding.state')
      must(s.call_me === 'Jai' && s.full_name === 'Newcomer', `called ${s.call_me}, full name ${s.full_name}`)
    })

    await check('TODAY.37', `${width} px: Areas: switching Money on and off changes no text under the title, and each switch is right of its area's name`, async () => {
      fresh()
      await openGuide('areas')
      const line = () => pg.locator('[data-guide-line]').innerText()
      const before = await line()
      await pg.locator('[data-guide-switch="Money"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Money"]')?.dataset.on === '1', null, { timeout: 8000 })
      must(await line() === before, 'the line changed: ' + await line())
      await pg.locator('[data-guide-switch="Money"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Money"]')?.dataset.on === '0', null, { timeout: 8000 })
      must(await line() === before, 'the line changed: ' + await line())
      for (const area of ['Career', 'Money']) {
        const name = await pg.locator(`[data-guide-area="${area}"] .text-base-medium`).first().boundingBox()
        const sw = await pg.locator(`[data-guide-switch="${area}"]`).boundingBox()
        must(sw.x > name.x + name.width - 1, `${area}: the switch is not to the right of the name`)
      }
    })

    await check('TODAY.38', `${width} px: Areas: a part sits indented under its area with an ×, stays greyed as Kept when the area goes off, and there is no area drop-down`, async () => {
      fresh()
      await openGuide('areas')
      await pg.locator('[data-guide-add-part="Career"]').click()
      await pg.locator('[data-guide-part-title] input, input[data-guide-part-title]').first().fill(`Tea ${stamp}`)
      await pg.locator('[data-guide-part-add]').click()
      const part = pg.locator('[data-guide-area="Career"] [data-guide-part]')
      await part.waitFor({ timeout: 8000 })
      const head = await pg.locator('[data-guide-area="Career"] .text-base-medium').first().boundingBox()
      must((await part.boundingBox()).x > head.x + 8, 'the part is not indented under Career')
      must(await pg.locator('[data-guide] select, [data-guide-part-area]').count() === 0, 'the page has an area drop-down')
      await pg.locator('[data-guide-switch="Career"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Career"]')?.dataset.on === '0', null, { timeout: 8000 })
      must(/Kept/.test(await part.innerText()) && await part.locator('[data-guide-part-remove]').count() === 0, 'the part is not shown as Kept')
      await pg.locator('[data-guide-switch="Career"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Career"]')?.dataset.on === '1', null, { timeout: 8000 })
      await part.locator('[data-guide-part-remove]').click()
      await part.waitFor({ state: 'detached', timeout: 8000 })
    })

    await check('TODAY.39', `${width} px: What's on your mind: three empty boxes with no placeholder`, async () => {
      fresh()
      await openGuide('things')
      const boxes = await pg.locator('[data-guide-thing] input, input[data-guide-thing]').evaluateAll((els) => els.map((e) => [e.value, e.placeholder]))
      must(boxes.length === 3 && boxes.every(([v, p]) => !v && !p), 'the boxes are ' + JSON.stringify(boxes))
    })

    // type one thing on the things step and press Next; the row's area label comes back
    const file = async (text) => {
      await pg.locator('[data-guide-thing="0"] input, input[data-guide-thing="0"]').first().fill(text)
      await pg.locator('[data-guide-next]').click()
      await pg.locator('[data-guide-task]').first().waitFor({ timeout: 10000 })
      await pg.waitForFunction(() => !/Filing/.test(document.querySelector('[data-guide-task-area]')?.textContent || ''), null, { timeout: 12000 })
      return (await pg.locator('[data-guide-task-area]').first().innerText()).trim()
    }
    const switchOn = async (area) => {
      await pg.locator(`[data-guide-switch="${area}"]`).click()
      await pg.waitForFunction((a) => document.querySelector(`[data-guide-area="${a}"]`)?.dataset.on === '1', area, { timeout: 8000 })
    }

    await check('TODAY.40', `${width} px: with a model that answers Money, the first thing shows Money, not Career`, async () => {
      fresh({ key: 'fake-i97-key-0001', area: 'Money' })
      await openGuide('areas')
      await switchOn('Money')
      await toStep('things')
      must(await file('Finish tax return meeting') === 'Money', 'the row is not filed under Money')
    })

    await check('TODAY.41', `${width} px: with no AI key the first thing's label reads Not sure`, async () => {
      fresh()
      await openGuide('things')
      must(await file('Finish tax return meeting') === 'Not sure', 'the label is not Not sure')
    })

    await check('TODAY.42', `${width} px: tapping the label and picking Health saves Health on the task and logs a correction`, async () => {
      fresh()
      await openGuide('things')
      await file('Finish tax return meeting')
      await pg.locator('[data-guide-task-area]').first().click()
      await pg.getByRole('menuitem', { name: 'Health' }).click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-task-area]')?.textContent.trim() === 'Health', null, { timeout: 8000 })
      const out = bench(`t = frappe.get_all("Life Task", filters={"space": "${space}"}, fields=["name", "area"])[0]
print(frappe.db.get_value("Life Area", t.area, "area_name"), frappe.db.count("Life Action Log", {"kind": "Area correction", "task": t.name}))`).split('\n').pop()
      must(out === 'Health 1', 'the task and its correction are: ' + out)
    })

    await check('TODAY.43', `${width} px: a model that answers Relationships while it is off shows "Relationships (off)", and Switch on files the task there`, async () => {
      fresh({ key: 'fake-i97-key-0001', area: 'Relationships' })
      await openGuide('things')
      must(await file('Call mum on Sunday') === 'Relationships (off)', 'the label is not "Relationships (off)"')
      await pg.locator('[data-guide-task-area]').first().click()
      await pg.getByRole('menuitem', { name: 'Switch on Relationships' }).click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-task-area]')?.textContent.trim() === 'Relationships', null, { timeout: 8000 })
      const out = bench(`t = frappe.get_all("Life Task", filters={"space": "${space}"}, fields=["name", "area"])[0]
a = frappe.db.get_value("Life Area", t.area, ["area_name", "is_on"])
print(a[0], a[1])`).split('\n').pop()
      must(out === 'Relationships 1', 'the task is filed: ' + out)
    })

    await check('TODAY.44', `${width} px: the microphone hint shows on a phone and not on a computer`, async () => {
      fresh()
      await openGuide('things')
      must((await pg.locator('[data-guide-mic]').count() === 1) === phone, `the hint is ${phone ? 'missing' : 'shown'}`)
    })

    await check('TODAY.45', `${width} px: You're set up: the summary counts what was made, no "level", and Done opens Today`, async () => {
      fresh()
      await openGuide('areas')
      await pg.locator('[data-guide-add-part="Career"]').click()
      await pg.locator('[data-guide-part-title] input, input[data-guide-part-title]').first().fill(`Tea ${stamp}`)
      await pg.locator('[data-guide-part-add]').click()
      await pg.locator('[data-guide-area="Career"] [data-guide-part]').waitFor({ timeout: 8000 })
      await toStep('things')
      await file('Pay the electricity bill')
      await toStep('done')
      must(await pg.locator('[data-guide-title]').innerText() === "You're set up", 'the title is wrong')
      must(await pg.locator('[data-guide-summary]').innerText() === '2 areas, 1 part, 1 task', 'the summary is ' + await pg.locator('[data-guide-summary]').innerText())
      must(!/level/i.test(await pg.locator('[data-guide]').innerText()), 'the page says "level"')
      must(await pg.locator('[data-guide-brain-off]').count() === 1, 'it does not say the Brain is off')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
    })

    await check('TODAY.46', `${width} px: every step in light and dark: no script error and no clipped text`, async () => {
      for (const scheme of ['light', 'dark']) {
        for (const m of await walk(scheme)) must(!m.clipped.length, `${scheme}, ${m.key}: clipped text: ${m.clipped.join(' | ')}`)
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      await pg.emulateMedia({ colorScheme: 'light' })
    })

    await check('TODAY.47', `${width} px: with no key the AI key step comes between areas and first things, and Skip goes on to first things`, async () => {
      fresh()
      await openGuide('areas')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'brain', null, { timeout: 8000 })
      must(await pg.locator('[data-guide-title]').innerText() === 'Turn on the Brain', 'the title is wrong')
      must(await pg.locator('[data-guide-key-help]').innerText() === 'Where do I get a key?', 'there is no key link')
      await pg.locator('[data-guide-skip]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'things', null, { timeout: 8000 })
    })

    await check('TODAY.48', `${width} px: a fake key is saved and shows "The Brain is on", and the first thing then gets the model's area`, async () => {
      fresh()
      await openGuide('brain')
      await pg.locator('[data-guide-key] input, input[data-guide-key]').first().fill('fake-i97-key-0002')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'things', null, { timeout: 12000 })
      must((await one.api('onboarding.state')).ai_set, 'the key was not saved')
      must(bench('from lifeos.ai import client\nprint(client.api_key() == "fake-i97-key-0002")').split('\n').pop() === 'True', 'the key was not stored')
      must(bench('print(frappe.db.get_value("Life Settings", None, "anthropic_api_key") != "fake-i97-key-0002")').split('\n').pop() === 'True', 'the key is stored in the clear')
      const label = await file('Finish tax return meeting')
      must(label && label !== 'Not sure', 'the label is ' + label)
    })

    await check('TODAY.49', `${width} px: with a key already set, the step shows "The Brain is on" and Next goes straight on`, async () => {
      fresh({ key: 'fake-i97-key-0003' })
      await openGuide('brain')
      must(await pg.locator('[data-guide-brain-on]').innerText().then((t) => /The Brain is on/.test(t)), 'it does not say the Brain is on')
      must(await pg.locator('[data-guide-skip]').count() === 0 && await pg.locator('[data-guide-key]').count() === 0, 'it still asks for a key')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'things', null, { timeout: 8000 })
    })
  } finally {
    if (one) await one.ctx.close()
    restore()
    keyIs(keyWas)
    fakeArea('')
  }
}


// Issue 55: Today shows tasks, not goals, and the old Open band lives where each number counts. I55.7 is a unit test (test_issue55_today). A user made
// for the run has a space of their own (I55.8 first, while it is empty; then a cycle of three goals with lead actions and no tasks: I55.1, I55.2, I55.3, I55.4, I55.9);
// I55.5 and I55.6 read the owner's demo site. Titles start "I55 ".
const OLD_ROUTES = /^\/life\/(tasks|plan|inbox|someday|outbox|projects|wiki|vault|graph|timeline|archive|sources|chats|journal|calendar|reset|areas)(\/|\?|$)/
for (const width of WIDTHS) {
  const tag = `I55.${width}`
  const phone = width < 800
  const user = `i55-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I55 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Task", "Life Goal", "Life Cycle", "Life Habit Log", "Life Habit", "Life Action Log"):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos.tools import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  try {
    bench(`from lifeos.tools import devtools
devtools.make_user("${user}", "Newcomer55", ["Life Admin", "Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)`)
    one = await session(user, width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    await one.api('onboarding.complete', { status: 'skipped' })
    const today55 = async () => { await one.open('/life/today'); await pg.locator('[data-dash-cards]').waitFor({ timeout: 10000 }).catch(() => {}); await pg.waitForTimeout(500) }

    await check('TODAY.22', `${width} px: on an empty site Today shows its empty state and no Open band`, async () => {
      await one.open('/life/today?mode=calendar')
      await pg.locator('[data-timeline-empty]').waitFor({ timeout: 10000 })
      must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is on an empty Today')
      must(await pg.locator('[data-no-plan]').count() === 0, 'a goal line is on an empty Today')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.76', `${width} px: on an empty space the Waiting list says what will appear and offers + Hand off`, async () => {
      await one.open('/life/today/week?open=list:waiting')
      await pg.locator('[data-list="waiting"] [data-list-empty]').waitFor({ timeout: 15000 })
      must((await pg.locator('[data-list="waiting"] [data-list-empty]').innerText()).includes('Nobody owes you anything'), 'the empty list says: ' + await pg.locator('[data-list="waiting"] [data-list-empty]').innerText())
      must(await pg.locator('[data-waiting-handoff]').count() === 1, 'the empty list has no Hand off')
      await pg.locator('[data-waiting-handoff]').click()
      await pg.getByText('Hand off to someone').waitFor({ timeout: 8000 })
      for (const label of ['Just track', 'Draft a message', 'Send']) must(await pg.getByText(label, { exact: true }).count() >= 1, `the dialog has no ${label}`)
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.84', `${width} px: a new person's Today opens in Overview with numbers, and with no goal the switch is Overview · Calendar and ?mode=goals shows Overview; Calendar is remembered across a reload`, async () => {
      await one.open('/life/today')
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(await pg.locator('[data-ruler]').count() === 0, 'a new person\'s Today did not open in Overview')
      for (const path of ['/life/today', '/life/today/week', '/life/today/month', '/life/today/year']) {
        await one.open(path)
        await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
        must((await pg.locator('[data-dash-card]').count()) === 4, `${path} has ${await pg.locator('[data-dash-card]').count()} cards`)
        for (const c of await pg.locator('[data-dash-card] [data-stat-value]').allInnerTexts()) must(/\d/.test(c), `${path}: a card shows "${c}" instead of a number`)
        await noSideways()
      }
      must((await pg.locator('[data-mode-option]').allInnerTexts()).join('|') === 'Overview|Calendar', 'with no goal the switch is not Overview · Calendar')
      await one.open('/life/today/week?mode=goals')
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(await pg.locator('[data-dashboard][data-mode="overview"]').count() === 1 && await pg.locator('[data-panel="goals"]').count() === 0, '?mode=goals without goals did not show Overview')
      await pg.locator('[data-mode-option="calendar"]').click()
      await pg.locator('[data-ruler]').waitFor({ timeout: 15000 })
      await pg.goto(new URL('/life/today', pg.url()).href, { waitUntil: 'networkidle' })
      await pg.locator('[data-ruler]').waitFor({ timeout: 15000 })
      await pg.locator('[data-mode-option="overview"]').click()
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    // a cycle of three goals, each with a lead action, and nothing planned this week
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, today
space = "${space}"
area = frappe.get_all("Life Area", filters={"space": space, "is_life_area": 1, "is_on": 1}, pluck="name", limit=1)[0]
cycle = frappe.get_doc({"doctype": "Life Cycle", "space": space, "title": "I55 cycle ${width}", "start_date": add_days(today(), -14), "status": "Active"}).insert(ignore_permissions=True)
goals = [frappe.get_doc({"doctype": "Life Goal", "space": space, "cycle": cycle.name, "title": f"I55 goal {i} ${width}", "area": area, "sort_order": i, "done_when": "Done",
  "actions": [{"title": f"I55 lead {i} ${width}", "per_week": 1}]}).insert(ignore_permissions=True) for i in range(3)]
print(json.dumps({"cycle": cycle.name, "goals": [g.name for g in goals], "actions": [g.actions[0].name for g in goals]}))`).split('\n').pop())

    await check('TODAY.23', `${width} px: cycle goals with lead actions and no task this week are not rows on Today`, async () => {
      await one.open('/life/today?mode=calendar')
      await pg.locator('[data-day-timeline]').waitFor({ timeout: 10000 })
      const text = await pg.locator('[data-day-timeline]').innerText()
      must(!/I55 goal|I55 lead/.test(text), 'a goal or lead action is in the list: ' + text.slice(0, 300))
      must(await pg.locator('[data-week-tick], [data-action]').count() === 0, 'a lead action tick box is on Today')
      must(!(await pg.locator('[data-main]').innerText()).includes('12WY'), 'a 12WY row is on Today')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.85', `${width} px: after a goal exists the switch is Overview · Goals · Calendar, and Goals on Week shows Goals by area with the goal, whose row opens in the Drawer`, async () => {
      await one.open('/life/today/week?mode=overview')
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must((await pg.locator('[data-mode-option]').allInnerTexts()).join('|') === 'Overview|Goals|Calendar', 'the switch is not Overview · Goals · Calendar')
      await pg.locator('[data-mode-option="goals"]').click()
      await pg.locator('[data-panel="goals"]').waitFor({ timeout: 15000 })
      const row = pg.locator('[data-panel="goals"] [data-dash-row]', { hasText: 'I55 goal 0' }).first()
      await row.waitFor({ timeout: 10000 })
      await row.locator('button').first().click()
      await pg.waitForFunction((g) => new URL(location.href).searchParams.get('open') === 'goal:' + g, made.goals[0], { timeout: 10000 })
      must(pathOf(pg) === '/life/today/week', 'the goal took the page away')
      await pg.keyboard.press('Escape')
      await pg.locator('[data-mode-option="overview"]').click()
    })

    await check('TODAY.86', `${width} px, light and dark: no card on any view, in Overview or in Goals, shows a paragraph or a Set a goal button; each shows a number; the cards sit two by two on a phone`, async () => {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        for (const mode of ['overview', 'goals']) {
          for (const p of ['/life/today', '/life/today/week', '/life/today/month', '/life/today/year']) {
            await one.open(`${p}?mode=${mode}`)
            await pg.locator('[data-dashboard][data-mode="' + mode + '"] [data-dash-card]').first().waitFor({ timeout: 15000 })
            const cards = pg.locator('[data-dash-card]')
            must((await cards.count()) === 4, `${p} ${mode} has ${await cards.count()} cards`)
            for (let i = 0; i < 4; i++) {
              const c = cards.nth(i), key = await c.getAttribute('data-card')
              must(/\d/.test(await c.locator('[data-stat-value]').innerText()), `${p} ${mode}: the ${key} card shows no number`)
              must((await c.locator('[data-empty], [data-empty-action]').count()) === 0 && !(await c.innerText()).includes('Set a goal'), `${p} ${mode}: the ${key} card has a paragraph or a button`)
            }
            if (phone) {
              const xs = await cards.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().x)))
              must(new Set(xs).size === 2, `${p} ${mode}: the cards are not two by two (${xs})`)
              const sw = await pg.locator('[data-mode-switch]').boundingBox()
              must(sw.x >= 0 && sw.x + sw.width <= 391, `${p}: the switch does not fit`)
            }
            await noSideways()
          }
        }
      }
      await pg.emulateMedia({ colorScheme: 'light' })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.87', `${width} px: Day Overview counts what is due today (overdue included), Your plate lists the overdue task first; ticking a row marks it Done, the count drops by one and Undo brings it back; a title opens the task in the Drawer`, async () => {
      const late = `I135 overdue ${width}`, now = `I135 today ${width}`
      await one.api('tasks.quick_add', { text: late, space, due_date: addDays(-30) })
      await one.api('tasks.quick_add', { text: now, space, due_date: today })
      await one.open('/life/today?mode=overview')
      const due = pg.locator('[data-card="due"] [data-stat-value]')
      await pg.waitForFunction((t) => document.querySelector('[data-panel="plate"]')?.innerText.includes(t), now, { timeout: 15000 })
      const n = Number(await due.innerText())
      const plate = pg.locator('[data-panel="plate"] [data-dash-row]')
      must(n >= 2 && n === (await one.api('dashboard.get', { view: 'day', space, mode: 'overview' })).cards[0].value, `Due today says ${n}`)
      must((await plate.first().innerText()).includes(late), 'the overdue task is not first on Your plate: ' + (await plate.first().innerText()))
      await plate.first().getByRole('checkbox').click()
      await pg.waitForFunction(([sel, v]) => document.querySelector(sel)?.innerText.trim() === String(v), ['[data-card="due"] [data-stat-value]', n - 1], { timeout: 10000 })
      must(!(await pg.locator('[data-panel="plate"]').innerText()).includes(late), 'a done task is still on Your plate')
      await pg.getByRole('button', { name: 'Undo' }).first().click()
      await pg.waitForFunction(([sel, v]) => document.querySelector(sel)?.innerText.trim() === String(v), ['[data-card="due"] [data-stat-value]', n], { timeout: 10000 })
      const first = pg.locator('[data-panel="plate"] [data-dash-row]').first()
      await first.locator('button').first().click()
      await pg.waitForFunction(() => /^task:/.test(new URL(location.href).searchParams.get('open') || ''), null, { timeout: 10000 })
      must(pathOf(pg) === '/life/today' && await pg.locator('[data-dashboard]').count() === 1, 'the task took the dashboard away')
      await noSideways()
      await pg.keyboard.press('Escape')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.26', `${width} px: the Open band is gone from Today; the Habits card counts today's habits and its list in the pane ticks them`, async () => {
      await one.api('goals.set_month_habits', { space, year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)), habits: [{ title: `I55 Walk ${width}` }, { title: `I55 Read ${width}` }] })
      await one.open('/life/today?mode=goals'); await pg.locator('[data-dash-cards]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(500)
      must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is on Today')
      must(await pg.locator('[data-tile]').count() === 0, 'a tile of the band is on Today')
      const card = pg.locator('[data-card="habits"]')
      await card.waitFor({ timeout: 10000 })
      must(/0 of 2/.test(await card.innerText()), 'the card does not count the habits: ' + (await card.innerText()))
      await card.locator('[data-stat-open]').click()
      const list = pg.locator('[data-list="habits"]')
      await list.locator('[data-list-habit]').first().waitFor({ timeout: 10000 })
      must((await list.innerText()).includes(`I55 Walk ${width}`) && (await list.innerText()).includes(`I55 Read ${width}`), 'the habits are not named in the list: ' + (await list.innerText()))
      const walk = list.locator('[data-list-row]', { hasText: `I55 Walk ${width}` }).locator('[data-list-habit]')
      await walk.click()
      await pg.waitForTimeout(1000)
      must(/1 of 2/.test(await card.innerText()), 'the count did not move: ' + (await card.innerText()))
      const done = bench(`print(frappe.db.count("Life Habit Log", {"space": "${space}", "done": 1}))`).split('\n').pop()
      must(done === '1', 'the tick was not stored: ' + done)
      await walk.click() // put it back
      await pg.waitForTimeout(500)
      await noSideways()
    })

    await check('TODAY.27', `${width} px: no link on Today goes to an old route, and each opens where it says`, async () => {
      await today55()
      const hrefs = [...new Set(await pg.locator('[data-main] a[href]').evaluateAll((as) => as.map((a) => a.getAttribute('href'))))]
      for (const h of hrefs) {
        if (!h.startsWith('/life')) continue
        must(!OLD_ROUTES.test(h), 'Today links to an old route: ' + h)
        await one.open(h)
        const at = new URL(pg.url()).pathname
        must(at === new URL(h, base).pathname, `${h} landed on ${at}`)
      }
      await one.open('/life/today')
      for (const h of await pg.locator('[data-main] a[href]').evaluateAll((as) => as.map((a) => a.getAttribute('href')))) must(!OLD_ROUTES.test(h), 'old route ' + h)
    })

  } finally {
    if (one) await one.ctx.close()
    restore()
  }
}


// Issue 55, on the owner's demo site: every number of the old Open band appears where it counts, with the same count.
for (const width of WIDTHS) {
  const tag = `I55.${width}`
  let one = null
  try {
    one = await session('owner@lifeos.test', width)
    const pg = one.page
    await check('TODAY.29', `${width} px: each moved number is in its new place with the count the old card had (All tasks, Goals, Library, Brain Activity)`, async () => {
      const band = await one.api('counts.get', { space: SPACE, which: 'open_band' })
      const week = await one.api('counts.get', { space: SPACE, which: 'week' })
      const num = async (sel) => Number(/(\d[\d,]*)\s*$/.exec((await pg.locator(sel).first().innerText()).trim())[1].replace(/,/g, ''))
      await one.open('/life/goals/tasks')
      await pg.locator('[data-all-tasks][data-loaded="1"]').waitFor({ timeout: 10000 })
      must(await num('[data-task-show="open"]') === band.open_tasks.n, `All tasks says ${await num('[data-task-show="open"]')} open, the old card ${band.open_tasks.n}`)
      must(await num('[data-task-show="stuck"]') === band.stuck.n, `Untouched filter says ${await num('[data-task-show="stuck"]')}, the old card ${band.stuck.n}`)
      must(await pg.locator('[data-all-tasks-reset]').count() === 1, 'Reset is not on All tasks')
      await one.open('/life/goals')
      await pg.locator('[data-goal-numbers]').waitFor({ timeout: 10000 })
      for (const [k, n] of [['goals', band.goals.n], ['open_goals', band.open_goals.n], ['idle_goals', band.idle_goals.n]]) {
        must(await num(`[data-goal-number="${k}"]`) === n, `Goals says ${k} ${await num(`[data-goal-number="${k}"]`)}, the old card ${n}`)
      }
      await one.open('/life/library?all=1') // all=1: not the filters the list remembered from the width before
      await pg.locator('[data-lib-numbers]').waitFor({ timeout: 10000 })
      must(await num('[data-lib-number="notes_sources"]') === band.notes_sources.n, 'Library notes and sources differ from the old card')
      must(await num('[data-lib-unopened]') === band.notes_unopened.n, `Not opened in 90 days says ${await num('[data-lib-unopened]')}, the old card ${band.notes_unopened.n}`)
      await pg.locator('[data-lib-unopened]').click()
      await pg.waitForTimeout(800)
      must(new URL(pg.url()).searchParams.get('unopened') === '1', 'the filter is not in the address')
      await one.open('/life/brain/activity')
      await pg.locator('[data-flow]').waitFor({ timeout: 10000 })
      must(await num('[data-flow-in]') === week.in.n && await num('[data-flow-out]') === week.out.n, `Activity says ${await num('[data-flow-in]')} in, ${await num('[data-flow-out]')} out; the old line ${week.in.n}, ${week.out.n}`)
      await one.open('/life/goals/cycles')
      await pg.locator('[data-main]').waitFor({ timeout: 10000 })
    })
    // issue 102: the AI service has no credit
    await check('TODAY.30', `${width} px: with the fake AI failing on credit, Today shows "The Brain is off" with a link to Settings > AI, until a call works`, async () => {
      bench(`from frappe.installer import update_site_config
update_site_config("lifeos_fake_ai_error", {"status": 400, "message": "Your credit balance is too low to access the Anthropic API."})
frappe.defaults.clear_default("lifeos_ai_off", parent="__default")`)
      try {
        bench(`from lifeos.ai import client\nclient.note_unavailable(client.error_from(400, "Your credit balance is too low to access the Anthropic API."))`) // a Brain call failed on credit
        await one.open('/life')
        await pg.locator('[data-brain-off]').waitFor({ timeout: 15000 })
        must(/The Brain is off: .*credit/i.test(await pg.locator('[data-brain-off]').innerText()), 'Today does not say the Brain is off')
        await pg.locator('[data-brain-off-open]').click()
        await pg.waitForURL(/\/life\/settings/, { timeout: 10000 })
      } finally {
        bench(`from frappe.installer import update_site_config
update_site_config("lifeos_fake_ai_error", {})`)
      }
      // a call that works clears it
      await one.api('settings.test_ai_connection')
      await one.open('/life')
      await pg.locator('[data-today-sub]').waitFor({ timeout: 15000 })
      must((await pg.locator('[data-brain-off]').count()) === 0, 'the Brain stays off after a call worked')
    })
  } finally {
    if (one) await one.ctx.close()
  }
}

// Issue 99: notes on events, hiding a Google event, all-day dates, the week's bars and its drawer. Two events that came from Google are made
// in the week of today (Google's all-day end is the day after the last day), and removed after.
for (const width of WIDTHS) {
  const phone = width < 800
  const { pg, s, settle } = await uxKit(width)
  const D = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
  const M = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  const mon = plusDays(today, -((new Date(today + 'T12:00:00Z').getUTCDay() + 6) % 7))
  const [tue, wed, thu] = [1, 2, 3].map((n) => plusDays(mon, n))
  const dm = (d) => `${Number(d.slice(8))} ${M[Number(d.slice(5, 7)) - 1]}`
  const wedding = `Wedding ${stamp} ${width}`, trip = `Trip ${stamp} ${width}`, mine = `Lunch ${stamp} ${width}`
  const make = (title, a, b, google) => bench(`import json
d = frappe.get_doc({"doctype": "Event", "subject": "${title}", "starts_on": "${a}", "ends_on": "${b}", "all_day": ${google ? 1 : 0}, "event_type": "Public", "life_space": "Private", "pulled_from_google_calendar": ${google ? 1 : 0}}).insert(ignore_permissions=True)
print(d.name)`).split('\n').pop()
  const ev = {
    wedding: make(wedding, `${mon} 00:00:00`, `${tue} 00:00:00`, true), trip: make(trip, `${tue} 00:00:00`, `${thu} 00:00:00`, true),
    mine: make(mine, `${wed} 12:00:00`, `${wed} 13:00:00`, false),
  }
  const chip = (name) => pg.locator(`[data-week-grid] [data-ref="event:${name}"]`)
  const open = async (name) => { await s.open('/life/today/week?mode=calendar'); await pg.locator('[data-week-grid]').waitFor({ timeout: 10000 }); await pg.locator(`[data-ref="event:${name}"]`).first().click(); await settle() }
  try {
    await check('TODAY.50', `${width} px: an event in Week opens without "Open full page", the path reads "Week / Event" and a note shows at once`, async () => {
      await open(ev.mine)
      must(await pg.locator('[data-pane-full]').count() === 0, 'an event has Open full page')
      must((await pg.locator('[data-pane-path]').innerText()).trim() === 'Week / Event', 'the path reads ' + await pg.locator('[data-pane-path]').innerText())
      await pg.locator('[data-note-box]').fill(`Bring the deck ${stamp}`)
      await pg.locator('[data-note-add]').click()
      await pg.locator('[data-note]', { hasText: `Bring the deck ${stamp}` }).waitFor({ timeout: 8000 })
      must((await pg.locator('[data-note]').first().innerText()).includes('You'), 'the note does not say who wrote it')
      await pg.locator('[data-note-make-task]').first().click()
      await pg.locator('[data-note-task]').first().waitFor({ timeout: 8000 })
      // it is still there after the pane is closed and opened again
      await open(ev.mine)
      must(await pg.locator('[data-note]', { hasText: `Bring the deck ${stamp}` }).count() === 1, 'the note is gone after reopening')
      await pg.locator('[data-note-delete]').first().click()
      await pg.getByRole('button', { name: 'Delete', exact: true }).last().click()
      await pg.locator('[data-notes-empty]').waitFor({ timeout: 8000 })
    })
    await check('TODAY.51', `${width} px: a Google event offers Hide in Life OS (not red, no Remove); hiding it takes it off the week and Show hidden events brings it back`, async () => {
      await open(ev.wedding)
      const hide = pg.locator('[data-event-hide]')
      must(await hide.count() === 1 && !/red/.test(await hide.getAttribute('class')), 'no plain Hide in Life OS button')
      must(await pg.locator('[data-event-delete]').count() === 0 && await pg.getByRole('button', { name: 'Remove' }).count() === 0, 'a Google event can be removed')
      await hide.click()
      await pg.locator('[data-pane]').waitFor({ state: 'detached', timeout: 8000 })
      await settle()
      must(await chip(ev.wedding).count() === 0, 'a hidden event is still on the week')
      must(bench(`print(frappe.db.exists("Event", "${ev.wedding}") and frappe.db.get_value("Event", "${ev.wedding}", "life_hidden"))`).split('\n').pop() === '1', 'the flag is not set, or the event is gone')
      await pg.locator('[data-week-menu]').click()
      await pg.getByRole('menuitem', { name: 'Show hidden events' }).click()
      await chip(ev.wedding).first().waitFor({ timeout: 8000 })
      await chip(ev.wedding).first().click()
      await settle()
      await pg.locator('[data-event-show]').click()
      await settle()
    })
    await check('TODAY.52', `${width} px: a Google all-day event reads "weekday, day month · all day"; a two-day one is one bar across its days`, async () => {
      await open(ev.wedding)
      const want = `${D[new Date(mon + 'T12:00:00Z').getUTCDay()]}, ${dm(mon)} · all day`
      must((await pg.locator('[data-event-when]').innerText()).trim() === want, `reads "${await pg.locator('[data-event-when]').innerText()}", not "${want}"`)
      await open(ev.trip)
      const want2 = `${Number(tue.slice(8))}–${dm(wed)} · all day`
      must((await pg.locator('[data-event-when]').innerText()).trim() === want2, `reads "${await pg.locator('[data-event-when]').innerText()}", not "${want2}"`)
      await pg.keyboard.press('Escape')
      await settle()
      must(await pg.locator(`[data-week-bar][data-ref="event:${ev.trip}"]`).count() === 1, 'the trip is not one bar')
      must(await chip(ev.trip).count() === 0, 'the trip is also a card on each day')
      if (!phone) {
        const bar = await pg.locator(`[data-week-bar][data-ref="event:${ev.trip}"]`).boundingBox()
        const day = await pg.locator('[data-week-grid] [data-day]').first().boundingBox()
        must(bar.width > day.width * 1.8, `the bar (${bar.width}) does not span two days (${day.width})`)
      }
    })
    if (!phone) await check('TODAY.53', `${width} px: with the drawer open all seven day headers of Week are visible`, async () => {
      await open(ev.mine)
      const pane = await pg.locator('[data-pane]').boundingBox()
      const heads = await pg.locator('[data-week-grid] [data-open-day]').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, w: r.width } }))
      must(heads.length === 7 && heads.every((h) => h.w > 0 && h.r <= pane.x + 1 && h.l >= 0), `the days are ${JSON.stringify(heads)} beside a drawer at ${pane.x}`)
    })
    await check('TODAY.54', `${width} px: the Week toolbar has no Reset and nothing cut off, the heading is the dates, and + Capture offers Important date`, async () => {
      for (const url of ['/life/today/week?view=calendar', '/life/today/week']) {
        await s.open(url)
        await pg.locator('[data-page-head]').waitFor({ timeout: 10000 })
        const head = await pg.locator('[data-page-head]').evaluate((el) => ({ text: el.innerText, cut: el.scrollWidth > el.clientWidth + 1, page: document.documentElement.scrollWidth > window.innerWidth + 1 }))
        must(!/Reset|Add important/.test(head.text) && !head.cut && !head.page, `the toolbar on ${url}: ${JSON.stringify(head)}`)
        must(/^\d+( [A-Za-z]+)? – \d+ [A-Za-z]+/m.test(head.text), `the heading on ${url} is not a date range: ${head.text.slice(0, 80)}`)
      }
      await s.open('/life')
      if (!phone) { await pg.locator('[data-nav-chat]').click(); await pg.locator('[data-ask-panel]:visible').waitFor({ timeout: 8000 }) }
      await pg.locator(phone ? '[data-chat-bar] [data-ask-attach]' : '[data-ask-panel] [data-ask-attach]').click()
      await settle()
      await pg.getByRole('menuitem', { name: 'Important date' }).click()
      await pg.getByRole('dialog', { name: 'Add important date' }).waitFor({ timeout: 8000 })
      await pg.keyboard.press('Escape')
    })
  } finally {
    bench(`for n in ${JSON.stringify(Object.values(ev))}:
    frappe.db.delete("Comment", {"reference_doctype": "Event", "reference_name": n})
    frappe.db.delete("Life Task", {"event": n})
    frappe.delete_doc("Event", n, force=1, ignore_permissions=True)`)
  }
}


// Issue 100: Year is the cycles around today, with key dates by week; Month names key dates and counts the other events. A cycle is made
// for the run (and the space's own running cycle put aside), so today is always in the second column. Titles start "I100 ".
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  // a Wednesday three or more weeks ahead whose week holds no key date yet (a document expiring, say), so the five are the week's only
  const taken = new Set((await s.api('calendar.year_plan', { space: SPACE })).key_weeks.map((k) => k.start))
  let wed = nextWeekday('Wednesday', 21)
  while (taken.has(plusDays(wed, -2))) wed = plusDays(wed, 7)
  const weekOf = plusDays(wed, -2)
  const monday = plusDays(today, -((new Date(today + 'T12:00:00Z').getUTCDay() + 6) % 7))
  const [keyDay, meetDay] = [0, 1, 2, 3, 4, 5, 6].map((n) => plusDays(monday, n)).filter((d) => d !== today)
  const five = [1, 2, 3, 4, 5].map((n) => `I100 five ${n} ${width} ${stamp}`)
  // lone key dates: two in neighbouring weeks, so one title has no room, and one on its own
  const singles = [[plusDays(wed, -14), `I100 single a ${width} ${stamp}`], [plusDays(wed, -7), `I100 single b with a long name ${width} ${stamp}`], [plusDays(wed, 28), `I100 single c ${width} ${stamp}`]]
  const monthKey = `I100 month key ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
from frappe.utils import add_days, today
active = frappe.get_all("Life Cycle", filters={"space": "${SPACE}", "status": "Active"}, pluck="name")
for n in active: frappe.db.set_value("Life Cycle", n, "status", "Planned")
cycle = frappe.get_doc({"doctype": "Life Cycle", "space": "${SPACE}", "title": "I100 cycle ${width} ${stamp}", "start_date": add_days(today(), -14), "status": "Active"}).insert(ignore_permissions=True).name
def event(title, start, end=None, all_day=1):
    return frappe.get_doc({"doctype": "Event", "subject": title, "starts_on": start, "ends_on": end, "all_day": all_day, "event_type": "Public", "life_space": "${SPACE}"}).insert(ignore_permissions=True).name
names = [event(t, "${wed} 00:00:00") for t in ${JSON.stringify(five)}]
names += [event(t, d + " 00:00:00") for d, t in ${JSON.stringify(singles)}]
names.append(event("${monthKey}", "${keyDay} 00:00:00"))
names += [event(f"I100 meeting {i} ${width} ${stamp}", "${meetDay} 1%d:00:00" % i, "${meetDay} 1%d:30:00" % i, 0) for i in (0, 1)]
print(json.dumps({"active": active, "cycle": cycle, "events": names}))`).split('\n').pop())
  try {
    await check('TODAY.58', `${width} px: Month names a key date, counts the day's meetings, and the count opens Day`, async () => {
      await s.open('/life/today/month?mode=calendar')
      await pg.locator('[data-month-grid]').waitFor({ timeout: 10000 })
      if (phone) {
        await pg.locator(`[data-month-grid] [data-day="${keyDay}"] > button`).click()
        await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), monthKey, { timeout: 5000 })
        await pg.locator(`[data-month-grid] [data-day="${meetDay}"] > button`).click()
        await pg.waitForFunction(() => /\d meetings/.test(document.querySelector('[data-month-list]')?.innerText || ''), null, { timeout: 5000 })
        await pg.locator('[data-open-day]').click()
      } else {
        await pg.waitForFunction(([d, t]) => document.querySelector(`[data-month-grid] [data-day="${d}"]`)?.innerText.includes(t), [keyDay, monthKey], { timeout: 10000 })
        const cell = pg.locator(`[data-month-grid] [data-day="${meetDay}"]`)
        const count = cell.locator('[data-meetings]')
        await count.waitFor({ timeout: 10000 })
        must(/^\d+ meetings$/.test((await count.innerText()).trim()) && Number(await count.getAttribute('data-count')) >= 2, 'the day does not count its meetings')
        must(!(await cell.innerText()).includes('I100 meeting'), 'a meeting is named in Month')
        await count.click()
      }
      await pg.waitForURL((u) => u.pathname === '/life/today' && u.searchParams.get('date') === meetDay, { timeout: 10000 })
      await pg.locator('[data-day-timeline]').waitFor({ timeout: 10000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('TODAY.60', `${width} px: Year and Month in light and dark have no script error and nothing cut off`, async () => {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        for (const [path, sel] of [['/life/today/year?mode=calendar', '[data-year-months]'], ['/life/today/month?mode=calendar', '[data-month-grid]']]) {
          await s.open(path)
          await pg.locator(sel).waitFor({ timeout: 10000 })
          await pg.waitForTimeout(400)
          await noSideways()
          const cut = await pg.evaluate(() => [...document.querySelectorAll('[data-year-months], [data-month-grid]')].filter((e) => e.scrollWidth > e.clientWidth + 1).length)
          must(cut === 0, `${path} is cut off in ${scheme}`)
        }
      }
      await pg.emulateMedia({ colorScheme: 'light' })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`for n in ${JSON.stringify(made.events)}: frappe.delete_doc("Event", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Skill Correction", {"skill": "key-date"})
frappe.delete_doc("Life Cycle", "${made.cycle}", force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.active)}: frappe.db.set_value("Life Cycle", n, "status", "Active")`)
    await s.ctx.close()
  }
}

// Issue 118: the waiting pile is never on Today; one line says when some of it is late.
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const title = `I118T waiting ${width} ${stamp}`
  try {
    await check('TODAY.61', `${width} px: a waiting task is not on Today; past its check-by date it is one line that names who and leads to the review`, async () => {
      const name = bench(`from frappe.utils import add_days, today
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${title}", "status": "Waiting", "waiting_on": "Meera I118T", "due_date": today(), "check_by": add_days(today(), 2)}).insert(ignore_permissions=True)
print(t.name)`).split('\n').pop()
      await s.open('/life/today')
      await pg.locator("[data-today-sub]").first().waitFor({ timeout: 15000 }).catch(() => {})
      await pg.waitForTimeout(1200)
      must(!(await pg.getByText(title).count()), 'the waiting task is on Today')
      must(!(await pg.locator('[data-waiting-past]').count()), 'the line shows before the check-by date')
      bench(`from frappe.utils import add_days, today
frappe.db.set_value("Life Task", "${name}", "check_by", add_days(today(), -1))`)
      await s.open('/life/today')
      await pg.locator('[data-waiting-past]').waitFor({ timeout: 15000 })
      const t = await pg.locator('[data-waiting-past]').innerText()
      must(/a day late/.test(t) && t.includes('Meera I118T'), 'the line says: ' + t)
      must(!(await pg.getByText(title, { exact: true }).count()), 'the waiting task is on Today past its date')  // the one line names it inside a sentence; it is not a row
      await pg.locator('[data-waiting-look]').click()
      await pg.locator('[data-list="waiting-overdue"]').waitFor({ timeout: 10000 })
    })
  } finally {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "I118T %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Issue 120: one chat on every screen. The panel (laptop) stays open between screens, knows the record on screen, takes dropped files and notes on the open event;
// the real run (Flow's agent and tools) against the fake model of tools/fake_openai.py.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const made = { events: [], goals: [], items: [], tasks: [] }
  const panel = () => pg.locator('[data-ask-panel]:visible').first()
  // the thread holds earlier answers: wait until the one just asked for is written
  const answered = async () => { await pg.waitForTimeout(700); await panel().locator('[data-ask-working]').waitFor({ state: 'detached', timeout: 90000 }); await panel().locator('[data-ask-answer][data-status="Done"]').last().waitFor({ timeout: 5000 }) }
  const openPanel = async () => {
    if (phone) { await pg.locator('[data-chat-bar-open]').click() } else if (!(await pg.locator('[data-ask-panel]:visible').count())) await pg.locator('[data-nav-chat]').click()
    await panel().waitFor({ timeout: 10000 })
  }
  try {
    chatOn()
    if (!phone) {
      await check('TODAY.62', `${width} px: the chat panel stays open with its messages from Today to the Library to a goal, and its chip shows the goal`, async () => {
        const goal = bench(`g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "I120 chip goal ${stamp}", "area": "${areaId('Career')}", "horizon": "Long term", "done_when": "Done"}).insert(ignore_permissions=True)
print(g.name)`).split('\n').pop()
        made.goals.push(goal)
        await s.open('/life/today')
        await pg.locator('[data-nav-chat]').click()
        await panel().waitFor({ timeout: 10000 })
        await pg.locator('[data-ask-input]:visible').fill('What tasks do I have?')
        await pg.locator('[data-ask-send]:visible').click()
        await answered()
        await pg.locator('[data-sidebar] [data-nav-item="Library"]').first().click()
        await pg.waitForURL((u) => u.pathname.startsWith('/life/library'), { timeout: 10000 })
        const kept = await pg.locator('[data-ask-panel]:visible').count() ? (await pg.locator('[data-ask-panel]:visible [data-ask-answer]').last().innerText()).slice(0, 80) : 'NO PANEL'
        must(kept.includes('From the tool'), 'the panel lost its messages on the Library: ' + kept)
        await pg.evaluate((g) => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push(`/goals/${g}`), goal) // in the app, not a reload: the panel keeps its messages
        await pg.locator('[data-ask-scope]:visible').waitFor({ timeout: 10000 })
        await pg.waitForFunction((t) => document.querySelector('[data-ask-scope]')?.textContent.includes(t), `I120 chip goal ${stamp}`, { timeout: 10000 })
        must((await pg.locator('[data-ask-scope]').first().innerText()).startsWith('About:'), 'the chip does not say About')
        await pg.locator('[data-ask-scope-clear]').click()
        must((await pg.locator('[data-ask-scope]').first().innerText()).includes('Everything'), 'removing the chip did not make it about everything')
        await pg.locator('[data-ask-expand]').click()
        must(await pg.locator('[data-ask-panel][data-wide="1"]').count(), 'Expand did not widen the panel')
        await pg.locator('[data-ask-close]').click()
      })
    }
    if (!phone) await check('TODAY.63', `${width} px: "add a note: quote by Friday" with an event open adds a Comment on that event, and the Done list shows it with Change`, async () => {
      const ev = bench(`e = frappe.get_doc({"doctype": "Event", "subject": "I120 RSH Global meeting ${stamp}", "starts_on": frappe.utils.today() + " 21:00:00", "event_type": "Public", "life_space": "${SPACE}"}).insert(ignore_permissions=True)
print(e.name)`).split('\n').pop()
      made.events.push(ev)
      await s.open(`/life/today/week?open=event:${ev}`)
      await pg.locator('[data-pane-title]').waitFor({ timeout: 10000 })
      await openPanel()
      await pg.waitForFunction(() => /About:/.test(document.querySelector('[data-ask-scope]')?.textContent || ''), null, { timeout: 10000 })
      await pg.locator('[data-ask-input]:visible').fill('add a note: quote by Friday')
      await pg.locator('[data-ask-send]:visible').click()
      await answered()
      const line = panel().locator('[data-ask-done-line]').last()
      must((await line.innerText()).includes('Change'), 'the Done line has no Change: ' + await line.innerText())
      const n = bench(`print(frappe.db.count("Comment", {"reference_doctype": "Event", "reference_name": "${ev}", "content": "quote by Friday"}))`).split('\n').pop()
      must(Number(n) === 1, 'no Comment on the event: ' + n)
    })
    await check('TODAY.82', `${width} px: "mark it done" on a task open in the Drawer: the Done list shows the line with Undo and the task leaves the open list`, async () => {
      const task = bench(`t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I149 finish me ${stamp}", "status": "Open"}).insert(ignore_permissions=True)
print(t.name)`).split('\n').pop()
      made.tasks.push(task)
      await s.open(`/life/today?open=task:${task}`)
      await pg.locator('[data-pane-title]').waitFor({ timeout: 10000 })
      if (phone) await pg.keyboard.press('Control+k') // the task fills the phone: Cmd/Ctrl+K opens the chat over it
      else await openPanel()
      await panel().waitFor({ timeout: 10000 })
      await pg.locator('[data-ask-input]:visible').fill('mark it done')
      await pg.locator('[data-ask-send]:visible').click()
      await answered()
      const line = panel().locator('[data-ask-done-line]').last()
      must(await line.locator('[data-ask-undo]').count() === 1, 'the Done line has no Undo: ' + await line.innerText())
      must((await line.innerText()).includes('I149 finish me'), 'the Done line is: ' + await line.innerText())
      const status = bench(`print(frappe.db.get_value("Life Task", "${task}", "status"))`).split('\n').pop()
      must(status === 'Done', 'the task is ' + status)
      const open = await s.api('tasks.list', { status: 'Open', space: SPACE })
      must(!JSON.stringify(open).includes(task), 'the task is still in the open list')
      await noSideways()
    })
    await check('TODAY.83', `${width} px: Chat "tell Subhangee it's done, email ok" shows a draft card with Send, Edit and Drop and sends nothing; Send sends it once and the Done list shows the line`, async () => {
      bench(`if not frappe.db.exists("Life Person", {"space": "${SPACE}", "full_name": "Subhangee I150"}):
    frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Subhangee I150", "kind": "Person", "email": "subhangee150@example.com"}).insert(ignore_permissions=True)
if not frappe.db.exists("Life Mail Account", {"space": "${SPACE}", "user": "owner@lifeos.test"}):
    frappe.get_doc({"doctype": "Life Mail Account", "space": "${SPACE}", "user": "owner@lifeos.test", "provider": "gmail", "address": "owner@example.com", "label": "Personal", "is_default": 1}).insert(ignore_permissions=True)
from lifeos.mail import fake
fake.clear()`)
      const sent = () => bench('from lifeos.mail import fake\nprint(len([c for c in fake.calls() if c["call"] == "send"]))').split('\n').pop()
      await s.open('/life/today')
      if (phone) await pg.keyboard.press('Control+k')
      else await openPanel()
      await panel().waitFor({ timeout: 10000 })
      await pg.locator('[data-ask-input]:visible').fill("tell Subhangee it's done, email ok")
      await pg.locator('[data-ask-send]:visible').click()
      await answered()
      const card = panel().locator('[data-ask-draft]').last()
      await card.waitFor({ timeout: 10000 })
      for (const k of ['send', 'edit', 'drop']) must(await card.locator(`[data-ask-draft-${k}]`).count() === 1, `the card has no ${k}`)
      must((await card.innerText()).includes('Subhangee I150'), 'the card is for: ' + await card.innerText())
      must(Number(sent()) === 0, 'something was sent before Send')
      await noSideways()
      await card.locator('[data-ask-draft-send]').click()
      await card.locator('[data-ask-draft-sent]').waitFor({ timeout: 15000 })
      must(Number(sent()) === 1, 'Send did not send once: ' + sent())
      must((await panel().locator('[data-ask-done-line]').last().innerText()).includes('Emailed Subhangee I150'), 'the Done line is: ' + await panel().locator('[data-ask-done-line]').last().innerText())
      must(await panel().locator('[data-ask-done-line]').last().locator('[data-ask-undo]').count() === 0, 'a sent email has an Undo')
      await noSideways()
    })
    if (!phone) {
      await check('TODAY.64', `${width} px: a PDF bill dropped on the page is attached to the chat and, sent, becomes a capture for the Brain, listed with Change`, async () => {
        await s.open('/life/today')
        await pg.evaluate(async (b64) => {
          const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
          const dt = new DataTransfer()
          dt.items.add(new File([bytes], 'water-bill-I120.pdf', { type: 'application/pdf' }))
          for (const type of ['dragenter', 'dragover', 'drop']) document.body.dispatchEvent(new DragEvent(type, { dataTransfer: dt, bubbles: true, cancelable: true }))
        }, PDF.toString('base64'))
        await pg.locator('[data-ask-file]:visible').waitFor({ timeout: 10000 })
        must((await pg.locator('[data-ask-file]').first().innerText()).includes('water-bill-I120.pdf'), 'the dropped file is not attached')
        await pg.locator('[data-ask-input]:visible').fill('file this bill')
        await pg.locator('[data-ask-send]:visible').click()
        await answered()
        const line = panel().locator('[data-ask-done-line]').last()
        must((await line.innerText()).includes('water-bill-I120.pdf') && (await line.innerText()).includes('Change'), 'the Done line is: ' + await line.innerText())
        const item = bench(`print(frappe.db.get_value("Life Inbox Item", {"title": "water-bill-I120.pdf", "space": "${SPACE}"}, "name") or "")`).split('\n').pop()
        must(item, 'no capture was made for the bill')
        made.items.push(item)
      })
    }
    await check('TODAY.65', `${width} px, light and dark: the chat open has no script error and nothing is cut off`, async () => {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        await s.open('/life/today')
        await openPanel()
        await pg.waitForTimeout(400)
        await noSideways()
        const cut = await pg.evaluate(() => { const r = document.querySelector('[data-ask-panel]')?.getBoundingClientRect(); return !r || r.right > window.innerWidth + 1 || r.left < -1 })
        must(!cut, `the chat is cut off in ${scheme}`)
        if (phone) await pg.keyboard.press('Escape'); else await pg.locator('[data-ask-close]').click()
      }
      await pg.emulateMedia({ colorScheme: 'light' })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    chatOff()
    bench(`for n in ${JSON.stringify(made.events)}: frappe.delete_doc("Event", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.goals)}: frappe.delete_doc("Life Goal", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.items)}: frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.tasks)}: frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Communication", filters={"reference_doctype": "Life Person", "recipients": "subhangee150@example.com"}, pluck="name"): frappe.delete_doc("Communication", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": "Subhangee I150"}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Mail Account", filters={"space": "${SPACE}", "user": "owner@lifeos.test"}, pluck="name"): frappe.delete_doc("Life Mail Account", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Agent Action", {"space": "${SPACE}", "agent": "lifeos-chat"})`)
    await s.ctx.close()
  }
}

// Issue 123: the Today dashboard. The ruler on every view, four cards and two panels in each, everything in the pane.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const tag = `I123 ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const inPane = () => new URL(pg.url()).searchParams.get('open')
  const dash = async (p) => { await s.open(p); await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 }) }
  const made = { items: [], tasks: [], rules: [] }
  try {
    await check('TODAY.66', `${width} px: Calendar has the ruler directly above the calendar and Overview has none; it is centred on today, nothing is clipped, and its clicks work`, async () => {
      const VIEWS = [['/life/today', '[data-day-timeline]'], ['/life/today/week', '[data-week-grid]'], ['/life/today/month', '[data-month-grid]'], ['/life/today/year', '[data-year-months]']]
      for (const [p, cal] of VIEWS) {
        await s.open(p + '?mode=overview')
        await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
        must(await pg.locator('[data-ruler]').count() === 0, `Overview of ${p} has the ruler`)
        await s.open(p + '?mode=calendar')
        await pg.locator(cal).first().waitFor({ timeout: 15000 })
        must(await pg.locator('[data-ruler]').isVisible(), `no ruler on ${p}`)
        must(await pg.locator('[data-dash-card]').count() === 0, `Calendar of ${p} has cards`)
        const h = (await pg.locator('[data-ruler]').boundingBox()).height
        must(h <= 62, `the ruler is ${h} px tall`)
        // directly above the calendar: nothing but the legend between them, and the ruler ends before the calendar starts
        const gap = await pg.evaluate((sel) => { const r = document.querySelector('[data-ruler]').getBoundingClientRect(), c = document.querySelector(sel).getBoundingClientRect(); return c.top - r.bottom }, cal)
        must(gap >= 0 && gap < 80, `the ruler is ${gap} px from the calendar`)
      }
      await s.open('/life/today/week?mode=calendar')
      await pg.locator('[data-ruler]').waitFor({ timeout: 10000 })
      const box = await pg.locator('[data-ruler]').boundingBox(), mid = box.x + box.width / 2
      const centre = async (sel) => { const b = await pg.locator(sel).boundingBox(); return b.x + b.width / 2 }
      const monthLabel = new Date(today + 'T12:00:00Z').toLocaleString('en', { month: 'long', timeZone: 'UTC' })
      must(Math.abs((await centre(`[data-ruler-month][data-current] [data-ruler-label]`)) - mid) <= 10, `${monthLabel} is not at the ruler's centre`)
      must(Math.abs((await centre(`[data-ruler-day="${today}"] [data-ruler-label]`)) - mid) <= 10, "today is not at the ruler's centre")
      must((await pg.locator('[data-ruler-month]').count()) === 11 && (await pg.locator('[data-ruler-day]').count()) === 31, 'the ruler is not 11 months and 31 days')
      const labels = await pg.locator('[data-ruler-label]').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { t: e.textContent, l: r.left, r: r.right } }))
      const vw = await pg.evaluate(() => window.innerWidth)
      for (const b of labels) must(b.l >= 0 && b.r <= vw, `"${b.t}" is clipped`)
      const dayNo = Number(today.slice(8))
      const days = await pg.locator('[data-ruler-days] [data-ruler-label]').allInnerTexts()
      must(days.some((t) => t.startsWith(DAY_SHORT(today)) && t.endsWith(String(dayNo))), `today's label is not "Thu 26" style: ${days}`)
      const months = await pg.locator('[data-ruler-months] [data-ruler-label]').allInnerTexts()
      if (phone) must(days.length === 1 && months.length === 1, `a phone labels ${days.length} days and ${months.length} months`)
      else must(days.length === 5 && months.length === 3, `the labels are ${days} and ${months}`)
      must(Boolean(await pg.locator(`[data-ruler-day="${today}"]`).getAttribute('aria-label')), 'a tick has no date')
      // another day opens in the Drawer
      const other = plusDays(today, 3)
      await pg.locator(`[data-ruler-day="${other}"]`).click()
      await pg.waitForFunction((d) => new URL(location.href).searchParams.get('open') === 'day:' + d, other, { timeout: 8000 })
      must(pathOf(pg) === '/life/today/week', 'a day took the page away')
      await pg.keyboard.press('Escape')
      await pg.waitForFunction(() => !new URL(location.href).searchParams.get('open'), null, { timeout: 8000 })
      // a month tick moves the calendar to that month
      const nextKey = plusDays(`${today.slice(0, 7)}-01`, 32).slice(0, 7)
      await pg.locator(`[data-ruler-month="${nextKey}"]`).click()
      await pg.waitForFunction((k) => (new URL(location.href).searchParams.get('date') || '').startsWith(k), nextKey, { timeout: 8000 })
      must(pathOf(pg) === '/life/today/week', 'a month tick took the page away')
      // today opens Day
      await pg.locator(`[data-ruler-day="${today}"]`).click()
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.67', `${width} px: Week's Goals: a goal row opens the goal in the pane and the dashboard stays on screen`, async () => {
      await dash('/life/today/week?mode=goals')
      const row = pg.locator('[data-panel="goals"] [data-dash-row]').first()
      await row.waitFor({ timeout: 10000 })
      await row.locator('button').first().click()
      await pg.waitForFunction(() => /^goal:/.test(new URL(location.href).searchParams.get('open') || ''), null, { timeout: 8000 })
      await pg.locator('[data-pane]:visible').first().waitFor({ timeout: 10000 })
      must(pathOf(pg) === '/life/today/week', 'the goal took the page away: ' + pathOf(pg))
      must(await pg.locator('[data-dashboard]').count() === 1, 'the dashboard is gone')
      if (!phone) must(await pg.locator('[data-dash-cards]').isVisible(), 'the dashboard is hidden')
      await pg.keyboard.press('Escape')
      await pg.waitForFunction(() => !new URL(location.href).searchParams.get('open'), null, { timeout: 8000 })
    })

    await check('TODAY.68', `${width} px: Needs you opens its rows in the pane; a row opens in the same pane with Back; j moves to the next; a reload keeps the list open`, async () => {
      const ids = JSON.parse(bench(`import json
from frappe.utils import now_datetime
out = []
for i in range(3):
    it = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${tag} needs " + str(i), "source_type": "Email", "status": "To Review", "raw_text": "x", "received_on": now_datetime()}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": it.name, "kind": "Note", "preview": "${tag} note", "payload": "{}", "status": "Pending"}).insert(ignore_permissions=True)
    out.append(it.name)
print(json.dumps(out))`).split('\n').pop())
      made.items.push(...ids)
      const total = (await s.api('brain.needs_you', { space: SPACE, limit: 50 })).total
      await dash('/life/today/week')
      const card = pg.locator('[data-card="needs"]')
      must(Number((await card.locator('[data-stat-value]').innerText()).replace(/\D/g, '')) === total, 'the card does not show ' + total)
      await card.locator('[data-stat-open]').click()
      const list = pg.locator('[data-list="needs-you"]')
      await list.waitFor({ timeout: 10000 })
      await list.locator('[data-list-row]').first().waitFor({ timeout: 10000 })
      must((await list.locator('[data-list-row]').count()) === Math.min(total, 50), `the list has ${await list.locator('[data-list-row]').count()} rows, not ${total}`)
      must(pathOf(pg) === '/life/today/week', 'the card took the page away')
      // a reload keeps the list open
      await pg.reload({ waitUntil: 'networkidle' })
      await pg.locator('[data-list="needs-you"] [data-list-row]').first().waitFor({ timeout: 10000 })
      must(inPane() === 'list:needs-you', 'a reload lost the list: ' + inPane())
      // a row opens in the same pane, Back returns, j moves to the next row
      const refs = await pg.locator('[data-list="needs-you"] [data-list-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-ref')))
      await pg.locator('[data-list="needs-you"] [data-list-row] button').first().click()
      await pg.waitForFunction((r) => new URL(location.href).searchParams.get('open') === r, refs[0], { timeout: 8000 })
      must(await pg.locator('[data-pane-back]').isVisible(), 'no Back in the pane')
      await pg.locator('[data-pane-back]').click()
      await pg.waitForFunction(() => new URL(location.href).searchParams.get('open') === 'list:needs-you', null, { timeout: 8000 })
      await pg.locator('[data-list="needs-you"] [data-list-row]').first().waitFor({ timeout: 10000 })
      await pg.locator('[data-list="needs-you"] [data-list-row] button').first().click()
      await pg.waitForFunction((r) => new URL(location.href).searchParams.get('open') === r, refs[0], { timeout: 8000 })
      await pg.waitForTimeout(600)
      await pg.keyboard.press('j')
      await pg.waitForFunction((r) => new URL(location.href).searchParams.get('open') === r, refs[1], { timeout: 8000 })
      must(await pg.locator('[data-pane-back]').isVisible(), 'Back is gone after j')
      await pg.keyboard.press('Escape') // Esc takes one layer off, the list shows; the second closes the Drawer
      await pg.waitForFunction(() => new URL(location.href).searchParams.get('open') === 'list:needs-you', null, { timeout: 8000 })
      await pg.waitForTimeout(700)
      await pg.keyboard.press('Escape')
      await pg.waitForFunction(() => !new URL(location.href).searchParams.get('open'), null, { timeout: 8000 })
      await noSideways()
    })

    await check('TODAY.69', `${width} px: "past check date" opens only the overdue waiting items; "rules learned" opens the rules, each with Change`, async () => {
      const out = JSON.parse(bench(`import json
from frappe.utils import add_days, today
for i, d in enumerate((-3, -1, 4)):
    frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${tag} wait " + str(i), "status": "Waiting", "waiting_on": "I123 person", "check_by": add_days(today(), d)}).insert(ignore_permissions=True)
rules = []
for i in range(4):
    rules.append(frappe.get_doc({"doctype": "Life Rule", "space": "${SPACE}", "made_by": "Brain", "enabled": 1, "sender": "i123-" + str(i) + "@example.com", "action": "Ask", "learned_from": "I123"}).insert(ignore_permissions=True).name)
past = frappe.db.count("Life Task", {"space": "${SPACE}", "status": "Waiting", "is_archived": 0, "check_by": ("<", today())})
print(json.dumps({"rules": rules, "past": past}))`).split('\n').pop())
      made.rules.push(...out.rules)
      await dash('/life/today/week')
      const part = pg.locator('[data-card="waiting"] [data-dash-part]')
      must((await part.innerText()).startsWith(`${out.past} late`), 'the card says: ' + await part.innerText())
      await part.click()
      const list = pg.locator('[data-list="waiting-overdue"]')
      await list.locator('[data-list-row]').first().waitFor({ timeout: 10000 })
      must((await list.locator('[data-list-row]').count()) === out.past, `the list has ${await list.locator('[data-list-row]').count()} rows, not ${out.past}`)
      must(!(await list.innerText()).includes('wait 2'), 'a waiting item that is not past is in the list')
      await pg.keyboard.press('Escape')
      await pg.waitForFunction(() => !new URL(location.href).searchParams.get('open'), null, { timeout: 8000 })
      await pg.locator('[data-brain-part]', { hasText: 'rules learned' }).click()
      const rules = pg.locator('[data-list="rules"]')
      await rules.locator('[data-rule-row]').first().waitFor({ timeout: 10000 })
      const n = await rules.locator('[data-rule-row]').count()
      must(n >= 4 && n === await rules.locator('[data-rule-change]').count(), `${n} rules, ${await rules.locator('[data-rule-change]').count()} with Change`)
      must(pathOf(pg) === '/life/today/week', 'the count took the page away')
    })

    await check('TODAY.70', `${width} px: Day, Week, Month and Year switch in place; Overview and Goals each have four cards and two panels; Open full page in the pane goes to the record's page`, async () => {
      await dash('/life/today?mode=overview')
      for (const [tab, want, key] of [['week', '/life/today/week', 'done'], ['month', '/life/today/month', 'done'], ['year', '/life/today/year', 'came'], ['day', '/life/today', 'due']]) {
        await pg.locator(`[data-place-tabs] [data-tab="${tab}"]`).first().click()
        await pg.waitForFunction((p) => location.pathname === p, want, { timeout: 10000 })
        await pg.locator(`[data-dashboard][data-view="${tab}"] [data-card="${key}"]`).waitFor({ timeout: 15000 })
        must((await pg.locator('[data-dash-card]').count()) === 4, `${tab} has ${await pg.locator('[data-dash-card]').count()} cards`)
        must((await pg.locator('[data-dash-panel]').count()) === 2, `${tab} has ${await pg.locator('[data-dash-panel]').count()} panels`)
        must(await pg.locator('[data-ruler], [data-day-timeline], [data-week-grid], [data-month-grid], [data-year-months]').count() === 0, `${tab} Overview has part of a calendar`)
        for (const gone of ['schedule', 'coming', 'key-dates']) must(await pg.locator(`[data-panel="${gone}"]`).count() === 0, `${tab} has the ${gone} panel`)
      }
      for (const [tab, path, key] of [['week', '/life/today/week', 'score'], ['month', '/life/today/month', 'plan'], ['year', '/life/today/year', 'year-goals'], ['day', '/life/today', 'top']]) {
        await dash(path + '?mode=goals')
        await pg.locator(`[data-dashboard][data-view="${tab}"][data-mode="goals"] [data-card="${key}"]`).waitFor({ timeout: 15000 })
        must((await pg.locator('[data-dash-card]').count()) === 4 && (await pg.locator('[data-dash-panel]').count()) === 2, `${tab} Goals has ${await pg.locator('[data-dash-card]').count()} cards and ${await pg.locator('[data-dash-panel]').count()} panels`)
      }
      const goal = bench(`print(frappe.db.get_value("Life Goal", {"space": "${SPACE}", "is_archived": 0}, "name"))`).split('\n').pop()
      await dash(`/life/today/week?mode=goals&open=goal:${goal}`)
      await pg.locator('[data-pane-full]:visible').first().click()
      await pg.waitForFunction((g) => location.pathname === '/life/goals/' + g, goal, { timeout: 10000 })
    })

    await check('TODAY.72', `${width} px, light and dark: every view, in Overview and in Calendar, has no script error and nothing cut off`, async () => {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        for (const p of ['/life/today', '/life/today/week', '/life/today/month', '/life/today/year']) {
          await dash(p)
          await pg.waitForTimeout(300)
          await noSideways()
          await s.open(p + '?mode=calendar')
          await pg.locator('[data-ruler]').waitFor({ timeout: 15000 })
          await pg.waitForTimeout(300)
          await noSideways()
        }
      }
      await pg.emulateMedia({ colorScheme: 'light' })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    // issue 132: Today has two modes
    const VIEWS132 = [['day', '/life/today'], ['week', '/life/today/week'], ['month', '/life/today/month'], ['year', '/life/today/year']]
    await check('TODAY.77', `${width} px: each of Day, Week, Month and Year has Overview · Goals · Calendar; switching keeps the period and sets ?mode=, a reload keeps it, and Today opens in the last mode used${phone ? '; on a phone the switch is full width under the tabs' : ''}`, async () => {
      const there = (mode) => pg.waitForFunction((m) => new URL(location.href).searchParams.get('mode') === m, mode, { timeout: 8000 })
      bench(`frappe.defaults.clear_user_default("lifeos_today_mode", user="owner@lifeos.test")\nfrappe.db.commit()`)  // a person who has never chosen
      for (const [view, path] of VIEWS132) {
        await s.open(path + '?mode=calendar')
        await pg.locator('[data-mode-switch]').waitFor({ timeout: 15000 })
        must((await pg.locator('[data-mode-option]').allInnerTexts()).join('|') === 'Overview|Goals|Calendar', `${view} has no Overview · Goals · Calendar`)
        if (phone) {
          const sw = await pg.locator('[data-mode-switch]').boundingBox(), tabs = await pg.locator('[data-place-tabs]').boundingBox()
          must(sw.width >= 390 - 40 && sw.y >= tabs.y + tabs.height - 2, `the switch is ${Math.round(sw.width)} px wide at y ${Math.round(sw.y)}, the tabs end at ${Math.round(tabs.y + tabs.height)}`)
        }
      }
      // never chosen: Today opens in Overview
      await s.open('/life/today')
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(await pg.locator('[data-ruler]').count() === 0, 'Today did not open in Overview for someone who has not chosen')
      // the period is kept: the week after this one, Calendar to Overview and back
      const next = plusDays(today, 7)
      await s.open(`/life/today/week?mode=calendar&date=${next}`)
      await pg.locator('[data-week-grid]').waitFor({ timeout: 15000 })
      const title = await pg.locator('[data-page-title]').innerText()
      await pg.locator('[data-mode-option="overview"]').click()
      await there('overview')
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(new URL(pg.url()).searchParams.get('date') === next && (await pg.locator('[data-page-title]').innerText()) === title, 'switching to Overview changed the week')
      await pg.reload({ waitUntil: 'networkidle' })
      await pg.locator('[data-dash-card]').first().waitFor({ timeout: 15000 })
      must(new URL(pg.url()).searchParams.get('mode') === 'overview', 'a reload lost the mode')
      await pg.locator('[data-mode-option="goals"]').click()
      await there('goals')
      await pg.locator('[data-dashboard][data-mode="goals"] [data-dash-card]').first().waitFor({ timeout: 15000 })
      // Today opens later in the last mode used (a user default, not browser storage)
      await pg.goto(new URL('/life/today?area=', pg.url()).href, { waitUntil: 'networkidle' })
      await pg.locator('[data-dashboard][data-mode="goals"] [data-dash-card]').first().waitFor({ timeout: 15000 })
      await pg.locator('[data-mode-option="calendar"]').click()
      await there('calendar')
      await pg.locator('[data-ruler]').waitFor({ timeout: 15000 })
      await pg.goto(new URL('/life/today?area=', pg.url()).href, { waitUntil: 'networkidle' })
      await pg.locator('[data-ruler]').waitFor({ timeout: 15000 })
      must(await pg.locator('[data-dash-card]').count() === 0, 'Today did not open in Calendar after it was chosen')
      await pg.locator('[data-mode-option="overview"]').click() // leave the owner where the other checks expect him
      await there('overview')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.78', `${width} px: Overview and Goals each have the four cards and two panels of their view and no calendar or ruler; Calendar has the ruler directly above the calendar and no cards`, async () => {
      const PANELS = { overview: { day: ['plate', 'needs'], week: ['active', 'waiting'], month: ['active', 'waiting'], year: ['active', 'by-month'] },
        goals: { day: ['top', 'habits'], week: ['goals', 'goal-work'], month: ['weeks', 'goals-due'], year: ['goals', 'cycles'] } }
      const CARDS = { overview: { day: 'due|needs|check|done', week: 'done|needs|waiting|filed', month: 'done|needs|waiting|filed', year: 'done|came|people|filed' },
        goals: { day: 'top|habits|score|work', week: 'score|top|track|habits', month: 'score|plan|due|reviews', year: 'year-goals|cycle|reviews|habits' } }
      const CAL = { day: '[data-day-timeline]', week: '[data-week-grid]', month: '[data-month-grid]', year: '[data-year-months]' }
      for (const [view, path] of VIEWS132) {
        for (const mode of ['overview', 'goals']) {
          await dash(`${path}?mode=${mode}`)
          const cards = await pg.locator('[data-dash-card]').evaluateAll((els) => els.map((e) => e.getAttribute('data-card')).join('|'))
          must(cards === CARDS[mode][view], `${view} ${mode} cards are ${cards}`)
          const keys = await pg.locator('[data-dash-panel]').evaluateAll((els) => els.map((e) => e.getAttribute('data-panel')))
          must(JSON.stringify(keys) === JSON.stringify(PANELS[mode][view]), `${view} ${mode} panels are ${keys}`)
          must(await pg.locator(`[data-ruler], ${CAL[view]}`).count() === 0, `${view} ${mode} has a calendar or the ruler`)
          const text = await pg.locator('[data-main]').innerText()
          for (const gone of ['Schedule', 'Coming up', 'Key dates']) must(!text.includes(gone), `${view} ${mode} still has ${gone}`)
        }
        await s.open(path + '?mode=calendar')
        await pg.locator(CAL[view]).first().waitFor({ timeout: 15000 })
        must(await pg.locator('[data-dash-card], [data-dash-panel]').count() === 0, `${view} Calendar has cards or panels`)
        const ruler = await pg.locator('[data-ruler]').boundingBox(), cal = await pg.locator(CAL[view]).first().boundingBox()
        must(ruler.y < cal.y && cal.y - (ruler.y + ruler.height) < 80, `${view}: the ruler is not directly above the calendar`)
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.79', `${width} px: Day Calendar lists an all-day event, a timed event, a task planned at 09:30 and a task due today in that order with the now line in place, each once`, async () => {
      const t = { allDay: `I132 all day ${width} ${stamp}`, timed: `I132 timed ${width} ${stamp}`, planned: `I132 planned ${width} ${stamp}`, due: `I132 due ${width} ${stamp}` }
      const names = JSON.parse(bench(`import json
from frappe.utils import add_days, today
sp = "${SPACE}"
mk = lambda s, a, b, all_day: frappe.get_doc({"doctype": "Event", "subject": s, "starts_on": a, "ends_on": b, "all_day": all_day, "event_type": "Public", "life_space": sp, "pulled_from_google_calendar": all_day}).insert(ignore_permissions=True).name
ev = [mk("${t.allDay}", today() + " 00:00:00", add_days(today(), 1) + " 00:00:00", 1), mk("${t.timed}", today() + " 08:00:00", today() + " 08:30:00", 0)]
tasks = [frappe.get_doc({"doctype": "Life Task", "space": sp, "title": "${t.planned}", "status": "Open", "scheduled_at": today() + " 09:30:00", "duration_min": 30}).insert(ignore_permissions=True).name,
  frappe.get_doc({"doctype": "Life Task", "space": sp, "title": "${t.due}", "status": "Open", "due_date": today()}).insert(ignore_permissions=True).name]
print(json.dumps({"events": ev, "tasks": tasks}))`).split('\n').pop())
      try {
        await s.open('/life/today?mode=calendar')
        await pg.waitForFunction((x) => document.querySelector('[data-day-timeline]')?.innerText.includes(x), t.due, { timeout: 15000 })
        const rows = await pg.locator('[data-day-timeline] [data-tl-row]').evaluateAll((els) => els.map((e) => ({ kind: e.dataset.tlKind, text: e.innerText.replace(/\s+/g, ' ').trim() })))
        const at = (x) => rows.findIndex((r) => r.text.includes(x))
        must([t.allDay, t.timed, t.planned, t.due].every((x) => rows.filter((r) => r.text.includes(x)).length === 1), 'an item is missing or listed twice: ' + JSON.stringify(rows))
        must(at(t.allDay) < at(t.timed) && at(t.timed) < at(t.planned) && at(t.planned) < at(t.due), 'the order is wrong: ' + JSON.stringify(rows.map((r) => r.text)))
        const now = rows.filter((r) => r.kind === 'now')
        must(now.length === 1 && at(t.allDay) < rows.indexOf(now[0]) && rows.indexOf(now[0]) < at(t.due), 'the now line is not among the timed items: ' + JSON.stringify(rows))
        // in time order: the now line sits after what has begun and before what has not
        const hm = (r) => /(\d\d:\d\d)/.exec(r.text)?.[1] || ''
        for (const r of rows.filter((x) => x.kind === 'timed')) must((hm(r) <= hm(now[0])) === (rows.indexOf(r) < rows.indexOf(now[0])), `"${r.text}" is on the wrong side of the now line`)
        await noSideways()
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      } finally {
        bench(`for n in ${JSON.stringify(names.events)}: frappe.delete_doc("Event", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(names.tasks)}: frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)`)
      }
    })

    await check('TODAY.80', `${width} px: Week Overview's Waiting panel lists the waiting items and a row opens in the Drawer`, async () => {
      const name = bench(`from frappe.utils import add_days, today
print(frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I132 waiting ${width} ${stamp}", "status": "Waiting", "waiting_on": "Ekta I132", "check_by": add_days(today(), -1)}).insert(ignore_permissions=True).name)`).split('\n').pop()
      try {
        await dash('/life/today/week?mode=overview')
        const row = pg.locator('[data-panel="waiting"] [data-dash-row]', { hasText: `I132 waiting ${width}` })
        await row.first().waitFor({ timeout: 15000 })
        must((await row.first().innerText()).includes('Ekta I132') && (await row.first().innerText()).includes('late'), 'the row does not name who and say late: ' + await row.first().innerText())
        const listed = (await s.api('dashboard.list', { kind: 'waiting', view: 'week', space: SPACE })).rows.some((r) => r.ref === 'task:' + name)
        must(listed, "the Waiting list does not hold the panel's item")
        await row.first().locator('button').first().click()
        await pg.waitForFunction((n) => new URL(location.href).searchParams.get('open') === 'task:' + n, name, { timeout: 8000 })
        must(pathOf(pg) === '/life/today/week', 'the row took the page away')
        await pg.keyboard.press('Escape')
      } finally {
        bench(`frappe.delete_doc("Life Task", "${name}", force=1, ignore_permissions=True)`)
      }
    })

    await check('TODAY.81', `${width} px: in a task's pane the goal picker is searchable: typing part of a goal's title filters it`, async () => {
      const goals = (await s.api('meta.space_context', { space: SPACE })).goals
      must(goals.length > 1, 'the space has fewer than two goals')
      const word = goals[0].title.replace(/[^A-Za-z]/g, '').slice(1, 5).toLowerCase()
      const name = bench(`print(frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I147 pane ${width} ${stamp}"}).insert(ignore_permissions=True).name)`).split('\n').pop()
      try {
        await s.open(`/life/today?open=task:${name}`)
        const picker = pg.locator('[data-task-goal-picker]')
        await picker.waitFor({ timeout: 15000 })
        await picker.locator(width < 800 ? '[data-goal-open]' : 'button').first().click()
        const search = width < 800 ? pg.locator('[data-goal-search] input, input[data-goal-search]').first() : pg.locator('[data-slot="content"] input[data-slot="input"]').last()
        await search.waitFor({ timeout: 8000 })
        const names = async () => (await (width < 800 ? pg.locator('[data-goal-option]') : pg.locator('[data-slot="item"]')).allInnerTexts()).map((t) => t.toLowerCase())
        const before = (await names()).length
        await search.fill(word)
        await pg.waitForTimeout(500)
        const after = await names()
        must(after.length > 0 && after.length < before && after.every((t) => t.replace(/[^a-z]/g, '').includes(word)), `typing "${word}" leaves ${after.length} of ${before} goals: ${after.join(' | ')}`)
        await pg.keyboard.press('Escape')
      } finally {
        bench(`frappe.delete_doc("Life Task", "${name}", force=1, ignore_permissions=True)`)
      }
    })
  } finally {
    bench(`for n in ${JSON.stringify(made.items)}:
    for p in frappe.get_all("Life Proposal", filters={"inbox_item": n}, pluck="name"): frappe.delete_doc("Life Proposal", p, force=1, ignore_permissions=True)
    frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Task", filters={"title": ["like", "I123 %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.rules)}: frappe.delete_doc("Life Rule", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Issue 130: the Waiting card and list (Looks done, Late, This week, Later; Confirm, Nudge, By person), a row opening the task layer with the message and the reply, and the
// WhatsApp link. Seeded here: Vivek with a phone and an email, an inbox for the owner (the site's fake Google records what is drafted), and five waiting tasks of his.
const SEED130 = `import json
from frappe.utils import add_days, today
sp = "${SPACE}"
for n in frappe.get_all("Life Task", filters={"title": ["like", "I130 %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
person = frappe.db.get_value("Life Person", {"space": sp, "full_name": "Vivek I130"})
if not person:
    person = frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": "Vivek I130", "kind": "Person", "email": "vivek130@example.com", "phone": "+91 98765 43210"}).insert(ignore_permissions=True).name
made_mail = 0
if not frappe.db.exists("Life Mail Account", {"space": sp, "user": "owner@lifeos.test"}):
    frappe.get_doc({"doctype": "Life Mail Account", "space": sp, "user": "owner@lifeos.test", "provider": "gmail", "address": "owner@example.com", "label": "Personal", "is_default": 1}).insert(ignore_permissions=True)
    made_mail = 1
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": sp, "title": "I130 Re: the ITR draft", "source_type": "Email", "raw_text": "Here is the ITR draft, attached.", "status": "Done", "sender": "vivek130@example.com"}).insert(ignore_permissions=True)
def make(title, check, **extra):
    return frappe.get_doc({"doctype": "Life Task", "space": sp, "title": title, "status": "Waiting", "waiting_on": "Vivek I130", "waiting_on_person": person, "check_by": check, "handed_off_how": "track", **extra}).insert(ignore_permissions=True).name
ids = {
    "late": make("I130 ITR draft", add_days(today(), -2), handed_off_how="draft", handed_off_channel="email", handed_off_ask="Vivek owes me the ITR draft by Friday", handed_off_message="ITR draft by Friday\\n\\nHi Vivek, could you send me the ITR draft by Friday? Thanks, Jai"),
    "twice": make("I130 Tax papers", add_days(today(), -1), nudge_count=2, handed_off_how="draft", handed_off_channel="email", handed_off_message="Re: tax papers\\n\\nHi Vivek, a quick nudge on the tax papers."),
    "looks": make("I130 Form 16", add_days(today(), 2), looks_done_item=item.name, looks_done_note="Vivek sent the Form 16"),
    "week": make("I130 Bank letter", today()),
    "later": make("I130 Audit file", add_days(today(), 30)),
}
doc = frappe.get_doc("Life Task", ids["twice"])
doc.add_comment("Info", "A reply came in: I130 Re: the ITR draft")
from lifeos.api import dashboard
print(json.dumps({"ids": ids, "person": person, "item": item.name, "mail": made_mail, "needs": dashboard.needs_you("${SPACE}")["n"], "waiting": dashboard.waiting("${SPACE}")}))`
const CLEAN130 = (made) => `for n in frappe.get_all("Life Task", filters={"title": ["like", "I130 %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I130 %"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Agent Action", {"space": "${SPACE}", "agent": "lifeos-chat"})
for n in frappe.get_all("Life Rule", filters={"action": "Route", "asks_to": "Close"}, pluck="name"): frappe.delete_doc("Life Rule", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I130"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
${made.mail ? 'for n in frappe.get_all("Life Mail Account", filters={"space": "' + SPACE + '", "user": "owner@lifeos.test"}, pluck="name"): frappe.delete_doc("Life Mail Account", n, force=1, ignore_permissions=True)' : ''}`

for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const phone = width < 800
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
  let seed = null
  const dash = async (p) => { await s.open(p); await pg.locator('[data-dashboard] [data-dash-card]').first().waitFor({ timeout: 20000 }); await pg.waitForTimeout(400) }
  const card = (key) => pg.locator(`[data-card="${key}"]`)
  const row = (id) => pg.locator(`[data-waiting-row][data-task="${id}"]`)
  try {
    seed = JSON.parse(bench(SEED130).split('\n').pop())
    await check('TODAY.73', `${width} px: the Waiting card shows the count, late and looks done; it opens the list grouped Looks done, Late, This week, Later; Confirm closes a looks-done row and Needs you drops by one; Nudge opens the draft; By person regroups`, async () => {
      await dash('/life/today/week')
      const w = seed.waiting
      must((await card('waiting').locator('[data-stat-value]').innerText()).trim() === String(w.n), `the card says ${await card('waiting').locator('[data-stat-value]').innerText()}, the server ${w.n}`)
      const parts = await card('waiting').locator('[data-dash-part]').allInnerTexts()
      must(parts.includes(`${w.past} late`) && parts.includes(`${w.looks_done} looks done`), 'the card parts are ' + parts.join(' | '))
      must(w.looks_done >= 1 && w.past >= 2, `seed: ${JSON.stringify(w)}`)
      const before = Number((await card('needs').locator('[data-stat-value]').innerText()).trim())
      must(before === seed.needs, `Needs you says ${before}, the server ${seed.needs}`)
      await card('waiting').locator('[data-stat-value], [data-stat-open]').first().click()
      const list = pg.locator('[data-list="waiting"]')
      await list.locator('[data-waiting-row]').first().waitFor({ timeout: 15000 })
      const order = await list.locator('[data-waiting-group]').evaluateAll((els) => els.map((e) => e.getAttribute('data-waiting-group')))
      must(JSON.stringify(order) === JSON.stringify(['looks_done', 'late', 'week', 'later']), 'the groups are ' + order.join(', '))
      must(!(await row(seed.ids.later).count()), 'Later is not folded')
      await list.locator('[data-waiting-later-toggle]').click()
      await row(seed.ids.later).waitFor({ timeout: 5000 })
      must(await row(seed.ids.looks).locator('[data-waiting-confirm]').count() === 1 && await row(seed.ids.late).locator('[data-waiting-nudge]').count() === 1, 'Confirm or Nudge is missing on its row')
      must((await row(seed.ids.twice).innerText()).includes('Nudged twice'), 'a row nudged twice does not say so')
      must((await row(seed.ids.late).innerText()).includes('by email'), 'the row does not say how it went: ' + await row(seed.ids.late).innerText())
      await row(seed.ids.looks).locator('[data-waiting-confirm]').click()
      await row(seed.ids.looks).waitFor({ state: 'detached', timeout: 10000 })
      const done = bench(`print(frappe.db.get_value("Life Task", "${seed.ids.looks}", ["status", "closed_by_item"]))`).split('\n').pop()
      must(done.includes('Done') && done.includes(seed.item), 'the task is not Done by the reply: ' + done)
      await row(seed.ids.late).locator('[data-waiting-nudge]').click()
      await pg.waitForFunction((t) => new URL(location.href).searchParams.get('open') === `task:${t}`, seed.ids.late, { timeout: 15000 })
      await pg.locator('[data-handoff-text-shown], [data-handoff-text]').first().waitFor({ timeout: 10000 })
      must((await pg.locator('[data-handoff-message]').innerText()).includes('nudge'), 'the nudge is not drafted: ' + await pg.locator('[data-handoff-message]').innerText())
      must(await pg.locator('[data-handoff-send]').count() === 1, 'the draft has no Send')
      const sent = bench(`print(frappe.db.count("Life Agent Action", {"space": "${SPACE}", "agent": "lifeos-chat", "action": "send_email"}))`).split('\n').pop()
      must(sent === '1', 'the nudge drafted ' + sent + ' emails')
      await pg.locator('[data-pane-back]').first().click()
      await list.locator('[data-waiting-row]').first().waitFor({ timeout: 10000 })
      await list.locator('[data-waiting-by-person]').click()
      await pg.locator('[data-waiting-list][data-by="person"]').waitFor({ timeout: 5000 })
      must((await pg.locator('[data-waiting-list]').innerText()).includes('Vivek I130'), 'By person has no section for Vivek')
      await pg.keyboard.press('Escape')
      await dash('/life/today/week')
      must(Number((await card('needs').locator('[data-stat-value]').innerText()).trim()) === before - 1, 'Needs you did not drop by one')
      must(!errors.length, 'script errors: ' + errors.join(' | '))
    })

    await check('TODAY.74', `${width} px: a row opens the task layer with what was asked, the message and the reply; Back returns to the list`, async () => {
      await s.open(`/life/today/week?open=list:waiting`)
      const list = pg.locator('[data-list="waiting"]')
      await list.locator('[data-waiting-row]').first().waitFor({ timeout: 15000 })
      await row(seed.ids.twice).locator('button[data-ref]').click()
      await pg.waitForFunction((t) => new URL(location.href).searchParams.get('open') === `task:${t}`, seed.ids.twice, { timeout: 10000 })
      await pg.locator('[data-handoff-card]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-handoff-message]').innerText()).includes('quick nudge on the tax papers'), 'the message is not shown')
      must((await pg.locator('[data-handoff-activity]').innerText()).includes('A reply came in'), 'the reply is not shown')
      must(await pg.locator('[data-handoff-edit]').count() === 1 && await pg.locator('[data-handoff-discard]').count() === 1, 'the draft has no Edit or Discard')
      must(await pg.locator('[data-task-handoff]').count() === 1, 'the task layer has no Hand off button')
      await pg.locator('[data-pane-back]').first().click()
      await pg.waitForFunction(() => new URL(location.href).searchParams.get('open') === 'list:waiting', null, { timeout: 10000 })
      await pg.locator('[data-list="waiting"] [data-waiting-row]').first().waitFor({ timeout: 10000 })
    })

    await check('TODAY.75', `${width} px: the list and the task layer ${phone ? 'are full screen with Back' : 'open in the Drawer'}; the WhatsApp link has the phone and the text, URL-encoded`, async () => {
      const text = 'Hi Vivek, could you send the ITR draft & Form 16 by Friday?'
      bench(`t = frappe.get_doc("Life Task", "${seed.ids.week}")
t.update({"handed_off_how": "draft", "handed_off_channel": "whatsapp", "handed_off_message": ${JSON.stringify(text)}})
t.save()`)
      await s.open(`/life/today/week?open=list:waiting`)
      await pg.locator('[data-list="waiting"] [data-waiting-row]').first().waitFor({ timeout: 15000 })
      if (phone) {
        const box = await pg.locator('[data-drawer-host]').boundingBox()
        must(box.width >= 388 && box.height >= 840, `the list is ${box.width} by ${box.height}`)
        must(await pg.locator('[data-pane-back]').count() >= 1, 'the list has no Back')
      }
      await row(seed.ids.week).locator('button[data-ref]').click()
      await pg.locator('[data-handoff-whatsapp]').waitFor({ timeout: 10000 })
      const href = await pg.locator('[data-handoff-whatsapp]').getAttribute('data-href')
      must(href === `https://wa.me/919876543210?text=${encodeURIComponent(text)}`, 'the link is ' + href)
      must(await pg.locator('[data-handoff-send]').count() === 0, 'a WhatsApp draft has a Send')
      if (phone) {
        const box = await pg.locator('[data-drawer-host]').boundingBox()
        must(box.width >= 388 && box.height >= 840, `the task layer is ${box.width} by ${box.height}`)
        must(await pg.locator('[data-pane-back]').count() >= 1, 'the task layer has no Back')
      }
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally {
    bench(CLEAN130(seed || { mail: 0 }))
    await s.ctx.close()
  }
}

// Fast panes: a record opens from the data layer's cache and follows the server.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const made = []
  const titleOf = () => pg.locator('[data-pane-title]').first().innerText()
  const go = (p) => pg.evaluate((to) => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push(to), p)
  try {
    const title = `Fast pane ${stamp} ${width}`
    const task = bench(`t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${title}", "status": "Open"}).insert(ignore_permissions=True)
print(t.name)`).split('\n').pop()
    made.push(task)
    await check('TODAY.88', `${width} px: a task opened in the Drawer, closed and opened again shows its title before any request for it finishes`, async () => {
      await s.open(`/life/today?open=task:${task}`)
      await pg.locator('[data-pane-title]', { hasText: title }).waitFor({ timeout: 15000 })
      await go('/today?mode=overview&area=')
      await pg.locator('[data-pane-title]').waitFor({ state: 'detached', timeout: 10000 })
      let finished = 0
      pg.on('requestfinished', (r) => { if (/tasks\.get|api\/v2\/document\/Life(%20| )Task/.test(r.url())) finished++ })
      const held = /tasks\.get|api\/v2\/document\/Life(%20| )Task/
      await pg.route(held, async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue().catch(() => {}) })
      try {
        await go(`/today?mode=overview&area=&open=task:${task}`)
        await pg.locator('[data-pane-title]', { hasText: title }).waitFor({ timeout: 1500 })
        must(finished === 0, 'the title came after a request finished')
      } finally {
        await pg.unroute(held)
      }
    })
    await check('TODAY.89', `${width} px: with a task open, a change saved on the server shows in the pane within 3 seconds, without reopening`, async () => {
      await s.open(`/life/today?open=task:${task}`)
      await pg.locator('[data-pane-title]', { hasText: title }).waitFor({ timeout: 15000 })
      bench(`frappe.db.set_value("Life Task", "${task}", "title", "${title} changed")
t = frappe.get_doc("Life Task", "${task}")
t.save(ignore_permissions=True)`)
      await pg.locator('[data-pane-title]', { hasText: 'changed' }).waitFor({ timeout: 3000 })
      must((await titleOf()).includes('changed'), 'the pane kept the old title')
    })
  } finally {
    await s.ctx.close()
    bench(`for n in ${JSON.stringify(made)}: frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)`)
  }
}
