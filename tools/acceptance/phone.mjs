// The phone and the way around: the sidebar and bottom bar, the router, the keyboard, the PWA and offline capture.
// Checks are numbered PHONE.<n> in the order they appear here; `node tools/acceptance.mjs --only=PHONE` runs this file's checks.
import { DAY_NAMES, PLACES, SETUP, SPACE, WIDTHS, areaId, areas, base, bench, browser, check, chromium, env, fs, must, owner, path, pathOf, root, session, stamp, today } from './context.mjs'
import { num, ux, uxArea, uxKit } from './ux.mjs'

for (const width of WIDTHS) {
  const { closeMore, count, errors, nav, openMore, overflow, pg, phone, s, settle, tag } = await uxKit(width)
  await check('PHONE.1', `${width} px: navigation: ${phone ? 'the phone bar is Today, Brain, Goals and Library under the chat bar; each opens; the chat bar opens the chat sheet; the lens sheet holds Settings; the Brain count' : 'the sidebar is the lens, Chat, Today, Brain, Goals, Library and Settings; the active item; the place tabs; the Brain count; the chat panel and what + adds'}; /graph is the Graph view of Notes`, async () => {
    let step = 'start'
    try {
    const PLACES = ['Today', 'Brain', 'Goals', 'Library']
    const path = () => new URL(pg.url()).pathname.replace(/\/$/, '')
    if (phone) {
      await s.open('/life')
      const items = await pg.locator('[data-tabbar] [data-tab-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab-item')))
      must(JSON.stringify(items) === JSON.stringify(PLACES), `the phone bar is ${items}`)
      must(!(await pg.locator('[data-tab-capture]').count()), 'the phone bar still has a Capture button')
      must(await pg.locator('[data-tabbar] [data-chat-bar]').count(), 'the phone bar has no chat bar')
      step = 'each place opens from the bar'
      for (const [label, want] of [['Brain', '/life/brain'], ['Goals', '/life/goals'], ['Library', '/life/library'], ['Today', '/life/today']]) {
        await nav(label)
        must(path() === want, `${label} opened ${path()}`)
      }
      step = 'the chat bar opens the chat sheet'
      await pg.locator('[data-chat-bar-open]').click()
      await settle()
      must(await pg.locator('[data-ask-sheet]:visible').count(), 'the chat bar did not open the chat sheet')
      await pg.keyboard.press('Escape')
      await settle()
      step = 'the Brain count'
      const due = (await s.api('session.counts', { space: SPACE })).doors.inbox.n
      const badge = pg.locator('[data-tabbar] [data-tab-count="Brain"]')
      must(due === 0 ? !(await badge.count()) : num(await badge.innerText()) === due, `the Brain tab says ${await badge.count() ? await badge.innerText() : 'nothing'}, the count helper says ${due}`)
      step = 'the menu sheet holds Settings'
      await pg.locator('[data-more-title]').click()
      await settle()
      must(await pg.locator('[data-more-sheet]').isVisible(), 'the title did not open the menu sheet')
      await pg.locator('[data-more-settings]').click()
      await settle()
      must(path() === '/life/settings', `Settings in the menu sheet opened ${path()}`)
    } else {
      await s.api('views.save', { screen: 'sidebar', space: '', state: { rail: false } })
      await s.open('/life')
      // Review joins the places once a review is locked, or on the review's day: the rest is fixed
      const navItems = () => pg.locator('[data-nav-places] [data-nav-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')).filter((x) => x !== 'Review'))
      must(JSON.stringify(await navItems()) === JSON.stringify(PLACES), `the places are ${await navItems()}`)
      must(JSON.stringify(await pg.locator('[data-nav-bottom] [data-nav-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav-item')))) === JSON.stringify(['Settings']), 'the bottom is not Settings')
      must(await pg.locator('[data-nav-chat]').count() && await pg.locator('[data-ask-box]').count(), 'Chat or the header box is missing')
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
      step = 'the chat panel opens and + holds what Capture held'
      await s.open('/life')
      await pg.locator('[data-nav-chat]').click()
      await pg.locator('[data-ask-panel]:visible').waitFor({ timeout: 10000 })
      must(!(await pg.locator('[data-nav-capture], [data-capture-sheet]').count()), 'the Capture button or sheet is still there')
      for (const [kind, ok] of [['Goal', async () => pg.getByRole('dialog', { name: 'New goal' }).isVisible()], ['Note', async () => pg.getByRole('dialog', { name: 'New note' }).isVisible()],
        ['Park on Someday', async () => pg.getByRole('dialog', { name: 'Park on Someday' }).isVisible()], ['Important date', async () => pg.getByRole('dialog', { name: 'Add important date' }).isVisible()]]) {
        await pg.locator('[data-ask-attach]:visible').click()
        await pg.getByRole('menuitem', { name: kind }).click()
        await settle()
        must(await ok(), `+, ${kind} did not open`)
        await pg.keyboard.press('Escape')
        if (!(await pg.locator('[data-ask-panel]:visible').count())) await pg.locator('[data-nav-chat]').click()
      }
      await pg.locator('[data-ask-attach]:visible').click()
      must(await pg.getByRole('menuitem', { name: 'Files or a photo' }).count(), '+ has no Files or a photo')
      await pg.keyboard.press('Escape')
    }
    // the Graph view of Library > Notes
    step = 'the Graph view of Notes'
    await s.open('/life/library/notes?view=graph')
    must(path() === '/life/library/notes' && new URL(pg.url()).searchParams.get('view') === 'graph', `the graph went to ${pg.url()}`)
    must((await pg.locator('[data-library-views] [aria-checked="true"], [data-library-views] [data-state="checked"], [data-library-views] [data-state="on"]').first().innerText()).includes('Graph'), '/graph is not the Graph view of Notes')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) }
  })

  await check('PHONE.2', `${width} px: a place's tabs: the path holds the tab, the view switch is in the URL, [ and ] move, the phone row scrolls`, async () => {
    const bar = pg.locator('[data-place-tabs]').first()
    await s.open('/life/today/month?view=habits')
    must((await bar.getAttribute('data-tab-current')) === 'month', 'Today did not open on Month from its path')
    must((await pg.locator('[data-plan-views] [aria-checked="true"], [data-plan-views] [data-state="checked"], [data-plan-views] [data-state="on"]').first().innerText()).includes('Habits'), 'the view switch is not on Habits')
    const tabs = await bar.locator('[data-tab]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab')))
    must(JSON.stringify(tabs) === JSON.stringify(['day', 'week', 'month', 'year']), `Today's tabs are ${tabs}`)
    await s.open('/life/library/notes')
    const lib = await pg.locator('[data-place-tabs] [data-tab]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab')))
    must(JSON.stringify(lib) === JSON.stringify(['pages', 'all', 'notes', 'documents', 'people', 'chats', 'files']), `Library's tabs are ${lib}`)
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

  await check('PHONE.3', `${width} px: no screen scrolls sideways: every place, Plan and Library tab and view, Settings section, a goal and a note page, with and without an area`, async () => {
    const before = errors.length
    const bad = []
    const screens = ['/life', '/life/brain', '/life/today/week?view=review', '/life/today/week?view=calendar', '/life/today/week?view=agenda', '/life/goals/cycles',
      '/life/today/month?view=habits', '/life/today/month?view=calendar', '/life/today/year?view=calendar',
      '/life/today/year?view=goals', '/life/goals', '/life/goals/tasks', '/life/goals/someday', '/life/library', '/life/library/notes',
      '/life/library/notes?view=tree', '/life/library/notes?view=graph', '/life/library/notes?view=changes', '/life/library/notes?view=health', '/life/library/notes?by=assistant',
      '/life/brain/captures', '/life/library/documents?tab=documents&sensitive=1', '/life/brain/captures?tab=photos', '/life/library/timeline',
      '/life/library/archive', '/life/library/archive?type=trash', '/life/insights', `/life/goals/${ux.goal}`, `/life/library/${ux.note}`,
      ...['profile', 'appearance', 'notifications', 'shortcuts', 'calendar', 'areas', 'rhythms', 'habits', 'data', 'connections', 'ai', 'cost', 'sensitive',
        'note-rules', 'spaces', 'members', 'agents', 'archive', 'import', 'backups'].map((t) => `/life/settings?tab=${t}`)]
    for (const p of screens) for (const area of ['', uxArea]) {
      if (area && p.includes('settings')) continue
      await s.open(p + (p.includes('?') ? '&' : '?') + 'area=' + area)
      const over = await overflow()
      if (over > 0) bad.push(`${p}${area ? ' (area)' : ''} by ${over} px`)
    }
    if (phone) { // the lens sheet and the Ask sheet too
      await s.open('/life')
      await openMore()
      if ((await overflow()) > 0) bad.push('the menu sheet')
      await closeMore()
    }
    must(!bad.length, 'scrolls sideways: ' + bad.join('; '))
    must(errors.length === before, 'script errors: ' + errors.slice(before).join(' | ').slice(0, 300))
    return `${screens.length} screens`
  })
  await s.ctx.close()
}

