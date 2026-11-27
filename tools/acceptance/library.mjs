// Library: Everything, Notes, Documents, People, Chats, files, search, the graph and the list screens' panes and filters.
// Checks are numbered LIBRARY.<n> in the order they appear here; `node tools/acceptance.mjs --only=LIBRARY` runs this file's checks.
import { SPACE, WIDTHS, addDays, agentFetch, areaId, base, bench, browser, check, must, owner, path, runAgent, session, stamp, today } from './context.mjs'
import { FILTERS, LISTS, ROW, num, ux, uxArea, uxKit } from './ux.mjs'

await check('LIBRARY.1', 'Security: rendered Markdown is sanitised', async () => {
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

await check('LIBRARY.48', 'A scanned bill is read on the server and found by a word from its contents', async () => {
  // a PDF that is only a picture: the worker reads it with OCRmyPDF (no model), then search finds it by a word that is in the picture alone
  const word = 'Hartwell'
  bench(`from lifeos.tests.helpers import scanned_pdf
from lifeos.tools.devtools import attach
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "Scanned bill ${stamp}", "source_type": "Upload", "intent": "Just keep", "status": "Done"}).insert(ignore_permissions=True)
attach("Life Inbox Item", item.name, "bill-${stamp}.pdf", scanned_pdf(["Electricity bill", "Customer ${word}", "Amount due 3200 rupees"]))`)
  const wait = async (tries) => {
    for (let i = 0; i < tries; i++) {
      if ((await owner.api('search.query', { text: word, space: SPACE })).results.some((r) => (r.title || '').includes(`Scanned bill ${stamp}`))) return true
      // Frappe queues global search updates and writes them on a scheduled job; the walk's site may not run it in time
      if (i % 5 === 4) bench('from frappe.utils.global_search import sync_global_search\nsync_global_search()')
      await new Promise((r) => setTimeout(r, 2000))
    }
    return false
  }
  let note = 'read once'
  if (!(await wait(30))) {
    // CI failed here twice with the same code that had passed: say what the record and the search index hold, read the file again, and wait again
    const state = bench(`import json
name = frappe.db.get_value("Life Inbox Item", {"title": "Scanned bill ${stamp}"})
row = frappe.db.get_value("Life Inbox Item", name, ["extracted_by", "extract_note", "needs_closer_read", "extract_files"], as_dict=True)
gs = frappe.qb.Table("__global_search")  # no creation column: frappe.db.get_value would order by it (Frappe 16.61)
hit = frappe.qb.from_(gs).select(gs.content).where((gs.doctype == "Life Inbox Item") & (gs.name == name)).run()
row["indexed"] = ((hit[0][0] if hit else "") or "")[:200]
print(json.dumps(row, default=str))`).split('\n').pop()
    console.log(`LIBRARY.48 not found after 60 s: ${state}`)
    bench(`from frappe.utils.global_search import sync_global_search
from lifeos.library import extract
name = frappe.db.get_value("Life Inbox Item", {"title": "Scanned bill ${stamp}"})
extract.run("Life Inbox Item", name, force=True)
sync_global_search()`)
    must(await wait(30), `search did not find the scanned bill by "${word}" even after reading it again (is a worker running, and are tesseract-ocr and ocrmypdf installed?) — ${state}`)
    note = 'found only after reading it again'
  }
  const row = JSON.parse(bench(`import json
print(json.dumps(frappe.db.get_value("Life Inbox Item", {"title": "Scanned bill ${stamp}"}, ["extracted_by", "needs_closer_read"], as_dict=True)))`).split('\n').pop())
  must(row.extracted_by === 'ocrmypdf' && !row.needs_closer_read, JSON.stringify(row))
  bench(`frappe.set_user("Administrator")
for n in frappe.get_all("Life Inbox Item", filters={"title": "Scanned bill ${stamp}"}, pluck="name"):
    frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)`)
  return note
})

for (const width of WIDTHS) {
  const { S5, asAgent, clickRow, count, docOf, editorEnd, errors, nav, overflow, pane, paneTitle, pg, phone, pickQuick, s, settle, tag } = await uxKit(width)
  await check('LIBRARY.2', `${width} px: a row opens a pane on every list screen and the list stays in the page`, async () => {
    // a view another check remembered (a grid on the Brain's feed) draws no highlighted row; this one is about the default list
    bench('frappe.db.delete("Life View State", {"user": "owner@lifeos.test"})')
    for (const [name, p, sel] of LISTS) {
      await s.open(p)
      must(await pg.locator(sel).count(), `${name}: no rows to click`)
      const before = pg.url()
      await clickRow(sel)
      must(await pane.isVisible(), `${name}: no pane after clicking a row`)
      must(pg.url().includes('open='), `${name}: the URL has no open=`)
      must(new URL(pg.url()).pathname === new URL(before).pathname, `${name}: the page changed`)
      must(await pg.locator(sel).count(), `${name}: the list left the page`)
      must(await pg.locator(`${sel}[data-active]`).count() >= 1, `${name}: the open row (${new URL(pg.url()).searchParams.get('open')}) is not highlighted`)
    }
    return `${LISTS.length} screens`
  })

  await check('LIBRARY.3', `${width} px: the URL has open=, Back closes the pane, reload reopens it`, async () => {
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
    await s.open('/life/brain/queue?open=inbox:' + ux.inbox)
    must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/brain/queue' && await pg.locator(ROW).count(), 'an inbox item does not show the list with the pane open')
    must((await pg.locator('[data-pane-title]').innerText()).includes('UX inbox'), 'the pane opened another item')
  })

  if (phone) {
    await check('LIBRARY.4', '390 px: the pane is a bottom sheet across the screen and closes with its close button', async () => {
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
    await check('LIBRARY.5', '1440 px: pane widths, Esc, j and k, focus, Open full page, search opens in the pane', async () => {
      await s.open('/life/goals/tasks?view=list')
      await clickRow(ROW)
      const host = Math.round((await pg.locator('[data-drawer-host]').boundingBox()).width)
      must(host === 480, `a task's drawer is ${host} px wide, not 480`)  // the Drawer's width (#128), measured on the Drawer itself (the pane inside sits within its border)
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
      await s.open('/life/brain/queue?open=inbox:' + ux.inbox)
      const wide = Math.round((await pg.locator('[data-drawer-host]').boundingBox()).width)
      must(wide === 760, `an inbox item's drawer is ${wide} px wide, not 760`)  // measured on the Drawer itself, as above
      await pg.locator('[data-pane-full]').click()
      await settle()
      must(new URL(pg.url()).pathname === `/life/item/${ux.inbox}` && !(await pane.isVisible()), "Open full page did not open the item page")
      // every pane type opens from its reference
      // set 6: goal: opens in the pane too
      for (const ref of [`task:${ux.task}`, `note:${ux.note}`, `vault:${ux.vault}`, `goal:${ux.goal}`, `chat:${ux.chat}`, `day:${today}`]) {
        await s.open('/life/library/timeline?open=' + encodeURIComponent(ref))
        must(await pane.isVisible() && !(await pg.locator('[data-pane-title]').innerText()).match(/Loading|Not found/), `the pane did not load ${ref}`)
      }
      await s.open('/life/library/timeline')
      await pg.keyboard.press('/')
      await pg.locator('input[aria-label="Search or chat"]').fill(`UX note ${stamp}`)
      await pg.waitForTimeout(900)
      await pg.keyboard.press('Enter')
      await settle()
      must(await pane.isVisible() && new URL(pg.url()).pathname === '/life/library/timeline', 'a search result did not open in the pane over the current screen')
      must((await pg.locator('[data-pane-title]').innerText()).includes('UX note'), 'the search result opened another record')
    })
  }

  await check('LIBRARY.6', `${width} px: filters on every ListView are in the URL and survive a reload`, async () => {
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

  await check('LIBRARY.7', `${width} px: no horizontal scrolling and no script errors on any converted screen`, async () => {
    const screens = [...LISTS.map(([n, p]) => [n, p]), ['Tasks table', '/life/goals/tasks?view=table'], ['Tasks board', '/life/goals/tasks?view=board'], ['Open loops', '/life/goals/tasks?view=loops'],
      ['Goals cards', '/life/goals?view=cards'], ['Notes tree', '/life/library/notes?view=tree'], ['Goal page', '/life/goals/' + ux.goal],
      ['Today', '/life'], ['Today under an area', '/life?area=' + uxArea], ['Week review', '/life/today/week?view=review'], ['Week calendar', '/life/today/week?view=calendar'],
      ['Week agenda', '/life/today/week?view=agenda'], ['Cycles', '/life/goals/cycles'], ['Habits', '/life/today/month?view=habits'],
      ['Month calendar', '/life/today/month?view=calendar'], ['Year calendar', '/life/today/year?view=calendar'], ['Goals across cycles', '/life/today/year?view=goals'],
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

  await check('LIBRARY.8', `${width} px: a list remembers its view on every device, a link with a query wins, Clear clears`, async () => {
    const param = (k) => new URL(pg.url()).searchParams.get(k)
    await s.open('/life/goals/no-goal?goal=none') // Goals > All tasks is the grouped screen now (issue 21); the remembered views are checked on No goal, which is the task list with goal=none
    await pickQuick('Priority', 'II')
    must(param('priority') === 'II', 'the filter was not set')
    const filtered = await count()
    await pg.waitForTimeout(1600) // the view is saved a moment after it changes; leaving sooner can lose it
    await nav('Today')
    must(new URL(pg.url()).pathname === '/life/today', 'the sidebar did not go to Today')
    await s.open('/life/goals/no-goal?goal=none') // the bare path is the screen of issue 22; the old list is behind the goal filter
    must(new URL(pg.url()).pathname === '/life/goals/no-goal', 'Goals > No goal did not open')
    await pg.waitForFunction(() => new URL(location.href).searchParams.get('priority') === 'II', null, { timeout: 5000 }).catch(() => {})
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
    // Today no longer carries an Overdue door (issue 132), so the door is read from the server and its link opened as a link
    const door = JSON.parse(bench(`import json
frappe.set_user("owner@lifeos.test")
from lifeos.review import counts
print(json.dumps(counts.overdue_tasks("${SPACE}")))`).split('\n').pop())
    const loops = door.n
    await s.open('/life/goals/tasks?' + new URLSearchParams(door.to.query))
    await pg.waitForLoadState('networkidle')
    await settle()
    must(!param('priority'), 'the Overdue link kept the saved filter')
    must((await count()) === loops, `Overdue shows ${await count()}, the number said ${loops}`)
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

  await check('LIBRARY.9', `${width} px: the record pane shows the tabs of its kind; ptab= survives a reload; a pane with one tab has no tab bar`, async () => {
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
      ['chat:' + one('Life Chat Log', "is_archived=0 and ifnull(transcript_md, '')=''"), ['Summary', 'Open items', 'Made from this', 'Links']],
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

  await check('LIBRARY.10', `${width} px: no sideways scrolling and no script errors on the new screens`, async () => {
    const before = errors.length
    const bad = []
    for (const p of ['/life', '/life/settings?tab=data', '/life/goals/someday', '/life/insights', '/life/library/archive?type=trash', '/life/settings?tab=ai', '/life/settings?tab=reset']) {
      await s.open(p)
      if ((await overflow()) > 0) bad.push(`${p} scrolls sideways by ${await overflow()} px`)
    }
    must(!bad.length, bad.join('; '))
    must(errors.length === before, 'script errors: ' + errors.slice(before).join(' | ').slice(0, 300))
    return '9 screens'
  })

  await check('LIBRARY.11', `${width} px: intent: Just keep is in Library > Captures, not the Inbox, with text and no proposals; Add to wiki writes pages and leaves no wiki proposals`, async () => {
    // Just keep (issue 120: the + Capture sheet and its intent switch are gone; the API still takes the intent)
    await s.api('inbox.create_item', { title: `S4 keep ${width} ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'A note to keep.', intent: 'Just keep' })
    await pg.waitForTimeout(600)
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

  await check('LIBRARY.12', `${width} px: Captures: each tab's count matches its rows; Photos shows thumbnails; Made from this lists the task and the assistant's note; /chats lands on the Chats tab`, async () => {
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
    // the Chats tab keeps its filters
    await s.open(`/life/library/chats?tab=chats&area=${uxArea}`)
    must(/\/life\/library\/chats\?/.test(pg.url()) && pg.url().includes('tab=chats') && pg.url().includes(`area=${uxArea}`), `Chats went to ${pg.url()}`)
    return `${Object.keys(res.tabs).length} tabs`
  })

  await check('LIBRARY.13', `${width} px: editor: headings, bold, checklists and [[links]] render; Cmd-B; the / menu inserts a table; a pasted image shows; Show Markdown; no Edit or Done`, async () => {
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

  await check('LIBRARY.14', `${width} px: conflict: an agent edits the open page; typing then saving shows the conflict and nothing is lost`, async () => {
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

  await check('LIBRARY.15', `${width} px: wiki rules: the agent cannot edit My notes or the rules page; a stale version is a conflict; Undo restores and logs Reverted; Keep in My notes stops the agent`, async () => {
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

  await check('LIBRARY.16', `${width} px: Health lists a broken [[link]] and an orphan page`, async () => {
    const p = await s.api('wiki.create_page', { space: SPACE, title: `S4 orphan ${width} ${stamp}`, summary: 'An orphan', content_md: `Points to [[S4 nowhere ${width} ${stamp}]].` })
    await s.open('/life/library/notes?view=health')
    await pg.locator('[data-health-refresh]').click()
    await pg.waitForTimeout(1500)
    must((await pg.locator('[data-health="orphans"]').innerText()).includes(`S4 orphan ${width} ${stamp}`), 'the orphan is not under Health')
    must((await pg.locator('[data-health="broken"]').innerText()).includes(`S4 nowhere ${width} ${stamp}`), 'the broken link is not under Health')
    must(p.name, '')
  })

  await check('LIBRARY.17', `${width} px: Library's tabs are Everything, Notes, Documents, People and Chats; each opens from its tab and its path`, async () => {
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

  await check('LIBRARY.18', `${width} px: Library > Notes: the assistant's notes carry "Kept by the assistant" with the rules on top; Written by me leaves them out; the Changes view shows a diff and Undo restores; Health lists an orphan`, async () => {
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
    await s.open('/life/library/notes?view=list&by=assistant')
    must(new URL(pg.url()).pathname === '/life/library/notes' && new URL(pg.url()).searchParams.get('by') === 'assistant', `the assistant's notes went to ${pg.url()}`)
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
  await s.ctx.close()
}

await check('LIBRARY.19', 'A Vault document is a capture of kind Document, marked sensitive, with its expiry; the agent cannot read it, nor a note marked sensitive, while the switch is off; only the owner unmarks', async () => {
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


// Issue 23: Library > Everything. Records titled "I23 ". Moved or changed rows are put back after.
for (const width of WIDTHS) {
  const tag = `I23.${width}`
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
    await check('LIBRARY.20', `${width} px: on an empty space the Library says what will appear and offers + Capture; People says the same`, async () => {
      bench(`frappe.db.sql("update \`tabLife Index\` set space = %s where space = %s and ref_doctype in ('Life Note', 'Life Vault Document', 'Life Chat Log', 'Life Inbox Item')", ("zz-i23-aside-${width}", "${SPACE}"))
frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("zz-i23-aside-${width}", "${SPACE}"))`)
      try {
        // People has its own screen and its own empty state since issue 25 (checked by I25.7)
        for (const p of ['/life/library']) {
          await openLib(p)
          must(await pg.locator('[data-lib-empty]').isVisible(), `no empty state at ${p}`)
          const t = await pg.locator('[data-lib-empty]').innerText()
          must(t.includes('will show up here') && t.includes('Chat'), 'the empty state says: ' + t)
          must(await pg.locator('[data-lib-capture]').isVisible(), 'no Chat button')
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
    await check('LIBRARY.21', `${width} px: Everything shows notes, documents, people and chats together, newest first, with the right kind and line`, async () => {
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
    await check('LIBRARY.22', `${width} px: each tab shows only its kind`, async () => {
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
    await check('LIBRARY.23', `${width} px: search finds a note by a word in its body and the Area filter narrows the list`, async () => {
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
    await check('LIBRARY.24', `${width} px: a sensitive document shows 🔒 and opens for the owner; the agent, with the Vault closed, never gets it`, async () => {
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
    await check('LIBRARY.25', `${width} px: Trash and archive opens the old archive`, async () => {
      await openLib()
      await pg.locator('[data-place-link="archive"]').click()
      await pg.waitForURL(/\/life\/library\/archive/, { timeout: 8000 })
      await pg.waitForLoadState('networkidle')
      must(await pg.locator('[data-main] h1').first().isVisible(), 'the archive shows nothing')
      must((await pg.locator('[data-place-tabs]').first().getAttribute('data-tab-current')) === 'archive', 'the archive is not the open page')
      must(await pg.locator('[data-place-link="timeline"]').count() === 1 && await pg.locator('[data-place-link="graph"]').count() === 1, 'Timeline and Graph links are missing')
    })
    await check('LIBRARY.26', `${width} px: ${phone ? 'rows stack and the tabs scroll sideways inside their bar, not the page' : 'a row has its title, area and date side by side; the tabs fit'}`, async () => {
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
for (const width of WIDTHS) {
  const tag = `I24.${width}`
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
    await check('LIBRARY.27', `${width} px: a file used by two items is listed once, with both under Used in`, async () => {
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
    await check('LIBRARY.28', `${width} px: a file with 2 versions shows "2 versions" and opens either`, async () => {
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
    await check('LIBRARY.29', `${width} px: the type filter shows only slides when Slides is chosen`, async () => {
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
    await check('LIBRARY.30', `${width} px: a user who cannot see any record using a file does not see the file`, async () => {
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
    await check('LIBRARY.31', `${width} px: ${phone ? 'at 390 px the list is one column' : 'a row has its name, Used in and the buttons side by side'}`, async () => {
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
    await check('LIBRARY.32', `${width} px: with no files the screen says what will appear and offers + Capture; a search with no match says so`, async () => {
      const aside = JSON.parse(bench(`import json
rows = frappe.db.sql("select name, attached_to_doctype from \`tabFile\` where attached_to_doctype in ('Life Inbox Item', 'Life Note', 'Life Vault Document', 'Life Chat Log')", as_dict=True)
frappe.db.sql("update \`tabFile\` set attached_to_doctype = concat('zz ', attached_to_doctype) where attached_to_doctype in ('Life Inbox Item', 'Life Note', 'Life Vault Document', 'Life Chat Log')")
frappe.db.commit()
print(json.dumps(rows))`).split('\n').pop())
      try {
        await openFiles()
        must(await pg.locator('[data-files-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-files-empty]').innerText()
        must(t.includes('will show up here') && t.includes('Chat'), 'the empty state says: ' + t)
        must(await pg.locator('[data-files-capture]').isVisible(), 'no Chat button')
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
for (const width of WIDTHS) {
  const tag = `I25.${width}`
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
    await check('LIBRARY.33', `${width} px: People lists persons and organisations; filtering by kind works`, async () => {
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
    await check('LIBRARY.34', `${width} px: a person page lists the notes and tasks that mention them, newest first`, async () => {
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
    await check('LIBRARY.35', `${width} px: an organisation page lists its people`, async () => {
      await openPerson(ids.org)
      const names = await pg.locator('[data-org-person]').evaluateAll((els) => els.map((e) => e.dataset.name).sort())
      must(JSON.stringify(names) === JSON.stringify([ids.asha, ids.ravi].sort()), 'the organisation lists ' + names.join())
      await pg.locator(`[data-org-person][data-name="${ids.asha}"] a`).click()
      await pg.waitForFunction((n) => location.pathname.endsWith('/library/people/' + n), ids.asha, { timeout: 8000 })
      await pg.locator('[data-person-org]').waitFor({ timeout: 8000 })
      must((await pg.locator('[data-person-org]').innerText()).includes(T('Acme Ltd')), 'the person page does not name the organisation')
    })
    await check('LIBRARY.36', `${width} px: ${phone ? 'at 390 px the person page is one column' : 'the facts sit beside the text and mentions'}`, async () => {
      await openPerson(ids.asha)
      await noSideways()
      const box = async (sel) => { const b = await pg.locator(sel).first().boundingBox(); must(b, sel + ' is not visible'); return b }
      const [who, mentions, facts] = [await box('[data-person-who]'), await box('[data-person-mentions]'), await box('[data-person-facts]')]
      for (const b of [who, mentions, facts]) must(b.x >= 0 && b.x + b.width <= width + 1, `part of the page is outside the ${width} px screen`)
      if (phone) must(Math.abs(who.x - facts.x) < 2 && facts.y > mentions.y && mentions.y > who.y, 'the page is not one column')
      else must(facts.x > who.x + who.width - 2 && Math.abs(facts.y - who.y) < 40, 'the facts are not beside the text')
    })
    await check('LIBRARY.37', `${width} px: with no people the screen says what will appear and offers + Capture`, async () => {
      bench(`frappe.db.sql("update \`tabLife Person\` set space = %s where space = %s", ("zz-i25-aside-${width}", "${SPACE}"))`)
      try {
        await openPeople()
        must(await pg.locator('[data-people-empty]').isVisible(), 'no empty state')
        const t = await pg.locator('[data-people-empty]').innerText()
        must(t.includes('will show up here') && t.includes('Chat'), 'the empty state says: ' + t)
        must(await pg.locator('[data-people-capture]').isVisible(), 'no Chat button')
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


// Issue 72: a photo of a journal page, captured from the phone, becomes a note in My notes: the photo attached, the Brain's
// transcript as its text, the page date, the area and goal it was filed to. It is found by search and shows on its goal's page.
{
  const s = await session('owner@lifeos.test', 390)
  const pg = s.page
  const name = `journal-i72-${stamp}.png`
  let item = null
  let note = null
  try {
    await check('LIBRARY.38', '390 px: a photo of a journal page captured from the phone becomes a note with the photo, the transcript and its date; search finds it and its goal shows it', async () => {
      await s.open('/life')
      await pg.locator('[data-chat-bar] [data-ask-camera-input]').setInputFiles({ name, mimeType: 'image/png', buffer: await pg.screenshot() })
      await pg.locator('[data-ask-sheet] [data-ask-input]').fill('transcribe and update my journal')
      await pg.locator('[data-ask-sheet] [data-ask-send]').click()
      await pg.waitForTimeout(3500)
      item = bench(`print(frappe.db.get_value("Life Inbox Item", {"title": "${name}"}, "name"))`).split('\n').pop()
      must(item && item !== 'None', 'the capture was not made')
      runAgent() // the fake AI reads the photo
      const got = await owner.api('inbox.get', { item })
      must(got.source_type === 'Journal Photo' && got.transcript_md.includes('MoneyOS'), 'the Brain did not transcribe the photo')
      const page = got.proposals.find((p) => p.kind === 'Journal Page')
      must(page, 'no journal page proposal')
      for (const p of got.proposals.filter((x) => x !== page)) await owner.api('review.decide', { proposal: p.name, decision: 'reject' })
      await owner.api('review.decide', { proposal: page.name, decision: 'accept', payload: { ...page.payload, area: uxArea, goal: ux.goal } })
      note = (await owner.api('inbox.get', { item })).proposals.find((p) => p.kind === 'Journal Page').created_name
      const n = await owner.api('library.get', { note })
      must(n.collection === 'My notes' && n.page_date === today && n.content_md.includes('MoneyOS') && n.inbox_item === item, 'the note is not the page: ' + JSON.stringify({ c: n.collection, d: n.page_date }))
      must(n.area === uxArea && n.goal === ux.goal, 'the note was not filed to the chosen area and goal')
      must(n.image && (await pg.request.get(base + n.image)).ok(), 'the photo is not attached')
      // found by a word of the transcript
      // the index is written by a background job a moment after the save, so ask again for up to 30 seconds
      let found = false
      for (let i = 0; i < 30 && !found; i++) {
        found = (await owner.api('search.query', { text: 'MoneyOS', space: SPACE, limit: 100 })).results.some((r) => r.ref_name === note)
        if (!found) await pg.waitForTimeout(1000)
      }
      must(found, 'search does not find the page by a word of its transcript')
      // listed in Library > Notes, and on its goal's page
      await s.open('/life/library/notes?view=list&all=1')
      await pg.getByText(n.title).filter({ visible: true }).first().waitFor({ timeout: 15000 })
      const onGoal = await owner.api('library.list', { space: SPACE, goal: ux.goal, page_length: 100 })
      must(onGoal.notes.some((r) => r.name === note), "the page is not among its goal's notes")
      await s.open(`/life/goals/${ux.goal}?tab=notes`)
      await pg.getByText(n.title).filter({ visible: true }).first().waitFor({ timeout: 15000 })
      return `note ${note}`
    })
  } finally {
    bench(`frappe.set_user("Administrator")
for dt, n in (("Life Note", "${note || ''}"), ("Life Inbox Item", "${item || ''}")):
    if n and frappe.db.exists(dt, n): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Search covers the whole app (issue 98): Frappe's Global Search, screens by name, and Chat without a key
{
  const subject = `RSH Global ${stamp}`
  const event = bench(`ev = frappe.get_doc({"doctype": "Event", "subject": "${subject}", "starts_on": frappe.utils.today() + " 16:00:00", "event_type": "Private", "life_space": "Private"}).insert(ignore_permissions=True)
frappe.db.commit()
print(ev.name)`).split('\n').pop()
  const pg = owner.page
  // the index is written by a background job a moment after the save: wait until search finds the event
  for (let i = 0; i < 30; i++) {
    const r = await owner.api('search.query', { text: `rsh ${stamp}`, limit: 5 })
    if (r.results.some((x) => x.ref_name === event)) break
    await owner.page.waitForTimeout(1000)
  }
  const palette = async (text) => {
    await owner.open('/life/today')
    await pg.keyboard.press('/')
    await pg.locator('input[aria-label="Search or chat"]').fill(text)
    await pg.waitForTimeout(1200)
  }
  try {
    await check('LIBRARY.39', '1440 px: search finds a calendar event by the start of a word, under Events, and Enter opens its drawer', async () => {
      await palette(`rsh ${stamp}`)
      const group = pg.locator('[data-search-group="Events"]')
      must(await group.count() === 1 && (await group.innerText()).includes(subject), 'the event is not under Events')
      await pg.keyboard.press('Enter')
      await pg.waitForTimeout(1200)
      must(new URL(pg.url()).searchParams.get('open') === `event:${event}`, `Enter did not open the event: ${pg.url()}`)
      must((await pg.locator('[data-pane-title]').innerText()).includes(subject), 'the drawer shows another record')
    })
    await check('LIBRARY.40', '1440 px: "ai key" offers Settings › AI and Enter opens it', async () => {
      await palette('ai key')
      must((await pg.locator('[data-search-screen]').first().innerText()).includes('Settings › AI'), 'Settings › AI is not offered')
      await pg.keyboard.press('Enter')
      await pg.waitForTimeout(1200)
      const u = new URL(pg.url())
      must(u.pathname === '/life/settings' && u.searchParams.get('tab') === 'advanced' && u.searchParams.get('part') === 'ai', `Enter went to ${pg.url()}`)
    })
    await check('LIBRARY.41', '1440 px: with no AI key, Chat says it needs one, links to Settings › AI, and shows what search finds for the same words', async () => {
      bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = None; s.save()')
      try {
        await palette(`rsh ${stamp}`)
        await pg.locator('[data-search-ask]').click()
        await pg.locator('[data-refusal="not_set_up"]').waitFor({ timeout: 15000 })
        must((await pg.locator('[data-ask-refusal]').innerText()).includes('Chat needs an AI key. Add one in Settings › AI.'), 'the key message is not shown')
        must((await pg.locator('[data-ask-key-link]').getAttribute('href')).includes('part=ai'), 'the link does not go to Settings › AI')
        must((await pg.locator('[data-ask-search-hits]').innerText()).includes(subject), 'the search result is not under the message')
      } finally {
        bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()')
      }
    })
  } finally {
    bench(`frappe.delete_doc("Event", "${event}", force=1, ignore_permissions=True)`)
  }
}


// ---- pages that build themselves (issue 111): a page for every person, company and part, with a brief, a timeline and pins ----
{
  const T = `Ambaji ${stamp}`
  const seeded = JSON.parse(bench(`import json
from lifeos.library import subjects
sp = "${SPACE}"
career = frappe.db.get_value("Life Area", {"space": sp, "area_name": "Career", "parent_area": ("is", "not set")})
part = frappe.get_doc({"doctype": "Life Area", "space": sp, "area_name": "BTW ${stamp}", "parent_area": career, "is_on": 1}).insert(ignore_permissions=True).name
org = frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": "${T} Food Products", "kind": "Organisation", "status": "Prospect", "area": part}).insert(ignore_permissions=True).name
people = [frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": f"${T} Contact {i}", "kind": "Person", "organisation": org, "email": f"c{i}-${stamp}@ambaji.example", "role": "Buyer"}).insert(ignore_permissions=True).name for i in (1, 2)]
emails = []
for i in range(1, 5):
    it = frappe.get_doc({"doctype": "Life Inbox Item", "space": sp, "title": f"${T} email {i}", "source_type": "Email", "status": "Done", "raw_text": f"Email {i} about the blueprint, quote 4.2 lakh.", "received_on": frappe.utils.add_days(frappe.utils.now_datetime(), -i)}).insert(ignore_permissions=True).name
    emails.append(it)
    subjects.link(sp, "Life Inbox Item", it, "Life Person", org)
for i in range(1, 4):
    frappe.get_doc({"doctype": "File", "file_name": f"${T}-file-{i}.txt", "content": f"file {i}", "attached_to_doctype": "Life Inbox Item", "attached_to_name": emails[0], "is_private": 1}).insert(ignore_permissions=True)
brief = " ".join(f"The ${T} thread {i} is about the blueprint. [{i}]" for i in (1, 2, 3))
frappe.db.set_value("Life Person", org, {"brief_md": brief, "brief_on": frappe.utils.now_datetime(), "brief_sources": json.dumps([{"n": i, "doctype": "Life Inbox Item", "name": emails[i - 1], "kind": "Email", "title": f"${T} email {i}", "date": str(frappe.utils.today()), "url": None, "ref": "source:" + emails[i - 1]} for i in (1, 2, 3)])})
frappe.get_doc({"doctype": "Life Task", "space": sp, "title": "${T} send the quote", "status": "Open", "inbox_item": emails[0]}).insert(ignore_permissions=True)
print(json.dumps({"org": org, "people": people, "emails": emails, "part": part}))`).split('\n').pop())
  const PAGE = `/life/library/pages/Life%20Person/${seeded.org}`
  const pinsOf = async () => (await owner.api('pages.pinned')).pins
  try {
    for (const width of WIDTHS) {
      const u = await session('owner@lifeos.test', width)
      const pg = u.page
      const phone = width < 800
      const problems = []
      pg.on('pageerror', (e) => problems.push(String(e).slice(0, 160)))
      const sideways = () => pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      await owner.api('pages.unpin', { doctype: 'Life Person', name: seeded.org }).catch(() => {})
      for (const p of await pinsOf()) await owner.api('pages.unpin', { doctype: p.doctype, name: p.name })

      await check('LIBRARY.42', `${width} px: a company page shows its header with the status and part, the brief with source numbers, Open, People, Files, Timeline and Your notes; a source number opens its email`, async () => {
        await u.open(PAGE)
        await pg.locator('[data-library-page][data-loaded="1"]').waitFor({ timeout: 15000 })
        const head = await pg.locator('[data-page-header]').innerText()
        must(head.includes(`${T} Food Products`) && head.includes('Prospect') && head.includes(`Career › BTW ${stamp}`), 'the header says: ' + head.replace(/\s*\n\s*/g, ' | '))
        must(await pg.locator('[data-page-icon]').isVisible(), 'no kind icon')
        must((await pg.locator('[data-brief-source]').count()) === 3, 'the brief has no three source numbers')
        must(/by the Brain · as of .* · 3 sources/.test(await pg.locator('[data-brief-by]').innerText()), 'the brief does not say who wrote it')
        must(await pg.locator('[data-brief-rewrite]').isVisible(), 'no Rewrite button')
        must((await pg.locator('[data-page-open] [data-open-task]').innerText()).includes('send the quote'), 'Open does not list the linked task')
        must((await pg.locator('[data-page-people] [data-page-person]').count()) === 2, 'People does not list the two people')
        must((await pg.locator('[data-page-files] [data-page-file]').count()) === 3, 'Files does not list the three files')
        must((await pg.locator('[data-page-timeline] [data-timeline-row]', { hasText: / email \d/ }).count()) === 4, 'the Timeline does not list the four emails')  // LIBRARY.43 at the first width links one more, "email new"
        must(await pg.locator('[data-page-timeline] [data-timeline-row][data-kind="Email"] .lucide-mail').first().isVisible(), 'a timeline line has no kind icon')
        must(await pg.locator('[data-page-notes] [data-notes-input]').isVisible(), 'no Your notes')
        await pg.locator('[data-brief-source][data-n="2"]').click()
        await pg.waitForFunction((n) => new URL(location.href).searchParams.get('open') === `source:${n}`, seeded.emails[1], { timeout: 8000 })
        must(await sideways() <= 1, 'the page scrolls sideways')
      })

      await check('LIBRARY.43', `${width} px: Pin puts the page in the sidebar with the company icon, a new link shows "· 1" until the page is opened, and dragging reorders the pins`, async () => {
        await u.open(PAGE)
        await pg.locator('[data-page-pin]').click()
        await pg.waitForFunction(() => document.querySelector('[data-page-pin]')?.innerText.includes('Pinned'), null, { timeout: 8000 })
        must((await pinsOf()).some((p) => p.name === seeded.org), 'the pin was not saved')
        const second = seeded.people[0]
        await owner.api('pages.pin', { doctype: 'Life Person', name: second })
        // a new item is linked: the count shows on the pin until the page is opened
        bench(`from lifeos.library import subjects
it = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T} email new", "source_type": "Email", "status": "Done", "raw_text": "new"}).insert(ignore_permissions=True).name
subjects.link("${SPACE}", "Life Inbox Item", it, "Life Person", "${seeded.org}")`)
        await u.open('/life/today')
        if (phone) {
          await u.open('/life/library/pages')
          const pin = pg.locator(`[data-pinned-pages="phone"] [data-pin][data-pin-name="${seeded.org}"]`)
          await pin.waitFor({ timeout: 10000 })
          must((await pin.getAttribute('data-pin-kind')) === 'company', 'the pin has no company kind')
          must((await pin.locator('[data-pin-count]').innerText()).includes('· 1'), 'the pin does not show "· 1"')
          return
        }
        const pin = pg.locator(`[data-sidebar] [data-pin][data-pin-name="${seeded.org}"]`)
        await pin.waitFor({ timeout: 10000 })
        must((await pin.getAttribute('data-pin-kind')) === 'company' && (await pin.locator('.lucide-building-2').count()) === 1, 'the pin has no company icon')
        must(!(await pg.locator('[data-sidebar] [data-pin-group]').count()), 'the pins have group headings')
        must((await pin.locator('[data-pin-count]').innerText()).includes('· 1'), 'the pin does not show "· 1": ' + (await pin.innerText()))
        await pin.click()
        await pg.locator('[data-library-page][data-loaded="1"]').waitFor({ timeout: 15000 })
        await pg.waitForTimeout(800)
        await u.open('/life/today')
        await pg.locator(`[data-sidebar] [data-pin][data-pin-name="${seeded.org}"]`).waitFor({ timeout: 10000 })
        must(!(await pg.locator(`[data-sidebar] [data-pin][data-pin-name="${seeded.org}"] [data-pin-count]`).count()), 'opening the page did not clear the count')
        const names = () => pg.locator('[data-sidebar] [data-pin]').evaluateAll((els) => els.map((e) => e.getAttribute('data-pin-name')))
        must(JSON.stringify(await names()) === JSON.stringify([seeded.org, second]), 'the pins are in another order: ' + JSON.stringify(await names()))
        await pg.locator(`[data-sidebar] [data-pin][data-pin-name="${second}"]`).dragTo(pg.locator(`[data-sidebar] [data-pin][data-pin-name="${seeded.org}"]`))
        await pg.waitForTimeout(800)
        must(JSON.stringify((await pinsOf()).map((p) => p.name)) === JSON.stringify([second, seeded.org]), 'dragging did not reorder the pins: ' + JSON.stringify((await pinsOf()).map((p) => p.name)))
      })

      await check('LIBRARY.44', `${width} px: Library > Pages is the first section, filters by kind and by status, and lists the seeded pages`, async () => {
        await u.open('/life/library/pages')
        await pg.locator('[data-library-pages][data-loaded="1"]').waitFor({ timeout: 15000 })
        const tabs = await pg.locator('[data-place-tabs] [role="tab"], [data-place-tabs] button').allInnerTexts()
        must(tabs[0]?.trim().startsWith('Pages'), 'Pages is not the first section: ' + tabs.join(' | '))
        const rows = () => pg.locator('[data-pages-row]').evaluateAll((els) => els.map((e) => ({ name: e.dataset.name, kind: e.dataset.kind, status: e.dataset.status })))
        const has = async (n) => (await rows()).some((r) => r.name === n)
        must((await has(seeded.org)) && (await has(seeded.people[0])) && (await has(seeded.part)), 'the seeded company, person and part are not listed')
        await pg.locator('[data-pages-kind="company"]').click()
        await pg.waitForFunction(() => { const r = [...document.querySelectorAll('[data-pages-row]')]; return r.length > 0 && r.every((e) => e.dataset.kind === 'company') }, null, { timeout: 8000 })
        must((await has(seeded.org)) && !(await has(seeded.people[0])), 'the Companies filter is wrong')
        await u.open('/life/library/pages?status=Prospect')
        await pg.locator('[data-library-pages][data-loaded="1"]').waitFor()
        must((await has(seeded.org)) && (await rows()).every((r) => r.status === 'Prospect'), 'the Prospect filter is wrong')
        await u.open('/life/library/pages?status=Client')
        await pg.locator('[data-library-pages][data-loaded="1"]').waitFor()
        must(!(await has(seeded.org)), 'the Client filter lists a Prospect')
        must(await sideways() <= 1, 'the list scrolls sideways')
      })

      await check('LIBRARY.45', `${width} px: Your notes takes text, and a brief rewrite afterwards leaves it unchanged`, async () => {
        await u.open(PAGE)
        await pg.locator('textarea[data-notes-input], [data-notes-input] textarea').first().fill(`My own note ${stamp} ${width}`)
        await pg.locator('[data-notes-save]').click()
        await pg.locator('[data-note-text]', { hasText: `My own note ${stamp} ${width}` }).waitFor({ timeout: 8000 })
        const was = await pg.locator('[data-note-text]').allInnerTexts()
        await owner.api('pages.rewrite', { doctype: 'Life Person', name: seeded.org }).catch(() => null)
        await u.open(PAGE)
        await pg.locator('[data-note-text]').first().waitFor({ timeout: 8000 })
        const after = await pg.locator('[data-note-text]').allInnerTexts()
        must(JSON.stringify(after) === JSON.stringify(was), `a brief rewrite changed Your notes: ${JSON.stringify(was)} became ${JSON.stringify(after)}`)
        const byAgents = Number(bench(`print(frappe.db.count("Comment", {"reference_doctype": "Life Person", "reference_name": "${seeded.org}", "comment_type": "Comment", "comment_email": ["!=", "owner@lifeos.test"]}))`).replace(/\D/g, '') || 0)
        must(byAgents === 0, 'someone other than the owner wrote a note')
      })

      await check('LIBRARY.46', `${width} px: the page, the list and a pin in light and dark: no script error, nothing cut off; on a phone the pins are at the top of Library`, async () => {
        await owner.api('pages.pin', { doctype: 'Life Person', name: seeded.org })
        for (const scheme of ['light', 'dark']) {
          await pg.emulateMedia({ colorScheme: scheme })
          for (const p of [PAGE, '/life/library/pages']) {
            await u.open(p)
            await pg.waitForTimeout(500)
            must(await sideways() <= 1, `${scheme}: ${p} scrolls sideways`)
          }
        }
        await pg.emulateMedia({ colorScheme: 'light' })
        if (phone) {
          await u.open('/life/library/pages')
          const strip = pg.locator('[data-pinned-pages="phone"]')
          await strip.waitFor({ timeout: 8000 })
          const top = await strip.evaluate((e) => e.getBoundingClientRect().top)
          const list = await pg.locator('[data-library-pages]').evaluate((e) => e.getBoundingClientRect().top)
          must(top < list, 'the pins are not at the top of Library')
        }
        must(!problems.length, 'script errors: ' + problems.join(' | '))
      })

      await check('LIBRARY.47', `${width} px: on an empty space Pages says what will appear and offers + Capture`, async () => {
        bench(`if not frappe.db.exists("Life Space", "zz-pages-empty"):
    frappe.get_doc({"doctype": "Life Space", "space_name": "zz-pages-empty", "owner_user": "owner@lifeos.test", "members": [{"user": "owner@lifeos.test", "access": "Write"}]}).insert(ignore_permissions=True)`)
        try {
          await pg.evaluate(() => localStorage.setItem('lifeos-space', 'zz-pages-empty'))
          await u.open('/life/library/pages')
          await pg.locator('[data-pages-empty]').waitFor({ timeout: 15000 })
          const text = await pg.locator('[data-pages-empty]').innerText()
          must(text.includes('No pages yet.') && text.includes('Chat'), 'the empty state says: ' + text)
          must(await pg.locator('[data-pages-capture]').isVisible(), 'no Chat button')
        } finally {
          await pg.evaluate(() => localStorage.setItem('lifeos-space', 'Private'))
        }
      })
      await u.ctx.close()
    }
  } finally {
    bench(`frappe.set_user("Administrator")
for dt, f in (("Life Person", "full_name"), ("Life Inbox Item", "title"), ("Life Task", "title")):
    for n in frappe.get_all(dt, filters={f: ["like", "${T}%"]}, pluck="name"):
        frappe.db.delete("Life Link", {"from_doctype": dt, "from_name": n})
        frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Area", filters={"area_name": "BTW ${stamp}"}, pluck="name"):
    frappe.delete_doc("Life Area", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Pin")
frappe.db.delete("Life Page Visit")
from lifeos.tools import devtools
devtools.purge_space("zz-pages-empty", drop=True)`)
  }
}

// ---- the Drawer's person layer (issue 128) ----
{
  const T = `I128 Person ${stamp}`
  const seeded = JSON.parse(bench(`import json
from lifeos.library import subjects
sp = "${SPACE}"
org = frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": "${T} Foods", "kind": "Organisation", "status": "Prospect"}).insert(ignore_permissions=True).name
people = [frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": f"${T} Contact {i}", "kind": "Person", "organisation": org, "email": f"c{i}-${stamp}@i128.example", "role": "Buyer"}).insert(ignore_permissions=True).name for i in (1, 2)]
task = frappe.get_doc({"doctype": "Life Task", "space": sp, "title": "${T} send the quote", "status": "Open"}).insert(ignore_permissions=True).name
subjects.link(sp, "Life Task", task, "Life Person", org)
lone = frappe.get_doc({"doctype": "Life Person", "space": sp, "full_name": "${T} Alone", "kind": "Person"}).insert(ignore_permissions=True).name
print(json.dumps({"org": org, "people": people, "task": task, "lone": lone}))`).split('\n').pop())
  try {
    for (const width of WIDTHS) {
      const u = await session('owner@lifeos.test', width)
      const pg = u.page
      const errors = []
      pg.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
      try {
        await check('LIBRARY.49', `${width} px: person: shows a company's people and mentions, a person opens on top of it with Back, and a person with nothing says what will appear`, async () => {
          await u.open(`/life/today?open=person:${seeded.org}`)
          await pg.locator('[data-person-pane]').waitFor({ timeout: 15000 })
          must((await pg.locator('[data-pane-title]').innerText()).includes('Foods'), 'the title is not the company')
          must(await pg.locator('[data-person-people] [data-person-row]').count() === 2, 'the company does not list its two people')
          must(await pg.locator('[data-person-mention]').count() >= 1, 'the mentions are missing')
          must((await pg.locator('[data-pane-full]').getAttribute('href') || '').includes(`/library/pages/Life%20Person/${seeded.org}`) || (await pg.locator('[data-pane-full]').getAttribute('href') || '').includes(seeded.org), 'Open full page does not go to the company')
          await pg.locator('[data-person-people] [data-person-row] button').first().click()
          await pg.waitForFunction((p) => new URL(location.href).searchParams.get('open') === `person:${p}`, seeded.people[0], { timeout: 8000 })
          must(new URL(pg.url()).searchParams.get('under') === `person:${seeded.org}`, 'the company is not the layer under')
          await pg.locator('[data-pane-back]').first().click()
          await pg.waitForFunction((o) => new URL(location.href).searchParams.get('open') === `person:${o}`, seeded.org, { timeout: 8000 })
          await u.open(`/life/today?open=person:${seeded.lone}`)
          await pg.locator('[data-person-pane]').waitFor({ timeout: 15000 })
          must((await pg.locator('[data-person-pane]').innerText()).includes('No brief yet.'), 'the empty person does not say what will appear')
          must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
          must(!errors.length, 'script errors: ' + errors.join(' | '))
        })
      } finally {
        await u.ctx.close()
      }
    }
  } finally {
    bench(`frappe.set_user("Administrator")
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "${T}%"]}, pluck="name"):
    frappe.db.delete("Life Link", {"to_doctype": "Life Person", "to_name": n})
    frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Task", filters={"title": ["like", "${T}%"]}, pluck="name"):
    frappe.db.delete("Life Link", {"from_doctype": "Life Task", "from_name": n})
    frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)`)
  }
}

// Issue 130: a person's layer shows what they owe you and what you owe them.
for (const width of WIDTHS) {
  const u = await session('owner@lifeos.test', width)
  const pg = u.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
  try {
    const seeded = JSON.parse(bench(`import json
from frappe.utils import add_days, today
for n in frappe.get_all("Life Task", filters={"title": ["like", "I130L %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I130L"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
p = frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Vivek I130L", "kind": "Person"}).insert(ignore_permissions=True)
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I130L ITR draft", "status": "Waiting", "waiting_on": p.full_name, "waiting_on_person": p.name, "check_by": add_days(today(), 2)}).insert(ignore_permissions=True)
m = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I130L Sign the mandate", "status": "Open", "notes_md": "With [[Vivek I130L]]"}).insert(ignore_permissions=True)
print(json.dumps({"person": p.name, "task": t.name, "mine": m.name}))`).split('\n').pop())
    await check('LIBRARY.50', `${width} px: a person's layer shows "What they owe you" with the ITR draft and "What you owe them"`, async () => {
      await u.open(`/life/today?open=person:${seeded.person}`)
      await pg.locator('[data-person-owed]').waitFor({ timeout: 15000 })
      must((await pg.locator('[data-person-owe-me]').innerText()).includes('What they owe you') && (await pg.locator('[data-person-owe-me]').innerText()).includes('I130L ITR draft'), 'the person does not owe the ITR draft: ' + await pg.locator('[data-person-owed]').innerText())
      must((await pg.locator('[data-person-i-owe]').innerText()).includes('What you owe them'), 'what you owe them is missing')
      await pg.locator('[data-person-owe-me] [data-person-owe-row] button').first().click()
      await pg.waitForFunction((t) => new URL(location.href).searchParams.get('open') === `task:${t}`, seeded.task, { timeout: 8000 })
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      must(!errors.length, 'script errors: ' + errors.join(' | '))
    })
  } finally {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "I130L %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I130L"]}, pluck="name"):
    frappe.db.delete("Life Link", {"to_doctype": "Life Person", "to_name": n})
    frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)`)
    await u.ctx.close()
  }
}

// Issue 136: one searchable person picker for Delegated to, Waiting on (person) and Hand off's Who: people only, the company under each name, searched by company too.
for (const width of WIDTHS) {
  const u = await session('owner@lifeos.test', width)
  const pg = u.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
  const phone = width < 768
  // opens a picker, types a search and waits for the list: a popover on a desktop, a sheet with the search focused on a phone
  const openPicker = async (root, text = '') => {
    await root.locator(phone ? '[data-person-open]' : 'button').first().click()
    const search = phone ? pg.locator('[data-person-search] input, input[data-person-search]').first() : pg.locator('[data-slot="content"] input[data-slot="input"]').last()
    if (phone) must(await search.evaluate((el) => el === document.activeElement), 'the search is not focused in the sheet')
    if (text) await search.fill(text)
    await pg.waitForTimeout(600)
    return search
  }
  const optionNames = async () => phone ? (await pg.locator('[data-person-option]').allInnerTexts()) : (await pg.locator('[data-slot="item"]').allInnerTexts())
  try {
    const seeded = JSON.parse(bench(`import json
for n in frappe.get_all("Life Task", filters={"title": ["like", "I136 %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I136"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
org = frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Linc pens I136", "kind": "Organisation"}).insert(ignore_permissions=True)
other = frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Hartwell Tea I136", "kind": "Organisation"}).insert(ignore_permissions=True)
ravi = frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Ravi Singh I136", "kind": "Person", "organisation": org.name}).insert(ignore_permissions=True)
asha = frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Asha Mehta I136", "kind": "Person"}).insert(ignore_permissions=True)
t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "I136 Send the samples", "status": "Open"}).insert(ignore_permissions=True)
print(json.dumps({"task": t.name, "ravi": ravi.name, "asha": asha.name}))`).split('\n').pop())
    const root = () => pg.locator('[data-task-delegated]')
    await check('LIBRARY.51', `${width} px: Delegated to is a searchable list of people only, the company under each name; Linc leaves Linc pens' people; picking saves, × clears`, async () => {
      await u.open(`/life/today?open=task:${seeded.task}`)
      await root().waitFor({ timeout: 15000 })
      await openPicker(root())
      let names = (await optionNames()).join('\n')
      must(names.includes('Ravi Singh I136') && names.includes('Linc pens I136'), 'Ravi does not show his company: ' + names)
      must(!names.includes('Hartwell Tea I136'), 'a company is in the list: ' + names)
      const search = phone ? pg.locator('[data-person-search] input, input[data-person-search]').last() : pg.locator('[data-slot="content"] input[data-slot="input"]').last()
      await search.fill('Linc')
      await pg.waitForTimeout(800)
      names = await optionNames()
      must(names.some((n) => n.includes('Ravi Singh I136')) && !names.some((n) => n.includes('Asha Mehta')), 'Linc does not leave only its people: ' + names.join(' | '))
      await (phone ? pg.locator('[data-person-option]') : pg.locator('[data-slot="item"]')).filter({ hasText: 'Ravi Singh I136' }).first().click()
      await pg.waitForFunction(() => document.querySelector('[data-task-delegated]')?.innerText.includes('Ravi Singh I136'), null, { timeout: 8000 })
      must((await bench(`print(frappe.db.get_value("Life Task", "${seeded.task}", "delegated_to"))`).trim().split('\n').pop()) === seeded.ravi, 'Delegated to was not saved')
      await root().locator('[data-person-clear]').click()
      await pg.waitForFunction(() => !document.querySelector('[data-task-delegated] [data-person-clear]'), null, { timeout: 8000 })
      must((await bench(`print(frappe.db.get_value("Life Task", "${seeded.task}", "delegated_to"))`).trim().split('\n').pop()) === 'None', '× did not clear Delegated to')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      must(!errors.length, 'script errors: ' + errors.join(' | '))
    })
    await check('LIBRARY.52', `${width} px: a new name offers "Add '…' as a person"; choosing it makes the person and selects them`, async () => {
      await u.open(`/life/today?open=task:${seeded.task}`)
      await root().waitFor({ timeout: 15000 })
      await openPicker(root(), 'Zubin Karanja I136')
      const add = (phone ? pg.locator('[data-person-option]') : pg.locator('[data-slot="item"]')).filter({ hasText: "Add 'Zubin Karanja I136' as a person" })
      must(await add.count() === 1, 'no Add as a person: ' + (await optionNames()).join(' | '))
      await add.click()
      await pg.waitForFunction(() => document.querySelector('[data-task-delegated]')?.innerText.includes('Zubin Karanja I136'), null, { timeout: 10000 })
      const made = bench(`print(frappe.db.get_value("Life Person", {"full_name": "Zubin Karanja I136", "space": "${SPACE}"}, "kind"))`).trim().split('\n').pop()
      must(made === 'Person', 'the person was not made: ' + made)
      must((await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) === false, 'the page scrolls sideways')
    })
    await check('LIBRARY.53', `${width} px: Hand off's Who uses the same picker`, async () => {
      await u.open(`/life/today?open=task:${seeded.task}`)
      await pg.locator('[data-task-delegated]').waitFor({ timeout: 15000 })
      await pg.getByRole('button', { name: /hand off/i }).first().click()
      const who = pg.locator('[data-handoff-person]')
      await who.waitFor({ timeout: 10000 })
      await openPicker(who, 'Linc')
      const names = await optionNames()
      must(names.some((n) => n.includes('Ravi Singh I136') && n.includes('Linc pens I136')), 'Hand off does not list Ravi at Linc pens: ' + names.join(' | '))
    })
    await check('LIBRARY.54', `${width} px: the picker is readable in the light and the dark theme, and nothing scrolls sideways`, async () => {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        await u.open(`/life/today?open=task:${seeded.task}`)
        await pg.locator('[data-task-delegated]').waitFor({ timeout: 15000 })
        await openPicker(pg.locator('[data-task-delegated]'), 'Linc')
        const item = (phone ? pg.locator('[data-person-option]') : pg.locator('[data-slot="item"]')).filter({ hasText: 'Ravi Singh I136' }).first()
        await item.waitFor({ timeout: 8000 })
        const seen = await item.evaluate((el) => {
          const lum = (c) => { const unit = c.startsWith('color(') ? 1 : 255; const m = c.replace('srgb', '').match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= unit; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2] }
          let bg = el, back = 'rgb(255, 255, 255)'
          for (; bg; bg = bg.parentElement) { const c = getComputedStyle(bg).backgroundColor; const a = c.replace('srgb', '').match(/[\d.]+/g); if (a.length < 4 || Number(a[3]) >= 0.95) { if (a.length >= 3 && (a.length < 4 || Number(a[3]) > 0)) { back = c; break } } }
          const label = [...el.querySelectorAll('span, div')].find((n) => n.textContent.trim().startsWith('Ravi')) || el
          return { text: lum(getComputedStyle(label).color), back: lum(back) }
        })
        must(Math.abs(seen.text - seen.back) > 0.3, `${scheme}: the names are not readable ${JSON.stringify(seen)}`)
        must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), `${scheme}: the page scrolls sideways`)
        await pg.keyboard.press('Escape')
      }
      await pg.emulateMedia({ colorScheme: null })
    })
  } finally {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "I136 %"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I136"]}, pluck="name"):
    frappe.db.delete("Life Link", {"to_doctype": "Life Person", "to_name": n})
    frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)`)
    await u.ctx.close()
  }
}
