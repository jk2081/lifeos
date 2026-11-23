// Brain: capture, Needs you, Activity, Sources, the item page, Ask and the fake agent.
// Checks are numbered BRAIN.<n> in the order they appear here; `node tools/acceptance.mjs --only=BRAIN` runs this file's checks.
import { PDF, SPACE, WIDTHS, agentFetch, agentKey, agentSecret, areaId, areas, base, bench, browser, check, env, execFileSync, fs, must, owner, path, root, runAgent, session, stamp, today } from './context.mjs'
import { ux, uxArea, uxKit } from './ux.mjs'

// records the checks of this place hand on to each other
let photoItem, photoFile

await check('BRAIN.1', 'Journal photo: agent submits 5 proposals; accept 3, edit 1, reject 1; records link back', async () => {
  const item = await owner.api('inbox.create_item', { title: `Journal photo ${stamp}`, source_type: 'Journal Photo', space: SPACE,
    instruction: 'transcribe and update my journal' })
  photoItem = item.name
  photoFile = (await owner.upload('Life Inbox Item', item.name, `journal-${stamp}.png`, 'image/png', await owner.page.screenshot())).file_url
  runAgent()
  let got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'To Review', 'item is ' + got.status)
  must(got.transcript_md && got.proposals.length === 5, `expected 5 proposals, got ${got.proposals.length}`)
  // accept the first and reject the second with the buttons on the Review screen
  await owner.open('/life/brain/queue?open=inbox:' + item.name)
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
  must(links.some((l) => l.doctype === 'Life Task') && links.some((l) => l.doctype === 'Life Note'), 'records do not link back to the photo')
  const tasks = await owner.api('tasks.list', { space: SPACE, page_length: 100, filters: [['title', 'like', stamp]] }) // this run's tasks: the site holds more than one page
  must(tasks.tasks.some((t) => t.title === `Promotion plan ${stamp}` && t.inbox_item === item.name), 'the edited task is not in Tasks')
  const page = links.find((l) => l.doctype === 'Life Note')
  const notes = await owner.api('library.list', { space: SPACE, page_length: 100, filters: [['title', 'like', 'Journal page%']] })
  must(notes.notes.some((n) => n.name === page.name), 'the journal page is not a note in Library > Notes')
  return `${made.length} accepted (1 edited), 1 rejected`
})

