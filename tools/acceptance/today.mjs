// Today: Day, Week, Month and Year, the lists' counts, rhythm banners, Reset and the first-run guide.
// Checks are numbered TODAY.<n> in the order they appear here; `node tools/acceptance.mjs --only=TODAY` runs this file's checks.
import { SPACE, WIDTHS, addDays, areaId, areas, base, bench, browser, check, must, nextWeekday, owner, path, plusDays, session, stamp, today } from './context.mjs'
import { ROW, num, ux, uxArea, uxKit } from './ux.mjs'

await check('TODAY.1', 'Log in, open /life, Today is filled from seed data', async () => {
  const guest = await browser.newContext()
  const res = await guest.request.get(base + '/life', { maxRedirects: 0 })
  must(res.status() === 302 && (res.headers().location || '').includes('/login'), 'a guest is not sent to login')
  must((await guest.request.get(base + '/api/method/lifeos.api.today.get')).status() >= 400, 'a guest can call the API')
  await guest.close()
  await owner.open('/life')
  const text = await owner.page.locator('[data-main]').innerText()
  must(/Week \d+ of 12/.test(text), 'no 12 Week Year week on Today')
  const habitNames = await owner.page.locator('[data-today-habits] [data-habit]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')).join(' '))
  const t = await owner.api('today.get', { space: SPACE })
  must(text.includes('Habits') && t.habits.length && t.habits.every((h) => habitNames.includes(h.title)), 'habits are missing on Today')
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
  await owner.open('/life/today/year?view=calendar')
  must((await owner.page.locator('[data-main]').innerText()).includes('Birthday'), 'not shown on the year screen')
})

