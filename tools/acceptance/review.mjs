// Review: the weekly, monthly and 12-week reviews and the screens they share.
// Checks are numbered REVIEW.<n> in the order they appear here; `node tools/acceptance.mjs --only=REVIEW` runs this file's checks.
import { SPACE, WIDTHS, addDays, areaId, bench, check, must, owner, session, stamp, today, walkScreens } from './context.mjs'
import { ux, uxKit } from './ux.mjs'

await check('REVIEW.1', "Archive job archives done tasks; a stale open task waits in the weekly review's list of stale tasks", async () => {
  const done = await owner.api('tasks.quick_add', { text: `Old done task ${stamp}`, space: SPACE, area: areaId('Personal') })
  const stale = await owner.api('tasks.quick_add', { text: `Stale open task ${stamp}`, space: SPACE, area: areaId('Personal') })
  await owner.api('tasks.set_status', { task: done.name, status: 'Done' })
  // move the clock: the first was finished 100 days ago, the second not touched for 100 days
  bench(`from frappe.utils import add_days, today
frappe.db.set_value("Life Task", "${done.name}", "completed_on", add_days(today(), -100), update_modified=False)
frappe.db.set_value("Life Task", "${stale.name}", {"last_touched_on": add_days(today(), -100), "creation": add_days(today(), -100)}, update_modified=False)
from lifeos.library import archive, index
index.update(frappe.get_doc("Life Task", "${done.name}"))
archive.run_daily()`)
  const arch = await owner.api('archive.list', { space: SPACE, page_length: 100, filters: [['title', 'like', `%${stamp}%`]] }) // earlier runs fill the Archive
  must(JSON.stringify(arch.groups).includes(done.name), 'the done task was not archived')
  must(!JSON.stringify(arch.groups).includes(stale.name), 'the stale open task was archived')
  // the age rules are gone: a stale open task is never archived for you; it waits in the weekly review's Tasks tab (issue 72)
  must((await owner.api('weekly.stale_tasks', { space: SPACE })).tasks.some((r) => r.name === stale.name), "the stale task is not in the weekly review's list")
  await owner.open('/life/today/week?view=review&tab=tasks')
  await owner.page.locator(`[data-stale-task][data-task="${stale.name}"]`).waitFor({ timeout: 15000 })
  await owner.page.keyboard.press('Escape')
})