await check('BRAIN.2', 'PDF with "summarise and extract to-dos" gives tasks through review', async () => {
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

await check('LIBRARY.1', 'Note with a [[link]]: the target shows the backlink, both are in the graph', async () => {
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

await check('BRAIN.3', 'Search for a word in a transcript finds the inbox item', async () => {
  const res = await owner.api('search.query', { text: `Nowrojee ${stamp}` }) // the word is in the transcript, the stamp in the title of this run's item
  must(res.results.some((r) => r.ref_doctype === 'Life Inbox Item' && r.ref_name === photoItem), 'the inbox item was not found')
  await owner.page.keyboard.press('Control+k')
  await owner.page.keyboard.type(`Nowrojee ${stamp}`)
  await owner.page.waitForTimeout(900)
  must((await owner.page.locator('body').innerText()).includes(`Journal photo ${stamp}`), 'the search palette does not show it')
  await owner.page.keyboard.press('Escape')
})

await check('BRAIN.4', 'A second user who is only in Shared sees nothing from Private, on any screen or in search', async () => {
  const fam = await session('family@lifeos.test')
  const boot = await fam.api('session.boot')
  must(!JSON.stringify(boot.spaces).includes('Private'), 'Private is offered in the space switcher')
  const reads = { 'today.get': {}, 'tasks.list': {}, 'timeline.get': {}, 'inbox.list': {}, 'library.tree': {}, 'vault.list': {}, 'chats.report': {},
    'graph.get': {}, 'archive.list': {}, 'calendar.get': { from_date: '2026-11-01', to_date: '2026-12-31' }, 'calendar.year': { year: 2026 },
    'goals.list': {}, 'sources.list': {}, 'someday.list': {}, 'counts.get': {}, 'session.counts': {}, 'area.tree': {}, 'goals.grid': {}, 'goals.across_cycles': {}, 'goals.this_month': {}, 'goals.month_habits': {},
    'today.week_summary': {}, 'settings.get': {}, 'weekly.get': {}, 'weekly.library': {}, 'weekly.goals': {}, 'weekly.plate': {}, 'weekly.stale_tasks': {} }
  for (const [m, args] of Object.entries(reads)) {
    const r = await fam.api(m, { ...args, space: SPACE }, { raw: true })
    must(r.status() === 403, `${m} with space=Private answered ${r.status()}`)
    const own = JSON.stringify(await fam.api(m, args)) || ''
    must(!own.includes(stamp) && !own.includes('Ruchi ITR') && !own.includes('Meditate'), `${m} leaks Private records`)
  }
  const privateGoal = (await owner.api('goals.list', { space: SPACE, horizon: 'Long term', page_length: 1 })).goals[0].name
  for (const [m, args] of [['inbox.get', { item: photoItem }], ['goals.get', { goal: privateGoal }], ['links.backlinks', { doctype: 'Life Inbox Item', name: photoItem }]]) {
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
  // every place, tab and view (set 6), and a Private goal's page and Private area in the URL
  for (const p of ['', '/brain', '/brain/queue', '/today/week?view=review', '/today/week?view=calendar', '/today/week?view=agenda', '/goals/cycles', '/today/month?view=habits',
    '/today/month?view=calendar', '/today/year?view=calendar', '/today/year?view=goals', '/goals', '/goals/tasks',
    '/goals/someday', '/settings?tab=data', '/library', '/library/notes', '/library/notes?view=tree', '/library/notes?view=graph', '/library/notes?by=assistant',
    '/library/documents?sensitive=1', '/library/chats', '/library/notes?view=list', '/library/timeline',
    '/library/archive', '/ask', '/settings', `/goals/${privateGoal}`, `/?area=${areaId('Tea & Coffee')}`]) {
    await fam.open('/life' + p)
    const text = await fam.page.locator('[data-app]').innerText()
    must(!/Ruchi|Merrill|Meditate|Tea & Coffee|Private/.test(text) && !text.includes(stamp), `screen ${p || '/'} shows Private content`)
    screens++
  }
  await fam.ctx.close()
  return `${Object.keys(reads).length} methods, ${screens} screens, search and file`
})

await check('BRAIN.5', 'At review, change the area with one tap and add a second: the record is under both areas in the lens', async () => {
  // set 6: the area pages became the lens; a record filed under one area and "also in" another shows under both
  const title = `Promotion plan ${stamp}`
  for (const name of ['Tea & Coffee', 'Personal']) {
    const rows = (await owner.api('tasks.list', { space: SPACE, area: areaId(name), status: 'all', page_length: 50, filters: [['title', '=', title]] })).tasks
    must(rows.length === 1, `not in Tasks under the ${name} lens`)
    await owner.open(`/life/goals/tasks?view=list&status=all&area=${areaId(name)}`)
    must((await owner.page.locator('[data-main]').innerText()).includes(title), `not on Plan > Tasks with ${name} in the lens`)
  }
  const item = await owner.api('inbox.list', { space: SPACE, status: 'To Review' })
  await owner.open('/life/brain/queue?open=inbox:' + item.items[0].name)
  must(await owner.page.locator('text=also in').count() > 0, 'the Review screen has no area chips')
})

await check('TODAY.4', 'Timeline shows everything captured on one day', async () => {
  const t = await owner.api('timeline.get', { space: SPACE, from_date: today, to_date: today, page_length: 100 })
  const kinds = new Set(t.days.flatMap((d) => d.entries.map((e) => e.kind)))
  for (const k of ['Inbox', 'Task', 'Note', 'Document']) must(kinds.has(k), `no ${k} on today's timeline`)
  must(t.days.length === 1, 'more than one day returned')
  await owner.open('/life/library/timeline?all=1') // a bare URL restores the remembered view, which a UX check may have filtered
  must((await owner.page.locator('[data-main]').innerText()).includes(`Target note ${stamp}`), 'the screen does not show today')
  return [...kinds].join(', ')
})

await check('BRAIN.6', 'Security: the family and agent users land on /life from /app; the agent works without desk access and cannot read a closed Vault', async () => {
  for (const user of ['family@lifeos.test', 'hermes@lifeos.test']) {
    const ctx = await browser.newContext()
    const r = await ctx.request.post(base + '/api/method/login', { form: { usr: user, pwd: env.LIFEOS_DEV_PASSWORD } })
    must(r.ok(), 'login failed for ' + user)
    for (const p of ['/app', '/app/todo', '/desk']) {
      const res = await ctx.request.get(base + p, { maxRedirects: 0 })
      const to = res.headers().location || ''
      must(res.status() >= 300 && res.status() < 400 && /\/life$/.test(to.replace(base, '')), `${user} at ${p}: ${res.status()} ${to}`)
    }
    await ctx.close()
  }
  // the agent end to end with its API key: claim_next and submit_result through the fake agent
  const item = await owner.api('inbox.create_item', { title: `S3 agent item ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Call the plumber tomorrow.' })
  runAgent()
  must((await owner.api('inbox.get', { item: item.name })).status === 'To Review', 'the agent did not process the item without desk access')
  // with the switch off the agent's key cannot read a Vault document
  const doc = await owner.api('vault.save', { space: SPACE, values: { title: `S3 secret ${stamp}`, doc_type: 'ID' } })
  const asAgent = agentFetch
  const vaultOpen = (await owner.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE).agents_can_read_vault
  if (!vaultOpen) {
    must((await asAgent('vault.get', { document: doc.name })).status === 404, 'the agent read a Vault document with the switch off')
    const listed = await (await asAgent('vault.list', { space: SPACE })).json()
    must(listed.message.total === 0, 'the agent listed Vault documents with the switch off')
  }
})

await check('BRAIN.7', 'Security: the PWA manifest and icons are served; an agent cannot decide or delete', async () => {
  const m = await (await owner.page.request.get(base + '/assets/lifeos/manifest.webmanifest')).json()
  must(m.start_url === '/life/today' && m.display === 'standalone' && m.icons.length >= 2, 'manifest is incomplete')
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

for (const width of WIDTHS) {
  const { S5, askOn, count, pane, paneTitle, pg, phone, s, settle, tag, tasksLike } = await uxKit(width)
  await check('BRAIN.8', `${width} px: Ask: from Today, Today under an area, a goal page and a record pane, with the scope of the screen; citations open their records; Make task only when clicked; the panel closes and the screen is as it was`, async () => {
    const done = []
    // set 6: the area page became the lens (Ask's scope is the lens), the project page the goal's page
    for (const [path, scope] of [['/life', 'Everything in this space'], ['/life?area=' + uxArea, areas.find((x) => x.name === uxArea).area_name],
      ['/life/goals/' + ux.goal, ux.goalTitle]]) {
      await askOn(path, scope)
      const here = new URL(pg.url()).pathname
      const cites = pg.locator('[data-ask-cite]:visible')
      if (await cites.count()) {
        const title = (await cites.first().innerText()).replace(/^\d+\s*/, '')
        await cites.first().click()
        await settle()
        must(await pane.count() && (await paneTitle()).trim() === title.trim(), `${path}: the citation did not open "${title}"`)
        if (phone) await pg.locator('[data-pane-close]:visible').first().click() // a phone closes the sheet with its button
        else await pg.keyboard.press('Escape')
        await settle()
      }
      if (!phone) { await pg.locator('[data-ask-close]').click(); await settle() } else { await pg.keyboard.press('Escape'); await settle() }
      must(!(await pg.locator('[data-ask-panel]:visible').count()), `${path}: the panel did not close`)
      must(new URL(pg.url()).pathname === here && here.replace(/\/$/, '') === (path.split('?')[0] === '/life' ? '/life/today' : path.split('?')[0]), `${path}: the screen changed under the panel (${new URL(pg.url()).pathname})`)
      done.push(scope)
    }
    // a record pane: Ask about this
    const task = await s.api('tasks.quick_add', { text: S5('ask about'), space: SPACE, area: uxArea })
    await s.open(`/life/goals/tasks?view=list&status=all&f=${encodeURIComponent(JSON.stringify([['title', 'like', `%${S5('ask about')}%`]]))}`)
    await pg.locator(`[data-ref="task:${task.name}"]`).first().click()
    await settle()
    await pg.locator('[data-pane-ask]').click()
    await settle()
    must((await pg.locator('[data-ask-scope]:visible').first().innerText()).trim() === S5('ask about'), 'Ask about this does not take the record as its scope')
    await pg.locator('[data-ask-panel] textarea').fill(`${S5('ask about')}?`)
    await pg.locator('[data-ask-send]:visible').click()
    for (let i = 0; i < 40 && await pg.locator('[data-ask-answer][data-status="Working"]').count(); i++) await pg.waitForTimeout(250)
    await settle()
    must(await pg.locator('[data-ask-cite]:visible').count(), 'the answer cites nothing')
    // a suggested Make task creates a task only when clicked
    const made = async () => (await tasksLike('Follow up: ' + S5('ask about'))).length
    must((await made()) === 0, 'a task was made before the click')
    await pg.locator('[data-ask-action="make_task"]:visible').first().click()
    await pg.waitForTimeout(900)
    must((await made()) === 1, 'Make task did not make one task')
    return done.join(', ') + ', a task pane'
  })

  if (!phone) await check('BRAIN.9', 'Ask: with no key it says it is not set up; at the cap it refuses and shows the spend; the family user never gets a Private record; a Vault document is never sent while the switch is off', async () => {
    // no key
    bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = None; s.save()')
    try {
      await s.open('/life')
      await pg.keyboard.press('Control+k'); await pg.waitForTimeout(300); await pg.keyboard.type('What is open this week?'); await pg.waitForTimeout(500); await pg.keyboard.press('Enter')
      await pg.waitForTimeout(1500)
      must(await pg.locator('[data-refusal="not_set_up"]').count() && (await pg.locator('[data-ask-refusal]').innerText()).includes('Ask is not set up yet'), 'no "not set up" message')
      await pg.locator('[data-ask-close]').click()
    } finally {
      bench('s = frappe.get_single("Life Settings"); s.anthropic_api_key = "fake-key-acceptance"; s.save()')
    }
    // the cap
    bench(`frappe.get_doc({"doctype": "Life AI Usage", "user": "owner@lifeos.test", "month": frappe.utils.now_datetime().strftime("%Y-%m"), "model": "claude-sonnet-5-5", "cost": 99, "purpose": "Test"}).insert(ignore_permissions=True)`)
    try {
      const res = await s.api('ask.ask', { question: 'What is open?', space: SPACE })
      must(res.error === 'cap' && /\$\d+\.\d\d of \$30/.test(res.error_text), `the cap did not refuse: ${JSON.stringify(res).slice(0, 200)}`)
      await s.open('/life/ask')
      must((await pg.locator('[data-ask-spend]').innerText()).includes('of $30'), 'the Ask page does not show the spend')
    } finally {
      bench('frappe.db.delete("Life AI Usage", {"purpose": "Test"})')
    }
    // the family user asks in Shared about a word only a Private record holds
    const secret = await s.api('tasks.quick_add', { text: S5('kumquat private'), space: SPACE, area: uxArea })
    bench('from lifeos.ai import fake\nfake.clear_received()')
    const fam = await session('family@lifeos.test', width)
    const r = await fam.api('ask.ask', { question: `kumquat ${stamp}?`, space: 'Shared' })
    must(!(r.message?.cited || []).some((c) => c.title.includes('kumquat')), 'the family user was given a Private record')
    must(!bench('from lifeos.ai import fake\nimport json\nprint(json.dumps(fake.received()))').includes(S5('kumquat private')), 'a Private record was sent for the family user')
    await fam.ctx.close()
    // a Vault document is never sent while "Ask may read Vault documents" is off
    await s.api('vault.save', { space: SPACE, values: { title: S5('zebra passport'), doc_type: 'ID', notes_md: `secret-${stamp}`, area: areaId('Money & Legal') } })
    bench('from lifeos.ai import fake\nfake.clear_received()')
    await s.api('ask.ask', { question: `Where is my zebra passport ${stamp}?`, space: SPACE })
    const sent = bench('from lifeos.ai import fake\nimport json\nprint(json.dumps(fake.received()))')
    must(sent.length > 10 && !sent.includes(`secret-${stamp}`) && !sent.includes(S5('zebra passport')), 'a Vault document reached the model')
    return 'no key, cap, family, Vault'
  })

  if (!phone) await check('BRAIN.10', 'streams: chats.log twice with one external_id leaves one log; importing the Claude and ChatGPT fixtures creates the expected logs, and again creates and updates none', async () => {
    const ext = `s4-${stamp}`
    const a = await s.api('chats.log', { space: SPACE, title: `S4 stream ${stamp}`, source_system: 'claude', external_id: ext, open_items: ['One'] })
    const b = await s.api('chats.log', { space: SPACE, title: `S4 stream ${stamp}, renamed`, source_system: 'claude', external_id: ext, open_items: ['One', 'Two'] })
    must(a.created && !b.created && a.name === b.name, 'the second log was not an update')
    const got = await s.api('chats.get', { chat: a.name })
    must(got.title.endsWith('renamed') && got.open_items.length === 2, 'the log was not updated')
    const fixtures = path.join(root, 'lifeos/tests/fixtures')
    const importOnce = async (system, file) => {
      const up = await s.page.request.post(base + '/api/method/upload_file', { headers: { 'X-Frappe-CSRF-Token': await pg.evaluate(() => window.csrf_token) },
        multipart: { is_private: '1', file: { name: file, mimeType: 'application/zip', buffer: fs.readFileSync(path.join(fixtures, file)) } } })
      must(up.ok(), 'upload failed ' + up.status())
      const url = (await up.json()).message.file_url
      await s.api('connections.start_import', { space: SPACE, system, file_url: url })
      for (let i = 0; i < 60; i++) {
        const st = await s.api('connections.import_status', { space: SPACE, system })
        if (st.status === 'Done' || st.status === 'Failed') return st
        await pg.waitForTimeout(1000)
      }
      throw new Error(`${system}: the import did not finish (is a worker running?)`)
    }
    const c1 = await importOnce('claude', 'claude_export.zip')
    must(c1.status === 'Done' && c1.created === 2 && c1.skipped === 1, `Claude: ${JSON.stringify(c1)}`)
    const g1 = await importOnce('chatgpt', 'chatgpt_export.zip')
    must(g1.status === 'Done' && g1.created === 2 && g1.skipped === 1, `ChatGPT: ${JSON.stringify(g1)}`)
    const c2 = await importOnce('claude', 'claude_export.zip')
    const g2 = await importOnce('chatgpt', 'chatgpt_export.zip')
    must(!c2.created && !c2.updated && !g2.created && !g2.updated, `the second import changed something: ${JSON.stringify([c2, g2])}`)
    await s.open('/life/library/chats?tab=chats')
    must((await pg.locator('[data-main]').innerText()).includes('Blend sheet for Dalmia Gold'), 'the imported chat is not on the Chats tab')
    return 'two systems'
  })

  await check('BRAIN.11', `${width} px: an Email Digest renders its sections and Open in Gmail buttons; the proposed reply task shows Open in Gmail`, async () => {
    const digest = `## Needs your attention\n- Mithun Sarkar: the despatch dates for December [Open](https://mail.google.com/mail/u/0/#inbox/s4${stamp}${width})\n- Ruchi: ITR papers [Open](https://mail.google.com/mail/u/0/#inbox/r${stamp})\n\n## Waiting on others\n- The auditor, scope letter [Open](https://mail.google.com/mail/u/0/#inbox/a${stamp})\n\n## Dates and deadlines\n- 20 Nov: board meeting\n\n## FYI from people\n- Anya: photos from the trip\n\n## Company information\n- Q3 numbers are out\n\n## Left out\n- 14 newsletters`
    const item = await s.api('inbox.create_item', { title: `S4 digest ${width} ${stamp}`, source_type: 'Email Digest', space: SPACE, raw_text: digest, source_system: 'gmail', external_id: `digest-${width}-${stamp}` })
    runAgent()
    await s.open(`/life/brain/captures?tab=email&open=source:${item.name}`)
    must((await pg.locator('[data-digest-section]').count()) >= 6, 'the digest sections are not headed lists')
    must((await pg.locator('[data-open-gmail]').count()) >= 3, 'no Open in Gmail buttons')
    const got = await s.api('inbox.get', { item: item.name })
    const p = got.proposals.find((x) => x.kind === 'Task')
    must(p && /mail\.google\.com/.test(p.payload.source_url || ''), 'the reply task has no Gmail link')
    const res = await s.api('review.decide', { proposal: p.name, decision: 'accept' })
    const task = res.created_name || (await s.api('inbox.get', { item: item.name })).proposals.find((x) => x.name === p.name).created_name
    await s.open(`/life/goals/tasks?open=task:${task}`)
    must((await pg.locator('[data-open-source]').innerText()).includes('Open in Gmail'), 'the task pane has no Open in Gmail')
  })
  await s.ctx.close()
}

await check('BRAIN.12', 'The fake agent runs end to end with the goal-based API: tasks it proposes are filed under the open-ended goal of their area', async () => {
  const goals = (await owner.api('goals.list', { space: SPACE, horizon: 'Long term', area: uxArea })).goals.map((g) => g.name)
  must(goals.length, 'Tea & Coffee has no open-ended goal')
  const item = await owner.api('inbox.create_item', { title: `S5 agent pdf ${stamp}.pdf`, space: SPACE, instruction: 'summarise and extract to-dos' })
  await owner.upload('Life Inbox Item', item.name, `s6-agent-${stamp}.pdf`, 'application/pdf', PDF)
  runAgent()
  const got = await owner.api('inbox.get', { item: item.name })
  must(got.status === 'To Review' && got.proposals.length === 3, `the agent left ${got.status} with ${got.proposals.length} proposals`)
  const goal = got.proposals[0].payload.goal
  must(goal && goals.includes(goal) && got.proposals.every((p) => p.payload.goal === goal && !p.payload.project), `the proposals are not filed under an open-ended goal of Tea & Coffee: ${JSON.stringify(got.proposals.map((p) => p.payload)).slice(0, 200)}`)
  await owner.api('review.decide_all', { item: item.name, decision: 'accept' })
  const made = (await owner.api('inbox.get', { item: item.name })).proposals.map((p) => p.created_name)
  const under = (await owner.api('tasks.list', { space: SPACE, goal, status: 'all', page_length: 200 })).tasks.map((t) => t.name)
  must(made.length === 3 && made.every((n) => under.includes(n)), 'the accepted tasks are not under the goal')
  // the agent's own reads with its key: Today and the goal's tasks; the old `project` argument is refused with an error that names `goal`
  const asAgentHttp = (m, args) => agentFetch(m, args).then(async (r) => [r.status, await r.json().catch(() => ({}))])
  const [ts] = await asAgentHttp('today.get', { space: SPACE })
  must(ts === 200, `today.get answered the agent ${ts}`)
  const [, byGoal] = await asAgentHttp('tasks.list', { space: SPACE, goal: ux.goal, status: 'all', page_length: 1 })
  must(byGoal.message && byGoal.message.total > 0, `goal= gives ${byGoal.message?.total}`)
  const [ps, pj] = await asAgentHttp('tasks.list', { space: SPACE, project: ux.goal, status: 'all', page_length: 1 })
  must(ps === 417 || ps === 400 || ps === 417, `project= answered ${ps}`)
  must(JSON.stringify(pj).includes('goal'), 'the error for project= does not name goal')
  return `3 tasks under ${goal}`
})


// Issue 7: a file is stored once by content, and an item filed again with a changed file of the same name keeps versions
for (const width of WIDTHS) {
  const tag = `I7.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const file = (title, ext) => s.api('inbox.create_item', { title, space: SPACE, source_type: 'Upload', intent: 'Just keep',
    source_system: 'hermes', external_id: ext })
  const ext = `i7-deck-${width}-${stamp}`
  const v1 = Buffer.from(`I7 standard deck ${stamp}, first version`)
  const v2 = Buffer.from(`I7 standard deck ${stamp}, second version`)
  const original = '[data-review-original]'
  await check('BRAIN.13', `${width} px: an item filed twice with the same file shows one attachment; with two versions it shows "2 versions" and opens the older one`, async () => {
    const item = await file(`I7 deck ${width} ${stamp}`, ext)
    const first = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v1)
    must((await file(`I7 deck ${width} ${stamp}`, ext)).name === item.name, 'filing again made a second item')
    const again = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v1)
    must(again.name === first.name, 'the same file sent again was attached a second time')
    must((await s.api('inbox.get', { item: item.name })).files.length === 1, 'the item has more than one attachment')
    await s.open(`/life/brain/review/${item.name}?tab=original`) // phones open on the summary
    must(await pg.locator(`${original} a[href="${first.file_url}"]`).count() === 1, 'the review does not show the one attachment once')
    must(!(await pg.locator('[data-file-versions]').count()), 'a file with one version shows versions')
    // a changed file of the same name: one current file and the old one as an earlier version
    await file(`I7 deck ${width} ${stamp}`, ext)
    const second = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v2)
    const got = await s.api('inbox.get', { item: item.name })
    must(got.files.length === 1 && got.files[0].file_url === second.file_url && got.files[0].versions.length === 1, 'not one current file with one earlier version: ' + JSON.stringify(got.files))
    await s.open(`/life/brain/review/${item.name}?tab=original`) // phones open on the summary
    const toggle = pg.locator('[data-file-versions-toggle]')
    must(/^2 versions, latest \d+ \w{3}$/.test((await toggle.innerText()).trim()), 'the versions line says: ' + (await toggle.innerText()))
    await toggle.click()
    const link = pg.locator('[data-file-version] a')
    must(await link.count() === 1, 'the earlier version is not listed')
    const href = await link.getAttribute('href')
    must(href === first.file_url, 'the earlier version links to ' + href)
    const [popup] = await Promise.all([pg.context().waitForEvent('page'), link.click()])
    await popup.waitForLoadState()
    must((await popup.locator('body').innerText()).includes('first version'), 'opening the earlier version did not show the old file')
    await popup.close()
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    must(!overflow, 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}


// Issue 8: an agent files a piece of work with one call (agent/fake_agent.py --file-job); it is one item in the Inbox
// (Needs you replaces it in issue 14), and its page shows Inputs, Outputs, the summary and the proposals
for (const width of WIDTHS) {
  const tag = `I8.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const title = `I8 deck ${width} ${stamp}`
  const fileJob = () => execFileSync('python3', [path.join(root, 'agent/fake_agent.py'), '--url', base, '--file-job', `i8-job-${width}-${stamp}`,
    '--title', title, '--space', SPACE], { env: { ...process.env, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' })
  await check('BRAIN.14', `${width} px: a job filed (twice) with the fake agent is one item in the Inbox; its page shows Inputs, Outputs, the summary and the proposals`, async () => {
    fileJob()
    fileJob() // filing the same job again updates it
    const found = await s.api('inbox.list', { space: SPACE, page_length: 10, filters: [['title', '=', title]] })
    must(found.total === 1, `${found.total} items with the job's title`)
    const item = found.items[0]
    must(item.status === 'To Review' && item.pending === 2, `the item is ${item.status} with ${item.pending} pending proposals`)
    await s.open('/life/brain/queue')
    const shown = await pg.locator('[data-row]', { hasText: title }).count()
    must(shown === 1, `the Inbox shows the job in ${shown} rows`)
    await s.open(`/life/brain/review/${item.name}?tab=original`) // phones open on the proposals
    must(await pg.locator('[data-review-outputs]').count() === 1, 'no Outputs section')
    for (const ext of ['txt', 'html'])
      must(await pg.locator('[data-review-original] a', { hasText: `${title}.${ext}` }).count() === 1, `the output ${title}.${ext} is not shown once`)
    const inputs = pg.locator('[data-review-inputs] [data-review-input]')
    must(await inputs.count() === 2, `${await inputs.count()} inputs shown`)
    const inputText = await pg.locator('[data-review-inputs]').innerText()
    must(inputText.includes('Standard sales deck.txt') && inputText.includes('Brand guidelines.txt'), 'the inputs are not named')
    must(!(await pg.locator('[data-review-original] a', { hasText: 'Standard sales deck.txt' }).count()), 'an input is listed as an output')
    must(await pg.locator('[data-review-filed-with]').count() === 1, 'the wiki page and chat log filed with it are not shown')
    await s.open(`/life/brain/review/${item.name}?tab=summary`)
    must((await pg.locator('body').innerText()).includes('An owner-first deck'), 'the summary is not shown')
    await s.open(`/life/brain/review/${item.name}?tab=proposals`)
    must(await pg.locator('[data-proposal="Pending"]').count() === 2, 'the two proposals are not shown')
    const overflow = await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    must(!overflow, 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}


// Issue 10: one page per capture at /item/<name>: where it came from, what came in, what the Brain made of it, the decisions
// waiting, what came of it and what is related. Its proposal cards are the Review screen's.
for (const width of WIDTHS) {
  const tag = `I10.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const title = `I10 capture ${width} ${stamp}`
  // an item with a file, a summary and three proposals from the fake agent; one is accepted, so two wait
  const made = await s.api('inbox.create_item', { title, space: SPACE, instruction: 'summarise and extract to-dos' })
  const id = made.name
  const pdfName = `i10-${width}-${stamp}.pdf`
  await s.upload('Life Inbox Item', id, pdfName, 'application/pdf', PDF)
  runAgent()
  const first = (await s.api('inbox.get', { item: id })).proposals[0]
  await s.api('review.decide', { proposal: first.name, decision: 'accept' })
  const section = (name) => pg.locator(`[data-item-section="${name}"]`)
  const openAll = async () => { // on a phone the folded sections are opened first
    const folded = pg.locator('[data-item-toggle][aria-expanded="false"]')
    for (let n = 0; n < 6 && await folded.count(); n++) await folded.first().click()
  }
  const settle = () => pg.waitForTimeout(700)

  await check('BRAIN.15', `${width} px: an item with a file, a summary, 2 waiting proposals and 1 accepted task shows every section right`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    const head = await pg.locator('[data-item-head]').innerText()
    must((await pg.locator('h1').first().innerText()).includes(title), 'the title is not in the header')
    must(head.includes('Upload') && head.includes('Private'), 'the header does not say the source and the space: ' + head)
    must(await section('came-in').locator('[data-file-view]', { hasText: pdfName }).count() === 1, 'the file is not under What came in once')
    must((await section('came-in').innerText()).includes('summarise and extract to-dos'), 'the instruction is not under What came in')
    must((await section('brain').innerText()).includes('summarised'), 'the summary is not under What the Brain made of it')
    must(await section('decisions').locator('[data-proposal="Pending"]').count() === 2, 'Decisions does not show the 2 waiting proposals')
    must(!(await section('decisions').locator('[data-proposal="Accepted"]').count()), 'an accepted proposal is still under Decisions')
    const rows = section('came-of-it').locator('[data-came-of-it]')
    must(await rows.count() === 1, `What came of it shows ${await rows.count()} records`)
    const row = await rows.first().innerText()
    must(row.includes(first.preview) && row.includes('Task') && row.includes('Open'), 'the accepted task is not shown with its state: ' + row)
    must(await section('related').count() === 1, 'no Related section')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check('BRAIN.16', `${width} px: accepting a proposal on the item page moves it to What came of it without a reload`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    await pg.evaluate(() => { window.__i10 = 1 })
    const card = section('decisions').locator('[data-proposal="Pending"]').first()
    const preview = (await card.locator('.text-base-medium').first().innerText()).trim()
    await card.getByRole('button', { name: 'Accept', exact: true }).click()
    await settle()
    must(await pg.evaluate(() => window.__i10 === 1), 'the page reloaded')
    must(await section('decisions').locator('[data-proposal="Pending"]').count() === 1, 'the accepted proposal is still waiting')
    const rows = await section('came-of-it').locator('[data-came-of-it]').allInnerTexts()
    must(rows.length === 2 && rows.some((r) => r.includes(preview)), `What came of it does not list "${preview}": ${rows.join(' | ')}`)
  })

  await check('BRAIN.17', `${width} px: the item page opens from the Inbox list, from Library and from search`, async () => {
    const full = async (from, what) => {
      await s.open(from)
      await pg.locator('[data-pane-full]').click()
      await settle()
      must(new URL(pg.url()).pathname === `/life/item/${id}`, `Open full page from ${what} went to ${new URL(pg.url()).pathname}`)
      must(await pg.locator('[data-item-page]').count() === 1, `the item page did not show from ${what}`)
    }
    await s.open('/life/brain/queue')
    const row = pg.locator('[data-row]', { hasText: title }).first()
    must(await row.count() === 1, 'the item is not in the Inbox list')
    await row.locator('[data-ref]').first().click()
    await settle()
    await pg.locator('[data-pane-full]').click()
    await settle()
    must(new URL(pg.url()).pathname === `/life/item/${id}`, 'the Inbox list did not lead to the item page')
    await full(`/life/brain/captures?open=${encodeURIComponent('source:' + id)}`, 'Library')
    await s.open('/life/library/notes')
    if (width < 768) await pg.locator('[data-phone-search]').click()
    else await pg.keyboard.press('Meta+k')
    await pg.locator('input[aria-label="Search or ask anything"]').fill(title)
    await pg.waitForTimeout(900)
    await pg.keyboard.press('Enter')
    await settle()
    must(new URL(pg.url()).pathname === `/life/item/${id}`, 'the search result did not open the item page: ' + new URL(pg.url()).pathname)
  })

  await check('BRAIN.18', `${width} px: a user without access to the item's space gets "Not found" rather than its content`, async () => {
    const f = await session('family@lifeos.test', width)
    try {
      await f.open(`/life/item/${id}`)
      must(await f.page.locator('[data-item-missing]').isVisible(), 'the page does not say Not found')
      const text = await f.page.locator('body').innerText()
      must(!text.includes(title) && !text.includes(pdfName) && !text.includes('summarised'), 'the page shows the item to a user outside its space')
      const r = await f.api('inbox.item_page', { item: id }, { raw: true })
      must(r.status() === 404, 'the API answers ' + r.status())
    } finally {
      await f.ctx.close()
    }
  })

  await check('BRAIN.19', `${width} px: the item page is one column with no sideways scroll`, async () => {
    await s.open(`/life/item/${id}`)
    await openAll()
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    const lefts = await pg.locator('[data-item-section]').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)))
    must(lefts.length === 5 && new Set(lefts).size === 1, 'the sections are not one column: ' + lefts.join(', '))
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.ctx.close()
}


// Issue 17: Brain > Needs you. Titles start "I17 " (known to the debris finder). Other waiting captures of the space are put
// aside (archived) for each width and brought back after, so the rows and the numbers are this check's alone.
for (const width of WIDTHS) {
  const tag = `I17.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I17 ${what} ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
area = lambda n: frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": n})
tea, mind, career = area("Tea & Coffee"), area("Mind"), area("Career")
was = {n: frappe.db.get_value("Life Area", n, "is_on") for n in (tea, mind, career)}
for n in (tea, mind, career): frappe.db.set_value("Life Area", n, "is_on", 1)
aside = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0, "status": ["in", ["To Review", "Failed", "New", "Processing"]]}, pluck="name")
for n in aside: frappe.db.set_value("Life Inbox Item", n, "is_archived", 1, update_modified=False)
print(json.dumps({"tea": tea, "mind": mind, "career": career, "was": was, "aside": aside, "tea_name": "Tea & Coffee", "mind_name": "Mind"}))`).split('\n').pop())
  // a capture waiting for a decision, with one proposal: { kind, area, alt, reason, hours, source, status }
  const mk = (what, o = {}) => JSON.parse(bench(`import json
from frappe.utils import add_to_date, now_datetime
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T(what)}", "source_type": "${o.source || 'Email'}", "status": "${o.status || 'To Review'}",
  "received_on": add_to_date(now_datetime(), hours=-${o.hours ?? 1})${o.error ? `, "error": "${o.error}"` : ''}}).insert(ignore_permissions=True)
out = {"item": item.name}
if "${o.status || 'To Review'}" == "To Review":
    body = {"title": "${T(what)}"${o.kind === 'Reading' ? ', "goal": "x", "value": 1, "excerpt": "x"' : ''}${o.area ? `, "area": ${JSON.stringify(o.area)}` : ''}}
    p = frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": item.name, "kind": "${o.kind || 'Task'}", "preview": "${T(what)}",
      "payload": frappe.as_json(body), "confidence": 0.6, "status": "Pending", "reason": ${o.reason ? JSON.stringify(o.reason) : 'None'}, "alt_area": ${o.alt ? JSON.stringify(o.alt) : 'None'}}).insert(ignore_permissions=True)
    out["proposal"] = p.name
print(json.dumps(out))`).split('\n').pop())
  const row = (p) => pg.locator(`[data-needs-row][data-proposal="${p}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openNeeds = async () => { await s.open('/life/brain'); await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(400) }
  const rowsOf = async () => (await s.api('brain.needs_you', { space: SPACE })).rows
  const queue = async () => { for (const r of await rowsOf()) await s.api('review.decide', { proposal: r.proposal, decision: 'reject' }) }
  try {
    await check('BRAIN.20', `${width} px: on an empty space Needs you says what will appear and offers + Capture`, async () => {
      await openNeeds()
      must(await pg.locator('[data-needs-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-needs-empty]').innerText()
      must(t.includes('Nothing needs you.') && t.includes('Things you capture or connect will show up here.'), 'the empty state says: ' + t)
      await pg.locator('[data-needs-capture]').click()
      await pg.locator('[data-capture-text]').first().waitFor({ timeout: 5000 })
      await pg.keyboard.press('Escape')
      await noSideways()
    })
    await check('BRAIN.21', `${width} px: with 3 waiting captures (one with two possible areas) Needs you shows 3 rows with their best guesses and reasons`, async () => {
      const a = await mk('voice', { area: made.mind, reason: 'Sounds like a task, but no date was said', hours: 3, source: 'Voice Note' })
      const b = await mk('torn', { area: made.tea, alt: made.mind, reason: 'Mentions both Tea and Mind', hours: 2 })
      const c = await mk('plain', { area: made.career, hours: 1 })
      await openNeeds()
      must((await pg.locator('[data-needs-row]').count()) === 3, `${await pg.locator('[data-needs-row]').count()} rows, not 3`)
      const ra = await row(a.proposal).innerText(), rb = await row(b.proposal).innerText(), rc = await row(c.proposal).innerText()
      must(ra.includes(T('voice')) && ra.includes('✦ Sounds like a task, but no date was said') && ra.includes('Best guess:') && ra.includes('Task') && ra.includes('Mind'), 'row 1: ' + ra)
      must(rb.includes('Mentions both Tea and Mind') && rb.includes('Tea & Coffee') && /\bor\b/.test(rb) && rb.includes('Mind'), 'row 2: ' + rb)
      must(rc.includes('Career') && !rc.includes('✦'), 'row 3 (no reason, no mark): ' + rc)
      must((await row(b.proposal).locator('[data-area-chip]').count()) === 2 && (await row(a.proposal).locator('[data-area-chip]').count()) === 1, 'the area chips are wrong')
      must(await row(a.proposal).locator('[data-keep]').count() && await row(a.proposal).locator('[data-change]').count() && await row(a.proposal).locator('[data-drop]').count(), 'a row lacks Keep, Change or Drop')
      must(!(await row(b.proposal).locator('[data-keep]').count()) && (await row(b.proposal).locator('[data-pick]').count()) === 2, 'the torn row has Keep, or not two choices')
      must((await pg.locator('[data-stat-needs]').getAttribute('data-n')) === '3', 'the Needs you number is not 3')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      made.k = { a, b, c }
    })
    await check('BRAIN.22', `${width} px: Keep accepts the proposal, the row leaves, and the record exists with the guessed area`, async () => {
      const { a } = made.k
      await openNeeds()
      await row(a.proposal).locator('[data-keep]').click()
      await row(a.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const got = JSON.parse(bench(`import json
p = frappe.get_doc("Life Proposal", "${a.proposal}")
print(json.dumps({"status": p.status, "area": frappe.db.get_value(p.created_doctype, p.created_name, "area"), "dt": p.created_doctype}))`).split('\n').pop())
      must(got.status === 'Accepted' && got.dt === 'Life Task' && got.area === made.mind, 'after Keep: ' + JSON.stringify(got))
    })
    await check('BRAIN.23', `${width} px: picking the second of two area chips files it there`, async () => {
      const { b } = made.k
      await openNeeds()
      await row(b.proposal).locator('[data-pick="second"]').click()
      await row(b.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const area = bench(`p = frappe.get_doc("Life Proposal", "${b.proposal}")
print(p.status, frappe.db.get_value(p.created_doctype, p.created_name, "area"))`).split('\n').pop()
      must(area === `Accepted ${made.mind}`, 'after the second chip: ' + area)
    })
    await check('BRAIN.24', `${width} px: Drop discards it and it appears in the Outbox as Discarded`, async () => {
      const { c } = made.k
      await openNeeds()
      await row(c.proposal).locator('[data-drop]').click()
      await row(c.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const listed = await s.api('outbox.list', { space: SPACE, pile: 'Discarded', page_length: 500 })
      must(listed.rows.some((r) => r.record === c.item), 'the capture is not in the Outbox as Discarded')
      await s.open('/life/brain/outbox?pile=Discarded')
      await pg.waitForFunction((t) => document.body.innerText.includes(t), T('plain'), { timeout: 10000 })
    })
    await check('BRAIN.25', `${width} px: Done, file all files every row in one go`, async () => {
      const rows = []
      for (let i = 0; i < 3; i++) rows.push(await mk(`all ${i}`, { area: made.tea, hours: 3 - i }))
      await openNeeds()
      const label = await pg.locator('[data-file-all]').innerText()
      must(label.includes('Done, file all 3'), 'the button says: ' + label)
      await pg.locator('[data-file-all]').click()
      await pg.locator('[data-needs-empty]').waitFor({ timeout: 10000 })
      const states = bench(`print(",".join(frappe.db.get_value("Life Proposal", n, "status") for n in ${JSON.stringify(rows.map((r) => r.proposal))}))`).split('\n').pop()
      must(states === 'Accepted,Accepted,Accepted', 'after Done, file all: ' + states)
    })
    await check('BRAIN.26', `${width} px: with more than 7 waiting, 7 show and the rest come in as rows are cleared`, async () => {
      const rows = []
      for (let i = 0; i < 9; i++) rows.push(await mk(`many ${i}`, { area: made.tea, hours: 20 - i }))
      await openNeeds()
      must((await pg.locator('[data-needs-row]').count()) === 7, `${await pg.locator('[data-needs-row]').count()} rows, not 7`)
      must((await pg.locator('[data-stat-needs]').getAttribute('data-n')) === '9', 'the Needs you number is not 9')
      must(!(await row(rows[7].proposal).count()), 'the eighth is already shown')
      await row(rows[0].proposal).locator('[data-drop]').click()
      await row(rows[7].proposal).waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-row]').count()) === 7, 'a row did not come in')
      await row(rows[1].proposal).locator('[data-drop]').click()
      await row(rows[8].proposal).waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-row]').count()) === 7, 'the ninth did not come in')
      await queue()
    })
    await check('BRAIN.27', `${width} px: the two numbers match the captures of the last 24 hours`, async () => {
      await queue()
      const before = await s.api('brain.needs_you', { space: SPACE })
      bench(`from frappe.utils import add_to_date, now_datetime
def mk(title, source, hours, area=None):
    frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": title, "source_type": source, "status": "Done", "area": area,
      "received_on": add_to_date(now_datetime(), hours=-hours)}).insert(ignore_permissions=True)
mk("${T('own 1')}", "Email", 2, "${made.tea}")
mk("${T('own 2')}", "Chat", 4, "${made.mind}")
mk("${T('own 3')}", "Email", 5, "${made.tea}")
mk("${T('old')}", "Email", 30, "${made.tea}")`)
      const after = await s.api('brain.needs_you', { space: SPACE })
      must(after.came_in.count === before.came_in.count + 3, `came in: ${before.came_in.count} then ${after.came_in.count}`)
      must(after.filed.count === before.filed.count + 3, `filed: ${before.filed.count} then ${after.filed.count}`)
      // the server's numbers are the captures of the last 24 hours
      const truth = JSON.parse(bench(`import json
from frappe.utils import add_to_date, now_datetime
rows = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0, "received_on": [">=", add_to_date(now_datetime(), hours=-24)]}, fields=["source_type"])
print(json.dumps({"n": len(rows), "sources": len({r.source_type for r in rows})}))`).split('\n').pop())
      must(truth.n === after.came_in.count && truth.sources === after.came_in.sources, `the server says ${after.came_in.count} from ${after.came_in.sources}; the captures say ${JSON.stringify(truth)}`)
      await openNeeds()
      must((await pg.locator('[data-stat-came-in]').getAttribute('data-n')) === String(after.came_in.count), 'the screen shows another number for came in')
      must((await pg.locator('[data-stat-came-in]').innerText()).includes(`from ${after.came_in.sources} source`), 'the sources are not shown')
      must((await pg.locator('[data-stat-filed]').getAttribute('data-n')) === String(after.filed.count), 'the screen shows another number for filed on its own')
      await pg.locator('[data-see-activity]').click()
      await pg.waitForURL((u) => u.pathname === '/life/brain/activity', { timeout: 10000 })
    })
    await check('BRAIN.28', `${width} px: each row stacks at 390 px, with Keep, Change and Drop reachable and no sideways scroll`, async () => {
      const r = await mk('stack', { area: made.tea, reason: 'A long reason that needs room to wrap on a phone, with more words than fit on one line', hours: 1 })
      await openNeeds()
      const rw = row(r.proposal)
      await rw.waitFor({ timeout: 10000 })
      const box = await rw.boundingBox()
      for (const sel of ['[data-keep]', '[data-change]', '[data-drop]']) {
        const b = await rw.locator(sel).boundingBox()
        must(b && b.x >= 0 && b.x + b.width <= width + 1 && b.y >= box.y && b.y + b.height <= box.y + box.height + 1, `${sel} is not inside the row (${JSON.stringify(b)})`)
      }
      if (phone) {
        const text = await rw.locator('[data-row-title]').boundingBox(), acts = await rw.locator('[data-row-actions]').boundingBox()
        must(acts.y >= text.y + text.height - 1, 'on a phone the actions do not sit under the text')
      }
      await noSideways()
      await rw.locator('[data-change]').click()
      await pg.waitForURL((u) => u.pathname.startsWith('/life/item/'), { timeout: 10000 })
      await queue()
    })
    await check('BRAIN.29', `${width} px: an agent's proposal with alt_area shows two area chips; picking the second files it in that area`, async () => {
      const out = JSON.parse(bench(`import json
from lifeos.api import inbox
frappe.set_user("owner@lifeos.test")
it = inbox.create_item(title="${T('agent')}", space="${SPACE}", raw_text="Mentions both", source_type="Email")
frappe.set_user("hermes@lifeos.test")
from lifeos import permissions
permissions.clear_cache()
inbox.claim_next(space="${SPACE}")
res = inbox.submit_result(item=it["name"], proposals=[{"kind": "Task", "preview": "${T('agent')}", "confidence": 0.6, "reason": "Mentions both Tea and Mind",
  "payload": {"title": "${T('agent')}", "area": "${made.tea}"}, "alt_area": "${made.mind}"}])
print(json.dumps({"item": it["name"], "proposal": res["created"][0]["name"], "errors": res["errors"]}))`).split('\n').pop())
      must(!out.errors.length, 'the agent was refused: ' + JSON.stringify(out.errors))
      await openNeeds()
      const rw = row(out.proposal)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-area-chip]').count()) === 2, 'not two area chips')
      await rw.locator('[data-pick="second"]').click()
      await rw.waitFor({ state: 'detached', timeout: 10000 })
      const area = bench(`p = frappe.get_doc("Life Proposal", "${out.proposal}")
print(p.status, frappe.db.get_value(p.created_doctype, p.created_name, "area"))`).split('\n').pop()
      must(area === `Accepted ${made.mind}`, 'filed as: ' + area)
    })
    await check('BRAIN.30', `${width} px: a Reading proposal shows as Read later`, async () => {
      const r = await mk('reading', { kind: 'Reading', hours: 1 })
      await openNeeds()
      const rw = row(r.proposal)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-row-kind]').innerText()) === 'Read later', 'the kind reads: ' + await rw.locator('[data-row-kind]').innerText())
      await queue()
    })
    await check('BRAIN.31', `${width} px: a capture that failed is listed under Unfiled with Retry, never lost`, async () => {
      const f = await mk('failed', { status: 'Failed', error: 'Could not read the file', source: 'Upload' })
      await openNeeds()
      const rw = pg.locator(`[data-failed-row][data-item="${f.item}"]`)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.innerText()).includes('Could not read the file') && (await rw.locator('[data-retry]').count()) === 1, 'the failed capture is not shown with Retry')
      await noSideways()
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for p in frappe.get_all("Life Proposal", filters={"preview": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Proposal", p, force=1, ignore_permissions=True)
for t in frappe.get_all("Life Task", filters={"title": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I17 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}:
    if frappe.db.exists("Life Inbox Item", n): frappe.db.set_value("Life Inbox Item", n, "is_archived", 0, update_modified=False)
for n, v in ${JSON.stringify(made.was)}.items(): frappe.db.set_value("Life Area", n, "is_on", v)`)
    await s.ctx.close()
  }
}


// Issue 18: Brain > Activity. Titles start "I18 " (known to the debris finder). The space's other captures are put aside (archived)
// for each width and brought back after, so the feed holds this check's captures alone.
for (const width of WIDTHS) {
  const tag = `I18.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I18 ${what} ${width} ${stamp}`
  const made = JSON.parse(bench(`import json
tea = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
was = frappe.db.get_value("Life Area", tea, "is_on")
frappe.db.set_value("Life Area", tea, "is_on", 1)
aside = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "is_archived": 0}, pluck="name")
for n in aside: frappe.db.set_value("Life Inbox Item", n, "is_archived", 1, update_modified=False)
print(json.dumps({"tea": tea, "was": was, "aside": aside}))`).split('\n').pop())
  const mk = (what, o = {}) => JSON.parse(bench(`import json
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T(what)}", "source_type": "${o.source || 'Email'}", "status": "${o.status || 'Done'}",
  "received_on": frappe.utils.now_datetime()${o.error ? `, "error": "${o.error}"` : ''}${o.area ? `, "area": "${o.area}"` : ''}}).insert(ignore_permissions=True)