await check('PHONE.4', 'Keyboard: G then T, I, O or L opens a place; the older G letters open their new homes', async () => {
  const pg = owner.page
  const done = []
  for (const [key, want, q] of [['t', '/life/today'], ['i', '/life/brain'], ['p', '/life/today/week'], ['l', '/life/library'], ['k', '/life/goals/tasks'], ['o', '/life/goals'],
    ['y', '/life/goals/someday'], ['w', '/life/today/week'], ['m', '/life/today/month'], ['j', '/life/goals/cycles'], ['c', '/life/today/year'], ['e', '/life/settings', { tab: 'data' }],
    ['n', '/life/library/notes'], ['u', '/life/brain/activity'], ['h', '/life/library/chats', { tab: 'chats' }], ['v', '/life/library/documents', { tab: 'documents', sensitive: '1' }],
    ['x', '/life/library/notes', { by: 'assistant' }], ['g', '/life/library/notes', { view: 'graph' }], ['r', '/life/library/archive'], ['b', '/life/brain/outbox'], ['d', '/life/review'],
    ['q', '/life/insights'], ['a', '/life/settings', { tab: 'areas' }], ['s', '/life/settings']]) {
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
  for (const width of WIDTHS) {
    const tag = `I14.${width}`
    const phone = width < 800
    if (!phone) {
      setDay(offDay)
      bench('frappe.db.delete("Life Review", {"user": "family@lifeos.test"})')
      const f = await session('family@lifeos.test', width)
      const fe = errs(f.page)
      try {
        await check('PHONE.5', `${width} px: the sidebar shows Chat, Today, Brain, Goals, Library and Settings, in that order, and no other place`, async () => {
          await f.open('/life/today')
          const order = await f.page.locator('[data-sidebar] [data-nav-chat], [data-sidebar] [data-nav-item]').evaluateAll((els) =>
            els.map((e) => (e.hasAttribute('data-nav-chat') ? 'Chat' : e.getAttribute('data-nav-item'))))
          must(JSON.stringify(order) === JSON.stringify(['Chat', 'Today', 'Brain', 'Goals', 'Library', 'Settings']), 'the sidebar reads ' + order.join(', '))
          must((await f.page.locator('[data-sidebar] [data-nav-chat]').innerText()).includes('Chat'), 'the first button is not Chat')
          for (const gone of ['[data-nav-pin]', '[data-nav-plan]', '[data-nav-new]']) must(!(await f.page.locator(gone).count()), 'the sidebar still has ' + gone)
          must(await f.page.locator('[data-page-head] [data-ask-box]').count(), 'Ask is not in the header')
          must(!fe.length, 'script errors: ' + fe.slice(0, 3).join(' | '))
        })
        await check('PHONE.6', `${width} px: Review is hidden for a user who has never locked a review, and shown between Goals and Library after one is locked`, async () => {
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
      await check('PHONE.7', `${width} px: Brain shows the Needs you count, the same number as the Inbox count`, async () => {
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
      await check('PHONE.8', `${width} px: an old address lands on Today with the moved note, and every route of the router loads without an error`, async () => {
        const goal = (await s.api('goals.list', { space: SPACE, horizon: 'Long term', page_length: 1 })).goals[0].name
        const area = areaId('Career') || areas[0].name
        const OLD = [['/life', '/life/today'], ['/life/inbox', '/life/brain'], [`/life/inbox/${item.name}`, '/life/brain/queue'],
          [`/life/inbox/${item.name}/review`, `/life/brain/review/${item.name}`], ['/life/plan', '/life/today/week'], ['/life/plan/week', '/life/today/week'],
          ['/life/plan/month', '/life/today/month'], ['/life/plan/12-weeks', '/life/goals/cycles'], ['/life/plan/year', '/life/today/year'],
          ['/life/plan/goals', '/life/goals'], [`/life/plan/goals/${goal}`, `/life/goals/${goal}`], ['/life/plan/tasks', '/life/goals/tasks'],
          ['/life/plan/someday', '/life/goals/someday'], ['/life/plan/reset', '/life/today/week'], ['/life/tasks', '/life/goals/tasks'],
          ['/life/someday', '/life/goals/someday'], ['/life/outbox', '/life/brain/outbox'], ['/life/archive', '/life/library/archive'],
          ['/life/wiki', '/life/library/notes'], ['/life/vault', '/life/library/documents'], ['/life/graph', '/life/library/notes'],
          ['/life/timeline', '/life/library/timeline'], ['/life/sources', '/life/brain/sources'], ['/life/chats', '/life/library/chats'],
          ['/life/projects', '/life/goals'],
          ['/life/reset', '/life/today/week'], ['/life/today/reset', '/life/today'], ['/life/calendar', '/life/today/week'], ['/life/calendar/month', '/life/today/month'],
          ['/life/calendar/year', '/life/today/year'], ['/life/calendar/agenda', '/life/today/week'], ['/life/journal', '/life/goals/cycles'],
          ['/life/journal/goals', '/life/goals/cycles'], ['/life/journal/month', '/life/goals/cycles'], ['/life/journal/habits', '/life/today/month'],
          ['/life/journal/checkins', '/life/today/month'], ['/life/journal/review', '/life/today/week'], ['/life/journal/pages', '/life/library/notes'],
          [`/life/journal/goals/${goal}`, `/life/goals/${goal}`], ['/life/areas', '/life/settings'], [`/life/areas/${area}`, '/life/today'],
          ['/life/no-such-page', '/life/today']]
        const bad = []
        for (const [from] of OLD) {
          const before = errors.length
          await s.open(from)
          if (path(pg) !== '/life/today') { bad.push(`${from} went to ${path(pg)}`); continue }
          if (from !== '/life' && !(await pg.locator('[data-moved-note]').isVisible())) { bad.push(`${from}: no "That page moved" note`); continue }
          try { await loaded(pg, from) } catch (e) { bad.push(e.message) }
          if (errors.length > before) bad.push(`${from}: ${errors.slice(before).join(' | ')}`)
        }
        must(!bad.length, bad.slice(0, 5).join('; '))
        return `${OLD.length} routes`
      })
      await check('PHONE.9', `${width} px: Archive, Outbox, Graph, Timeline, Reset and Vault are reached from their new homes`, async () => {
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
        await via('/life/goals/tasks', '[data-all-tasks-reset]', '/life/settings', { tab: 'data' }) // issue 55: Reset moved from Today's band to All tasks; issue 72: it is Settings > Data
        // Settings > Data lists every page with no other home
        await s.open('/life/settings?tab=places')
        const listed = await pg.locator('[data-settings-places] [data-elsewhere]').evaluateAll((els) => els.map((e) => e.getAttribute('data-elsewhere')))
        for (const k of ['archive', 'outbox', 'graph', 'timeline', 'reset', 'vault']) must(listed.includes(k), 'Settings > Data does not list ' + k)
        await noSideways(pg)
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
      if (phone) {
        await check('PHONE.10', `${width} px: the chat bar is above the tabs on every screen and there is no + Capture; "buy rakhi thread", with no question, makes a capture`, async () => {
          for (const path of ['/life/today', '/life/brain', '/life/goals', '/life/library']) {
            await s.open(path)
            must(await pg.locator('[data-tabbar] [data-chat-bar]').isVisible(), `no chat bar on ${path}`)
            must(!(await pg.locator('[data-tab-capture], [data-nav-capture]').count()), `a Capture button on ${path}`)
            for (const sel of ['[data-ask-attach]', '[data-ask-camera]', '[data-ask-mic]']) must(await pg.locator(`[data-chat-bar] ${sel}`).count(), `the chat bar has no ${sel} on ${path}`)
          }
          const bar = pg.locator('[data-tabbar]')
          const items = await bar.locator('[data-tab-item]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tab-item')))
          must(JSON.stringify(items) === JSON.stringify(['Today', 'Brain', 'Goals', 'Library']), 'the bar reads ' + items.join(', '))
          const above = await pg.evaluate(() => document.querySelector('[data-chat-bar]').getBoundingClientRect().bottom <= document.querySelector('[data-tabbar] nav, [data-tabbar] [aria-label="Places"]').getBoundingClientRect().top + 1)
          must(above, 'the chat bar is not above the tabs')
          await s.open('/life/today')
          const title = `buy rakhi thread ${width} ${stamp}`
          await pg.locator('[data-chat-bar-input] input, input[data-chat-bar-input]').first().fill(title)
          await pg.locator('[data-chat-bar-send]').click()
          let made = []
          for (let i = 0; i < 20 && !made.length; i++) { made = JSON.parse(bench(`import json\nprint(json.dumps(frappe.get_all("Life Inbox Item", filters={"title": "${title}"}, pluck="name")))`).split('\n').pop()); if (!made.length) await pg.waitForTimeout(500) }
          must(made.length === 1, 'the message with no question did not make a capture')
          must(!(await pg.locator('[data-ask-sheet]:visible').count()), 'a capture opened the chat sheet')
          bench(`frappe.delete_doc("Life Inbox Item", "${made[0]}", force=1, ignore_permissions=True)`)
          await noSideways(pg)
          must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
        })
      }
      await check('PHONE.11', `${width} px: tabs are routes: each tab has its own path, and reloading /life/goals/tasks lands on Goals > All tasks`, async () => {
        const TABS = { today: ['day', 'week', 'month', 'year'], brain: ['needs-you', 'activity', 'sources'], goals: ['by-area', 'tasks', 'no-goal', 'cycles'],
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
  for (const width of WIDTHS) {
    const tag = `I15.${width}`
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
      await check('PHONE.12', `${width} px: Today > Day shows today's tasks, the top three and the day's events from the calendar`, async () => {
        await s.open('/life/today')
        await pg.locator('[data-next]').waitFor({ timeout: 10000 })
        if (await pg.locator('[data-next-more]').count()) await pg.locator('[data-next-more]').click() // earlier checks leave tasks due today: show them all
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
        must(await pg.locator('[data-open-band]').count() === 0, 'the Open band is gone from Today (issue 55)')
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
      await check('PHONE.13', `${width} px: ticking a task on Today marks it done and updates the counts`, async () => {
        await s.open('/life/today')
        if (await pg.locator('[data-next-more]').count()) await pg.locator('[data-next-more]').click()
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
      await check('PHONE.14', `${width} px: the Needs you line shows the waiting count and opens Brain > Needs you`, async () => {
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
      await check('PHONE.15', `${width} px: the switch moves to Week, Month and Year routes`, async () => {
        await s.open('/life/today')
        for (const t of ['week', 'month', 'year', 'day']) {
          await pg.locator(`[data-place-tabs] [data-tab="${t}"]`).first().click()
          const want = t === 'day' ? '/life/today' : `/life/today/${t}`
          await pg.waitForURL((u) => u.pathname === want, { timeout: 10000 }).catch(() => {})
          must(path(pg) === want, `${t} opened ${path(pg)}`)
        }
      })
      await check('PHONE.16', `${width} px: the layout matches the mockups (${phone ? 'Needs you, the plate, then the calendar below it' : 'the plate with the calendar beside it'}), with no sideways scroll`, async () => {
        await s.open('/life/today')
        await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
        const box = async (sel) => (await pg.locator(sel).first().boundingBox())
        const nu = await box('[data-needs-you]'), plate = await box('[data-next]'), rail = await box('[data-rail-today]')
        must(nu.y < plate.y, 'Needs you is not above the plate')
        if (phone) must(rail.y > plate.y && Math.abs(rail.x - plate.x) < 4, 'the calendar is not below the plate')
        else must(rail.x > plate.x + plate.width - 4 && rail.y < plate.y + 80, 'the calendar is not beside the plate')
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


// Issue 50: Life OS on the phone: install, share to it, capture offline, voice. One browser with a fake microphone and a phone profile.
// Titles start "I50 " (the debris finder knows them); the voice note is named by its file, so it is removed by its instruction.
{
  const pb = await chromium.launch({ executablePath: SETUP.chrome, headless: true, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })
  const ctx = await pb.newContext({ viewport: { width: 390, height: 844 }, timezoneId: 'Asia/Kolkata', isMobile: true, hasTouch: true, permissions: ['microphone'] })
  // a fake microphone: a tone from the Web Audio API stands in for getUserMedia, the same on every machine
  await ctx.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const ac = new AudioContext(); const osc = ac.createOscillator(); const dest = ac.createMediaStreamDestination()
      osc.connect(dest); osc.start(); return dest.stream
    }
  })
  const pg = await ctx.newPage()
  const apiCalls = []
  pg.on('request', (r) => { if (/inbox\.create_item|upload_file/.test(r.url())) apiCalls.push(r.url()) })
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const items = (where) => JSON.parse(bench(`import json
rows = frappe.db.sql("select name, source_type, source_system, external_id, title, instruction from \`tabLife Inbox Item\` where ${where}", as_dict=True)
for r in rows: r["files"] = frappe.db.count("File", {"attached_to_doctype": "Life Inbox Item", "attached_to_name": r["name"], "attached_to_field": ["is", "not set"]})
print(json.dumps(rows))`).split('\n').pop())
  const queued = () => pg.evaluate(() => new Promise((res) => { const r = indexedDB.open('lifeos-phone', 1)
    r.onupgradeneeded = () => { for (const n of ['queue', 'shares']) if (!r.result.objectStoreNames.contains(n)) r.result.createObjectStore(n, { keyPath: 'id' }) }
    r.onsuccess = () => { const q = r.result.transaction('queue').objectStore('queue').count(); q.onsuccess = () => { r.result.close(); res(q.result) } } }))
  const openCapture = async () => { await pg.locator('[data-chat-bar-input]').waitFor() }
  const typeAndSend = async (text) => { await pg.locator('[data-chat-bar-input] input, input[data-chat-bar-input]').first().fill(text); await pg.locator('[data-chat-bar-send]').click() }
  const waitCount = (n) => pg.waitForFunction((n) => (document.querySelector('[data-queue-note]')?.textContent.match(/(\d+) waiting/) || [0, 0])[1] == n, n, { timeout: 15000 })
  const where = `title like 'I50 %${stamp}%'`
  try {
    const res = await ctx.request.post(base + '/api/method/login', { form: { usr: 'owner@lifeos.test', pwd: env.LIFEOS_DEV_PASSWORD } })
    must(res.ok(), 'login failed')
    await pg.goto(base + '/life/today', { waitUntil: 'networkidle' })
    await pg.evaluate(() => navigator.serviceWorker.ready)
    await pg.reload({ waitUntil: 'networkidle' }) // now the worker controls the page
    await pg.locator('[data-chat-bar-input]').waitFor()

    await check('PHONE.17', 'The manifest is valid and the service worker is registered (phone profile)', async () => {
      const m = await (await ctx.request.get(base + '/assets/lifeos/manifest.webmanifest')).json()
      must(m.name === 'Life OS' && m.display === 'standalone' && m.start_url === '/life/today', 'manifest name, display or start_url is wrong')
      must(m.icons.some((i) => i.sizes === '512x512') && m.icons.some((i) => i.sizes === '192x192') && m.theme_color, 'manifest icons or theme colour missing')
      must(m.share_target?.action === '/life/share' && m.share_target.method === 'POST', 'manifest has no share target')
      must(await pg.evaluate(() => document.querySelector('link[rel=manifest]')?.href.endsWith('/assets/lifeos/manifest.webmanifest')), 'the page does not link the manifest')
      for (const i of m.icons) must((await ctx.request.get(base + i.src)).ok(), 'icon not served: ' + i.src)
      const sw = await pg.evaluate(async () => { const r = await navigator.serviceWorker.getRegistration('/life/'); return { scope: r?.scope, active: !!r?.active, controlled: !!navigator.serviceWorker.controller } })
      must(sw.scope === base + '/life/' && sw.active && sw.controlled, 'the service worker is not registered and in control: ' + JSON.stringify(sw))
    })

    await check('PHONE.18', "The service worker's cache holds only static app files, never an /api/ response", async () => {
      for (const p of ['/life/today', '/life/brain', '/life/goals', '/life/settings']) await pg.goto(base + p, { waitUntil: 'networkidle' })
      const urls = await pg.evaluate(async () => { const out = []; for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(r.url); return out })
      must(urls.length > 0, 'nothing is cached')
      const bad = urls.filter((u) => !new URL(u).pathname.startsWith('/assets/lifeos/') || /\/api\//.test(u))
      must(!bad.length, 'cached and not static: ' + bad.slice(0, 3).join(' '))
    })

    await check('PHONE.19', 'Posting to the share target with a photo and text opens the share screen; Save puts it in the chat, which keeps the file as a capture', async () => {
      const png = await pg.screenshot()
      const url = await pg.evaluate(async ({ stamp, bytes }) => {
        const f = new FormData()
        f.append('title', `I50 shared ${stamp}`); f.append('text', `Look at this ${stamp}`); f.append('url', 'https://example.com/i50')
        f.append('files', new File([new Uint8Array(bytes)], `shared-${stamp}.png`, { type: 'image/png' }))
        const r = await fetch('/life/share', { method: 'POST', body: f })
        return r.url
      }, { stamp, bytes: [...png] })
      must(/\/life\/share\?id=/.test(url), 'the share was not taken: ' + url)
      await pg.goto(url, { waitUntil: 'networkidle' })
      await pg.locator('[data-share-what]').waitFor()
      const t = await pg.locator('[data-share-what]').innerText()
      must(t.includes(`I50 shared ${stamp}`) && t.includes(`Look at this ${stamp}`) && t.includes(`shared-${stamp}.png`), 'the capture screen does not show what was shared: ' + t)
      must(await pg.locator('[data-share-what] img').count() === 1, 'no photo preview')
      must(items(where).length === 0, 'something was sent before Save')
      await pg.getByLabel('Instruction (optional)').fill('I50 summarise')
      await pg.locator('[data-share-save]').click()
      await pg.waitForFunction(() => location.pathname.startsWith('/life/today'), null, { timeout: 15000 })
      let rows = []
      for (let i = 0; i < 20 && !rows.length; i++) { rows = items(`title = 'shared-${stamp}.png'`); if (!rows.length) await pg.waitForTimeout(500) }
      must(rows.length === 1 && rows[0].source_type === 'Upload' && rows[0].files === 1 && rows[0].instruction.includes('I50 summarise'), 'the capture is wrong: ' + JSON.stringify(rows))
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('PHONE.20', 'Offline, two captures are queued ("2 waiting to send"); back online both are sent, once each', async () => {
      await pg.goto(base + '/life/today', { waitUntil: 'networkidle' })
      await ctx.setOffline(true)
      await pg.waitForFunction(() => !navigator.onLine)
      await openCapture()
      await typeAndSend(`I50 offline one ${stamp}`)
      await pg.waitForTimeout(500)
      await openCapture()
      await typeAndSend(`I50 offline two ${stamp}`)
      await pg.waitForTimeout(500)
      await waitCount(2)
      must((await pg.locator('[data-queue-note]').innerText()).includes('2 waiting to send'), 'the note does not say "2 waiting to send"')
      must(await pg.locator('[data-offline]').count() === 1, 'no offline note on the screen')
      must(items(`title like 'I50 offline %${stamp}%'`).length === 0, 'something reached the server while offline')
      await ctx.setOffline(false)
      await pg.waitForFunction(() => !document.querySelector('[data-queue-note]'), null, { timeout: 20000 })
      const rows = items(`title like 'I50 offline %${stamp}%'`)
      must(rows.length === 2 && new Set(rows.map((r) => r.title)).size === 2 && rows.every((r) => r.source_type !== undefined), 'each capture should be in Brain once: ' + JSON.stringify(rows))
      await pg.goto(base + '/life/brain/captures', { waitUntil: 'networkidle' })
      must(await queued() === 0, 'the queue is not empty')
    })

    await ctx.setOffline(false)
    await check('PHONE.21', 'The mic on the chat bar records (fake microphone) and sends the recording to the server to be turned into text; nothing is captured and the recording is not kept', async () => {
      await pg.goto(base + '/life/today', { waitUntil: 'networkidle' })
      const before = items(`source_type = 'Voice Note'`).length
      await pg.locator('[data-chat-bar] [data-ask-mic]').click()
      await pg.waitForFunction(() => document.querySelector('[data-chat-bar] [data-ask-mic]')?.getAttribute('aria-label')?.startsWith('Stop'), null, { timeout: 10000 })
      await pg.waitForTimeout(1500)
      const answered = pg.waitForResponse((r) => r.url().includes('chat.transcribe'), { timeout: 60000 })
      await pg.locator('[data-chat-bar] [data-ask-mic]').click()
      await answered // the text (or, for a beep, "nothing was heard") comes from faster-whisper on the server
      must(items(`source_type = 'Voice Note'`).length === before, 'the recording was captured instead of written down')
      const left = bench(`print(frappe.db.count("File", {"file_name": ["like", "voice-%"], "attached_to_doctype": ["is", "not set"]}))`).split('\n').pop()
      must(Number(left) === 0, 'the recording was kept: ' + left)
    })

    await check('PHONE.22', 'Logging out empties the offline queue', async () => {
      await pg.goto(base + '/life/today', { waitUntil: 'networkidle' })
      await pg.route('**/api/method/lifeos.api.inbox.create_item', (r) => r.abort('connectionfailed')) // sending fails: it stays queued
      await openCapture()
      await typeAndSend(`I50 queued at logout ${stamp}`)
      await pg.waitForTimeout(500)
      await waitCount(1)
      must(await queued() === 1, 'one capture should be waiting')
      await pg.locator('[data-more-title]').click()
      await pg.getByRole('button', { name: 'Log out' }).click()
      await pg.waitForFunction(() => location.pathname === '/login', null, { timeout: 15000 })
      must(await queued() === 0, 'the queue still holds a capture after logging out')
      await pg.unroute('**/api/method/lifeos.api.inbox.create_item')
      must(items(`title like 'I50 queued at logout %${stamp}%'`).length === 0, 'the queued capture was sent')
    })

    await check('PHONE.23', 'The share target while logged out goes to login and sends nothing', async () => {
      const before = apiCalls.length
      await pg.goto(base + `/life/share?id=none`, { waitUntil: 'networkidle' })
      must(new URL(pg.url()).pathname === '/login', 'went to ' + pg.url())
      await pg.waitForTimeout(1500)
      must(apiCalls.length === before, 'something was sent: ' + apiCalls.slice(before).join(' '))
      must(items(`title = 'shared-${stamp}.png'`).length === 1 && items(`title like 'I50 queued%${stamp}%'`).length === 0, 'no new capture should exist') // the one saved in I50.3
    })
  } finally {
    bench(`for n in frappe.get_all("Life Inbox Item", filters={"instruction": "I50 voice ${stamp}"}, pluck="name"): frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)`)
    await ctx.close()
    await pb.close()
  }
}


// Issue 61: every route of the router loads without an error, and an address that is not a screen lands on Today with "That page moved".
// I61.2 to I61.5 are unit tests (test_i61_cleanup).
for (const width of WIDTHS) {
  const tag = `I61.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  try {
    await check('PHONE.24', `${width} px: every route in the router loads without an error; an unknown address lands on Today with "That page moved"`, async () => {
      const ids = JSON.parse(bench(`import json
first = lambda dt, **f: frappe.db.get_value(dt, {"space": "${SPACE}", **f}) or "none"
print(json.dumps({"item": first("Life Inbox Item"), "goal": first("Life Goal"), "area": first("Life Area"), "note": first("Life Note"),
	"person": first("Life Person"), "skill": frappe.db.get_value("Life Skill", {}) or "process-capture"}))`).split('\n').pop())
      // router path -> an address that opens it
      const ROUTES = {
        '/': '/life', '/today/:tab(week|month|year)?': '/life/today/month', '/brain/:tab(...)?': '/life/brain/activity',
        '/brain/skills/:name': `/life/brain/skills/${ids.skill}`, '/brain/sources/:key': '/life/brain/sources/gmail', '/brain/review/:id': `/life/brain/review/${ids.item}`, '/share': '/life/share',
        '/item/:id': `/life/item/${ids.item}`, '/goals/:tab(...)?': '/life/goals/cycles', '/goals/:id': `/life/goals/${ids.goal}`,
        '/focus/:id': `/life/focus/${ids.area}`, '/library/:tab(...)?': '/life/library/notes', '/library/pages/:doctype/:name': `/life/library/pages/Life%20Person/${ids.person}`, '/library/people/:person': `/life/library/people/${ids.person}`,
        '/library/:id': `/life/library/${ids.note}`, '/review': '/life/review', '/how-it-works': '/life/how-it-works', '/insights': '/life/insights', '/settings': '/life/settings',
        '/dev/editor': '/life/dev/editor',
      }
      const source = fs.readFileSync(path.join(root, 'frontend/src/router.js'), 'utf8')
      const declared = [...source.matchAll(/\{ path: (`[^`]*`|'[^']*'),\s*(?:name|redirect|component)/g)].map((m) => m[1].slice(1, -1).replace(/\$\{[^}]*\}/g, '...'))
        .filter((x) => x !== '/:rest(.*)*' && x !== '/dev/throw')
      const norm = (x) => x.replace(/\(([^)]*)\)/g, '(...)')
      const covered = new Set(Object.keys(ROUTES).map(norm))
      const missing = declared.map(norm).filter((x) => !covered.has(x))
      must(!missing.length, `routes with no address in this check: ${missing.join(', ')}`)
      const bad = []
      for (const [route, address] of Object.entries(ROUTES)) {
        const before = errors.length
        await s.open(address)
        await pg.locator('[data-main], [data-app]').first().waitFor({ timeout: 10000 }).catch(() => {})
        await pg.waitForTimeout(300)
        if (pathOf(pg) === '/life/today' && address !== '/life' && !address.startsWith('/life/today')) bad.push(`${route}: ${address} was sent to Today`)
        if (await pg.locator('[data-screen-error]').count()) bad.push(`${route}: the screen shows the error message`)
        if (errors.length > before) bad.push(`${route}: ${errors.slice(before).join(' | ')}`)
      }
      must(!bad.length, bad.slice(0, 5).join('; '))
      for (const from of ['/life/no-such-page', '/life/plan/week', '/life/library/x/y']) {
        await s.open(from)
        must(pathOf(pg) === '/life/today', `${from} went to ${pathOf(pg)}`)
        must((await pg.locator('[data-moved-note]').innerText()).includes('That page moved'), `${from} has no "That page moved" note`)
      }
      await pg.locator('[data-moved-note] button').click()
      await pg.waitForTimeout(300)
      must(!(await pg.locator('[data-moved-note]').count()) && !new URL(pg.url()).searchParams.has('moved'), 'Dismiss does not remove the note')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      return `${Object.keys(ROUTES).length} routes`
    })
  } finally { await s.ctx.close() }
}
