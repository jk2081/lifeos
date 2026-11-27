// The Drawer (issue 128): the one control for everything that opens over a screen, Chat included. Layers, the URL that holds them, Back and Esc, the widths, the guard.
// Checks are numbered CORE.<n> in the order they appear here; `node tools/acceptance.mjs --only=CORE` runs this file's checks.
import { SPACE, WIDTHS, bench, chatOff, chatOn, check, fs, must, os, path, pathOf, root, session, stamp } from './context.mjs'
import { findRecordLinks, problems } from '../guard-routes.mjs'

const T = `I128 ${stamp}`
const made = { tasks: [], threads: [] }
const tasks = JSON.parse(bench(`import json
out = []
for i in range(3):
    out.append(frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": f"${T} task {i}", "status": "Open", "due_date": frappe.utils.today()}).insert(ignore_permissions=True).name)
print(json.dumps(out))`).split('\n').pop())
made.tasks.push(...tasks)
const params = (pg) => new URL(pg.url()).searchParams
const top = (pg) => params(pg).get('open') || ''
const under = (pg) => params(pg).get('under') || ''
const gone = (pg) => pg.waitForFunction(() => !new URL(location.href).searchParams.get('open'), null, { timeout: 8000 })
const openIs = (pg, v) => pg.waitForFunction((x) => new URL(location.href).searchParams.get('open') === x, v, { timeout: 8000 })
const keyUntil = async (pg, key, ref) => {
  for (let i = 0; i < 6; i++) {
    await pg.evaluate(() => document.activeElement?.blur?.())
    await pg.keyboard.press(key)
    if (await pg.waitForFunction((x) => new URL(location.href).searchParams.get('open') === x, ref, { timeout: 1500 }).then(() => true, () => false)) return
  }
  await openIs(pg, ref)
}