out = {"item": item.name}
${o.task ? `t = frappe.get_doc({"doctype": "Life Task", "space": "${SPACE}", "title": "${T(what)}", "area": "${o.area}", "inbox_item": item.name}).insert(ignore_permissions=True)
p = frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": item.name, "kind": "Task", "preview": "${T(what)}",
  "payload": frappe.as_json({"title": "${T(what)}"}), "status": "Pending"}).insert(ignore_permissions=True)
frappe.db.set_value("Life Proposal", p.name, {"status": "Accepted", "created_doctype": "Life Task", "created_name": t.name})
out["task"] = t.name` : ''}
print(json.dumps(out))`).split('\n').pop())
  const row = (i) => pg.locator(`[data-activity-row][data-item="${i}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openFeed = async (q = '') => { await s.open('/life/brain/activity' + q); await pg.locator('[data-activity]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(500) }
  try {
    await check('BRAIN.32', `${width} px: on a space with nothing captured Activity says what will appear and offers + Capture`, async () => {
      await openFeed()
      must(await pg.locator('[data-activity-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-activity-empty]').innerText()
      must(t.includes('Nothing has come in yet.') && t.includes('will show up here'), 'the empty state says: ' + t)
      await pg.locator('[data-activity-capture]').click()
      await pg.locator('[data-capture-text]').first().waitFor({ timeout: 5000 })
      await pg.keyboard.press('Escape')
      await noSideways()
    })
    await check('BRAIN.33', `${width} px: a capture filed on its own today shows under Today with its area and a link to the record`, async () => {
      const a = await mk('filed', { area: made.tea, task: true })
      made.a = a
      await openFeed()
      const day = pg.locator('[data-activity-day]').first()
      must((await day.locator('h2').innerText()) === 'Today', 'the first group is not Today')
      const rw = row(a.item)
      await rw.waitFor({ timeout: 10000 })
      const t = await rw.innerText()
      must(t.includes(T('filed')) && t.includes('Tea & Coffee') && t.includes('Email'), 'the row says: ' + t)
      const href = await rw.locator('[data-made-link]').first().getAttribute('href')
      must(href && href.includes(a.task), 'the link to the record is ' + href)
      must((await rw.locator('[data-row-item]').getAttribute('href')) === `/life/item/${a.item}`, 'the item page link is wrong')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.34', `${width} px: the source filter narrows the feed to that source`, async () => {
      const v = await mk('voice', { source: 'Voice Note' })
      await openFeed()
      must(await row(v.item).count() && await row(made.a.item).count(), 'both captures should be listed first')
      await pg.locator('[data-activity-source]').selectOption('Voice Note')
      await pg.waitForTimeout(600)
      must(new URL(pg.url()).searchParams.get('source') === 'Voice Note', 'the filter is not in the URL')
      must((await row(v.item).count()) === 1 && (await row(made.a.item).count()) === 0, 'the feed is not narrowed to Voice Note')
      const sources = await pg.locator('[data-activity-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-source')))
      must(sources.every((x) => x === 'Voice Note'), 'other sources remain: ' + sources)
      await pg.locator('[data-outcome="dropped"]').click()
      await pg.waitForTimeout(500)
      must((await pg.locator('[data-activity-row]').count()) === 0, 'Dropped should hold nothing here')
    })
    await check('BRAIN.35', `${width} px: a failed capture shows its reason and Retry puts it back in the queue`, async () => {
      const f = await mk('failed', { status: 'Failed', error: 'Could not read the file', source: 'Upload' })
      await openFeed('?outcome=failed')
      const rw = row(f.item)
      await rw.waitFor({ timeout: 10000 })
      must((await rw.locator('[data-row-reason]').innerText()).includes('Could not read the file'), 'the reason is not shown')
      await rw.locator('[data-retry]').click()
      await pg.waitForTimeout(800)
      const status = bench(`print(frappe.db.get_value("Life Inbox Item", "${f.item}", "status"))`).split('\n').pop()
      must(status === 'New', 'the status is ' + status)
      must((await row(f.item).count()) === 0, 'it is still listed as failed')
    })
    await check('BRAIN.36', `${width} px: the Outbox piles in Activity show the same numbers as the Outbox`, async () => {
      await openFeed()
      const listed = (await s.api('outbox.list', { space: SPACE, pile: 'all', period: 'week', page_length: 1 })).tabs
      for (const pile of ['Done', 'Delegated', 'Parked', 'Discarded']) {
        const n = await pg.locator(`[data-plate-pile][data-pile="${pile}"]`).getAttribute('data-n')
        must(Number(n) === listed[pile], `${pile}: Activity says ${n}, the Outbox ${listed[pile]}`)
      }
      must((await pg.locator('[data-flow-in]').innerText()) === String(listed.in) && (await pg.locator('[data-flow-out]').innerText()) === String(listed.all), 'the flow line differs')
      await pg.locator('[data-plate-pile][data-pile="Done"]').click()
      await pg.waitForURL((u) => u.pathname === '/life/brain/outbox' && u.searchParams.get('pile') === 'Done', { timeout: 10000 })
      await pg.locator('[data-outbox-sub]').waitFor({ timeout: 10000 })
    })
    await check('BRAIN.37', `${width} px: the feed is one column and nothing scrolls sideways`, async () => {
      await openFeed()
      await noSideways()
      const boxes = await pg.locator('[data-activity-row]').evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.width] }))
      must(boxes.length > 0, 'no rows')
      must(boxes.every(([x, w]) => Math.abs(x - boxes[0][0]) < 1 && Math.abs(w - boxes[0][1]) < 1), 'the rows are not one column')
      if (phone) must(boxes[0][1] <= width, 'a row is wider than the screen')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for p in frappe.get_all("Life Proposal", filters={"preview": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Proposal", p, force=1, ignore_permissions=True)
for t in frappe.get_all("Life Task", filters={"title": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Task", t, force=1, ignore_permissions=True)
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I18 % ${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}:
    if frappe.db.exists("Life Inbox Item", n): frappe.db.set_value("Life Inbox Item", n, "is_archived", 0, update_modified=False)
frappe.db.set_value("Life Area", "${made.tea}", "is_on", ${made.was ? 1 : 0})`)
    await s.ctx.close()
  }
}


// Issue 19: Brain > Sources. Titles start "I19 ". The space's own connections are put aside (their space renamed) for each width and
// brought back after, so the cards are this check's alone.
for (const width of WIDTHS) {
  const tag = `I19.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const ASIDE = `zz-i19-aside-${width}`
  const made = JSON.parse(bench(`import json
tea = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Tea & Coffee"})
was = frappe.db.get_value("Life Area", tea, "is_on")
frappe.db.set_value("Life Area", tea, "is_on", 1)
aside = frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name")
for n in aside: frappe.db.set_value("Life Connection", n, "space", "${ASIDE}", update_modified=False)
print(json.dumps({"tea": tea, "was": was, "aside": aside}))`).split('\n').pop())
  const card = (sys) => pg.locator(`[data-source-card][data-system="${sys}"]`)
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openSources = async () => { await s.open('/life/brain/sources'); await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const capture = (title, system, extra = {}) => s.api('inbox.create_item', { space: SPACE, title: `I19 ${title} ${width} ${stamp}`, source_system: system, ...extra })
  try {
    await check('BRAIN.38', `${width} px: with no source connected Sources says what will appear and offers Add a source`, async () => {
      await openSources()
      must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-sources-empty]').innerText()
      must(t.includes('Nothing is connected yet.') && t.includes('switch them on below'), 'the empty state says: ' + t)
      must(await pg.locator('[data-source-tile][data-system="upload"]').innerText().then((x) => x.includes('Always on')), 'the Upload tile is missing')
      await pg.locator('[data-add-source-empty]').click()
      await pg.locator('[data-add-more]').waitFor({ state: 'visible' })
      await noSideways()
    })
    await check('BRAIN.39', `${width} px: connected sources show with this week's counts, matching the captures in the database`, async () => {
      for (const n of [1, 2, 3]) await capture(`hermes ${n}`, 'hermes')
      await capture('gmail 1', 'gmail')
      await openSources()
      must((await pg.locator('[data-source-card]').count()) === 2, 'expected two cards, got ' + await pg.locator('[data-source-card]').count())
      must((await pg.locator('[data-connected-count]').innerText()) === '2', 'the count in the heading is wrong')
      for (const sys of ['hermes', 'gmail']) {
        const n = bench(`from frappe.utils import add_days, getdate
d = getdate()
print(frappe.db.count("Life Inbox Item", {"space": "${SPACE}", "source_system": "${sys}", "creation": [">=", add_days(d, -d.weekday())]}))`).split('\n').pop()
        const shown = await card(sys).getAttribute('data-week')
        must(shown === n && n !== '0', `${sys}: the card says ${shown}, the database ${n}`)
        must((await card(sys).locator('[data-source-line]').innerText()).includes(`${n} this week`), `${sys}: the line does not say ${n} this week`)
      }
      must((await card('hermes').innerText()).includes('Agent · Telegram'), 'the kind of Hermes is missing')
      must((await card('gmail').innerText()).includes('only people, not newsletters'), 'the Gmail note is missing')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.40', `${width} px: switching Hermes off makes create_item from hermes fail with a clear message; switching it on again works`, async () => {
      await openSources()
      await card('hermes').locator('button[role="switch"]').click()
      await pg.waitForTimeout(800)
      must((await card('hermes').getAttribute('data-active')) === '0', 'the card still says On')
      const r = await s.api('inbox.create_item', { space: SPACE, title: `I19 refused ${width} ${stamp}`, source_system: 'hermes' }, { raw: true })
      const text = await r.text()
      must(!r.ok() && text.includes('switched off'), `create_item answered ${r.status()}: ${text.slice(0, 200)}`)
      must(bench(`print(frappe.db.count("Life Inbox Item", {"title": "I19 refused ${width} ${stamp}"}))`).split('\n').pop() === '0', 'the refused capture was stored')
      must((await (await s.api('inbox.create_item', { space: SPACE, title: `I19 upload ${width} ${stamp}`, source_system: 'upload' })).title).includes('upload'), 'Upload should always work')
      await card('hermes').locator('button[role="switch"]').click()
      await pg.waitForTimeout(800)
      must((await card('hermes').getAttribute('data-active')) === '1', 'the card still says Off')
      const ok = await capture('back on', 'hermes')
      must(ok.created, 'create_item should work again')
      must((await card('hermes').getAttribute('data-week')) !== null && bench(`print(frappe.db.count("Life Inbox Item", {"title": ["like", "I19 hermes %${width} ${stamp}"]}))`).split('\n').pop() === '3', 'what Hermes brought earlier was deleted')
    })
    await check('BRAIN.41', `${width} px: a Coming tile cannot be switched on`, async () => {
      await openSources()
      const tile = pg.locator('[data-tile-coming][data-system="github"]')
      must((await tile.innerText()).includes('Coming'), 'the GitHub tile does not say Coming')
      must((await tile.locator('button').count()) === 0, 'a Coming tile has a button')
      await tile.click({ force: true })
      await pg.waitForTimeout(500)
      must((await pg.locator('[data-source-settings]').count()) === 0 && (await card('github').count()) === 0, 'a Coming tile opened or added something')
      for (const sys of ['github', 'whatsapp', 'wearable', 'tally', 'drive', 'erpnext']) must(await pg.locator(`[data-tile-coming][data-system="${sys}"]`).count() === 1, sys + ' is missing')
      const r = await s.api('connections.save', { space: SPACE, system: 'github', active: 1 }, { raw: true })
      must(!r.ok() && (await r.text()).includes('not built yet'), 'the server switched GitHub on: ' + r.status())
    })
    await check('BRAIN.42', `${width} px: opening a source shows its default intent, area and goal, and saving changes what create_item uses`, async () => {
      await openSources()
      await card('gmail').locator('[data-source-open]').click()
      const dlg = pg.locator('[data-source-settings][data-system="gmail"]')
      await dlg.waitFor({ timeout: 5000 })
      must(await dlg.locator('[data-settings-intent]').count() && await dlg.locator('[data-settings-area]').count() && await dlg.locator('[data-settings-goal]').count(), 'intent, area or goal is missing')
      await dlg.locator('[data-settings-intent] [role="combobox"], [data-settings-intent] button').first().click()
      await pg.getByRole('option', { name: 'Just keep', exact: true }).first().click()
      await dlg.locator('[data-settings-area] button').click()
      await pg.getByRole('menuitem', { name: 'Tea & Coffee', exact: false }).first().click()
      await pg.getByRole('button', { name: 'Save' }).click()
      await pg.waitForTimeout(1000)
      const c = bench(`import json
print(json.dumps(frappe.db.get_value("Life Connection", {"space": "${SPACE}", "system": "gmail"}, ["default_intent", "default_area"], as_dict=True)))`).split('\n').pop()
      must(JSON.parse(c).default_intent === 'Just keep' && JSON.parse(c).default_area === made.tea, 'the defaults were not saved: ' + c)
      const item = await capture('defaults', 'gmail')
      must(item.intent === 'Just keep' && item.area === made.tea, `create_item used intent ${item.intent}, area ${item.area}`)
      await card('gmail').locator('[data-source-open]').click()
      await pg.locator('[data-source-settings][data-system="gmail"]').waitFor({ timeout: 5000 })
      must((await pg.locator('[data-source-settings] [data-settings-intent]').innerText()).includes('Just keep'), 'the saved intent is not shown when it is opened again')
      await pg.keyboard.press('Escape')
    })
    await check('BRAIN.43', `${width} px: ${phone ? 'the cards stack in one column' : 'the cards sit in a grid'} and nothing scrolls sideways`, async () => {
      await openSources()
      await noSideways()
      const boxes = await pg.locator('[data-source-card]').evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width] }))
      must(boxes.length >= 2, 'expected at least two cards')
      if (phone) must(boxes.every(([x, , w]) => Math.abs(x - boxes[0][0]) < 1 && w <= width), 'the cards do not stack')
      else must(Math.abs(boxes[1][1] - boxes[0][1]) < 1 && boxes[1][0] > boxes[0][0], 'the cards are not side by side')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`import json
frappe.set_user("Administrator")
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I19 %${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for c in frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Connection", c, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}: frappe.db.set_value("Life Connection", n, "space", "${SPACE}", update_modified=False)
frappe.db.set_value("Life Area", "${made.tea}", "is_on", ${made.was ? 1 : 0})`)
    await s.ctx.close()
  }
}


