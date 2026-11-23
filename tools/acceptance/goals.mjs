// Goals: By area, All tasks, No goal, Cycles, the goal page and its edit form, focuses, horizons and Someday.
// Checks are numbered GOALS.<n> in the order they appear here; `node tools/acceptance.mjs --only=GOALS` runs this file's checks.
import { SPACE, WIDTHS, addDays, areaId, areas, base, bench, check, iso, must, owner, path, results, root, runAgent, session, stamp, today } from './context.mjs'
import { ROW, STATE_TABS, num, ux, uxArea, uxKit } from './ux.mjs'

await check('GOALS.1', 'Tick a habit at phone width and see the month count change', async () => {
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

await check('GOALS.2', 'Tick week cells in the 12 Week Year grid and see the week score change', async () => {
  await owner.open('/life/goals/cycles')
  await owner.page.locator('[data-week-so-far]').waitFor({ timeout: 10000 })
  const stat = () => owner.page.locator('[data-week-so-far]').first().innerText()
  const before = (await stat()).replace(/\n/g, ' ')
  const g = await owner.api('goals.grid', { space: SPACE })
  const col = g.current_week
  // an empty tick of the current week (issue 45: the ticks are on Goals > Cycles)
  const cells = owner.page.locator('[data-tick]:not([disabled])')
  const empty = owner.page.locator('[data-tick][aria-pressed="false"]:not([disabled])')
  must(await cells.count(), 'Cycles has no ticks for the current week')
  await ((await empty.count()) ? empty.first() : cells.first()).click()
  await owner.page.waitForTimeout(800)
  const after = (await stat()).replace(/\n/g, ' ')
  must(before !== after, 'score stayed at ' + before)
  const g2 = await owner.api('goals.grid', { space: SPACE })
  must(JSON.stringify(g2.weeks?.[col - 1] ?? g2.average) !== JSON.stringify(g.weeks?.[col - 1] ?? g.average) || before !== after, 'server score unchanged')
  return `${before} -> ${after}`
})

await check('GOALS.3', 'Carry an open October goal into November: the month card of Cycles shows it with where it came from', async () => {
  // a month goal is a goal with the Month horizon; carrying is what the monthly review does, so this calls the rule it calls
  const old = (await owner.api('goals.create', { space: SPACE, title: `October goal ${stamp}`, horizon: 'Month', target_date: '2026-10-31', done_when: 'Done' })).name
  const out = JSON.parse(bench(`import json
from lifeos.goals import cycles
frappe.set_user("owner@lifeos.test")
print(json.dumps(cycles.carry_month_goal("${old}")))`).split('\n').pop())
  const oct = await owner.api('goals.this_month', { space: SPACE, year: 2026, month: 10 })
  const nov = await owner.api('goals.this_month', { space: SPACE, year: 2026, month: 11 })
  must(oct.goals.find((x) => x.row === old).status === 'Carried', 'the October goal is not marked Carried')
  const moved = nov.goals.find((x) => x.row === out.row)
  must(moved && moved.title === `October goal ${stamp}` && moved.carried_from === old && moved.carried_from_month === 10, 'the goal is not in November, carried from October')
  return moved.title
})

await check('GOALS.4', 'Tea & Coffee in the lens: Plan and Library show its open-ended goals, tasks, notes and chats together', async () => {
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

await check('GOALS.5', 'Complete an open-ended goal: it and its records move to Archive. Restore it', async () => {
  const g = await owner.api('goals.create', { space: SPACE, title: `Open goal ${stamp}`, horizon: 'Long term', area: areaId('Learning') })
  const task = await owner.api('tasks.quick_add', { text: `Goal task ${stamp}`, space: SPACE, goal: g.name })
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

for (const width of WIDTHS) {
  const { S5, count, errors, nav, overflow, pane, paneTitle, pg, phone, s, settle, tag, tasksLike } = await uxKit(width)
  await check('GOALS.6', `${width} px: state tabs: each count equals the rows its tab shows, with and without another filter; links land on their tab`, async () => {
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
    // issue 55: the Open band's doors moved to Goals, the Library and the sidebar; I55.5 checks them there
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
      await s.open('/life/library/archive?type=Life+Vault+Document')
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

  await check('GOALS.7', `${width} px: a goal's page: each tab opens with its count, its list matches the main screen, reload stays, a row opens the pane in the tab`, async () => {
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

  await check('GOALS.8', `${width} px: goals of every type: task figure, archive keeps it, tabs, score blank, add to a cycle, family sees none`, async () => {
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
    const gridHas = async (n) => { const g = await s.api('goals.across_cycles', { space: SPACE }); return g.cycles.some((c) => c.goals.some((x) => x.name === n)) }
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

  await check('GOALS.9', `${width} px: Someday: a task, an open-ended goal with two tasks, a goal and an idea leave Today, Tasks and the Open counts and keep their creation dates; due for review after the date, also in Reset; Bring back with a date; Purge to the trash and Restore`, async () => {
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

  await check('GOALS.10', `${width} px: ?area= narrows Today, Inbox, every Plan tab and every Library tab; each count matches its rows and the server; the chip and the URL show it; it survives a reload; clearing it restores every count`, async () => {
    let step = 'start'
    const calls = []
    const onReq = (r) => { const u = r.url(); if (u.includes('/api/method/lifeos.api.')) calls.push({ m: u.split('/api/method/lifeos.api.')[1].split('?')[0], url: u, body: r.postData() || '' }) }
    const carries = (m) => calls.some((c) => (!m || c.m === m) && (new URL(c.url).searchParams.get('area') === uxArea || c.body.includes(`"area":"${uxArea}"`)))
    const lensIn = () => new URL(pg.url()).searchParams.get('area')
    const areaName = areas.find((x) => x.name === uxArea).area_name
    const goto = async (p, area = uxArea) => { calls.length = 0; await pg.goto(base + p + (p.includes('?') ? '&' : '?') + 'area=' + area, { waitUntil: 'networkidle' }); await settle() } // issue 46: the area is each page's own `?area=`, not carried
    const band = async (area) => (await s.api('counts.get', { space: SPACE, which: 'tasks', area })).open_tasks.n // issue 55: the open tasks number moved from Today to Goals > All tasks
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
    const R = [['Plan > Week, Calendar', '/life/today/week?view=calendar'], /* set 8: the review is about the whole plate and keeps no lens, like Reset */ ['Goals > Cycles', '/life/goals/cycles'],
      ['Plan > Month, Calendar', '/life/today/month?view=calendar'], ['Plan > Year, Calendar', '/life/today/year?view=calendar'],
      ['Plan > Year, Goals', '/life/today/year?view=goals']]
    pg.on('request', onReq)
    try {
      step = 'the counts on All of life'
      const before = {}
      await s.open('/life') // a first visit to Today makes what it needs (a record Library > All lists), so it is made before counting
      for (const [name, p] of L) { step = `the counts on All of life: ${name}`; await s.open(p); before[name] = await count() }
      await s.open('/life')
      const band0 = await band('')
      step = 'open Today with the area'
      await goto('/life')
      must(lensIn() === uxArea, `the URL has area=${lensIn()}`)
      must((await pg.locator('[data-lens-chip]:visible').innerText()).includes(areaName), 'the header has no chip for the area')
      step = 'Today under the lens'
      must(carries('today.get'), 'Today did not ask for the area')
      const c = await s.api('counts.get', { space: SPACE, area: uxArea })
      must((await band(uxArea)) === c.open_tasks.n && c.open_tasks.n < band0, `the open tasks say ${await band(uxArea)} (all of life ${band0}), the count helper ${c.open_tasks.n}`)
      if (!phone) {
        const sc = await s.api('session.counts', { space: SPACE, area: uxArea })
        const inboxBadge = pg.locator('[data-nav-count="Inbox"]')
        must(((await inboxBadge.count()) ? num(await inboxBadge.innerText()) : 0) === sc.doors.inbox.n, `the sidebar's Inbox count is not the area's (${sc.doors.inbox.n})`)
      }
      // the open tasks number is a door (now on Goals > All tasks): under the lens it opens a list with exactly that many rows
      await goto('/life' + c.open_tasks.to.path + '?' + new URLSearchParams(Object.fromEntries(Object.entries(c.open_tasks.to.query).filter(([k]) => k !== 'area'))))
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
      await pg.locator('[data-lens-chip]:visible').first().click(); await pg.waitForLoadState('networkidle'); await settle()
      must(!lensIn() && !(await pg.locator('[data-lens-chip]:visible').count()), `clearing left area=${lensIn()} or the chip`)
      for (const [name, p] of L) {
        await goto(p, '')
        must(!lensIn(), `${name}: the cleared lens came back`)
        const server = L.find((x) => x[0] === name)[3]
        const want = server ? await server(undefined) : before[name] // the server's own count: a record made while the check ran is not a failure of clearing
        must((await count()) === want, `${name}: ${await count()} after clearing, ${want} expected (${before[name]} before)`)
      }
      await goto('/life', '')
      must((await band('')) === band0, `the open tasks say ${await band('')} after clearing, ${band0} before`)
      return done.join(', ')
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) } finally {
      pg.off('request', onReq)
      await s.open('/life?area=')
    }
  })
  await s.ctx.close()
}

await check('GOALS.11', 'An open-ended goal opens with its tasks; a goal shows what it serves and what serves it, and cannot serve its own servant', async () => {
  const pg = owner.page
  const got = await owner.api('goals.get', { goal: ux.goal })
  must(got.goal.horizon === 'Long term', `the goal is ${got.goal.horizon}`)
  await owner.open(`/life/goals/${ux.goal}`)
  must((await pg.locator('h1').first().innerText()).includes(got.goal.title), 'the goal page does not show the goal title')
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
  return `${got.goal.title}: ${open} open tasks`
})
// Key results, the Outbox and the weekly review's goal step. Every record carries "S7 … <width> <stamp>" and is removed by S4.1.
const s7Settings = await owner.api('settings.get', { space: SPACE })
for (const width of WIDTHS) {
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
  const cycle = (await owner.api('goals.grid', { space: SPACE })).cycle

  await check('GOALS.12', `${width} px: New goal asks "Done when…": a milestone goal and a number goal through the dialog; a frequency offers Make it a habit`, async () => {
    const make = async (title, fill) => {
      await s.open('/life/goals')
      await pg.locator('[data-new-goal]').first().click()
      await settle()
      const dlg = pg.locator('[role="dialog"]').last()
      await field(dlg, 'data-goal-title').fill(title)
      // Open goals are retired (issue 57): a goal here is a 12 Week Year goal, which needs no target date
      await pick(dlg, 'Horizon', '12 weeks', 'data-goal-horizon')
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
    const habits = await s.api('goals.month_habits', { space: SPACE })
    must(habits.habits.some((h) => h.title === `S7 walk 3 times a week ${W}` && h.days_per_week === 3), 'the habit is not in this month')
    must(!(await s.api('goals.list', { space: SPACE, state: 'all', filters: [['title', 'like', `S7 walk%${stamp}%`]] })).goals.length, 'a goal was made for the habit')
    return 'milestone, number 84 → 78 kg, habit 3 a week'
  })

  await check('GOALS.13', `${width} px: the fake agent submits a Reading; it waits in the weekly review; Confirm updates the goal's current value and result bar`, async () => {
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
  await check('GOALS.14', `${width} px: a 12-week goal serving a longer goal shows on both`, async () => {
    must(cycle, 'no active cycle')
    const long = (await s.api('goals.create', { space: SPACE, title: `S7 long goal ${W}`, horizon: 'Year', target_date: addDays(200), area: areaId('Tea & Coffee'),
      done_when: 'A new client signed' })).name
    const g = (await s.api('goals.save_goal', { cycle: cycle.name, title: `S7 cycle goal ${W}`, area: areaId('Tea & Coffee'), serves: long, measure_kind: 'Milestone',
      done_when: 'Ten pitches made', actions: [{ title: `S7 calls ${W}`, per_week: 4 }] })).goal
    action = (await s.api('goals.detail', { goal: g })).goal.actions[0]
    await s.open('/life/goals/cycles')
    const line = pg.locator('[data-grid-serves]', { hasText: `S7 long goal ${W}` })
    await line.first().waitFor({ timeout: 10000 }).catch(() => {})
    must(await line.count(), 'Goals > Cycles does not show the goal it serves')
    await s.open(`/life/goals/${long}`)
    const served = pg.locator('[data-goal-served-by]')
    must((await served.innerText()).includes(`S7 cycle goal ${W}`) && (await served.innerText()).includes(cycle.title), 'the longer goal does not show the cycle goal with its cycle')
    await s.open(`/life/goals/${g}`)
    must((await pg.locator('[data-goal-serves-progress]').innerText()).includes(`S7 long goal ${W}`), "the cycle goal's page does not show what it serves")
    return `${cycle.title}`
  })

  await check('GOALS.15', `${width} px: ticking a 4-a-week action once shows 1 of 4 and raises the week score`, async () => {
    must(action, 'no action from the check before')
    const g = await s.api('goals.grid', { space: SPACE })
    const wk = g.current_week
    const before = await s.api('goals.week_score', { cycle: cycle.name, week: wk })
    await s.open('/life/goals/cycles')
    const cell = pg.locator(`button[data-tick][aria-label^="S7 calls ${W}, tick 1 "]`).first()
    await cell.waitFor({ timeout: 10000 }).catch(() => {})
    must(await cell.count(), 'the action is not on Goals > Cycles')
    await cell.click()
    await pg.waitForLoadState('networkidle')
    await settle()
    must((await cell.getAttribute('aria-pressed')) === 'true', 'the first tick of the action is not set')
    must((await pg.locator('[data-cycle-goal]', { hasText: `S7 calls ${W}` }).locator('[data-tick-count]').innerText()).startsWith('1 of 4'), 'the goal row does not say 1 of 4')
    const after = await s.api('goals.week_score', { cycle: cycle.name, week: wk })
    must(after.done === before.done + 1 && after.percent > before.percent, `score ${before.percent}% → ${after.percent}%`)
    await s.open('/life')
    const row = pg.locator('[data-next] [data-why="12WY"]', { hasText: `S7 calls ${W}` })
    if (await row.count()) must((await row.innerText()).includes('1 of 4 this week'), 'Today does not say 1 of 4')
    return `${before.percent}% → ${after.percent}%`
  })

  await check('GOALS.16', `${width} px: completing, delegating, parking and dropping a task each add to the right Outbox pile; Bring back reverses; Brain > Activity's in and out match the Outbox lists`, async () => {
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
    // issue 55: the in and out line moved from Today to Brain > Activity; its numbers are the lists' counts
    const line = await s.api('counts.get', { space: SPACE, which: 'week' })
    await s.open('/life/brain/activity')
    await pg.locator('[data-flow]').waitFor({ timeout: 10000 })
    const seen = []
    for (const [key, sel] of [['in', '[data-flow-in]'], ['out', '[data-flow-out]']]) {
      const n = Number((await pg.locator(sel).innerText()).replace(/\D/g, ''))
      must(n === line[key].n, `Activity says ${n} ${key}, the count helper ${line[key].n}`)
      const listed = await s.api('outbox.list', { space: SPACE, pile: key === 'in' ? 'in' : 'all', period: 'week', page_length: 500 })
      must(listed.total === n, `${key}: ${n} on Activity, the Outbox lists ${listed.total}`)
      seen.push(n)
    }
    must(errors.length === 0, 'script errors: ' + errors.join(' | ').slice(0, 300))
    return `in ${seen[0]}, out ${seen[1]}`
  })

  await check('GOALS.17', `${width} px: goal work planned the way Lock the week plans it makes a scheduled task that shows on Today and in the week calendar, and a delegated one that shows as Waiting`, async () => {
    // set 8: the cards of set 7's goal step became the review's Goals tab (checked by S8); here the same planning call
    const a = (await s.api('goals.create', { space: SPACE, title: `S7 plan goal ${W}`, horizon: 'Long term', area: areaId('Personal'), done_when: 'Planned' })).name
    const b = (await s.api('goals.create', { space: SPACE, title: `S7 handoff goal ${W}`, horizon: 'Long term', area: areaId('Personal'), done_when: 'Handed over' })).name
    const now = iso(new Date()) // the run may cross midnight
    const at = `${now} 23:${phone ? '30' : '00'}:00`
    // the weekly review's Goals tab makes this work; the call it makes is lifeos.tasks.weekplan.add
    const addWork = (args) => JSON.parse(bench(`import json
from lifeos.tasks import weekplan
frappe.set_user("owner@lifeos.test")
args = json.loads(${JSON.stringify(JSON.stringify(args))})
d = weekplan.add(args.pop("goal"), **args)
print(json.dumps({"task": d.name, "status": d.status, "waiting_on": d.waiting_on, "scheduled_at": str(d.scheduled_at)[:19] if d.scheduled_at else None}))`).split('\n').pop())
    const task = addWork({ goal: a, title: `S7 plan step ${W}`, scheduled_at: at, duration_min: 30, note: 'the soil report' })
    must(task.scheduled_at && task.scheduled_at.slice(0, 10) === now, 'no task scheduled today: ' + JSON.stringify(task))
    const handed = addWork({ goal: b, title: `S7 handoff step ${W}`, who: 'Vivek' })
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

  await check('GOALS.18', `${width} px: Inbox items left too long: on Suggest an old item gets a suggested decision and the batch confirms it; on Park and Discard the job acts and Today's Undo restores`, async () => {
    const age = (name, days) => bench(`frappe.db.set_value("Life Inbox Item", "${name}", "received_on", frappe.utils.add_days(frappe.utils.now_datetime(), -${days}), update_modified=False)`)
    const run = () => JSON.parse(bench(`import json\nfrom lifeos.brain import old_inbox\nfrappe.clear_document_cache("Life Settings", "Life Settings")\nprint(json.dumps(old_inbox.run_for_space("${SPACE}")))`).split('\n').pop())
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
    await check('GOALS.19', `${width} px: nothing in the goal dialog, readings, Outbox or old-items work scrolls sideways`, async () => {
      const bad = []
      for (const p of ['/life', '/life/goals', '/life/today/week?view=review', '/life/brain/outbox', '/life/brain/outbox?pile=in&period=12weeks',
        '/life/goals/cycles', '/life/settings?tab=rhythms', '/life/settings?tab=reset']) {
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


// Issue 13: every task has an area. A task quick-captured with no area shows the area the Brain guessed, with ✦ and how
// sure it is; one tap confirms it and the ✦ goes.
for (const width of WIDTHS) {
  const tag = `I13.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  await check('GOALS.20', `${width} px: a quick-captured task shows its guessed area with ✦ and the confidence; one tap confirms it and the ✦ goes`, async () => {
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


// Issue 20: Goals > By area. Titles start "I20 ". Areas switched on or off here are put back after.
for (const width of WIDTHS) {
  const tag = `I20.${width}`
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
    await check('GOALS.21', `${width} px: with no goals By area says what will appear and offers + Goal`, async () => {
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
    await check('GOALS.22', `${width} px: with eight goals over Career (two parts), Health, Money and Mind each appears under its area and part`, async () => {
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
    await check('GOALS.23', `${width} px: a goal's card shows its Done when, score, next action and open task count, matching the goal page`, async () => {
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
    await check('GOALS.24', `${width} px: an area that is off has no section; turning it on shows its goals`, async () => {
      bench(`frappe.db.set_value("Life Area", "${made.ids.Mind}", "is_on", 0)`)
      await openGoals('show=open')
      must((await pg.locator('[data-area-section][data-area="Mind"]').count()) === 0 && (await row('read').count()) === 0, 'the off area still has a section')
      must((await pg.locator('[data-area-chip-off="Mind"]').count()) === 1, 'the off area has no dimmed chip')
      bench(`frappe.db.set_value("Life Area", "${made.ids.Mind}", "is_on", 1)`)
      await openGoals('show=open')
      must((await pg.locator('[data-area-section][data-area="Mind"]').count()) === 1 && (await row('read').count()) === 1, 'the goal did not come back')
    })
    await check('GOALS.25', `${width} px: + Goal in an empty area opens the new-goal form with that area set`, async () => {
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
    await check('GOALS.26', `${width} px: ${phone ? 'goal cards are full width under area headings' : 'goal cards stack one to a row under area headings'}`, async () => {
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
for (const width of WIDTHS) {
  const tag = `I21.${width}`
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
    await check('GOALS.27', `${width} px: with no tasks All tasks says what will appear and offers a box to add one`, async () => {
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
    await check('GOALS.28', `${width} px: every open task appears once, under its area`, async () => {
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
    await check('GOALS.29', `${width} px: grouping by goal and by due date shows the same tasks`, async () => {
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
    await check('GOALS.30', `${width} px: quick add under Health creates a task in Health`, async () => {
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
    await check('GOALS.31', `${width} px: the Someday filter shows the tasks of the Someday page`, async () => {
      await openTasks('show=someday')
      const here = (await shown()).sort()
      const old = (await s.api('someday.list', { space: SPACE, tab: 'tasks', page_length: 100 })).rows.map((r) => r.name).sort()
      must(old.includes(ids.parked) && JSON.stringify(here) === JSON.stringify(old), `All tasks > Someday ${here.length}, the Someday page ${old.length}`)
    })
    await check('GOALS.32', `${width} px: a task with a guessed area shows ✦`, async () => {
      await openTasks()
      const row = pg.locator(`[data-task="${ids.guess}"]`)
      must((await row.locator('[data-area-guess]').count()) === 1 && (await row.locator('[data-area-guess]').innerText()).includes('✦'), 'no ✦ on the guessed task')
      must((await pg.locator(`[data-task="${ids.money}"] [data-area-guess]`).count()) === 0, '✦ on a task whose area is known')
    })
    await check('GOALS.33', `${width} px: ${phone ? 'the list is one column' : 'a row has its task, goal and due date side by side'}`, async () => {
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
for (const width of WIDTHS) {
  const tag = `I22.${width}`
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
    await check('GOALS.34', `${width} px: with every task under a goal No goal says what will appear and offers a box to add one`, async () => {
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
    await check('GOALS.35', `${width} px: tasks without a goal are grouped by area; a task with a goal is not listed`, async () => {
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
    await check('GOALS.36', `${width} px: adding a task to a goal takes it off the list and it shows under that goal`, async () => {
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
    await check('GOALS.37', `${width} px: confirming a guessed area clears ✦`, async () => {
      await openNoGoal()
      const row = pg.locator(`[data-task="${ids.guess}"]`)
      must((await row.locator('[data-area-guess]').count()) === 1, 'no ✦ on the guessed task')
      await row.locator('[data-area-guess]').click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-task="${n}"] [data-area-guess]`), ids.guess, { timeout: 8000 })
      must(dbRow(T('guess'), ['area_guessed']).area_guessed === 0, 'the guess is still marked')
      must((await pg.locator(`[data-task="${ids.guess}"]`).count()) === 1, 'the task left the list when its area was confirmed')
    })
    await check('GOALS.38', `${width} px: Make it a goal creates one goal in that area with the tasks attached`, async () => {
      await openNoGoal()
      const group = pg.locator('[data-no-goal-group][data-group="Health"]')
      must(await group.locator('[data-suggestion]').isVisible(), 'no suggestion under Health')
      must((await group.locator('[data-suggestion]').innerText()).includes('look like a goal'), 'the suggestion does not say it looks like a goal')
      const before = JSON.parse(bench(`import json\nprint(json.dumps(frappe.db.count("Life Goal", {"space": "${SPACE}"})))`).split('\n').pop())
      await group.locator('[data-make-goal]').click()
      // issue 56: it asks for the goal's name and its "Done when" first
      const ask = pg.locator('[data-make-goal-dialog], [role="dialog"]').last()
      await ask.locator('[data-measure-kind]').getByText('A finish line').click()
      await ask.locator('[data-measure-done-when] textarea, textarea[data-measure-done-when]').first().fill('The Quillfeather work is finished')
      await ask.getByRole('button', { name: 'Make goal' }).click()
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
    await check('GOALS.39', `${width} px: the tab count is the number of open tasks with no goal`, async () => {
      await openNoGoal()
      const n = Number((await pg.locator('[data-tab="no-goal"] [data-tab-count]').innerText()).trim())
      const sql = JSON.parse(bench(`import json
print(json.dumps(frappe.db.sql("select count(*) from \`tabLife Task\` where space=%s and is_archived=0 and status in ('Open','Doing','Waiting') and ifnull(goal,'')='' and ifnull(standalone,0)=0", "${SPACE}")[0][0]))`).split('\n').pop())
      must(n === sql, `the tab says ${n}, the database has ${sql}`)
      must((await shown()).length === n, `${(await shown()).length} rows under a tab that says ${n}`)
    })
    await check('GOALS.40', `${width} px: ${phone ? 'groups stack and a task\'s actions are reachable' : 'a row has its task and its actions side by side'}`, async () => {
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
    await check('GOALS.41', `${width} px: Fine as is leaves the list and keeps the task without a goal`, async () => {
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


// Issue 60: one kind of goal with a horizon, one parking lot (Someday), no tags. I60.1 to I60.3, I60.5 to I60.7 are unit tests
// (test_issue60_horizons_someday_no_tags). Titles start "I60 ".
for (const width of WIDTHS) {
  const tag = `I60.${width}`
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
    await check('GOALS.42', `${width} px: a Month goal created with a parent 12-week goal shows under it on its page and in Goals > By area`, async () => {
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
    await check('GOALS.43', `${width} px: no screen shows a tag, a tag picker or Settings > Tags`, async () => {
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
    await check('GOALS.44', `${width} px: Cycles lists this month's Month goals in priority order, with the habits`, async () => {
      const [y, m] = [Number(today.slice(0, 4)), Number(today.slice(5, 7))]
      const last = `${today.slice(0, 8)}${new Date(Date.UTC(y, m, 0)).getUTCDate()}`
      const made = {}
      for (const w of ['first', 'second', 'third']) made[w] = (await s.api('goals.create', { space: SPACE, title: T(w), horizon: 'Month', target_date: last, done_when: 'Done' })).name
      await s.api('goals.reorder', { goals: [made.first, made.third, made.second] })
      await s.open('/life/goals/cycles')
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


// Issue 45: Goals > Cycles. The 12 Week Year (week bars, each goal's lead action and this week's ticks) beside this month's plan; the Plan
// section's month, year, 12 Weeks and journal routes land here; journal pages are notes in Library > Notes. Titles start "I45 ".
for (const width of WIDTHS) {
  const tag = `I45.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I45 ${what} ${width} ${stamp}`
  const settle = () => pg.waitForTimeout(700)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const ready = () => pg.locator('[data-cycles][data-loaded="1"]').waitFor({ timeout: 15000 })
  const was = (await s.api('settings.get', { space: SPACE })).settings
  const cleanup = () => bench(`frappe.set_user("Administrator")
for g in frappe.get_all("Life Goal", filters={"title": ["like", "I45 % ${width} ${stamp}"]}, pluck="name"):
    frappe.db.delete("Life Task", {"goal": g})
    frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
for c in frappe.get_all("Life Cycle", filters={"title": ["like", "I45 % ${width} ${stamp}"]}, pluck="name"):
    for g in frappe.get_all("Life Goal", filters={"cycle": c}, pluck="name"): frappe.delete_doc("Life Goal", g, force=1, ignore_permissions=True)
    frappe.db.delete("Life Cycle", {"name": c})`)
  // the active cycle gets one goal of this check, with a lead action done three times a week
  let seeded = null
  const seed = () => {
    if (!seeded) seeded = JSON.parse(bench(`import json
cycle = frappe.db.get_value("Life Cycle", {"space": "${SPACE}", "status": "Active"})
g = frappe.get_doc({"doctype": "Life Goal", "space": "${SPACE}", "title": "${T('cycle goal')}", "horizon": "12 weeks", "cycle": cycle, "done_when": "Done", "sort_order": 999,
  "actions": [{"title": "${T('lead')}", "per_week": 3, "status": "Open"}]}).insert(ignore_permissions=True)
print(json.dumps({"cycle": cycle, "goal": g.name}))`).split('\n').pop())
    return seeded
  }
  try {
    await check('GOALS.45', `${width} px: Goals shows four tabs, and Cycles opens at /life/goals/cycles`, async () => {
      await s.open('/life/goals')
      const tabs = await pg.locator('[data-place-tabs] [data-tab]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab')))
      must(JSON.stringify(tabs) === JSON.stringify(['by-area', 'tasks', 'no-goal', 'cycles']), `Goals' tabs are ${tabs}`)
      await pg.locator('[data-place-tabs] [data-tab="cycles"]').click()
      await pg.waitForURL((u) => u.pathname === '/life/goals/cycles', { timeout: 10000 })
      await ready()
      must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === 'cycles', 'the Cycles tab is not the open one')
      await s.open('/life/goals/cycles')
      await ready()
      must(await pg.locator('[data-cycle-card]').isVisible(), 'the 12 Week Year card is not shown')
    })

    await check('GOALS.46', `${width} px: the week bars show the scores of the grid, with this week marked "so far"`, async () => {
      seed()
      const g = await s.api('goals.grid', { space: SPACE })
      await s.open('/life/goals/cycles')
      await ready()
      must(await pg.locator('[data-week-bar]').count() === 12, 'there are not twelve week bars')
      for (const w of g.weeks.slice(0, g.current_week - 1)) {
        const got = await pg.locator(`[data-week-bar="${w.week}"]`).getAttribute('data-score')
        must(Number(got) === Math.round(w.percent), `week ${w.week} shows ${got}, the grid says ${Math.round(w.percent)}`)
        must((await pg.locator(`[data-week-bar="${w.week}"]`).getAttribute('data-week-state')) === 'past', `week ${w.week} is not marked as past`)
      }
      const now = pg.locator(`[data-week-bar="${g.current_week}"]`)
      must((await now.getAttribute('data-week-state')) === 'now' && (await now.innerText()).includes('so far'), 'this week is not marked "so far"')
      if (g.current_week < 12) must((await pg.locator(`[data-week-bar="${g.current_week + 1}"]`).getAttribute('data-week-state')) === 'future', 'a later week is not empty')
      must(/week \d+ of 12/.test(await pg.locator('[data-cycle-line]').innerText()) && /average \d+%/.test(await pg.locator('[data-cycle-line]').innerText()) && /target \d+%/.test(await pg.locator('[data-cycle-line]').innerText()),
        'the header line does not give the week, average and target')
    })

    await check('GOALS.47', `${width} px: ticking a lead action records the tick and the week's score so far changes`, async () => {
      const { cycle, goal } = seed()
      await s.open('/life/goals/cycles')
      await ready()
      const row = pg.locator(`[data-cycle-goal][data-goal="${goal}"]`)
      const before = (await pg.locator('[data-week-so-far]').innerText()).trim()
      await row.locator('[data-tick]').first().click()
      await settle()
      const after = (await pg.locator('[data-week-so-far]').innerText()).trim()
      must(before !== after, `the score so far stayed at ${before}`)
      must((await row.locator('[data-tick-count]').innerText()).startsWith('1 of 3'), 'the row does not say 1 of 3')
      const g = await s.api('goals.grid', { space: SPACE, cycle })
      const a = g.goals.find((x) => x.name === goal).actions[0]
      must(a.ticks[String(g.current_week)] === 1, 'the tick was not recorded on the server')
      must(Math.round(g.weeks[g.current_week - 1].percent) + '%' === after, `the server says ${Math.round(g.weeks[g.current_week - 1].percent)}%, the page ${after}`)
      await row.locator('[data-tick]').first().click() // un-tick again: the same button turns it off
      await settle()
      must((await row.locator('[data-tick-count]').innerText()).startsWith('0 of 3'), 'a second press did not clear the tick')
    })

    await check('GOALS.48', `${width} px: each cycle goal shows its lead action and this week's ticks, as the goal page does`, async () => {
      const { cycle, goal } = seed()
      await s.api('goals.tick', { action: (await s.api('goals.detail', { goal })).goal.actions[0].name, week: (await s.api('goals.grid', { space: SPACE, cycle })).current_week, count: 2 })
      await s.open('/life/goals/cycles')
      await ready()
      const row = pg.locator(`[data-cycle-goal][data-goal="${goal}"]`)
      must((await row.locator('[data-lead-action]').innerText()).includes(T('lead')) && (await row.locator('[data-lead-action]').innerText()).includes('3/wk'), 'the row does not show the lead action and how often')
      must((await row.locator('[data-tick-count]').innerText()).startsWith('2 of 3') && await row.locator('[data-tick][aria-pressed="true"]').count() === 2, 'the row does not show 2 of 3 ticks')
      // every goal of the cycle has a row with the lead action the grid gives it
      const g = await s.api('goals.grid', { space: SPACE, cycle })
      for (const x of g.goals) {
        const lead = x.actions.find((a) => a.status === 'Open')
        const rows = pg.locator(`[data-cycle-goal][data-goal="${x.name}"]`)
        must(await rows.count() === 1, `${x.title} has no row`)
        if (lead) must((await rows.locator('[data-lead-action]').innerText()).includes(lead.title), `${x.title}: the lead action is not ${lead.title}`)
      }
      await s.open(`/life/goals/${goal}`)
      await pg.getByText(T('lead')).first().waitFor({ timeout: 10000 }).catch(() => {})
      // what the goal page reads (journal.goal) names the same lead action, with the same ticks
      const asked = (await s.api('goals.detail', { goal })).goal.actions.find((x) => x.status === 'Open')
      must(asked && asked.title === T('lead') && asked.per_week === 3 && Object.values(asked.ticks).reduce((x, y) => x + y, 0) === 2, 'the goal page data does not match the row')
    })

    // the month card lists Month goals: goals with the Month horizon, this month's and the ones carried from last month
    await check('GOALS.49', `${width} px: Cycles lists the month goals in priority order with their status; a goal carried from last month says so`, async () => {
      const [y, m] = [Number(today.slice(0, 4)), Number(today.slice(5, 7))]
      const [py, pm] = m === 1 ? [y - 1, 12] : [y, m - 1]
      const lastDay = (yy, mm) => `${yy}-${String(mm).padStart(2, '0')}-${new Date(Date.UTC(yy, mm, 0)).getUTCDate()}`
      const old = (await s.api('goals.create', { space: SPACE, title: T('carried'), horizon: 'Month', target_date: lastDay(py, pm), done_when: 'Done' })).name
      bench(`from lifeos.goals import cycles
frappe.set_user("owner@lifeos.test")
cycles.carry_month_goal("${old}")`)
      const made = {}
      for (const w of ['second', 'third']) made[w] = (await s.api('goals.create', { space: SPACE, title: T(w), horizon: 'Month', target_date: lastDay(y, m), done_when: 'Done' })).name
      await s.api('goals.reorder', { goals: [made.third, made.second] })
      const order = (await s.api('goals.this_month', { space: SPACE })).goals.map((x) => x.title).filter((x) => x.startsWith('I45 ') && x.endsWith(`${width} ${stamp}`))
      await s.open('/life/goals/cycles')
      await ready()
      const rows = await pg.locator('[data-month-goal]').evaluateAll((els) => els.map((e) => ({ text: e.innerText, status: e.querySelector('[data-month-status]')?.innerText })))
      const mine = rows.filter((r) => r.text.includes(`${width} ${stamp}`))
      must(mine.map((r) => r.text.split('\n').find((l) => l.startsWith('I45 '))).join('|') === order.join('|'), `the month goals are in the order ${mine.map((r) => r.text.split('\n').find((l) => l.startsWith('I45 ')))}, not ${order}`)
      must(order.indexOf(T('third')) < order.indexOf(T('second')), 'the reorder did not put the third before the second')
      must(mine.some((r) => /Carried from/.test(r.status || '') && r.text.includes(T('carried'))), 'the goal carried from last month does not say so')
      must(mine.filter((r) => r.text.includes(T('second'))).every((r) => /In progress|\d+ of \d+/.test(r.status)), 'an open goal does not say In progress')
      must((await pg.locator('[data-month-title]').innerText()).endsWith('goals') && /month goals? ·/.test(await pg.locator('[data-month-card]').innerText()), 'the month card has no title or count')
      must(await pg.locator('[data-month-edit], [data-month-start], [data-month-next]').count() === 0, 'the month plan record is still on screen')
    })

    await check('GOALS.50', `${width} px: a month goal marked Achieved shows Done on Cycles; its title opens the goal page`, async () => {
      const goal = (await s.api('goals.this_month', { space: SPACE })).goals.find((x) => x.title === T('second')).row
      await s.api('goals.close', { goal, outcome: 'Achieved' })
      await s.open('/life/goals/cycles')
      await ready()
      const row = pg.locator('[data-month-card] [data-month-goal]', { hasText: T('second') })
      await row.locator('[data-month-status]', { hasText: 'Done' }).waitFor({ timeout: 10000 })
      await row.getByRole('link', { name: T('second') }).click()
      await pg.waitForURL((u) => u.pathname === `/life/goals/${goal}`, { timeout: 10000 })
    })

    await check('GOALS.51', `${width} px: on an empty space (an area with nothing in it) Cycles says what will appear and how to add it`, async () => {
      const area = bench(`a = frappe.get_doc({"doctype": "Life Area", "space": "${SPACE}", "area_name": "${T('empty area')}", "parent_area": frappe.db.get_value("Life Area", {"space": "${SPACE}", "is_life_area": 1}, "name")}).insert(ignore_permissions=True)
print(a.name)`).split('\n').pop()
      try {
        await s.open(`/life/goals/cycles?area=${area}`)
        await ready()
        const card = pg.locator('[data-month-card]')
        must((await card.innerText()).includes('No goals this month.'), 'the month card has no empty state')
        must(await card.getByRole('button', { name: 'Goal' }).count() === 1, 'the month card has no Goal button')
        must(await pg.locator('[data-cycle-card]').isVisible(), 'the 12 Week Year card is gone')
        await noSideways()
      } finally {
        bench(`frappe.set_user("Administrator")
frappe.delete_doc("Life Area", "${area}", force=1, ignore_permissions=True)`)
      }
    })

    await check('GOALS.52', `${width} px: a closed cycle chosen from the picker is shown read-only`, async () => {
      const closed = bench(`from frappe.utils import add_days, today
c = frappe.get_doc({"doctype": "Life Cycle", "space": "${SPACE}", "title": "${T('closed')}", "start_date": add_days(today(), -400), "status": "Closed", "final_score": 66}).insert(ignore_permissions=True)
print(c.name)`).split('\n').pop()
      must(closed, 'no closed cycle was made')
      await s.open('/life/goals/cycles')
      await ready()
      await pg.locator('[data-cycle-picker]').click()
      await pg.getByRole('menuitem', { name: new RegExp(T('closed')) }).click()
      await pg.locator('[data-cycle-closed]').waitFor({ timeout: 10000 })
      must(new URL(pg.url()).searchParams.get('cycle') === closed, 'the picked cycle is not in the address')
      must((await pg.locator('[data-cycle-title]').innerText()).includes(T('closed').slice(0, 0)) && /closed/.test(await pg.locator('[data-cycle-line]').innerText()), 'the header does not say the cycle is closed')
      must(await pg.locator('[data-tick]:not([disabled])').count() === 0, 'a closed cycle has ticks that can be pressed')
      must(await pg.locator('[data-week-bar][data-week-state="future"]').count() === 0, 'a closed cycle shows empty future weeks')
      await pg.locator('[data-cycle-goals]').click()
      await pg.locator('[data-cycle-goals-body]').waitFor()
      must(!(await pg.locator('[data-cg-add]').count()) && /read-only/.test(await pg.locator('[data-cycle-goals-body]').innerText()), 'a closed cycle can be edited')
      await pg.keyboard.press('Escape')
    })

    await check('GOALS.53', `${width} px: a journal page is a note in Library > Notes and opens with its photo and its date`, async () => {
      // a page of its own, with a photograph, so that this check does not depend on another check having made one
      const jp = bench(`p = frappe.get_doc({"doctype": "Life Note", "space": "${SPACE}", "title": "${T('journal page')}", "collection": "My notes", "page_date": frappe.utils.today(), "content_md": "${T('page words')}"}).insert(ignore_permissions=True)
print(p.name)`).split('\n').pop()
      const file = (await s.upload('Life Note', jp, `i45-${width}-${stamp}.png`, 'image/png', await pg.screenshot())).file_url
      bench(`frappe.db.set_value("Life Note", "${jp}", "image", "${file}")`)
      try {
        await s.api('views.save', { screen: 'library', space: SPACE, state: {} }) // an earlier check left "Written by the assistant" remembered
        await s.open('/life/library/notes?view=list')
        await pg.getByText(T('journal page')).first().waitFor({ timeout: 15000 })
        await s.open(`/life/library/notes?view=list&open=note:${jp}`)
        await pg.locator('[data-pane]').waitFor({ timeout: 10000 })
        await pg.locator('[data-pane] [data-note-image] img[alt="Photographed journal page"]').waitFor({ timeout: 10000 })
        await pg.getByText(T('page words')).first().waitFor({ timeout: 10000 })
        must((await s.api('library.get', { note: jp })).page_date === today, 'the note does not carry its page date')
      } finally {
        bench(`frappe.set_user("Administrator")
frappe.delete_doc("Life Note", "${jp}", force=1, ignore_permissions=True)`)
      }
    })

    await check('GOALS.54', `${width} px: the Month and Year headers link to Goals > Cycles`, async () => {
      for (const [from, link] of [['/life/today/month', 'Month goals'], ['/life/today/year', '12 Week Year']]) {
        await s.open(from)
        await pg.locator('[data-view-links]').waitFor({ timeout: 10000 })
        must(await pg.locator('[data-view-links] a', { hasText: link }).first().getAttribute('href') === '/life/goals/cycles', `${from}'s header does not link to Goals > Cycles`)
      }
    })

    await check('GOALS.55', `${width} px: ${phone ? 'one column, and the week bars scroll inside their card, not the page' : 'two columns, the 12 Week Year beside the month plan'}`, async () => {
      await s.open('/life/goals/cycles')
      await ready()
      const left = await pg.locator('[data-cycle-card]').boundingBox(), right = await pg.locator('[data-month-card]').boundingBox()
      if (!right) return 'the month plan is off here'
      if (phone) {
        must(right.y >= left.y + left.height - 2 && Math.abs(right.x - left.x) < 2, 'the cards are not one column, the 12 Week Year first')
        const sc = await pg.locator('[data-week-bars-scroll]').evaluate((e) => ({ inner: e.scrollWidth, outer: e.clientWidth }))
        must(sc.inner > sc.outer, `the week bars do not scroll inside their card (${sc.inner} in ${sc.outer})`)
      } else must(right.x > left.x + left.width - 2 && Math.abs(right.y - left.y) < 4, 'the cards are not side by side')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('GOALS.56', `${width} px: Cycles on a space with no cycle shows what will appear and the one action`, async () => {
      const fam = await session('family@lifeos.test', width)
      try {
        await fam.open('/life/goals/cycles')
        await fam.page.locator('[data-cycles][data-loaded="1"]').waitFor({ timeout: 15000 })
        const text = await fam.page.locator('[data-cycle-card]').innerText()
        must(/No 12 Week Year yet\./.test(text) && /Start a cycle next Monday/.test(text), `the empty card says "${text.slice(0, 120)}"`)
        const over = await fam.page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
        must(!over, 'the empty screen scrolls sideways')
      } finally { await fam.ctx.close() }
    })
  } finally {
    cleanup()
    await s.ctx.close()
  }
}


// Issue 56: edit a goal where you see it, "Done when" required on new goals (a setting, on by default), and a cycle goal's actions on its page.
// A user made for the run has a space of their own and a cycle of two goals ("I56 ..." titles). I56.6, I56.7 and I56.10 are unit tests (test_issue56_goal_edit).
for (const width of WIDTHS) {
  const tag = `I56.${width}`
  const phone = width < 800
  const user = `i56-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I56 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
frappe.db.set_single_value("Life Settings", "require_done_when", 0)
s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()
for dt in ("Life Note", "Life Task", "Life Goal", "Life Cycle", "Life Action Log"):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos.tools import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  try {
    bench(`from lifeos.tools import devtools
devtools.make_user("${user}", "Newcomer56", ["Life Admin", "Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)`)
    one = await session(user, width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    const settle = () => pg.waitForTimeout(450)
    const inField = (root, attr) => root.locator(`[${attr}] input, input[${attr}], [${attr}] textarea, textarea[${attr}]`).first()
    await one.api('onboarding.complete', { status: 'skipped' })
    bench('frappe.db.set_single_value("Life Settings", "require_done_when", 1)')
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, today
space = "${space}"
areas = frappe.get_all("Life Area", filters={"space": space, "is_life_area": 1, "is_on": 1}, fields=["name", "area_name"])
career = next(a for a in areas if a.area_name == "Career")
part = frappe.get_all("Life Area", filters={"space": space, "parent_area": career.name}, fields=["name", "area_name"], limit=1)
part = part[0] if part else frappe.get_doc({"doctype": "Life Area", "space": space, "area_name": "I56 part ${width}", "parent_area": career.name}).insert(ignore_permissions=True)
cycle = frappe.get_doc({"doctype": "Life Cycle", "space": space, "title": "I56 cycle ${width}", "start_date": add_days(today(), -3), "status": "Active"}).insert(ignore_permissions=True)
g = frappe.get_doc({"doctype": "Life Goal", "space": space, "cycle": cycle.name, "title": "I56 RMT ${width}", "area": areas[0].name, "done_when": "The systems run on their own",
  "actions": [{"title": "I56 audit ${width}", "per_week": 2}, {"title": "I56 newsletter ${width}", "per_week": 1}]}).insert(ignore_permissions=True)
old = frappe.get_doc({"doctype": "Life Goal", "space": space, "title": "I56 old ${width}", "horizon": "Long term", "area": career.name}).insert(ignore_permissions=True)
t = frappe.get_doc({"doctype": "Life Task", "space": space, "title": "I56 task ${width}", "goal": g.name, "area": areas[0].name}).insert(ignore_permissions=True)
n = frappe.get_doc({"doctype": "Life Note", "space": space, "title": "I56 note ${width}", "goal": g.name, "area": areas[0].name, "content_md": "x"}).insert(ignore_permissions=True)
print(json.dumps({"cycle": cycle.name, "goal": g.name, "old": old.name, "career": career.name, "part": part.name, "actions": [a.name for a in g.actions], "task": t.name, "note": n.name}))`).split('\n').pop())
    const goalPage = async (name) => { await one.open(`/life/goals/${name}`); await pg.locator('[data-goal-overview]').waitFor({ timeout: 10000 }); await settle() }
    const dialog = () => pg.locator('[role="dialog"]').last()
    const openEdit = async () => { await pg.locator('[data-goal-edit]').click(); await dialog().waitFor({ timeout: 8000 }); await settle() }
    const save = async () => { await dialog().getByRole('button', { name: 'Save goal' }).click(); await dialog().waitFor({ state: 'detached', timeout: 8000 }); await settle() }

    await check('GOALS.57', `${width} px: the page of a 12 Week Year goal shows the cycle's name, Open grid and its actions with this week's ticks`, async () => {
      await goalPage(made.goal)
      must((await pg.locator('main, [data-main]').first().innerText()).includes(`I56 cycle ${width}`), 'the cycle name is not in the header')
      const grid = pg.locator('[data-open-grid]')
      must(await grid.count() === 1, 'Open grid is missing')
      must((await grid.getAttribute('href') || '').includes(`/goals/cycles?cycle=${made.cycle}`), 'Open grid goes elsewhere')
      const rows = pg.locator('[data-goal-actions] [data-action-line]')
      must(await rows.count() === 2, 'the Actions section does not list both actions')
      must(/0 of 2 this week/.test(await rows.first().innerText()), 'the first action has no ticks this week: ' + await rows.first().innerText())
      await noSideways()
    })

    await check('GOALS.58', `${width} px: progress on a 12 Week Year goal shows this week's ticks and the tasks done`, async () => {
      bench(`from lifeos.goals import cycles
cycles.set_tick("${made.actions[0]}", cycles.current_week(frappe.get_doc("Life Cycle", "${made.cycle}")), 1)`)
      await goalPage(made.goal)
      const line = await pg.locator('[data-goal-week-ticks]').innerText()
      must(/Actions this week: 1 of 3 ticks/.test(line), 'the ticks line says: ' + line)
      must(/0 of 1 tasks done/.test(await pg.locator('[data-goal-figure]').innerText()), 'the tasks line is missing: ' + await pg.locator('[data-goal-figure]').innerText())
    })

    await check('GOALS.59', `${width} px: Edit renames the goal; its task, note and cycle still show it under the new name`, async () => {
      await goalPage(made.goal)
      await openEdit()
      await inField(dialog(), 'data-edit-title').fill(`I56 RMT systems ${width}`)
      await save()
      must((await pg.locator('main, [data-main]').first().innerText()).includes(`I56 RMT systems ${width}`), 'the page does not show the new name')
      const rows = JSON.parse(bench(`import json
print(json.dumps([frappe.db.get_value("Life Task", "${made.task}", "goal"), frappe.db.get_value("Life Note", "${made.note}", "goal"), frappe.db.get_value("Life Goal", "${made.goal}", ["cycle", "title"])]))`).split('\n').pop())
      must(rows[0] === made.goal && rows[1] === made.goal && rows[2][0] === made.cycle && rows[2][1] === `I56 RMT systems ${width}`, 'a link moved: ' + JSON.stringify(rows))
      await one.open('/life/goals/tasks?goal=' + made.goal + '&status=all&view=list')
      await pg.waitForTimeout(800)
      must((await pg.locator('main, [data-main]').first().innerText()).includes(`I56 task ${width}`), 'the task is not under the goal')
      await one.open(`/life/goals/cycles?cycle=${made.cycle}`)
      await pg.locator('[data-cycle-goal-list]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-cycle-goal-list]').innerText()).includes(`I56 RMT systems ${width}`), 'the cycle does not show the new name')
    })

    await check('GOALS.60', `${width} px: Edit changes the goal's area to a part of Career; Goals > By area shows it there`, async () => {
      await goalPage(made.old)
      await openEdit()
      await dialog().locator('[data-edit-area] [role="combobox"], [data-edit-area] button, [role="combobox"][data-edit-area]').first().click()
      await pg.getByRole('option', { name: new RegExp(`I56 part ${width}`) }).first().click()
      await settle()
      await save()
      await one.open('/life/goals?show=open')
      await pg.locator('[data-goal-card]').first().waitFor({ timeout: 10000 })
      const card = pg.locator(`[data-goal="${made.old}"]`)
      must(await card.count() === 1, 'the goal is not on By area')
      must(Boolean(await card.getAttribute('data-part-name')), 'the card is not under a part')
      must(await card.getAttribute('data-area-name') === 'Career', 'the card is not in Career: ' + await card.getAttribute('data-area-name'))
    })

    await check('GOALS.61', `${width} px: Edit adds a weekly action and retires another; the cycle grid and Goals > Cycles show the same`, async () => {
      await goalPage(made.goal)
      await openEdit()
      await dialog().locator('[data-edit-add-action]').click()
      const added = dialog().locator('[data-edit-action]').last()
      await added.locator('input').first().fill(`I56 training ${width}`)
      await dialog().locator('[data-edit-action]').first().locator('[data-edit-retire]').click()
      await save()
      const text = await pg.locator('[data-goal-actions]').innerText()
      must(text.includes(`I56 training ${width}`), 'the new action is not on the goal page')
      await one.open(`/life/goals/cycles?cycle=${made.cycle}`)
      await pg.locator('[data-cycle-goal-list]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-lead-action]').first().innerText()).includes(`I56 newsletter ${width}`), 'Cycles does not lead with the next open action')
      await pg.locator('[data-cycle-goals]').click()
      const body = pg.locator('[data-cycle-goals-body]')
      await body.waitFor({ timeout: 8000 })
      const bodyText = await body.innerText()
      must(bodyText.includes(`I56 training ${width}`) && bodyText.includes(`I56 audit ${width}`), 'the cycle goals list differs: ' + bodyText.slice(0, 300))
      must(await body.locator('li.line-through', { hasText: `I56 audit ${width}` }).count() === 1, 'the retired action is not struck through')
    })

    await check('GOALS.62', `${width} px: the Edit form works one field after another, actions included, with no sideways scroll`, async () => {
      await goalPage(made.goal)
      await openEdit()
      const box = await dialog().boundingBox()
      must(box.x >= -1 && box.x + box.width <= width + 1, 'the dialog is wider than the screen')
      const fields = ['data-edit-title', 'data-edit-area', 'data-edit-type', 'data-edit-cycle', 'data-edit-serves', 'data-edit-actions']
      let last = -1
      for (const f of fields) {
        const at = await dialog().locator(`[${f}]`).first().boundingBox()
        must(at, f + ' is not in the form')
        if (phone) must(at.y > last, f + ' is not below the one before it')
        last = at.y
      }
      await dialog().locator('[data-edit-action]').last().scrollIntoViewIfNeeded()
      must(await dialog().locator('[data-edit-add-action]').isVisible(), 'Add action is out of reach')
      await noSideways()
      await dialog().getByRole('button', { name: 'Cancel' }).click()
    })

    await check('GOALS.63', `${width} px: an existing goal without Done when shows "Done when is missing" with Add, and By area marks it`, async () => {
      await goalPage(made.old)
      const alert = pg.locator('[data-needs-finish-line]')
      must((await alert.innerText()).includes('Done when is missing'), 'the page does not say it')
      await pg.locator('[data-done-when-add]').click()
      await pg.locator('[data-measure-save]').waitFor({ timeout: 5000 })
      await one.open('/life/goals?show=open')
      await pg.locator('[data-goal-card]').first().waitFor({ timeout: 10000 })
      const line = pg.locator(`[data-goal="${made.old}"] [data-goal-done-when]`)
      must((await line.innerText()).includes('Done when is missing'), 'By area does not mark it')
    })

    await check('GOALS.64', `${width} px: Suggest with the assistant faked fills a finish line from the goal's title; with no key it shows two examples`, async () => {
      await goalPage(made.old)
      await pg.locator('[data-done-when-add]').click()
      await pg.locator('[data-measure-suggest]').click()
      await pg.locator('[data-measure-done-when]').waitFor({ timeout: 8000 })
      must((await inField(pg, 'data-measure-done-when').inputValue()).includes(`I56 old ${width}`), 'the finish line did not come from the title')
      bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = None; s.save()')
      try {
        await goalPage(made.old)
        await pg.locator('[data-done-when-add]').click()
        await pg.locator('[data-measure-suggest]').click()
        await pg.locator('[data-measure-examples]').waitFor({ timeout: 8000 })
        must(await pg.locator('[data-measure-example]').count() === 2, 'there are not two examples')
        await pg.locator('[data-measure-example]').first().click()
        must((await inField(pg, 'data-measure-done-when').inputValue()).length > 10, 'tapping an example did not fill the finish line')
      } finally {
        bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()')
      }
    })

    await check('GOALS.65', `${width} px: the setting is on on a new site and can be switched off in Settings`, async () => {
      // a site that never saved the setting has the default: on
      bench('frappe.db.delete("Singles", {"doctype": "Life Settings", "field": "require_done_when"})\nfrappe.clear_cache()')
      must((await one.api('session.boot')).settings.require_done_when === 1, 'the setting is not on by default')
      await one.open('/life/settings?tab=rhythms')
      const row = pg.locator('[data-setting="require_done_when"]')
      await row.waitFor({ timeout: 10000 })
      must((await pg.locator('[data-settings-goals]').innerText()).includes('Done when'), 'the Goals section is missing')
      await row.getByText('Off', { exact: true }).click()
      await pg.waitForTimeout(900)
      must(bench('print(frappe.db.get_single_value("Life Settings", "require_done_when"))').split('\n').pop() === '0', 'Off did not save')
      await row.getByText('On', { exact: true }).click()
      await pg.waitForTimeout(900)
      must(bench('print(frappe.db.get_single_value("Life Settings", "require_done_when"))').split('\n').pop() === '1', 'On did not save')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    if (one) await one.ctx.close()
    restore()
  }
}


// Issue 57: focuses, an optional level under each part. A user made for the run has a space of their own with an estate part, two focuses
// under it (one with an annual goal), a goal under the part and an Open goal with a task. I57.1 to I57.3, I57.7 and I57.9 are unit tests (test_issue57_focuses).
for (const width of WIDTHS) {
  const tag = `I57.${width}`
  const phone = width < 800
  const user = `i57-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I57 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
frappe.db.set_single_value("Life Settings", "use_focuses", 1)
for dt in ("Life Note", "Life Task", "Life Goal", "Life Cycle", "Life Action Log"):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos.tools import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  try {
    bench(`from lifeos.tools import devtools
devtools.make_user("${user}", "Newcomer57", ["Life Admin", "Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)
frappe.db.set_single_value("Life Settings", "use_focuses", 1)`)
    one = await session(user, width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    const settle = () => pg.waitForTimeout(450)
    const inField = (root, attr) => root.locator(`[${attr}] input, input[${attr}], [${attr}] textarea, textarea[${attr}]`).first()
    await one.api('onboarding.complete', { status: 'skipped' })
    const made = JSON.parse(bench(`import json
from frappe.utils import add_days, today
space = "${space}"
career = frappe.get_all("Life Area", filters={"space": space, "is_life_area": 1, "area_name": "Career"}, pluck="name")[0]
frappe.db.set_value("Life Area", career, "is_on", 1)
def area(name, parent, **kw):
    return frappe.get_doc({"doctype": "Life Area", "space": space, "area_name": name, "parent_area": parent, **kw}).insert(ignore_permissions=True)
part = area("I57 Estate ${width}", career, part_kind="Estate")
yld = area("I57 Yield ${width}", part.name, is_focus=1, standard="Above 1,700 kg/ha on a 12-month basis", principles=[{"line": "One system"}, {"line": "Fix the process first"}])
qual = area("I57 Quality ${width}", part.name, is_focus=1, standard="Every lot meets its grade")
def goal(title, **kw):
    return frappe.get_doc({"doctype": "Life Goal", "space": space, "title": title, "done_when": "Done", **kw}).insert(ignore_permissions=True)
cycle = frappe.get_doc({"doctype": "Life Cycle", "space": space, "title": "I57 cycle ${width}", "start_date": add_days(today(), -3), "status": "Active"}).insert(ignore_permissions=True)
annual = goal("I57 annual ${width}", horizon="Year", target_date=add_days(today(), 200), area=yld.name)
twelve = goal("I57 twelve ${width}", horizon="12 weeks", cycle=cycle.name, area=yld.name, serves=annual.name)
old_done = goal("I57 finished ${width}", horizon="Year", target_date=add_days(today(), -30), area=yld.name, outcome="Achieved")
direct = goal("I57 part goal ${width}", horizon="Year", target_date=add_days(today(), 100), area=part.name)
open_goal = goal("I57 open ${width}", horizon="Long term", area=part.name)
task = frappe.get_doc({"doctype": "Life Task", "space": space, "title": "I57 task ${width}", "goal": open_goal.name, "area": part.name}).insert(ignore_permissions=True)
print(json.dumps({"part": part.name, "yield": yld.name, "quality": qual.name, "annual": annual.name, "twelve": twelve.name, "direct": direct.name, "open": open_goal.name, "task": task.name, "career": career}))`).split('\n').pop())
    const block = (name) => pg.locator(`[data-focus-block][data-focus="${name}"]`)
    const byArea = async () => { await one.open('/life/goals?show=open'); await pg.locator('[data-goals-by-area][data-loaded="1"]').waitFor({ timeout: 10000 }); await settle() }

    await check('GOALS.66', `${width} px: Goals > By area shows each focus as a heading in its part, its annual goal first, then 12 Week Year goals, then part-level goals`, async () => {
      await byArea()
      const yb = block(`I57 Yield ${width}`)
      await yb.waitFor({ timeout: 8000 })
      must((await yb.locator('[data-focus-tag]').innerText()).includes('FOCUS'), 'the FOCUS tag is missing')
      must((await yb.locator('[data-focus-standard]').innerText()).includes('Above 1,700 kg/ha'), 'the standard is missing')
      const titles = await yb.locator('[data-goal-title]').allInnerTexts()
      must(titles[0] === `I57 annual ${width}` && titles[1] === `I57 twelve ${width}`, 'the goals under the focus are in the wrong order: ' + JSON.stringify(titles))
      const order = await pg.evaluate(([f, d]) => {
        const a = document.querySelector(`[data-focus-block][data-focus="${f}"]`)
        const b = document.querySelector(`[data-goal="${d}"]:not([data-focus-goal])`)
        return !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING))
      }, [`I57 Yield ${width}`, made.direct])
      must(order, 'the part-level goal does not come after the focus')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('GOALS.67', `${width} px: a focus with no active Annual goal shows "No annual goal" and + Annual goal; adding one clears it`, async () => {
      await byArea()
      const qb = block(`I57 Quality ${width}`)
      must(await qb.locator('[data-focus-no-annual]').count() === 1, 'No annual goal is not shown')
      must(await block(`I57 Yield ${width}`).locator('[data-focus-no-annual]').count() === 0, 'a focus with an annual goal says it has none')
      await qb.locator('[data-focus-add-annual]').click()
      await pg.locator('[role="dialog"]').last().waitFor({ timeout: 8000 })
      must((await pg.locator('[role="dialog"]').last().innerText()).includes('Year'), 'the new goal does not start as a Year goal')
      await pg.keyboard.press('Escape')
      await one.api('goals.create', { space, title: `I57 new annual ${width}`, horizon: 'Year', target_date: bench('from frappe.utils import add_days, today\nprint(add_days(today(), 120))').split('\n').pop(), area: made.quality, done_when: 'Done' })
      await byArea()
      must(await block(`I57 Quality ${width}`).locator('[data-focus-no-annual]').count() === 0, 'No annual goal is still shown after adding one')
    })

    await check('GOALS.68', `${width} px: a focus page shows the standard, numbered principles (edit and reorder) and goals by horizon`, async () => {
      await one.open(`/life/focus/${made.yield}`)
      await pg.locator('[data-focus-page][data-loaded="1"]').waitFor({ timeout: 10000 })
      await settle()
      must((await pg.locator('[data-standard-text]').innerText()).includes('Above 1,700 kg/ha'), 'the standard is not shown')
      must(await pg.locator('[data-principle]').count() === 2, 'the principles are not listed')
      must((await pg.locator('[data-principle]').first().innerText()).includes('1') , 'the principles are not numbered')
      const tags = await pg.locator('[data-goal-tag]').allInnerTexts()
      must(tags[0] === 'Annual' && tags[1] === '12 Week Year' && tags[tags.length - 1].startsWith('Done'), 'goals are not by horizon: ' + JSON.stringify(tags))
      must(await pg.locator('[data-focus-goal].opacity-60').count() === 1, 'the finished goal is not greyed')
      await pg.locator('[data-principles-edit]').click()
      await pg.locator('[data-principles-editor]').waitFor({ timeout: 5000 })
      await pg.locator('[data-principle-down]').first().click()
      await pg.locator('[data-principle-add]').click()
      await inField(pg.locator('[data-principle-row]').last(), 'data-principle-input').fill(`Every report has an owner ${width}`)
      await pg.locator('[data-principles-save]').click()
      await pg.locator('[data-principles-editor]').waitFor({ state: 'detached', timeout: 8000 })
      await pg.getByText(`Every report has an owner ${width}`).first().waitFor({ timeout: 8000 })
      const lines = await pg.locator('[data-principle]').allInnerTexts()
      must(lines[0].includes('Fix the process first') && lines[1].includes('One system') && lines[2].includes(`Every report has an owner ${width}`), 'the order did not change: ' + JSON.stringify(lines))
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('GOALS.69', `${width} px: an existing Open goal shows To sort; Make it a focus creates the focus and an Annual goal holding the old goal's tasks`, async () => {
      await byArea()
      const card = pg.locator(`[data-goal="${made.open}"]`).first()
      must(await card.locator('[data-to-sort-tag]').count() === 1, 'To sort is not shown')
      must(await card.locator('[data-sort-annual]').count() === 1 && await card.locator('[data-sort-drop]').count() === 1, 'the three choices are not all there')
      await card.locator('[data-sort-focus]').click()
      const dlg = pg.locator('[role="dialog"]').last()
      await dlg.waitFor({ timeout: 8000 })
      await inField(dlg, 'data-sort-title').fill(`I57 systems annual ${width}`)
      await inField(dlg, 'data-sort-done-when').fill('All stores on one system')
      await pg.getByRole('button', { name: 'Make a focus' }).click()
      await dlg.waitFor({ state: 'detached', timeout: 8000 })
      const got = JSON.parse(bench(`import json
focus = frappe.db.get_value("Life Area", {"space": "${space}", "area_name": "I57 open ${width}"}, ["name", "is_focus", "parent_area"], as_dict=True)
annual = frappe.db.get_value("Life Goal", {"space": "${space}", "title": "I57 systems annual ${width}"}, ["name", "horizon", "area"], as_dict=True)
print(json.dumps({"focus": focus, "annual": annual, "task_goal": frappe.db.get_value("Life Task", "${made.task}", "goal"), "old": frappe.db.get_value("Life Goal", "${made.open}", "outcome")}))`).split('\n').pop())
      must(got.focus && got.focus.is_focus === 1 && got.focus.parent_area === made.part, 'the focus was not made under the part: ' + JSON.stringify(got))
      must(got.annual && got.annual.horizon === 'Year' && got.annual.area === got.focus.name && got.task_goal === got.annual.name, 'the annual goal does not hold the task: ' + JSON.stringify(got))
      must(got.old === 'Dropped', 'the old goal is still open')
      await byArea()
      must(await block(`I57 open ${width}`).count() === 1, 'the new focus is not on Goals')
    })

    await check('GOALS.70', `${width} px: Settings > Areas shows focuses under each part, with switches and + Add a focus`, async () => {
      await one.open('/life/settings?tab=areas')
      await pg.locator('[data-areas-section]').waitFor({ timeout: 10000 })
      await settle()
      const rowsOf = pg.locator(`[data-focuses-of="I57 Estate ${width}"]`)
      must(await rowsOf.locator('[data-focus-switch]').count() >= 2, 'the focuses are not under the part')
      must(await rowsOf.locator(`[data-add-focus="I57 Estate ${width}"]`).count() === 1, '+ Add a focus is missing')
      await rowsOf.locator(`[data-focus-switch="I57 Quality ${width}"]`).click()
      await pg.waitForTimeout(900)
      must(bench(`print(frappe.db.get_value("Life Area", ${JSON.stringify(made.quality)}, "is_on"))`).split('\n').pop() === '0', 'the switch did not save')
      await rowsOf.locator(`[data-focus-switch="I57 Quality ${width}"]`).click()
      await pg.waitForTimeout(900)
      await rowsOf.locator(`[data-add-focus="I57 Estate ${width}"]`).click()
      const dlg = pg.locator('[role="dialog"]').last()
      await dlg.waitFor({ timeout: 8000 })
      await inField(dlg, 'data-part-title').fill(`I57 People ${width}`)
      await dlg.getByRole('button', { name: 'Add', exact: true }).click()
      await dlg.waitFor({ state: 'detached', timeout: 8000 })
      must(bench(`print(frappe.db.exists("Life Area", {"space": "${space}", "area_name": "I57 People ${width}", "is_focus": 1, "parent_area": "${made.part}"}) is not None)`).split('\n').pop() === 'True', 'the focus was not added')
      // switched off, no focus is shown anywhere in Settings
      await one.api('settings.save', { values: { use_focuses: 0 } })
      await one.open('/life/settings?tab=areas')
      await pg.locator('[data-areas-section]').waitFor({ timeout: 10000 })
      await settle()
      must(await pg.locator('[data-focus-switch]').count() === 0, 'focuses are shown with Use focuses off')
      await one.api('settings.save', { values: { use_focuses: 1 } })
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('GOALS.71', `${width} px: focus headings and their goals stack on a phone and the focus page is one column`, async () => {
      await byArea()
      await noSideways()
      await one.open(`/life/focus/${made.yield}`)
      await pg.locator('[data-focus-page][data-loaded="1"]').waitFor({ timeout: 10000 })
      await settle()
      const cols = await pg.locator('[data-focus-page]').evaluate((el) => (el.children[1].getBoundingClientRect().left > el.children[0].getBoundingClientRect().left + 10 ? 2 : 1))
      must(phone ? cols === 1 : cols === 2, `the focus page has ${cols} columns at ${width} px`)
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    if (one) await one.ctx.close()
    restore()
  }
}