try {
  chatOn()
  for (const width of WIDTHS) {
    const phone = width < 800
    const s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    try {
      await check('CORE.1', `${width} px: a task opened from Today shows in the Drawer and the screen stays; Back closes it; a reload reopens it`, async () => {
        await s.open('/life/today?mode=calendar')
        const row = pg.locator(`[data-ref="task:${tasks[0]}"]`).first()
        await row.waitFor({ timeout: 15000 })
        await row.click()
        await pg.locator(`[data-drawer-host] [data-pane-ref="task:${tasks[0]}"]`).waitFor({ timeout: 8000 })
        must(top(pg) === `task:${tasks[0]}` && pathOf(pg) === '/life/today', `the URL is ${pg.url()}`)
        must(await pg.locator('[data-main]').count(), 'the screen is gone')
        await pg.reload({ waitUntil: 'networkidle' })
        await pg.locator(`[data-drawer-host] [data-pane-ref="task:${tasks[0]}"]`).waitFor({ timeout: 10000 })
        await pg.goBack()
        await gone(pg)
        await pg.locator('[data-drawer-host]').waitFor({ state: 'detached', timeout: 5000 })
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })

      await check('CORE.2', `${width} px: Chat is a layer (Cmd+K); a source in an answer opens on top of it with Back; Back returns to the same chat with its answer; Esc twice closes everything`, async () => {
        await s.open('/life/today')
        if (phone) await pg.locator('[data-chat-bar-open]').first().click()
        else await pg.keyboard.press('Control+k')
        await pg.locator('[data-ask-panel]:visible').first().waitFor({ timeout: 10000 })
        await pg.waitForFunction(() => /^ask:/.test(new URL(location.href).searchParams.get('open') || ''), null, { timeout: 8000 })
        const ask = async (q) => {
          await pg.locator('[data-ask-panel] textarea').fill(q)
          await pg.locator('[data-ask-send]:visible').click()
          await pg.waitForTimeout(700)
          await pg.locator('[data-ask-working]').waitFor({ state: 'detached', timeout: 90000 })
          await pg.locator('[data-ask-answer][data-status="Done"]').last().waitFor({ timeout: 8000 })
        }
        await ask('What is open today?')
        await pg.waitForFunction(() => /^ask:(?!new)/.test(new URL(location.href).searchParams.get('open') || ''), null, { timeout: 8000 }) // the thread is in the URL
        const chat = top(pg)
        const thread = chat.slice(4)
        made.threads.push(thread)
        // the answer cites a record: the model here only lists tasks, so the answer is written as one that cites R1; a reload rebuilds the chat from the thread in the URL
        bench(`import json
t = frappe.get_doc("Life Ask Thread", "${thread}")
run = frappe.get_all("Flow Run", filters={"session": t.flow_session}, order_by="creation desc", limit=1, pluck="name")[0]
frappe.db.set_value("Flow Run", run, "output", "${T} task 1 is open today. [R1]")
t.db_set("refs", json.dumps({"R1": {"doctype": "Life Task", "name": "${tasks[1]}", "title": "${T} task 1", "kind": "Task", "date": None, "pane": "task:${tasks[1]}", "route": None}}))`)
        await pg.reload({ waitUntil: 'networkidle' })
        await pg.locator('[data-ask-cite="1"]').last().waitFor({ timeout: 15000 })
        must(top(pg) === chat, `the reload did not keep the chat layer: ${pg.url()}`)
        const before = (await pg.locator('[data-ask-answer]').last().innerText()).slice(0, 60)
        await pg.locator('[data-ask-cite="1"]').last().click()
        await openIs(pg, `task:${tasks[1]}`)
        must(under(pg) === chat, `the layer under is "${under(pg)}", not ${chat}`)
        await pg.locator('[data-pane-back]').first().waitFor({ timeout: 5000 })
        if (!phone) must(await pg.locator('[data-ask-panel]:visible').count() === 0, 'the chat and the record are both showing')
        await pg.locator('[data-pane-back]').first().click()
        await openIs(pg, chat)
        await pg.locator('[data-ask-panel]:visible').first().waitFor({ timeout: 8000 })
        const after = (await pg.locator('[data-ask-answer]').last().innerText()).slice(0, 60)
        must(after === before && await pg.locator('[data-ask-answer]').count() >= 1, `the chat lost its answers: "${after}"`)
        // Esc twice
        await pg.locator('[data-ask-cite="1"]').last().click()
        await openIs(pg, `task:${tasks[1]}`)
        await pg.keyboard.press('Escape')
        await openIs(pg, chat)
        await pg.waitForTimeout(700)
        await pg.keyboard.press('Escape')
        await gone(pg)
        must(!under(pg), 'layers are left in the URL: ' + under(pg))
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })

      await check('CORE.3', `${width} px: a list, then a row, then Back returns to the list with its row marked; j moves to the next row's record`, async () => {
        await s.open('/life/today?open=list:plate')
        const rows = pg.locator('[data-list="plate"] [data-list-row]')
        await rows.first().waitFor({ timeout: 15000 })
        const refs = await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-ref')))
        must(refs.length >= 3, `only ${refs.length} rows in the plate`)
        await rows.nth(1).locator('button').first().click()
        await openIs(pg, refs[1])
        must(under(pg) === 'list:plate', `the layer under is "${under(pg)}"`)
        if (!phone) {
          // the pane takes focus into a field as it loads and j is ignored there: wait for it, then press until it moves
          await pg.locator(`[data-drawer-host] [data-pane-ref="${refs[1]}"]`).waitFor({ timeout: 8000 })
          await keyUntil(pg, 'j', refs[2])
          must(under(pg) === 'list:plate', 'j lost the list layer')
          await keyUntil(pg, 'k', refs[1])
        }
        await pg.locator('[data-pane-back]').first().click()
        await openIs(pg, 'list:plate')
        await pg.locator('[data-list="plate"] [data-list-row][data-active]').waitFor({ timeout: 8000 })
        const active = await pg.locator('[data-list="plate"] [data-list-row]').evaluateAll((els) => els.findIndex((e) => e.hasAttribute('data-active')))
        must(active === 1, `the marked row is ${active}, not 1`)
        must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      })
    } finally {
      await s.ctx.close()
    }
  }

  // widths: docked from 1440, floating below it, full screen on a phone with Back
  await check('CORE.4', 'At 1440 px the Drawer is docked and the page narrows; at 1280 px it floats and the page keeps its width; at 390 px it is full screen with Back, in light and dark', async () => {
    const s = await session('owner@lifeos.test', 1440)
    const pg = s.page
    try {
      for (const scheme of ['light', 'dark']) {
        await pg.emulateMedia({ colorScheme: scheme })
        await pg.setViewportSize({ width: 1440, height: 1000 })
        await s.open('/life/today?mode=calendar')
        await pg.locator(`[data-ref="task:${tasks[0]}"]`).first().waitFor({ timeout: 15000 })
        const wide = (await pg.locator('[data-main]').boundingBox()).width
        await pg.locator(`[data-ref="task:${tasks[0]}"]`).first().click()
        const host = pg.locator('[data-drawer-host]')
        await host.waitFor({ timeout: 8000 })
        await pg.waitForTimeout(400)
        must((await host.getAttribute('data-docked')) === '1', 'not docked at 1440')
        must(Math.abs((await host.boundingBox()).width - 480) < 2, `the Drawer is ${(await host.boundingBox()).width} px, not 480`)
        const narrowed = (await pg.locator('[data-main]').boundingBox()).width
        must(narrowed < wide - 400, `the page is ${narrowed} px beside the Drawer, ${wide} without`)
        await pg.locator('[data-pane-expand]').click()
        await pg.waitForTimeout(300)
        must(Math.abs((await host.boundingBox()).width - 720) < 2, `Expand made it ${(await host.boundingBox()).width} px, not half the window`)
        await pg.locator('[data-pane-expand]').click()
        await pg.setViewportSize({ width: 1280, height: 1000 })
        await pg.waitForTimeout(400)
        must((await host.getAttribute('data-docked')) === '0', 'docked at 1280')
        const kept = (await pg.locator('[data-main]').boundingBox()).width
        must(Math.abs(kept - (await pg.evaluate(() => document.documentElement.clientWidth - document.querySelector('[data-sidebar]').getBoundingClientRect().width))) < 40, `the page is ${kept} px at 1280 with the Drawer floating`)
        must((await pg.evaluate(() => getComputedStyle(document.querySelector('[data-drawer-host]')).position)) === 'fixed', 'the Drawer does not float at 1280')
        await pg.keyboard.press('Escape')
        await gone(pg)
        await pg.setViewportSize({ width: 390, height: 844 })
        await s.open('/life/today?open=list:plate')
        await pg.locator('[data-list="plate"] [data-list-row]').first().waitFor({ timeout: 15000 })
        await pg.locator('[data-list="plate"] [data-list-row] button').first().click()
        await pg.locator('[data-drawer-host] [data-pane-back]').waitFor({ timeout: 8000 })
        const box = await host.boundingBox()
        must(box.width >= 388 && box.height >= 840, `the Drawer is ${box.width} by ${box.height} at 390 px`)
        must((await pg.locator('[data-pane-back]').boundingBox()).x < 80, 'Back is not at the top left')
        must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), `the page scrolls sideways in ${scheme}`)
        await pg.locator('[data-pane-back]').click()
        await openIs(pg, 'list:plate')
        await pg.keyboard.press('Escape')
        await gone(pg)
      }
    } finally {
      await s.ctx.close()
    }
  })

  await check('CORE.5', 'The guard finds a link to a record route in a .vue file, and the tree has none', async () => {
    const bad = findRecordLinks('<RouterLink :to="`/goals/${g.name}`">x</RouterLink>')
    must(bad.length === 1 && bad[0].route.startsWith('/goals/${'), 'the guard missed a fixture link: ' + JSON.stringify(bad))
    for (const line of ["router.push('/item/' + id)", '<a :href="`/library/people/${p}`">', 'to="/focus/abc"', "router.push(`/brain/review/${n}`)", "router.push(`/library/${note.name}`)"])
      must(findRecordLinks(line).length === 1, 'the guard missed: ' + line)
    for (const line of ["router.push('/goals/tasks')", 'to="/library/notes"', "router.push('/goals')"])
      must(findRecordLinks(line).length === 0, 'the guard flagged a place: ' + line)
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lifeos-guard-'))
    fs.mkdirSync(path.join(dir, 'frontend/src/components'), { recursive: true })
    fs.writeFileSync(path.join(dir, 'frontend/src/components/Fixture.vue'), '<template><RouterLink :to="`/goals/${g.name}`">x</RouterLink></template>')
    must(problems(dir).length === 1, 'a fixture file with a record link did not fail the guard')
    const found = problems(root)
    must(!found.length, found.join('; '))
  })
} finally {
  chatOff()
  bench(`frappe.set_user("Administrator")
for n in ${JSON.stringify(made.tasks)}:
    frappe.db.delete("Life Link", {"from_doctype": "Life Task", "from_name": n})
    frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.threads)}:
    frappe.delete_doc("Life Ask Thread", n, force=1, ignore_permissions=True)`)
}