// Issue 58: Brain > Sources says who processes each source and offers Connect Gmail; a connected mailbox shows its week's counts; a capture the Brain
// could not process shows Retry and File it myself in Needs you. Titles start "I58 ". The space's own connections are put aside for each width
// and brought back after; the Brain is switched on for the check and off again (the acceptance site starts like one with an agent).
// I58.1 to I58.8 and I58.10 are unit tests (test_issue58_routing).
for (const width of WIDTHS) {
  const tag = `I58.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const ASIDE = `zz-i58-aside-${width}`
  const made = JSON.parse(bench(`import json
aside = frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name")
for n in aside: frappe.db.set_value("Life Connection", n, "space", "${ASIDE}", update_modified=False)
frappe.db.set_value("Life Skill", "process-capture", "active", 1)
print(json.dumps({"aside": aside}))`).split('\n').pop())
  const openSources = async () => { await s.open('/life/brain/sources'); await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  try {
    await check('BRAIN.44', `${width} px: Sources offers Connect Gmail, a connected mailbox shows its week's counts and "Processed by: the Brain", every card has a Processed by line`, async () => {
      await openSources()
      must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state on an empty space')
      must((await pg.locator('[data-source-tile][data-system="upload"] [data-processed-by]').innerText()).includes('Processed by: the Brain'), 'the Upload tile has no Processed by line')
      const tile = pg.locator('[data-source-tile][data-system="gmail"]')
      must((await tile.innerText()).includes('Connect Gmail'), 'the Gmail tile does not say Connect Gmail: ' + await tile.innerText())
      await tile.locator('[data-tile-add]').click()
      await pg.locator('[data-gmail-connect]').waitFor({ timeout: 5000 })
      const t = await pg.locator('[data-gmail-connect]').innerText()
      must(t.includes('read-only') && /never marks, labels, moves, deletes or sends/.test(t), 'the dialog does not say it is read only: ' + t)
      await pg.keyboard.press('Escape')
      bench(`from frappe.utils import add_days, getdate
d = getdate()
frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "gmail", "mailbox": "i58-${width}@example.com", "label": "i58-${width}@example.com", "active": 1,
  "week_start": add_days(d, -d.weekday()), "seen_week": 218, "kept_week": 31}).insert(ignore_permissions=True)
for system in ("hermes", "claude", "google-calendar"):
    frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": system, "active": 1}).insert(ignore_permissions=True)`)
      await openSources()
      const mail = pg.locator('[data-source-card][data-system="gmail"]')
      must((await mail.locator('[data-source-line]').innerText()).includes('218 this week · 31 kept'), 'the mailbox line says: ' + await mail.locator('[data-source-line]').innerText())
      must((await mail.locator('[data-processed-by]').innerText()) === 'Processed by: the Brain', 'the mailbox does not say the Brain processes it')
      const lines = await pg.locator('[data-source-card] [data-processed-by]').allInnerTexts()
      must(lines.length === 4 && lines.every((x) => /^(Processed by|Not processed)/.test(x)), 'every card needs a Processed by line: ' + lines.join(' | '))
      must(lines.includes('Processed by: Hermes') && lines.filter((x) => x === 'Not processed: kept as is').length === 2, 'the lines are wrong: ' + lines.join(' | '))
      await mail.locator('[data-source-open]').click()
      await pg.locator('[data-source-settings][data-system="gmail"]').waitFor({ timeout: 5000 })
      must(await pg.locator('[data-gmail-include]').isVisible() && await pg.locator('[data-gmail-skip]').isVisible(), 'the always include and always skip lists are missing')
      await pg.keyboard.press('Escape')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.45', `${width} px: a capture the Brain could not process is in Needs you with Retry and File it myself; File it myself takes it out`, async () => {
      const item = JSON.parse(bench(`import json
d = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "I58 not processed ${width} ${stamp}", "source_type": "Upload", "raw_text": "x", "status": "Failed",
  "error": "Not processed: no AI key"}).insert(ignore_permissions=True)
print(json.dumps(d.name))`).split('\n').pop())
      await s.open('/life/brain')
      const row = pg.locator(`[data-failed-row][data-item="${item}"]`)
      await row.waitFor({ timeout: 10000 })
      must((await row.innerText()).includes('Not processed: no AI key'), 'the reason is not shown')
      must(await row.locator('[data-retry]').isVisible() && await row.locator('[data-file-myself]').isVisible(), 'Retry and File it myself are not both shown')
      await row.locator('[data-file-myself]').click()
      await pg.waitForURL(new RegExp(`/item/${item}`), { timeout: 10000 })
      const status = bench(`print(frappe.db.get_value("Life Inbox Item", "${item}", "status"))`).split('\n').pop()
      must(status === 'Done', 'the capture is ' + status)
      await s.open('/life/brain')
      must(!(await pg.locator(`[data-failed-row][data-item="${item}"]`).count()), 'it is still in Needs you')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`frappe.set_user("Administrator")
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I58 %${width} ${stamp}"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)
for c in frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Connection", c, force=1, ignore_permissions=True)
for n in ${JSON.stringify(made.aside)}: frappe.db.set_value("Life Connection", n, "space", "${SPACE}", update_modified=False)
frappe.db.set_value("Life Skill", "process-capture", "active", 0)`)
    await s.ctx.close()
  }
}