await check('TODAY.3', 'Vault document expiring in 30 days shows a badge on Today', async () => {
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

  await check('TODAY.5', `${width} px: Today: no Open band, the list of tasks in order, the rail; Someday never shows; the amber dot on the Week's Reset`, async () => {
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
    must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is still on Today (issue 55)')
    const groups = await pg.locator('[data-next-group]').evaluateAll((els) => els.map((e) => e.getAttribute('data-next-group')))
    const order = ['top', 'today', 'overdue', 'week']
    must(JSON.stringify(groups) === JSON.stringify(order.filter((g) => groups.includes(g))), `Next groups are ${groups}`)
    if (await pg.locator('[data-overdue-toggle]').count()) { await tap(pg.locator('[data-overdue-toggle]')); await settle() } // issue 15: overdue is folded
    if (await pg.locator('[data-next-more]').count()) { await tap(pg.locator('[data-next-more]')); await settle() }
    const next = await pg.locator('[data-next]').innerText()
    must(next.includes(S5('overdue')) && next.includes(S5('due today')), 'the overdue or due task is not in Next')
    must(!next.includes(S5('parked')), 'a Someday task is on Today')
    must(await pg.locator('[data-next-row][data-why="12WY"]').count() === 0 && await pg.locator('[data-next-group="decisions"]').count() === 0, 'a 12 Week Year row or a decision is in the list')
    must(await pg.locator('[data-rail-today]').isVisible() && await pg.locator('[data-rail-week]').isVisible(), 'the rail is missing')
    // the stuck count over the limit puts an amber dot on the Week's Reset; the limit is put back after
    const limit = (await s.api('counts.get', { space: SPACE })).rules.stuck_limit
    await s.api('settings.save', { values: { stuck_limit: 0 } })
    try {
      if (!phone) { // set 6: the dot sits on the Week's Reset button (issue 14: the sidebar has no Week item)
        await s.open('/life/today/week?view=calendar')
        must(await pg.locator('[data-plan-reset] [role="img"]').count(), "no amber dot on the Week's Reset button")
      }
    } finally {
      await s.api('settings.save', { values: { stuck_limit: limit } })
    }
    return `${groups.join(', ')}`
  })

  await check('TODAY.6', `${width} px: counts: every number on Today, Reset, Someday and the sidebar opens a list with exactly that many rows`, async () => {
    let n = 0
    for (const from of ['/life', '/life/settings?tab=data', '/life/goals/someday?all=1']) {
      await s.open(from)
      if (phone && from === '/life/settings?tab=data') { await pg.locator('[role="tab"]', { hasText: 'Inventory' }).first().click(); await settle() }
      const keys = await pg.locator('[data-count-door]:visible').evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute('data-count-key')))])
      // Someday's own numbers are its tab counts, which U.8 clicks; here only the doors on the page (the sidebar's on a wide screen)
      must(keys.length || from.includes('someday'), `no counts on ${from}`)
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
    bench(`from lifeos import cycles, habits
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
      const order = await pg.evaluate(() => { const a = document.querySelector('[data-rhythm-banner]'), o = document.querySelector('[data-next]'); return !!(a && o && (a.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING)) })
      must(order, 'the banner is not above the list')
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
goal = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${goalTitle}", "area": tea, "horizon": "Year", "target_date": "${year}-12-31"}).insert(ignore_permissions=True).name
off = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${offTitle}", "area": mind, "horizon": "Year", "target_date": "${year}-12-31"}).insert(ignore_permissions=True).name
print(json.dumps({"career": career, "tea": tea, "mind": mind, "was": was, "event": ev.name, "tasks": tasks, "goal": goal, "off": off}))`).split('\n').pop())
  let reviewName = null
  try {
    await check('TODAY.11', `${width} px: Week shows this week's calendar events and due tasks on the right days, and a day opens Day`, async () => {
      await s.open('/life/today/week')
      await pg.locator('[data-week-grid]').waitFor({ timeout: 10000 })
      const dayText = async (d) => await pg.locator(`[data-week-grid] [data-day="${d}"]`).innerText()
      must((await dayText(meetDay)).includes(meeting), `${meeting} is not on ${meetDay}`)
      must((await dayText(dueDay)).includes(due), `${due} is not on ${dueDay}`)
      for (const d of [plusDays(monday, 4), plusDays(monday, 5)]) must(!(await dayText(d)).includes(meeting) && !(await dayText(d)).includes(due), 'an item is on the wrong day ' + d)
      const to = dueDay === today ? meetDay : dueDay
      await pg.locator(`[data-week-grid] [data-day="${to}"] [data-open-day]`).click()
      await pg.waitForURL((u) => u.pathname === '/life/today' && u.searchParams.get('date') === to, { timeout: 10000 })
      await pg.locator('[data-day-other]').waitFor({ timeout: 10000 })
      await pg.waitForFunction((t) => document.querySelector('[data-day-other]')?.innerText.includes(t), to === dueDay ? due : meeting, { timeout: 10000 }).catch(() => {})
      must((await pg.locator('[data-day-other]').innerText()).includes(to === dueDay ? due : meeting), 'Day does not list the item of ' + to)
      must((await pg.locator('[data-page-head]').first().innerText()).includes(String(Number(to.slice(8)))), 'Day is not headed with the date')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('TODAY.12', `${width} px: Month shows events and due tasks on the right dates; next and previous months work`, async () => {
      await s.open('/life/today/month')
      await pg.locator('[data-month-grid]').waitFor({ timeout: 10000 })
      const month = today.slice(0, 7)
      must((await pg.locator('[data-month-view]').getAttribute('data-month')) === month, 'Month is not on this month')
      if (phone) {
        for (const [d, title] of [[meetDay, meeting], [dueDay, due]]) {
          await pg.locator(`[data-month-grid] [data-day="${d}"] > button`).click()
          await pg.waitForFunction((t) => document.querySelector('[data-month-list]')?.innerText.includes(t), title, { timeout: 5000 })
        }
      } else {
        must((await pg.locator(`[data-month-grid] [data-day="${meetDay}"]`).innerText()).includes(meeting), `${meeting} is not on ${meetDay}`)
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
    await check('TODAY.13', `${width} px: Year shows a bar for each goal in its area's lane, and one tick per weekly review with the right count`, async () => {
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
    await check('TODAY.14', `${width} px: an area that is off has no lane`, async () => {
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
    await check('TODAY.15', `${width} px: clicking a goal opens the goal; clicking a month opens Month`, async () => {
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
from lifeos import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  try {
    bench(`from lifeos import devtools
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

    await check('TODAY.17', `${width} px: the first visit opens the guide; skipping every step lands on Today and the guide does not return`, async () => {
      await guideOpens()
      must(await stepKey() === 'welcome', 'the guide does not open on Welcome')
      must((await pg.locator('[data-guide-flow] li').count()) === 3, 'Welcome does not show Sources, Brain and Plan')
      await pg.locator('[data-guide-next]').click()
      for (const key of ['you', 'areas', 'things']) {
        must(await stepKey() === key, `expected the ${key} step, at ${await stepKey()}`)
        await pg.locator('[data-guide-skip]').click()
      }
      must(await stepKey() === 'next', 'the last step is not Next step')
      await pg.locator('[data-guide-today]').click()
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
      must(await pg.locator('[data-guide]').count() === 0, 'the guide is still open')
      await one.open('/life')
      await pg.waitForTimeout(1200)
      must(await pg.locator('[data-guide]').count() === 0, 'the guide came back after a reload')
      must((await one.api('onboarding.state')).status === 'skipped', 'the guide is not recorded as skipped')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    if (phone) {
      reset()
      await check('TODAY.18', `${width} px: the guide shows one screen at a time and each screen fits the phone`, async () => {
        await guideOpens()
        for (const key of ['welcome', 'you', 'areas', 'things', 'next']) {
          must(await stepKey() === key, `expected ${key}, at ${await stepKey()}`)
          must(await pg.locator('[data-guide-step]:visible').count() === 1, `${key}: more than one screen is shown`)
          must(!(await pg.evaluate(() => document.querySelector('[data-guide]').scrollWidth > window.innerWidth + 1)), `${key}: the screen scrolls sideways`)
          if (key !== 'next') {
            const box = await pg.locator('[data-guide-next]').boundingBox()
            must(box && box.x >= 0 && box.x + box.width <= width, `${key}: the Next button is off the screen`)
            await pg.locator('[data-guide-skip], [data-guide-next]').last().click()
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
      for (const [p, sel] of [['/life/today', '[data-today-empty]'], ['/life/brain', '[data-needs-empty]'], ['/life/goals', '[data-goals-empty]'], ['/life/library', '[data-lib-empty]']]) {
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

    await check('TODAY.20', `${width} px: going through the guide sets the name and time zone, switches on a third area and turns three typed things into tasks with areas`, async () => {
      reset()
      await guideOpens()
      await pg.locator('[data-guide-next]').click() // Start
      const name = `Asha Newcomer ${stamp}`
      await pg.locator('[data-guide-name] input, input[data-guide-name]').first().fill(name)
      await pg.locator('[data-guide-zone] select, select[data-guide-zone]').first().selectOption('Asia/Dubai')
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'areas', null, { timeout: 8000 })
      must(await pg.locator('[data-guide-area][data-on="1"]').count() === 2, 'Career and Health are not the two areas on')
      await pg.locator('[data-guide-switch="Mind"]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide-area="Mind"]')?.dataset.on === '1', null, { timeout: 8000 })
      await pg.locator('[data-guide-part-title] input, input[data-guide-part-title]').first().fill(`I49 part ${stamp}`)
      await pg.locator('[data-guide-part-add]').click()
      await pg.locator('[data-guide-parts]').waitFor({ timeout: 8000 })
      await pg.locator('[data-guide-next]').click()
      await pg.waitForFunction(() => document.querySelector('[data-guide]')?.dataset.step === 'things', null, { timeout: 8000 })
      const things = [`I49 book the dentist ${stamp}`, `I49 pay the electricity bill ${stamp}`, `I49 read a chapter of my book ${stamp}`]
      for (const [i, t] of things.entries()) await pg.locator(`[data-guide-thing="${i}"] input, input[data-guide-thing="${i}"]`).first().fill(t)
      await pg.locator('[data-guide-next]').click()
      await pg.locator('[data-guide-made]').waitFor({ timeout: 10000 })
      must(await pg.locator('[data-guide-task]').count() === 3, 'three tasks were not made')
      const areas = await pg.locator('[data-guide-task-area]').allInnerTexts()
      must(areas.every((a) => a && a !== 'No area'), 'a task has no area: ' + areas.join())
      await pg.locator('[data-guide-next]').click() // Continue
      await pg.locator('[data-guide-today]').click()
      await pg.waitForFunction(() => location.pathname === '/life/today', null, { timeout: 8000 })
      const out = JSON.parse(bench(`import json
doc = frappe.get_doc("User", "${user}")
on = frappe.get_all("Life Area", filters={"space": "${space}", "is_life_area": 1, "is_on": 1}, pluck="area_name")
tasks = frappe.get_all("Life Task", filters={"space": "${space}"}, fields=["title", "area"])
print(json.dumps({"name": doc.full_name, "zone": frappe.db.get_single_value("System Settings", "time_zone"), "on": sorted(on),
  "tasks": len(tasks), "unfiled": len([t for t in tasks if not t.area]),
  "part": frappe.db.exists("Life Area", {"space": "${space}", "area_name": "I49 part ${stamp}"}) is not None}))`).split('\n').pop())
      must(out.name === name, 'the name is ' + out.name)
      must(out.zone === 'Asia/Dubai', 'the time zone is ' + out.zone)
      must(out.on.join() === 'Career,Health,Mind', 'the areas on are ' + out.on.join())
      must(out.tasks === 3 && out.unfiled === 0, `tasks: ${out.tasks}, without an area: ${out.unfiled}`)
      must(out.part, 'the part was not made')
      must((await one.api('onboarding.state')).status === 'done', 'the guide is not recorded as done')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.21', `${width} px: after the guide the ladder card shows level 1 and connect a source`, async () => {
      await one.open('/life/today')
      if (phone) await pg.locator('[data-more-title]').click()
      const card = pg.locator('[data-setup-card]:visible')
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('level 1 of 6'), 'the card says: ' + t)
      must(/connect a source/i.test(t), 'the next step is not to connect a source: ' + t)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    if (one) await one.ctx.close()
    restore()
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
from lifeos import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  try {
    bench(`from lifeos import devtools
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
    const today55 = async () => { await one.open('/life/today'); await pg.locator('[data-next]').waitFor({ timeout: 10000 }).catch(() => {}); await pg.waitForTimeout(500) }

    await check('TODAY.22', `${width} px: on an empty site Today shows its empty state and no Open band`, async () => {
      await one.open('/life/today')
      await pg.locator('[data-today-empty]').waitFor({ timeout: 10000 })
      must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is on an empty Today')
      must(await pg.locator('[data-no-plan]').count() === 0, 'a goal line is on an empty Today')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    // a cycle of three goals, each with a lead action, and nothing planned this week
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, today
space = "${space}"
area = frappe.get_all("Life Area", filters={"space": space, "is_life_area": 1, "is_on": 1}, pluck="name", limit=1)[0]
cycle = frappe.get_doc({"doctype": "Life Cycle", "space": space, "title": "I55 cycle ${width}", "start_date": add_days(today(), -14), "status": "Active"}).insert(ignore_permissions=True)
goals = [frappe.get_doc({"doctype": "Life Goal", "space": space, "cycle": cycle.name, "title": f"I55 goal {i} ${width}", "area": area, "sort_order": i,
  "actions": [{"title": f"I55 lead {i} ${width}", "per_week": 1}]}).insert(ignore_permissions=True) for i in range(3)]
print(json.dumps({"cycle": cycle.name, "goals": [g.name for g in goals], "actions": [g.actions[0].name for g in goals]}))`).split('\n').pop())

    await check('TODAY.23', `${width} px: cycle goals with lead actions and no task this week are not rows on Today`, async () => {
      await today55()
      const text = await pg.locator('[data-next]').innerText()
      must(!/I55 goal|I55 lead/.test(text), 'a goal or lead action is in the list: ' + text.slice(0, 300))
      must(await pg.locator('[data-week-tick], [data-action]').count() === 0, 'a lead action tick box is on Today')
      must(!(await pg.locator('[data-main]').innerText()).includes('12WY'), 'a 12WY row is on Today')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.24', `${width} px: a task planned this week under a cycle goal shows with its goal, and ticking it records the lead action's tick`, async () => {
      bench(`from frappe.utils import today
frappe.get_doc({"doctype": "Life Task", "space": "${space}", "title": "I55 lead 0 ${width}", "goal": "${made.goals[0]}", "due_date": today()}).insert(ignore_permissions=True)`)
      await today55()
      const row = pg.locator('[data-task-row]', { hasText: `I55 lead 0 ${width}` })
      await row.waitFor({ timeout: 10000 })
      must((await row.locator('[data-task-goal-link]').innerText()) === `I55 goal 0 ${width}`, 'the goal is not shown as a link on the task')
      must((await row.locator('[data-task-goal-link]').getAttribute('href')) === `/life/goals/${made.goals[0]}`, 'the goal link goes elsewhere')
      await row.locator('[role="checkbox"], input[type="checkbox"], button[role="checkbox"]').first().click()
      await pg.waitForTimeout(1200)
      const ticks = bench(`print(frappe.db.get_value("Life Action Log", {"action_id": "${made.actions[0]}"}, "count"))`).split('\n').pop()
      must(ticks === '1', 'the lead action has ' + ticks + ' ticks')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.25', `${width} px: with three cycle goals planned for nothing, one line says so and Plan opens Goals > Cycles`, async () => {
      await today55()
      const line = pg.locator('[data-no-plan]')
      await line.waitFor({ timeout: 10000 })
      must((await line.getAttribute('data-count')) === '3', 'the line counts ' + (await line.getAttribute('data-count')))
      must(/3 cycle goals have nothing planned this week/.test(await line.innerText()), 'the line says: ' + (await line.innerText()))
      await line.locator('[data-no-plan-link]').click()
      await pg.waitForFunction(() => location.pathname === '/life/goals/cycles', null, { timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('TODAY.26', `${width} px: the Open band is gone from Today; the habits row shows today's habits by name and ticks them`, async () => {
      await one.api('goals.set_month_habits', { space, year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)), habits: [{ title: `I55 Walk ${width}` }, { title: `I55 Read ${width}` }] })
      await today55()
      must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is on Today')
      must(await pg.locator('[data-tile]').count() === 0, 'a tile of the band is on Today')
      const row = pg.locator('[data-today-habits]')
      await row.waitFor({ timeout: 10000 })
      const text = await row.innerText()
      must(text.includes(`I55 Walk ${width}`) && text.includes(`I55 Read ${width}`), 'the habits are not named: ' + text)
      const walk = row.locator('button', { hasText: `I55 Walk ${width}` })
      await walk.click()
      await pg.waitForTimeout(1000)
      must(/1 of 2 today/.test(await row.innerText()), 'the count did not move: ' + (await row.innerText()))
      const done = bench(`print(frappe.db.count("Life Habit Log", {"space": "${space}", "done": 1}))`).split('\n').pop()
      must(done === '1', 'the tick was not stored: ' + done)
      await walk.click() // put it back
      await noSideways()
    })

    await check('TODAY.27', `${width} px: no link on Today goes to an old route, and each opens where it says`, async () => {
      await today55()
      const hrefs = [...new Set(await pg.locator('[data-main] a[href]').evaluateAll((as) => as.map((a) => a.getAttribute('href'))))]
      must(hrefs.length > 0, 'no links on Today')
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

    if (phone) {
      await check('TODAY.28', `${width} px: the order is Needs you, the list, habits, then the rail`, async () => {
        bench(`from frappe.utils import now_datetime
frappe.get_doc({"doctype": "Life Inbox Item", "space": "${space}", "title": "I55 to review ${width}", "source_type": "Upload", "status": "To Review", "raw_text": "x", "received_on": now_datetime()}).insert(ignore_permissions=True)`)
        await today55()
        await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
        const y = async (sel) => (await pg.locator(sel).first().boundingBox()).y
        const [needs, list, habits, rail] = [await y('[data-needs-you]'), await y('[data-next]'), await y('[data-today-habits]'), await y('[data-rail]')]
        must(needs < list && list < habits && habits < rail, `the order is Needs you ${needs}, list ${list}, habits ${habits}, rail ${rail}`)
        await noSideways()
      })
    }
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
      await one.open('/life/library')
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
  } finally {
    if (one) await one.ctx.close()
  }
}