for (const width of WIDTHS) {
  const { count, overflow, pane, pg, phone, s, settle, tag } = await uxKit(width)
  await check('REVIEW.2', `${width} px: an inbox item's pane and full review page are tabbed: Summary first, then the original, Decisions and What came of it`, async () => {
    await s.open('/life/brain/queue?open=inbox:' + ux.inbox)
    const bar = pg.locator('[data-pane-tabs]')
    await bar.waitFor({ timeout: 10000 })
    const names = (await bar.locator('[role="tab"]').allInnerTexts()).map((t) => t.replace(/\s*\d+$/, '').trim())
    must(names.length === 4 && names[0] === 'Summary' && names[2] === 'Decisions' && names[3] === 'What came of it', 'the tabs are ' + JSON.stringify(names))
    must((await bar.getAttribute('data-tab-current')) === 'summary', `it opened on ${await bar.getAttribute('data-tab-current')}`)
    await bar.locator('[data-tab="decisions"]').click()
    await settle()
    must(new URL(pg.url()).searchParams.get('ptab') === 'decisions', 'the tab is not in the URL as ptab= in the pane')
    await s.open(`/life/brain/review/${ux.inbox}?tab=decisions`) // the full page uses tab=
    must((await pg.locator('[data-review-tabs]').getAttribute('data-tab-current')) === 'decisions', 'the full review page does not open on tab=decisions')
    must((await overflow()) <= 0, 'the page scrolls sideways')
  })
  await s.ctx.close()
}
// On data shaped like the owner's (lifeos/tools/devtools_review.py: a number goal with a Suggested reading, a milestone goal without its
// finish line, stuck, waiting and delegated tasks, Inbox items of every kind) plus the fixture calendar. Records carry
// "S8 … <width> <stamp>" and are removed by S4.1; devtools_review.cleanup removes the rest and puts the settings back.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const tag = `S8.${width}`
  const W = `${width} ${stamp}`
  const settle = () => pg.waitForTimeout(600)
  const data = JSON.parse(bench(`import json
from lifeos.tools import devtools_review
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

  await check('REVIEW.3', `${width} px: the review opens from Today's banner on Library, with its period in the header; Goals cannot open before Tasks is done`, async () => {
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

  await check('REVIEW.4', `${width} px: a meeting that matters with a linked voice note; a task made from its follow-up leaves the meeting's drawer and the Revelations list`, async () => {
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

  await check('REVIEW.5', `${width} px: a reading confirmed from Revelations shows its value on the goal's row in Goals`, async () => {
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

  await check('REVIEW.6', `${width} px: the Tasks tab lists each stale task once with Keep, Someday and Drop; each button does what it says; the Outbox counts match`, async () => {
    await goTab('tasks')
    must(tabNow() === 'tasks', 'Tasks did not open')
    const row = (name) => pg.locator(`[data-stale-task][data-task="${name}"]`)
    for (const name of [data.keep, data.park[0], data.letgo]) {
      await row(name).waitFor({ timeout: 10000 })
      must(await pg.locator(`[data-stale-task][data-task="${name}"]`).count() === 1, 'a stale task is listed twice')
      must(JSON.stringify(await row(name).locator('[data-stale-decision]').allInnerTexts()) === JSON.stringify(['Keep', 'Someday', 'Drop']), 'the buttons are not Keep, Someday and Drop')
    }
    const plateN = async (p) => (await s.api('weekly.plate', { space: SPACE })).piles.find((x) => x.pile === p).n
    const before = { Parked: await plateN('Parked'), Discarded: await plateN('Discarded') }
    const status = async (n) => (await s.api('frappe.client.get_value', { doctype: 'Life Task', filters: { name: n }, fieldname: 'status' })).status
    const press = async (name, decision) => {
      await row(name).locator(`[data-stale-decision="${decision}"]`).click()
      await row(name).waitFor({ state: 'detached', timeout: 10000 })
      await settle()
    }
    await press(data.keep, 'keep')
    must(await status(data.keep) === 'Open', 'Keep changed the task')
    must(bench(`print(str(frappe.db.get_value("Life Task", "${data.keep}", "last_touched_on")))`).split('\n').pop() === today, 'Keep did not touch the task, so it would be stale again next week')
    await press(data.park[0], 'someday')
    must(await status(data.park[0]) === 'Someday', 'Someday did not park the task')
    await press(data.letgo, 'drop')
    must(await status(data.letgo) === 'Dropped', 'Drop did not drop the task')
    must(await plateN('Parked') === before.Parked + 1 && await plateN('Discarded') === before.Discarded + 1, 'the Outbox counts did not follow')
    for (const p of ['Parked', 'Discarded']) {
      const plate = (await s.api('weekly.plate', { space: SPACE })).piles.find((x) => x.pile === p)
      const listed = await s.api('outbox.list', { space: SPACE, pile: p, from_date: plate.to.query.from, to_date: plate.to.query.to, page_length: 500 })
      must(plate.n === listed.total && plate.n === listed.rows.length, `${p} says ${plate.n}, the Outbox lists ${listed.rows.length}`)
    }
    must(Number(await pg.locator('[data-left-to-clear]').getAttribute('data-n')) === (await s.api('weekly.stale_tasks', { space: SPACE })).left, 'the count left to decide is not the list')
    return 'Keep, Someday and Drop'
  })

  await check('REVIEW.7', `${width} px: every stale task decided; Next: Goals opens`, async () => {
    for (let i = 0; i < 12; i++) {
      const row = pg.locator('[data-stale-task]').first()
      if (!(await row.count())) break
      await row.locator('[data-stale-decision="keep"]').click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
    must(!(await pg.locator('[data-stale-task]').count()), 'stale tasks are left')
    must((await pg.locator('[data-stale-tasks]').innerText()).includes('No stale tasks.'), 'the empty list does not say what will appear here')
    const next = pg.locator('[data-review-next]')
    must(await next.isEnabled(), 'Next: Goals is still closed: ' + (await pg.locator('[data-review-footer-line]').innerText()))
    await next.dispatchEvent('click') // a toast may sit over the footer for a moment
    await pg.waitForLoadState('networkidle')
    await settle()
    must(tabNow() === 'goals', 'Goals did not open')
    return 'every stale task decided'
  })

  await check('REVIEW.8', `${width} px: every cycle goal gets a next action or a skip with a reason; exactly three stars; more than the free time shows the warning`, async () => {
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

  await check('REVIEW.9', `${width} px: Pause and reopen: everything is where it was left; no tab scrolls the page at 1440 x 900 or sideways at 390`, async () => {
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
    must(!(await pg.locator('[data-stale-task]').count()) && (await pg.locator('[data-left-to-clear]').getAttribute('data-n')) === '0', 'the decided stale tasks came back')
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

  await check('REVIEW.10', `${width} px: what went well; Lock; the done screen; Today's Top three panel lists them; the scheduled tasks are on Today and in Plan > Week`, async () => {
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
    await s.open('/life/today?mode=overview')
    await pg.locator('[data-panel="top"] [data-dash-row]').first().waitFor({ timeout: 15000 })
    const tops = await pg.locator('[data-panel="top"] [data-dash-row]').count()
    must(tops === 3, `${tops} top-three rows on Today's Top three panel`)
    const made = (await s.api('tasks.list', { space: SPACE, status: 'all', filters: [['title', 'like', `S8 next % ${W}`]] })).tasks
    const scheduled = made.filter((x) => x.scheduled_at)
    must(scheduled.length >= 2, 'the plans were not scheduled')
    must(made.some((x) => x.status === 'Waiting' && x.waiting_on === 'Vivek'), 'the delegated plan is not Waiting on Vivek')
    const weekCal = await s.api('calendar.get', { space: SPACE, from_date: addDays(0), to_date: addDays(8) })
    must(scheduled.every((x) => weekCal.items.some((i) => i.name === x.name && i.scheduled)), 'a scheduled task is not in Plan > Week')
    // the plans fall on the days ahead, which on a Friday to Sunday run are in next week: open the week of the earliest one
    const firstDay = scheduled.map((x) => String(x.scheduled_at).slice(0, 10)).sort()[0]
    await s.open(`/life/today/week?mode=calendar&date=${firstDay}`)
    await pg.locator('[data-week-item]').first().waitFor({ timeout: 20000 })
    const text = await pg.locator('[data-main]').innerText()
    must(scheduled.some((x) => text.includes(x.title)), 'no scheduled task on the Week calendar')
    // the next review starts after this one
    must((await s.api('weekly.get', { space: SPACE })).status === 'Locked', 'the review is not locked')
    must(!errors.length, errors.splice(0).join(' | '))
    return `${made.length} tasks, ${scheduled.length} scheduled, top three on Today`
  })

  bench(`from lifeos.tools import devtools_review
devtools_review.cleanup("${stamp}", ${JSON.stringify(JSON.stringify(data.was))})`)
  await s.ctx.close()
}
// Records carry "BF1 … <width> <stamp>" and are removed by S4.1.
for (const width of WIDTHS) {
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

  await check('REVIEW.11', `${width} px: the weekly review renders on data like the owner's (a goal migrated from a project, a number goal with a Suggested reading, a milestone goal without "done when", a goal with no cycle, a delegated task), reached by clicking and by URL`, async () => {
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, now_datetime, today
from lifeos.goals import readings
frappe.set_user("owner@lifeos.test")
area = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
cycle = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"})
def goal(title, **kw):
    if "measure_kind" not in kw: kw.setdefault("done_when", "BF1 set-up")  # a new goal has its Done when
    g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": title, "area": area, **kw})
    g.flags.ignore_permissions = True
    return g.insert().name
# an open-ended goal with no finish line and no measure, as the migrated projects were
migrated = goal("BF1 migrated ${W}", horizon="Long term")
frappe.db.set_value("Life Goal", migrated, "done_when", None)  # as the migrated projects were: no finish line
number = goal("BF1 number ${W}", horizon="Long term", measure_kind="Number", measure="BF1 weight", unit="kg", start_value=84, target_value=78)
readings.suggest(number, 81, excerpt="Weighed 81 kg this morning.", by="Agent")
milestone = goal("BF1 milestone ${W}", horizon="12 weeks", cycle=cycle, measure_kind="Milestone", done_when="Signed")
frappe.db.set_value("Life Goal", milestone, "done_when", None)
nocycle = goal("BF1 no cycle ${W}", horizon="12 weeks", cycle=cycle)
frappe.db.set_value("Life Goal", nocycle, "done_when", None)
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

  await check('REVIEW.12', `${width} px: a screen forced to fail shows "This screen could not be shown." with Reload and a reference, logs it, and navigation keeps working`, async () => {
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

  await check('REVIEW.13', `${width} px: every place, every Plan and Library tab and every view of Plan's rhythms opens by clicking, and navigation works afterwards`, async () => {
    await s.open('/life')
    errors.splice(0)
    const { seen, failures } = await walkScreens(pg, { width })
    must(!failures.length, failures.join('; '))
    return `${seen} screens`
  })
  await s.ctx.close()
}


// Issue 47: the monthly and the 12-week review in the weekly review's shell. They run in the Shared space, which has no plan or cycle of
// its own on the acceptance site: last month's plan and an ended 12 Week Year are made here and removed after. Titles start "I47 ".
// (I47.1 and I47.5, the due rules, are unit tests in lifeos/tests/test_issue47_reviews.py.)
for (const width of WIDTHS) {
  const tag = `I47.${width}`
  const phone = width < 800
  const S = 'Shared'
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I47 ${what} ${width} ${stamp}`
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const sb = (code) => bench(`import json
from frappe.utils import add_days, getdate, today
from lifeos.goals import cycles, habits
SP = "${S}"
OWNER = "owner@lifeos.test"
now = getdate(today())
last = add_days(now.replace(day=1), -1)
${code}`).split('\n').pop()
  const open = (p, extra = '') => s.open(`/life${p}${p.includes('?') ? '&' : '?'}space=${S}${extra}`)
  const cleanup = () => sb(`frappe.set_user("Administrator")
for r in frappe.get_all("Life Review", filters={"space": SP, "user": OWNER}, pluck="name"): frappe.delete_doc("Life Review", r, force=1, ignore_permissions=True)
for g in frappe.get_all("Life Goal", filters={"space": SP, "title": ["like", "I47 % ${width} ${stamp}"]}, pluck="name"):
    frappe.db.delete("Life Task", {"goal": g})
    frappe.db.set_value("Life Goal", g, {"carried_from": None, "serves": None})
for c in frappe.get_all("Life Cycle", filters={"space": SP}, pluck="name"):
    for g in frappe.get_all("Life Goal", filters={"cycle": c}, pluck="name"): frappe.db.set_value("Life Goal", g, "carried_from", None)
for g in frappe.get_all("Life Goal", filters={"space": SP, "title": ["like", "I47 % ${width} ${stamp}"]}, pluck="name"):
    frappe.db.delete("Life Goal Action", {"parent": g})
    frappe.db.delete("Life Goal", {"name": g})
for c in frappe.get_all("Life Cycle", filters={"space": SP}, pluck="name"):
    frappe.db.delete("Life Action Log", {"cycle": c})
    frappe.db.delete("Life Cycle", {"name": c})
frappe.db.delete("Life Habit", {"space": SP, "title": ["like", "I47 %"]})
print("{}")`)
  const area = () => sb('print(json.dumps(frappe.db.get_value("Life Area", {"space": SP, "is_on": 1}, "name") or frappe.db.get_value("Life Area", {"space": SP}, "name")))').replace(/"/g, '')
  // last month's plan: one goal done, three open, a habit; and a closed cycle that covers it, with ticks, so its weeks have scores
  const seedMonth = () => JSON.parse(sb(`frappe.set_user(OWNER)
a = frappe.db.get_value("Life Area", {"space": SP, "is_on": 1}, "name") or frappe.db.get_value("Life Area", {"space": SP}, "name")
goals = {}
for key in ("done", "carry", "drop", "finish"):
    goals[key] = cycles.add_month_goal(SP, last.year, last.month, "I47 goal " + key + " ${width} ${stamp}", a).name
frappe.db.set_value("Life Goal", goals["done"], "outcome", "Achieved")
habit = frappe.get_doc({"doctype": "Life Habit", "space": SP, "title": "I47 habit ${width} ${stamp}"}).insert().name
habits.set_month_habits(SP, last.year, last.month, [{"habit": habit, "days_per_week": 5}])
start = add_days(last.replace(day=1), -last.replace(day=1).weekday())
cyc = frappe.get_doc({"doctype": "Life Cycle", "space": SP, "title": "I47 look ${width} ${stamp}", "start_date": start, "status": "Planned"}).insert()
g = frappe.get_doc({"doctype": "Life Goal", "space": SP, "cycle": cyc.name, "horizon": "12 weeks", "title": "I47 look goal ${width} ${stamp}", "done_when": "x", "actions": [{"title": "I47 look act", "per_week": 3, "status": "Open"}]}).insert()
for w in (1, 2, 3, 4): cycles.set_tick(g.actions[0].name, w, 2)
frappe.db.set_value("Life Cycle", cyc.name, "status", "Closed")
print(json.dumps({"month": last.month, "year": last.year, "goals": goals, "habit": habit}))`))
  // an ended 12 Week Year: it ended today, with two goals, ticks, and lead actions
  const seedCycle = () => JSON.parse(sb(`frappe.set_user(OWNER)
a = frappe.db.get_value("Life Area", {"space": SP, "is_on": 1}, "name") or frappe.db.get_value("Life Area", {"space": SP}, "name")
for c in frappe.get_all("Life Cycle", filters={"space": SP, "status": "Active"}, pluck="name"): frappe.db.set_value("Life Cycle", c, "status", "Closed")
cyc = frappe.get_doc({"doctype": "Life Cycle", "space": SP, "title": "I47 cycle ${width} ${stamp}", "start_date": add_days(now, -84), "status": "Active"}).insert()
out = {}
for key, per in (("done", 3), ("carry", 2), ("drop", 1)):
    g = frappe.get_doc({"doctype": "Life Goal", "space": SP, "cycle": cyc.name, "horizon": "12 weeks", "title": "I47 cg " + key + " ${width} ${stamp}", "area": a, "done_when": "Finished " + key,
        "sort_order": 10 + per, "actions": [{"title": "I47 act " + key, "per_week": per, "status": "Open"}]}).insert()
    out[key] = g.name
    for w in (1, 2, 3, 5): cycles.set_tick(g.actions[0].name, w, per)
actions, ticks = cycles._actions(cyc.name), cycles._ticks(cyc.name)
print(json.dumps({"cycle": cyc.name, "goals": out, "expected": cycles.cycle_average(cyc, actions, ticks, cycles.WEEKS)}))`))
  const next = async () => { await pg.locator('[data-review-next]').click(); await pg.waitForTimeout(700) }
  const tabNow = () => pg.locator('[data-review]').first().getAttribute('data-review-tab')
  const choose = (goal, pile) => pg.locator(`[data-decide-goal][data-goal="${goal}"] [data-choose="${pile}"]`).click()
  try {
    cleanup()
    await check('REVIEW.14', `${width} px: the monthly review's Look back shows the month's goals, habits and weekly scores`, async () => {
      seedMonth()
      await open('/review?kind=monthly')
      await pg.locator('[data-review-look]').waitFor({ timeout: 20000 })
      await pg.waitForTimeout(800)
      const rows = await pg.locator('[data-look-goal]').evaluateAll((els) => els.map((e) => [e.innerText, e.getAttribute('data-result')]))
      must(rows.length === 4, `Look back lists ${rows.length} goals, not 4: ${JSON.stringify(rows)}`)
      must(rows.some(([t, r]) => t.includes(T('goal done')) && r === 'done'), 'the done goal is not marked done')
      must(rows.some(([t, r]) => t.includes(T('goal carry')) && r === 'missed'), 'an open goal with no tasks is not marked missed')
      must((await pg.locator('[data-look-habit]').allInnerTexts()).some((t) => t.includes(`I47 habit ${width} ${stamp}`)), 'the habit is not shown')
      const look = await s.api('periodic.look', { space: S, kind: 'monthly' })
      must(look.weeks.length >= 3, 'the server gives no weeks for the month')
      must(await pg.locator('[data-look-week]').count() === look.weeks.length, `Look back shows ${await pg.locator('[data-look-week]').count()} weeks, the server ${look.weeks.length}`)
      must((await pg.locator('[data-look-week]').first().innerText()).includes(Math.round(look.weeks[0].percent) + '%'), 'the first weekly score is not the server\'s')
      must(await pg.locator('[data-review-head] [data-page-title]').innerText() === 'Monthly review', 'the title is not Monthly review')
      await noSideways()
    })

    await check('REVIEW.15', `${width} px: Decide: carry one goal and drop another with a reason; after Lock the plan holds the carried goal and the dropped one is dropped`, async () => {
      const g = JSON.parse(sb(`print(json.dumps({k: frappe.db.get_value("Life Goal", {"space": SP, "title": "I47 goal " + k + " ${width} ${stamp}"}) for k in ("done", "carry", "drop", "finish")}))`))
      await open('/review?kind=monthly&tab=decide')
      await pg.locator('[data-review-decide]').waitFor({ timeout: 20000 })
      must(await pg.locator('[data-decide-goal]').count() === 3, 'Decide does not list the three goals that are not done')
      must(!(await pg.locator(`[data-decide-goal][data-goal="${g.done}"]`).count()), 'the done goal is up for decision')
      must(await pg.locator('[data-review-next]').isDisabled(), 'Next is open with goals undecided')
      await choose(g.carry, 'carry')
      await choose(g.drop, 'drop')
      await choose(g.finish, 'finish')
      await pg.waitForTimeout(600)
      const counts = await pg.locator('[data-pile-key]').evaluateAll((els) => Object.fromEntries(els.map((e) => [e.getAttribute('data-pile-key'), e.querySelector('[data-pile-count]').innerText.trim()])))
      must(counts.finish === '1' && counts.carry === '1' && counts.drop === '1', `the piles read ${JSON.stringify(counts)}`)
      must(await pg.locator('[data-review-next]').isDisabled(), 'Next is open with a reason and a date missing')
      await pg.locator(`[data-decide-goal][data-goal="${g.drop}"] [data-decide-reason] input, input[data-decide-reason]`).first().fill('Not worth the time')
      await pg.locator(`[data-decide-goal][data-goal="${g.finish}"] input[data-decide-date], [data-decide-goal][data-goal="${g.finish}"] [data-decide-date] input`).first().fill(addDays(5))
      await pg.keyboard.press('Tab')
      await pg.waitForTimeout(1800)
      must(await pg.locator('[data-review-next]').isEnabled(), 'Next stays shut: ' + (await pg.locator('[data-review-footer-line]').innerText()))
      await next()
      await pg.locator('[data-review-plan]').waitFor({ timeout: 10000 })
      const first = await pg.locator('[data-plan-goal]').first().innerText()
      must(first.includes('goal carry') && (await pg.locator('[data-plan-goal]').first().getAttribute('data-carried')) === '1', 'the carried goal is not first in the plan')
      // Plan: two goals in the order given, and a habit
      const a = await area()
      for (const n of ['one', 'two']) {
        await pg.locator('[data-plan-add]').click()
        const row = pg.locator('[data-plan-goal]').last()
        await row.locator('[data-plan-title] input, input[data-plan-title]').first().fill(T('plan ' + n))
        await row.locator('[data-plan-area]').first().click(); await pg.getByRole('option').first().click()
      }
      await pg.waitForTimeout(1800)
      must(await pg.locator('[data-review-next]').isEnabled(), 'Plan stays shut: ' + (await pg.locator('[data-review-footer-line]').innerText()))
      await next()
      await pg.locator('[data-review-reflect]').waitFor({ timeout: 10000 })
      await pg.locator('[data-went-well] textarea, textarea[data-went-well]').first().fill('I47 went well')
      await pg.locator('[data-review-next]').click()
      await pg.locator('[data-review-done]').waitFor({ timeout: 20000 })
      const out = JSON.parse(sb(`print(json.dumps({"carry": frappe.db.get_value("Life Goal", "${g.carry}", "outcome"), "drop": frappe.db.get_value("Life Goal", "${g.drop}", ["outcome", "result_note"]),
  "finish": str(frappe.db.get_value("Life Goal", "${g.finish}", "target_date")), "next": [x["title"] for x in cycles.month_goals(SP, now.year, now.month)]}))`))
      must(out.carry === 'Carried', `the carried goal is ${out.carry}`)
      must(out.drop[0] === 'Dropped' && out.drop[1] === 'Not worth the time', `the dropped goal is ${JSON.stringify(out.drop)}`)
      must(out.finish === addDays(5), `the finish date is ${out.finish}`)
      must(out.next.some((t) => t.endsWith('goal carry ' + width + ' ' + stamp)), `this month's plan lacks the carried goal: ${out.next}`)
    })

    await check('REVIEW.16', `${width} px: the goals made in Plan are in the order given, and Goals > Cycles shows them`, async () => {
      const order = JSON.parse(sb(`print(json.dumps([x["title"] for x in cycles.month_goals(SP, now.year, now.month) if x["title"].startswith("I47 ") and x["title"].endswith("${width} ${stamp}") and " finish " not in x["title"]]))`))
      must(order.length === 3 && order[0].includes('goal carry') && order[1].endsWith(`plan one ${width} ${stamp}`) && order[2].endsWith(`plan two ${width} ${stamp}`), `this month's goals are ${order}`)
      await open('/goals/cycles')
      await pg.locator('[data-cycles][data-loaded="1"]').waitFor({ timeout: 15000 })
      const shown = (await pg.locator('[data-month-goal]').allInnerTexts()).filter((t) => !t.includes(' finish ')).map((t) => t.split('\n').find((l) => l.startsWith('I47 ')))
      must(JSON.stringify(shown.filter(Boolean)) === JSON.stringify(order), `Cycles shows ${shown}, not ${order}`)
      const reviewed = await s.api('periodic.due', { space: S })
      must(!reviewed.due.some((d) => d.kind === 'monthly'), 'the monthly review is still due after Lock')
      must(reviewed.past.some((p) => p.kind === 'Monthly'), 'the locked review is not among the past reviews')
    })

    cleanup()
    await check('REVIEW.17', `${width} px: with no month to look back on, the monthly review says nothing is due`, async () => {
      await open('/review?kind=monthly')
      await pg.locator('[data-review-not-due]').waitFor({ timeout: 15000 })
      must((await pg.locator('[data-review-not-due]').innerText()).includes('No monthly review is due'), 'the empty state does not say so')
      await noSideways()
    })

    await check('REVIEW.18', `${width} px: the 12-week review's Score shows the twelve weekly scores and the cycle view's average`, async () => {
      const c = seedCycle()
      await open('/review?kind=12-weeks')
      await pg.locator('[data-review-score]').waitFor({ timeout: 20000 })
      await pg.waitForTimeout(800)
      const grid = await s.api('goals.grid', { space: S, cycle: c.cycle })
      must(await pg.locator('[data-score-week]').count() === 12, 'Score does not show twelve weeks')
      const got = await pg.locator('[data-score-week]').evaluateAll((els) => els.map((e) => Number(e.getAttribute('data-score'))))
      must(JSON.stringify(got) === JSON.stringify(grid.weeks.map((w) => Math.round(w.percent))), `the weeks read ${got}, the grid ${grid.weeks.map((w) => Math.round(w.percent))}`)
      must((await pg.locator('[data-score-average]').innerText()).trim() === Math.round(grid.average) + '%', 'the average is not the grid\'s')
      must(await pg.locator('[data-score-goal]').count() === 3, 'Score does not list the three goals')
      must(await pg.locator('[data-review-head] [data-page-title]').innerText() === '12-week review', 'the title is not 12-week review')
      await noSideways()
    })

    await check('REVIEW.19', `${width} px: Goals > Cycles offers the 12-week review, and there is no Close cycle pop-up (its link opens the review)`, async () => {
      await open('/goals/cycles')
      await pg.locator('[data-cycles][data-loaded="1"]').waitFor({ timeout: 15000 })
      const card = pg.locator('[data-review-due][data-review-kind="12-weeks"]')
      must(await card.isVisible(), 'Cycles does not say the 12-week review is due')
      must((await card.innerText()).includes('The 12-week review is due'), 'the card does not say so')
      await open('/today/year?view=goals')
      await pg.locator('[data-open-cycle-review]').waitFor({ timeout: 15000 })
      must(!(await pg.getByRole('button', { name: 'Close cycle', exact: true }).count()), 'a Close cycle button is still there')
      await pg.locator('[data-open-cycle-review]').click()
      await pg.waitForURL((u) => u.pathname === '/life/review' && u.searchParams.get('kind') === '12-weeks', { timeout: 10000 })
      await pg.locator('[data-review-kind="12-weeks"], [data-review-not-due]').first().waitFor({ timeout: 20000 })
      must(await pg.locator('[data-review-kind="12-weeks"]').isVisible(), 'the link did not open the 12-week review')
    })

    await check('REVIEW.20', `${width} px: both reviews show ${phone ? 'one tab at a time behind a step bar' : 'numbered tabs'}, and nothing scrolls sideways`, async () => {
      for (const kind of ['12-weeks', 'monthly']) {
        if (kind === 'monthly') { seedMonth() }
        await open(`/review?kind=${kind}`)
        await pg.locator(`[data-review-kind="${kind}"] [data-review-head]`).waitFor({ timeout: 20000 })
        const bar = await pg.locator('[data-review-stepbar]').isVisible()
        const tabs = await pg.locator('[data-review-tab-btn]').first().isVisible()
        must(phone ? bar && !tabs : !bar && tabs, `${kind}: the step bar is ${bar} and the tabs ${tabs}`)
        must(await pg.locator('[data-review-score], [data-review-look], [data-review-decide], [data-review-plan], [data-review-reflect]').count() === 1, `${kind}: more than one tab is shown`)
        if (phone) must(/Step \d of 4/.test(await pg.locator('[data-review-stepbar]').innerText()), `${kind}: the step bar does not say Step n of 4`)
        await noSideways()
      }
      must(!errors.length, 'page errors: ' + errors.join('; '))
    })

    await check('REVIEW.21', `${width} px: when a weekly and a monthly review are both due, Review shows the weekly first, then the monthly`, async () => {
      // no cycle: only the weekly (an open one) and the monthly are due
      cleanup()
      seedMonth()
      sb(`for c in frappe.get_all("Life Cycle", filters={"space": SP, "status": "Active"}, pluck="name"): frappe.db.set_value("Life Cycle", c, "status", "Closed")
from lifeos.review.record import Review
Review.start(SP, OWNER)`)
      const due = (await s.api('periodic.due', { space: S })).due.map((d) => d.kind)
      must(JSON.stringify(due) === JSON.stringify(['weekly', 'monthly']), `the server says ${due}`)
      await open('/review')
      await pg.locator('[data-review-strip]').waitFor({ timeout: 20000 })
      const chips = await pg.locator('[data-due-kind]').evaluateAll((els) => els.map((e) => e.getAttribute('data-due-kind')))
      must(JSON.stringify(chips) === JSON.stringify(['weekly', 'monthly']), `the strip shows ${chips}`)
      await pg.locator('[data-review]').first().waitFor({ timeout: 20000 })
      must(await pg.locator('[data-review][data-review-kind="weekly"]').count() === 1, 'Review did not open on the weekly review')
      await pg.locator('[data-due-kind="monthly"]').click()
      await pg.locator('[data-review-kind="monthly"]').waitFor({ timeout: 20000 })
    })

    await check('REVIEW.22', `${width} px: a review left after step 2 resumes at step 2 with its decisions kept`, async () => {
      sb(`frappe.db.delete("Life Review", {"space": SP, "user": OWNER, "kind": "Weekly"})`)
      const g = JSON.parse(sb(`print(json.dumps({k: frappe.db.get_value("Life Goal", {"space": SP, "title": "I47 goal " + k + " ${width} ${stamp}"}) for k in ("done", "carry", "drop", "finish")}))`))
      await open('/review?kind=monthly&tab=decide')
      await pg.locator('[data-review-decide]').waitFor({ timeout: 20000 })
      await choose(g.carry, 'carry')
      await choose(g.drop, 'drop')
      await pg.waitForTimeout(800)
      await s.open('/life')
      await open('/review?kind=monthly')
      await pg.locator('[data-review-decide]').waitFor({ timeout: 20000 })
      must((await tabNow()) === 'decide', `the review resumed at ${await tabNow()}`)
      must((await pg.locator(`[data-decide-goal][data-goal="${g.carry}"] [data-choose="carry"]`).getAttribute('aria-pressed')) === 'true', 'the carry decision was lost')
      must((await pg.locator(`[data-decide-goal][data-goal="${g.drop}"]`).getAttribute('data-pile')) === 'drop', 'the drop decision was lost')
      must(Number(sb(`print(frappe.db.count("Life Review", {"space": SP, "user": OWNER, "kind": "Monthly", "status": "Open"}))`)) === 1, 'there is more than one open monthly review')
    })

    await check('REVIEW.23', `${width} px: deciding each goal and locking closes the cycle with cycles.close_cycle's score and makes the next cycle with the carried goals and their lead actions`, async () => {
      cleanup()
      const c = seedCycle()
      await open('/review?kind=12-weeks')
      await pg.locator('[data-review-score]').waitFor({ timeout: 20000 })
      await next()
      await pg.locator('[data-review-decide]').waitFor({ timeout: 10000 })
      await choose(c.goals.done, 'done')
      await choose(c.goals.carry, 'carry')
      await choose(c.goals.drop, 'drop')
      await pg.locator(`[data-decide-goal][data-goal="${c.goals.drop}"] [data-decide-reason] input, input[data-decide-reason]`).first().fill('Out of scope')
      await pg.waitForTimeout(1800)
      await next()
      await pg.locator('[data-review-plan]').waitFor({ timeout: 10000 })
      const carried = pg.locator('[data-plan-goal][data-carried="1"]')
      must(await carried.count() === 1, 'the plan does not hold the one carried goal')
      await carried.locator('[data-plan-done-when] input, input[data-plan-done-when]').first().fill('I47 shipped by March')
      await carried.locator('[data-plan-action] input').first().fill('I47 weekly push')
      await pg.locator('[data-plan-add]').click()
      const fresh = pg.locator('[data-plan-goal]').last()
      await fresh.locator('[data-plan-title] input, input[data-plan-title]').first().fill(T('new cycle goal'))
      await fresh.locator('[data-plan-area]').first().click(); await pg.getByRole('option').first().click()
      await fresh.locator('[data-plan-done-when] input, input[data-plan-done-when]').first().fill('It is live')
      await fresh.locator('[data-plan-action] input').first().fill('I47 write')
      await pg.waitForTimeout(1800)
      await next()
      await pg.locator('[data-review-reflect]').waitFor({ timeout: 10000 })
      await pg.locator('[data-went-well] textarea, textarea[data-went-well]').first().fill('I47 cycle learned')
      await pg.locator('[data-review-next]').click()
      await pg.locator('[data-review-done]').waitFor({ timeout: 30000 })
      const out = JSON.parse(sb(`cyc = frappe.get_doc("Life Cycle", "${c.cycle}")
nxt = frappe.db.get_value("Life Cycle", {"space": SP, "start_date": cycles.next_monday(cyc.end_date)}, ["name", "status"], as_dict=True)
goals = frappe.get_all("Life Goal", filters={"cycle": nxt.name}, fields=["name", "title", "done_when", "carried_from"], order_by="sort_order asc")
acts = {g.name: [(a.title, a.per_week) for a in frappe.get_doc("Life Goal", g.name).actions] for g in goals}
print(json.dumps({"status": cyc.status, "score": cyc.final_score, "next": nxt.status, "goals": goals, "acts": acts,
  "outcomes": {k: frappe.db.get_value("Life Goal", v, "outcome") for k, v in ${JSON.stringify(c.goals)}.items()}}))`))
      must(out.status === 'Closed' && out.score === c.expected, `the cycle is ${out.status} with score ${out.score}, cycles.close_cycle gives ${c.expected}`)
      must(out.outcomes.done === 'Achieved' && out.outcomes.carry === 'Carried' && out.outcomes.drop === 'Dropped', `the outcomes are ${JSON.stringify(out.outcomes)}`)
      must(out.next === 'Planned' && out.goals.length === 2, `the next cycle is ${out.next} with ${out.goals.length} goals`)
      const kept = out.goals.find((g) => g.carried_from === c.goals.carry)
      must(kept && kept.done_when === 'I47 shipped by March', 'the carried goal is not in the next cycle with its new Done when')
      must(JSON.stringify(out.acts[kept.name]) === JSON.stringify([['I47 weekly push', 2]]), `the carried goal's lead actions are ${JSON.stringify(out.acts[kept.name])}`)
      must(out.goals.some((g) => g.title.includes('new cycle goal')), 'the goal added in Plan is not in the next cycle')
    })
  } finally {
    try { cleanup() } catch (e) { /* reported by the debris check */ }
    await s.ctx.close()
  }
}

// Issue 118: Weekly review > Tasks > Waiting on others: the waiting pile by person, oldest first; Done, Move to my plate, Still waiting.
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const tag = `I118W ${width} ${stamp}`
  const mk = (who, title, days) => bench(`import json
from frappe.utils import add_days, now_datetime
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${tag} ${title}", "status": "Waiting", "waiting_on": "${who}", "check_by": add_days(frappe.utils.today(), 3)}).insert(ignore_permissions=True)
frappe.db.set_value("Life Task", t.name, "creation", add_days(now_datetime(), -${days}), update_modified=False)
print(t.name)`).split('\n').pop()
  try {
    await check('REVIEW.24', `${width} px: Waiting on others groups the waiting tasks by person, oldest first; Done closes one, Move to my plate puts one on Today's list, Still waiting moves check-by on by 7 days`, async () => {
      const ravi1 = mk('Ravi I118W', 'old photos', 12)
      const ravi2 = mk('Ravi I118W', 'newer sheet', 3)
      const meera = mk('Meera I118W', 'fee form', 8)
      await s.open('/life/today/week?view=review&tab=tasks')
      const sec = pg.locator('[data-waiting-on-others]')
      await sec.locator(`[data-waiting-task][data-task="${ravi1}"]`).waitFor({ timeout: 15000 })
      const rows = async (who) => sec.locator(`[data-waiting-group][data-who="${who}"] [data-waiting-task]`).evaluateAll((els) => els.map((e) => e.getAttribute('data-task')))
      must(JSON.stringify(await rows('Ravi I118W')) === JSON.stringify([ravi1, ravi2]), 'the person group is not oldest first: ' + JSON.stringify(await rows('Ravi I118W')))
      must((await sec.locator(`[data-waiting-task][data-task="${meera}"]`).innerText()).includes('since'), 'a row does not say since when')
      await sec.locator(`[data-waiting-task][data-task="${ravi2}"] [data-waiting-done]`).click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-waiting-task][data-task="${n}"]`), ravi2, { timeout: 10000 })
      const status = (n) => bench(`print(frappe.db.get_value("Life Task", "${n}", "status"))`).split('\n').pop()
      must(status(ravi2) === 'Done', 'Done did not close the task')
      const before = bench(`print(frappe.db.get_value("Life Task", "${meera}", "check_by"))`).split('\n').pop()
      await sec.locator(`[data-waiting-task][data-task="${meera}"] [data-waiting-change]`).click()
      await pg.getByRole('menuitem', { name: 'Still waiting' }).click()
      await pg.waitForTimeout(800)
      const after = bench(`print(frappe.db.get_value("Life Task", "${meera}", "check_by"))`).split('\n').pop()
      must(Math.round((Date.parse(after) - Date.parse(before)) / 86400e3) === 7, `check-by went from ${before} to ${after}`)
      await sec.locator(`[data-waiting-task][data-task="${ravi1}"] [data-waiting-change]`).click()
      await pg.getByRole('menuitem', { name: 'Move to my plate' }).click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-waiting-task][data-task="${n}"]`), ravi1, { timeout: 10000 })
      const t = JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Task", "${ravi1}", ["status", "due_date"], as_dict=True), default=str))`).split('\n').pop())
      must(t.status === 'Open' && t.due_date === today, 'the task is not on the plate: ' + JSON.stringify(t))
    })
  } finally {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "I118W %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}