// Brain > Sources in two groups and one page for each source: its strip, Rules (saved as a version of the skill), Try it. Titles start "I84 ".
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const pathOf = async () => (await pg.locator('[data-page-path]').innerText()).replace(/\s+/g, ' ').trim()
  const version = () => Number(bench('print(frappe.db.get_value("Life Skill", "ingest-document", "version"))').split('\n').pop())
  const openSources = async (query = '') => { await s.open('/life/brain/sources' + query); await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const pdfName = `I84 sample ${width} ${stamp}.pdf`
  try {
    await check('BRAIN.46', `${width} px: Sources shows channels and kinds with counts and switches; each row opens its page with the path Brain / Sources / <name>`, async () => {
      await openSources()
      const channels = Number(await pg.locator('[data-group-count="channels"]').innerText())
      must(channels >= 5 && (await pg.locator('[data-group-count="kinds"]').innerText()) === '6', `the counts are ${channels} and ${await pg.locator('[data-group-count="kinds"]').innerText()}`)
      must((await pg.locator('[data-group][aria-selected="true"]').getAttribute('data-group')) === 'channels', 'Channels is not the first group')
      await pg.locator('[data-group="kinds"]').click()
      await pg.locator('[data-kinds]').waitFor({ timeout: 5000 })
      must((await pg.locator('[data-kind-card]').count()) === 6, 'expected six kinds')
      must(!(await pg.locator('[data-connected]').count()), 'the channels still show with Kinds open')
      await pg.locator('[data-kind-card][data-kind="kind-document"] [data-kind-open]').click()
      await pg.locator('[data-source-page][data-source="kind-document"]').waitFor({ timeout: 10000 })
      must(/^Brain \/ Sources/.test(await pathOf()) && (await pg.locator('[data-page-title]').innerText()) === 'Documents (PDF)', 'the path says: ' + await pathOf())
      const strip = await pg.locator('[data-source-strip]').innerText()
      for (const word of ['Arrives from', 'This week', 'Filed without you', 'AI cost this week', 'Skill']) must(strip.includes(word), `the strip lacks ${word}: ${strip}`)
      must(strip.includes('ingest-document v'), 'the strip does not name the skill and its version')
      for (const t of ['Overview', 'Rules', 'Examples & lessons', 'Activity', 'Try it']) must(await pg.locator(`[data-tab-bar] >> text="${t}"`).first().isVisible(), `no ${t} tab`)
      await pg.locator('[data-page-back]').click()
      await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 })
      await openSources()
      await pg.locator('[data-source-tile][data-system="upload"] [data-tile-rules]').click()
      await pg.locator('[data-source-page][data-source="upload"]').waitFor({ timeout: 10000 })
      must((await pathOf()).startsWith('Brain / Sources') && (await pg.locator('[data-page-title]').innerText()) === 'Upload', 'the Upload path says: ' + await pathOf())
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.47', `${width} px: Rules: add a Skip chip and save to see version n+1, go back restores it; Try it on a sample PDF (fake AI) files nothing until File it for real`, async () => {
      await s.open('/life/brain/sources/kind-document?tab=rules')
      await pg.locator('[data-rule-section][data-section="Skip"]').waitFor({ timeout: 10000 })
      const before = version()
      const chip = `Fax cover sheets ${width}`
      await pg.locator('[data-section="Skip"] [data-chip-input]').fill(chip)
      await pg.locator('[data-section="Skip"] [data-chip-add]').click()
      must(await pg.locator(`[data-section="Skip"] [data-chip]:has-text("${chip}")`).count() === 1, 'the chip was not added')
      await pg.locator('[data-rules-anything]').fill('Ask before filing anything over Rs 1,00,000.')
      await pg.locator('[data-rules-save]').click()
      await pg.locator(`[data-rules-version]:has-text("Version ${before + 1}")`).waitFor({ timeout: 10000 })
      must(version() === before + 1, `the skill is at version ${version()}, expected ${before + 1}`)
      must(bench('print(frappe.db.get_value("Life Skill", "ingest-document", "instructions"))').includes(`- ${chip}`), 'the chip is not in the skill text')
      await pg.reload()
      await pg.locator(`[data-section="Skip"] [data-chip]:has-text("${chip}")`).waitFor({ timeout: 10000 })
      await pg.locator(`[data-version-row][data-version="${before}"] [data-version-back]`).click()
      await pg.locator(`[data-rules-version]:has-text("Version ${before + 2}")`).waitFor({ timeout: 10000 })
      must(!bench('print(frappe.db.get_value("Life Skill", "ingest-document", "instructions"))').includes(chip), 'going back did not restore the old text')
      // Try it
      const count = () => Number(bench(`print(frappe.db.count("Life Inbox Item", {"space": "${SPACE}", "title": ["like", "I84 sample%${stamp}%"]}))`).split('\n').pop())
      await s.open('/life/brain/sources/kind-document?tab=try')
      await pg.locator('[data-try-file]').setInputFiles({ name: pdfName, mimeType: 'application/pdf', buffer: PDF })
      await pg.locator('[data-try-drop]:has-text("I84 sample")').waitFor({ timeout: 10000 })
      await pg.locator('[data-try-run]').click()
      await pg.locator('[data-try-result], [data-sonner-toast][data-type="error"]').first().waitFor({ timeout: 30000 })
      if (!(await pg.locator('[data-try-result]').count())) must(false, 'Try it said: ' + await pg.locator('[data-sonner-toast]').first().innerText())
      must((await pg.locator('[data-try-summary]').innerText()).includes('stand-in model'), 'the summary says: ' + await pg.locator('[data-try-summary]').innerText())
      must((await pg.locator('[data-try-proposal]').count()) >= 1, 'no proposal shown')
      must((await pg.locator('[data-try-result]').innerText()).includes('ingest-document v'), 'the result does not name the skills used')
      must(count() === 0, 'Try it filed something')
      await pg.locator('[data-try-file-it]').click()
      await pg.locator('[data-try-result]').waitFor({ state: 'detached', timeout: 10000 })
      must(count() === 1, `File it for real made ${count()} captures`)
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.48', `${width} px: on a new site the sources say Nothing yet and how to connect each`, async () => {
      const aside = `zz-i84-aside-${width}`
      const moved = JSON.parse(bench(`import json
from frappe.utils import add_days, getdate
d = getdate()
names = frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "creation": [">=", add_days(d, -d.weekday())]}, pluck="name")
for n in names: frappe.db.set_value("Life Inbox Item", n, "space", "${aside}", update_modified=False)
conns = frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name")
for n in conns: frappe.db.set_value("Life Connection", n, "space", "${aside}", update_modified=False)
print(json.dumps({"names": names, "conns": conns}))`).split('\n').pop())
      try {
        await openSources('?group=kinds')
        for (const k of ['kind-document', 'kind-photo', 'kind-video', 'kind-link', 'kind-voice', 'kind-email'])
          must((await pg.locator(`[data-kind-card][data-kind="${k}"] [data-kind-line]`).innerText()) === 'Nothing yet', `${k} does not say Nothing yet`)
        await openSources()
        must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state')
        must(await pg.locator('[data-email-in]').isVisible(), 'the email-in address does not say how to set it up')
        for (const sys of ['gmail', 'google-calendar']) must((await pg.locator(`[data-source-tile][data-system="${sys}"]`).innerText()).length > 10, `${sys} has no hint`)
        await s.open('/life/brain/sources/gmail')
        await pg.locator('[data-source-page][data-source="gmail"]').waitFor({ timeout: 10000 })
        const t = await pg.locator('[data-source-connect]').innerText()
        must(t.includes('Nothing yet') && t.includes('Connect Gmail'), 'Gmail does not say how to connect: ' + t)
        must((await pg.locator('[data-strip="week"]').innerText()) === 'Nothing yet', 'the week does not say Nothing yet')
        await pg.locator('[data-tab="activity"]').click()
        await pg.locator('[data-activity-empty]').waitFor({ timeout: 5000 })
        await noSideways()
      } finally {
        bench(`for n in ${JSON.stringify(moved.names)}: frappe.db.set_value("Life Inbox Item", n, "space", "${SPACE}", update_modified=False)
for n in ${JSON.stringify(moved.conns)}: frappe.db.set_value("Life Connection", n, "space", "${SPACE}", update_modified=False)`)
      }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`frappe.set_user("Administrator")
for i in frappe.get_all("Life Inbox Item", filters={"title": ["like", "I84 %${stamp}%"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", i, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}
