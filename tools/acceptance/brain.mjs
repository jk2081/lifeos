// Brain: capture, Needs you, Activity, Sources, the item page, Chat and the fake agent.
// Checks are numbered BRAIN.<n> in the order they appear here; `node tools/acceptance.mjs --only=BRAIN` runs this file's checks.
import { PDF, SPACE, WIDTHS, agentFetch, agentKey, agentSecret, areaId, areas, base, bench, browser, chatOff, chatOn, check, env, execFileSync, fs, must, owner, path, pathOf, root, runAgent, session, stamp, today } from './context.mjs'
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
  await owner.open('/life/brain/queue?open=inbox:' + item.name + '&ptab=decisions') // issue 118: the proposals are on the Decisions tab
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
  // the word is in the transcript, the stamp in the title of this run's item. Global Search is written by a background job after the save
  // (and since issue 104 the same worker reads the files first), so on a slow runner the item appears a little late: wait up to a minute
  let found = false
  for (let i = 0; i < 30 && !found; i++) {
    const res = await owner.api('search.query', { text: `Nowrojee ${stamp}` })
    found = res.results.some((r) => r.ref_doctype === 'Life Inbox Item' && r.ref_name === photoItem)
    if (!found) await owner.page.waitForTimeout(2000)
  }
  must(found, 'the inbox item was not found')
  await owner.page.keyboard.press('/')
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
  await owner.open('/life/brain/queue?open=inbox:' + item.items[0].name + '&ptab=decisions')
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
  await check('BRAIN.8', `${width} px: Chat: from Today, Today under an area, a goal page and a record pane, the chip names the scope of the screen; the panel closes and the screen is as it was`, async () => {
    const done = []
    // set 6: the area page became the lens (Chat's scope is the lens), the project page the goal's page
    for (const [path, scope] of [['/life', 'Everything in this space'], ['/life?area=' + uxArea, areas.find((x) => x.name === uxArea).area_name],
      ['/life/goals/' + ux.goal, 'About: ' + ux.goalTitle]]) {
      await askOn(path, scope)
      const here = new URL(pg.url()).pathname
      if (!phone) { await pg.locator('[data-ask-close]').click(); await settle() } else { await pg.keyboard.press('Escape'); await settle() }
      must(!(await pg.locator('[data-ask-panel]:visible').count()), `${path}: the panel did not close`)
      must(new URL(pg.url()).pathname === here && here.replace(/\/$/, '') === (path.split('?')[0] === '/life' ? '/life/today' : path.split('?')[0]), `${path}: the screen changed under the panel (${new URL(pg.url()).pathname})`)
      done.push(scope)
    }
    // a record pane: Chat about this
    const task = await s.api('tasks.quick_add', { text: S5('chat about'), space: SPACE, area: uxArea })
    await s.open(`/life/goals/tasks?view=list&status=all&f=${encodeURIComponent(JSON.stringify([['title', 'like', `%${S5('chat about')}%`]]))}`)
    await pg.locator(`[data-ref="task:${task.name}"]`).first().click()
    await settle()
    await pg.locator('[data-pane-ask]').click()
    await settle()
    must((await pg.locator('[data-ask-scope]:visible').first().innerText()).trim() === 'About: ' + S5('chat about'), 'Chat about this does not take the record as its scope')
    return done.join(', ') + ', a task pane'
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
    await s.open(`/life/brain/review/${item.name}?tab=file`) // issue 118: a file with no text opens under File
    must(await pg.locator(`${original} a[href="${first.file_url}"]`).count() === 1, 'the review does not show the one attachment once')
    must(!(await pg.locator('[data-file-versions]').count()), 'a file with one version shows versions')
    // a changed file of the same name: one current file and the old one as an earlier version
    await file(`I7 deck ${width} ${stamp}`, ext)
    const second = await s.upload('Life Inbox Item', item.name, 'BTW standard deck.txt', 'text/plain', v2)
    const got = await s.api('inbox.get', { item: item.name })
    must(got.files.length === 1 && got.files[0].file_url === second.file_url && got.files[0].versions.length === 1, 'not one current file with one earlier version: ' + JSON.stringify(got.files))
    await s.open(`/life/brain/review/${item.name}?tab=file`) // issue 118: a file with no text opens under File
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
    await s.open(`/life/brain/review/${item.name}?tab=original`) // issue 118: the outputs are under the original
    must(await pg.locator('[data-review-outputs]').count() === 1, 'no Outputs section')
    for (const ext of ['txt', 'html'])
      must(await pg.locator('[data-file-view] a', { hasText: `${title}.${ext}` }).count() === 1, `the output ${title}.${ext} is not shown once`)
    const inputs = pg.locator('[data-review-inputs] [data-review-input]')
    must(await inputs.count() === 2, `${await inputs.count()} inputs shown`)
    const inputText = await pg.locator('[data-review-inputs]').innerText()
    must(inputText.includes('Standard sales deck.txt') && inputText.includes('Brand guidelines.txt'), 'the inputs are not named')
    must(!(await pg.locator('[data-file-view] a', { hasText: 'Standard sales deck.txt' }).count()), 'an input is listed as an output')
    await s.open(`/life/brain/review/${item.name}?tab=came`) // issue 118: what was filed with it is under What came of it
    must(await pg.locator('[data-related]').count() >= 1, 'the wiki page and chat log filed with it are not shown')
    await s.open(`/life/brain/review/${item.name}?tab=summary`)
    must((await pg.locator('body').innerText()).includes('An owner-first deck'), 'the summary is not shown')
    await s.open(`/life/brain/review/${item.name}?tab=decisions`)
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
  // issue 118: the page has tabs (Summary, File, Decisions, What came of it), one at a time, in the URL as tab=
  const openTab = async (tab) => { await s.open(`/life/item/${id}?tab=${tab}`); await pg.locator(`[data-item-tab="${tab}"]`).waitFor({ timeout: 10000 }) }
  const settle = () => pg.waitForTimeout(700)

  await check('BRAIN.15', `${width} px: an item with a file, a summary, 2 waiting proposals and 1 accepted task shows every tab right`, async () => {
    await openTab('summary')
    const head = await pg.locator('[data-item-head]').innerText()
    must((await pg.locator('h1').first().innerText()).includes(title), 'the title is not in the header')
    must(head.includes('Upload') && head.includes('Private'), 'the header does not say the source and the space: ' + head)
    must((await pg.locator('[data-item-tab="summary"]').innerText()).includes('summarised'), 'the summary is not on the Summary tab')
    await openTab('file')
    must(await pg.locator('[data-file-view]', { hasText: pdfName }).count() === 1, 'the file is not under File once')
    must((await pg.locator('[data-item-tab="file"]').innerText()).includes('summarise and extract to-dos'), 'the instruction is not under File')
    await openTab('decisions')
    must(await pg.locator('[data-proposal="Pending"]').count() === 2, 'Decisions does not show the 2 waiting proposals')
    must(!(await pg.locator('[data-proposal="Accepted"]').count()), 'an accepted proposal is still under Decisions')
    await openTab('came')
    const rows = pg.locator('[data-came-of-it]')
    must(await rows.count() === 1, `What came of it shows ${await rows.count()} records`)
    const row = await rows.first().innerText()
    must(row.includes(first.preview) && row.includes('Task') && row.includes('Open'), 'the accepted task is not shown with its state: ' + row)
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check('BRAIN.16', `${width} px: accepting a proposal on the item page moves it to What came of it without a reload`, async () => {
    await openTab('decisions')
    await pg.evaluate(() => { window.__i10 = 1 })
    const card = pg.locator('[data-proposal="Pending"]').first()
    const preview = (await card.locator('.text-base-medium').first().innerText()).trim()
    await card.getByRole('button', { name: 'Accept', exact: true }).click()
    await settle()
    must(await pg.evaluate(() => window.__i10 === 1), 'the page reloaded')
    must(await pg.locator('[data-proposal="Pending"]').count() === 1, 'the accepted proposal is still waiting')
    await pg.locator('[data-item-tabs] [role="tab"]', { hasText: 'What came of it' }).click() // a tab click, not a reload
    await pg.locator('[data-item-tab="came"]').waitFor({ timeout: 10000 })
    const rows = await pg.locator('[data-came-of-it]').allInnerTexts()
    must(rows.length === 2 && rows.some((r) => r.includes(preview)), `What came of it does not list "${preview}": ${rows.join(' | ')}`)
    must(await pg.evaluate(() => window.__i10 === 1), 'the page reloaded')
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
    else await pg.keyboard.press('/')
    await pg.locator('input[aria-label="Search or chat"]').fill(title)
    await pg.waitForTimeout(900)
    await pg.keyboard.press('Enter')
    await settle()
    must(new URL(pg.url()).searchParams.get('open') === `inbox:${id}`, 'the search result did not open the item in the Drawer: ' + pg.url())
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
    for (const tab of ['summary', 'file', 'decisions', 'came']) {
      await openTab(tab)
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), `the ${tab} tab scrolls sideways`)
      const lefts = await pg.locator(`[data-item-tab="${tab}"] > *`).evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)))
      must(new Set(lefts).size <= 1, `the ${tab} tab is not one column: ` + lefts.join(', '))
    }
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
    await check('BRAIN.20', `${width} px: on an empty space Needs you says what will appear and offers Chat`, async () => {
      await openNeeds()
      must(await pg.locator('[data-needs-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-needs-empty]').innerText()
      must(t.includes('Nothing needs you.') && t.includes('Things you capture or connect will show up here.'), 'the empty state says: ' + t)
      await pg.locator('[data-needs-capture]').click()
      await pg.locator('[data-ask-panel]:visible').first().waitFor({ timeout: 5000 })
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
      // issue 117: the guess is taken as right, so a row has one button, Change; the choices are behind it
      for (const r of [a, b, c]) must((await row(r.proposal).locator('button').count()) === 2 || (await row(r.proposal).locator('[data-row-actions] button').count()) === 1, 'a row has more than one button')
      must(!(await row(a.proposal).locator('[data-keep]').count()) && (await row(a.proposal).locator('[data-change]').count()) === 1 && !(await row(a.proposal).locator('[data-drop]').count()), 'a row is not Change alone')
      await row(b.proposal).locator('[data-change]').click()
      must((await row(b.proposal).locator('[data-pick]').count()) === 2, 'the torn row does not offer its two choices under Change')
      must((await pg.locator('[data-stat-needs]').getAttribute('data-n')) === '3', 'the Needs you number is not 3')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
      made.k = { a, b, c }
    })
    await check('BRAIN.62', `${width} px: a Needs you row's title opens the capture in the side pane, and closing it leaves the row in place`, async () => {
      const { a } = made.k
      await row(a.proposal).locator('[data-row-title]').click()
      const shown = await pg.locator('[data-pane]', { hasText: T('voice') }).first().waitFor({ timeout: 10000 }).then(() => true, () => false)
      must(shown, 'the pane does not show the capture: ' + (await pg.locator('[data-pane]').first().innerText().catch(() => 'no pane')).slice(0, 200))
      await pg.keyboard.press('Escape')
      await openNeeds()  // at phone width the pane is a full screen; come back to Needs you either way
      must(await row(a.proposal).count(), 'the row left after only looking at it')
    })
    await check('BRAIN.22', `${width} px: Done files a row that was not changed, with its guess, and the record exists with the guessed area`, async () => {
      const { a, c } = made.k
      await openNeeds()
      await pg.locator('[data-file-all]').click()
      await row(a.proposal).waitFor({ state: 'detached', timeout: 10000 })
      await row(c.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const got = JSON.parse(bench(`import json
p = frappe.get_doc("Life Proposal", "${a.proposal}")
print(json.dumps({"status": p.status, "area": frappe.db.get_value(p.created_doctype, p.created_name, "area"), "dt": p.created_doctype}))`).split('\n').pop())
      must(got.status === 'Accepted' && got.dt === 'Life Task' && got.area === made.mind, 'after Keep: ' + JSON.stringify(got))
    })
    await check('BRAIN.23', `${width} px: picking the second of two area chips files it there`, async () => {
      const { b } = made.k
      await openNeeds()
      await row(b.proposal).locator('[data-change]').click()
      await row(b.proposal).locator('[data-pick="second"]').click()
      await row(b.proposal).waitFor({ state: 'detached', timeout: 10000 })
      const area = bench(`p = frappe.get_doc("Life Proposal", "${b.proposal}")
print(p.status, frappe.db.get_value(p.created_doctype, p.created_name, "area"))`).split('\n').pop()
      must(area === `Accepted ${made.mind}`, 'after the second chip: ' + area)
    })
    await check('BRAIN.24', `${width} px: Change, Not needed discards it and it appears in the Outbox as Discarded`, async () => {
      const c = await mk('plain', { area: made.career, hours: 1 })
      await openNeeds()
      await row(c.proposal).locator('[data-change]').click()
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
      await row(rows[0].proposal).locator('[data-change]').click()
      await row(rows[0].proposal).locator('[data-drop]').click()
      await row(rows[7].proposal).waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-row]').count()) === 7, 'a row did not come in')
      await row(rows[1].proposal).locator('[data-change]').click()
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
    await check('BRAIN.28', `${width} px: each row stacks at 390 px, with Change and what is behind it reachable and no sideways scroll`, async () => {
      const r = await mk('stack', { area: made.tea, reason: 'A long reason that needs room to wrap on a phone, with more words than fit on one line', hours: 1 })
      await openNeeds()
      const rw = row(r.proposal)
      await rw.waitFor({ timeout: 10000 })
      const box = await rw.boundingBox()
      {
        const b = await rw.locator('[data-change]').boundingBox()
        must(b && b.x >= 0 && b.x + b.width <= width + 1 && b.y >= box.y && b.y + b.height <= box.y + box.height + 1, `Change is not inside the row (${JSON.stringify(b)})`)
      }
      await rw.locator('[data-change]').click()
      for (const sel of ['[data-drop]', '[data-always-ask]', '[data-open-capture]']) {
        const b = await rw.locator(sel).boundingBox()
        must(b && b.x >= 0 && b.x + b.width <= width + 1, `${sel} is not on the screen (${JSON.stringify(b)})`)
      }
      if (phone) {
        const text = await rw.locator('[data-row-title]').boundingBox(), acts = await rw.locator('[data-row-actions]').boundingBox()
        must(acts.y >= text.y + text.height - 1, 'on a phone the actions do not sit under the text')
      }
      await noSideways()
      await rw.locator('[data-open-capture]').click()
      await pg.waitForURL((u) => (u.searchParams.get('open') || '').startsWith('inbox:'), { timeout: 10000 })
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
      await rw.locator('[data-change]').click()
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
    await check('BRAIN.32', `${width} px: on a space with nothing captured Activity says what will appear and offers Chat`, async () => {
      await openFeed()
      must(await pg.locator('[data-activity-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-activity-empty]').innerText()
      must(t.includes('Nothing has come in yet.') && t.includes('will show up here'), 'the empty state says: ' + t)
      await pg.locator('[data-activity-capture]').click()
      await pg.locator('[data-ask-panel]:visible').first().waitFor({ timeout: 5000 })
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
      must((await rw.locator('[data-row-item]').getAttribute('data-ref')) === `inbox:${a.item}`, 'the row does not open the item in the pane')  // issue 118: a drawer, not the page
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
  const openSources = async (query = '') => { await s.open('/life/brain/sources' + query); await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(300) }
  const capture = (title, system, extra = {}) => s.api('inbox.create_item', { space: SPACE, title: `I19 ${title} ${width} ${stamp}`, source_system: system, ...extra })
  try {
    await check('BRAIN.38', `${width} px: with no source connected Sources says what will appear, shows Capture as always on and has no Add a source`, async () => {
      await openSources()
      must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state')
      const t = await pg.locator('[data-sources-empty]').innerText()
      must(t.includes('Nothing is connected yet.') && t.includes('Connect a source below'), 'the empty state says: ' + t)
      must((await pg.locator('[data-capture-line]').innerText()).includes('always on'), 'Capture is not said to be always on')
      must((await pg.locator('[data-add-source], [data-add-source-empty], [data-add-more]').count()) === 0, 'an Add a source button or grid is still there')
      await noSideways()
    })
    await check('BRAIN.39', `${width} px: connected sources show with this week's counts, matching the captures in the database`, async () => {
      for (const n of [1, 2, 3]) await capture(`hermes ${n}`, 'hermes')
      await capture('claude 1', 'claude')
      await openSources()
      must((await pg.locator('[data-source-card]:not([data-state="Not connected"])').count()) === 2, 'expected two connected cards, got ' + await pg.locator('[data-source-card]:not([data-state="Not connected"])').count())
      for (const sys of ['hermes', 'claude']) {
        const n = bench(`from frappe.utils import add_days, getdate
d = getdate()
print(frappe.db.count("Life Inbox Item", {"space": "${SPACE}", "source_system": "${sys}", "creation": [">=", add_days(d, -d.weekday())]}))`).split('\n').pop()
        const shown = await card(sys).getAttribute('data-week')
        must(shown === n && n !== '0', `${sys}: the card says ${shown}, the database ${n}`)
        must((await card(sys).locator('[data-source-line]').innerText()).includes(`${n} this week`), `${sys}: the line does not say ${n} this week`)
      }
      must((await card('hermes').innerText()).includes('Your assistant'), 'the assistant is not called Your assistant')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.40', `${width} px: switching the assistant off makes create_item from hermes fail with a clear message; switching it on again works`, async () => {
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
      must((await card('hermes').getAttribute('data-week')) !== null && bench(`print(frappe.db.count("Life Inbox Item", {"title": ["like", "I19 hermes %${width} ${stamp}"]}))`).split('\n').pop() === '3', 'what the assistant brought earlier was deleted')
    })
    await check('BRAIN.41', `${width} px: a source that is not built cannot be switched on and shows no Coming tile`, async () => {
      await openSources()
      must((await pg.locator('[data-tile-coming]').count()) === 0 && !(await pg.locator('[data-brain-sources]').innerText()).includes('Coming'), 'a Coming tile shows')
      const r = await s.api('connections.save', { space: SPACE, system: 'github', active: 1 }, { raw: true })
      must(!r.ok() && (await r.text()).includes('not built yet'), 'the server switched GitHub on: ' + r.status())
    })
    await check('BRAIN.42', `${width} px: opening a source shows its default intent, area and goal, and saving changes what create_item uses`, async () => {
      bench(`for n in frappe.get_all("Life Connection", filters={"space": "${SPACE}", "system": "gmail"}, pluck="name"): frappe.delete_doc("Life Connection", n, force=1, ignore_permissions=True)
frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "gmail", "mailbox": "i19-${width}@example.com", "label": "i19-${width}@example.com", "active": 1}).insert(ignore_permissions=True)`)
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

    // issue 101: what is really connected. Each check sets up its own mailbox rows and takes them away (a Connected App and a mail account are not in the space's connections).
    const clear = () => bench(`frappe.set_user("Administrator")
for c in frappe.get_all("Life Connection", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Connection", c, force=1, ignore_permissions=True)
for a in frappe.get_all("Life Mail Account", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Mail Account", a, force=1, ignore_permissions=True)
for a in frappe.get_all("Connected App", filters={"provider_name": ["like", "life-os-gmail-%"]}, pluck="name"): frappe.delete_doc("Connected App", a, force=1, ignore_permissions=True)
frappe.defaults.clear_default("lifeos_redirects_confirmed", parent="__default")`)
    const googleOn = () => JSON.parse(bench(`import json
s = frappe.get_doc("Google Settings")
was = {"enable": s.enable, "client_id": s.client_id, "secret": s.get_password("client_secret", raise_exception=False)}
s.enable, s.client_id, s.client_secret = 1, "acceptance-client.apps.example", "acceptance-secret"
s.save(ignore_permissions=True)
frappe.clear_cache(doctype="Google Settings")
print(json.dumps(was))`).split('\n').pop())
    const googleBack = (was) => bench(`s = frappe.get_doc("Google Settings")
s.enable, s.client_id, s.client_secret = ${was.enable ? 1 : 0}, ${JSON.stringify(was.client_id || '')}, ${JSON.stringify(was.secret || '')}
s.save(ignore_permissions=True)
frappe.clear_cache(doctype="Google Settings")`)
    const pending = (extra = '') => bench(`from lifeos.mail import gmail
frappe.set_user("Administrator")
app = gmail.make_app(gmail.free_app_name())
c = frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "gmail", "label": "Gmail", "active": 0, "connected_app": app.name, "connected_by": "owner@lifeos.test"${extra}}).insert(ignore_permissions=True)
print(app.name)`).split('\n').pop()
    await check('BRAIN.55', `${width} px: a half-connected Gmail shows once, Waiting, with no switch and a Remove button; after Google's error it says what happened and shows the address to add; Remove clears it`, async () => {
      const was = googleOn()
      try {
        clear()
        const app = pending()
        await openSources()
        const cards = pg.locator('[data-source-card][data-system="gmail"]')
        must((await cards.count()) === 1, `Gmail shows ${await cards.count()} times`)
        must((await cards.first().getAttribute('data-state')) === 'Waiting', 'the card is not Waiting')
        must((await cards.first().locator('[data-source-switch]').count()) === 0 && (await cards.first().innerText()).includes('Finish signing in first'), 'the switch is not replaced by "Finish signing in first"')
        must(await cards.first().locator('[data-source-remove]').isVisible(), 'there is no Remove button')
        must((await pg.locator('[data-add-another], [data-source-card][data-system="gmail"] [data-source-connect]').count()) === 0, 'Gmail is offered again')
        // Google sends the person back to Frappe's address with the error: it lands on Sources with the card showing it
        await pg.goto(`${base}/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/${app}?error=redirect_uri_mismatch&state=x`)
        await pg.waitForURL(/\/life\/brain\/sources/, { timeout: 15000 })
        await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 15000 })
        must((await cards.first().locator('[data-source-error]').innerText()).includes('does not know this return address'), 'the card does not say what happened')
        must((await cards.first().locator('[data-redirect-address]').innerText()).endsWith(`connected_app.callback/${app}`), 'the card does not show the address to add')
        must(await cards.first().locator('[data-redirect-copy]').isVisible() && await cards.first().locator('[data-source-retry]').isVisible(), 'Copy or Try again is missing')
        await noSideways()
        await cards.first().locator('[data-source-remove]').click()
        await pg.locator('[data-source-card][data-system="gmail"][data-state="Not connected"]').waitFor({ timeout: 10000 })
        must(bench(`print(frappe.db.exists("Connected App", "${app}") or "gone")`).split('\n').pop() === 'gone', 'the Connected App is still there')
      } finally { clear(); googleBack(was) }
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.56', `${width} px: the Sources page names neither Hermes nor OpenClaw, even with both connected`, async () => {
      clear()
      bench(`for system in ("hermes", "openclaw", "claude"):
    frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": system, "label": {"hermes": "Hermes", "openclaw": "OpenClaw"}.get(system), "active": 1}).insert(ignore_permissions=True)`)
      try {
        await openSources()
        const text = await pg.locator('body').innerText()
        must(!/hermes|openclaw/i.test(text), 'the page names an agent: ' + (text.match(/.{0,20}(hermes|openclaw).{0,20}/i) || [''])[0])
        must(!/hermes|openclaw/i.test(await pg.locator('[data-source-card][data-system="hermes"]').innerText()) && (await pg.locator('[data-source-card][data-system="hermes"]').innerText()).includes('Your assistant'), 'the assistant is not Your assistant')
        await s.open('/life/brain/sources/hermes')
        await pg.locator('[data-source-page][data-source="hermes"]').waitFor({ timeout: 10000 })
        must(!/hermes|openclaw/i.test(await pg.locator('body').innerText()), 'the assistant page names the agent')
      } finally { clear() }
    })
    await check('BRAIN.57', `${width} px: Sources lists exactly Capture, Google Calendar, Gmail, Your assistant and Claude, with no Coming tile, no tabs and no Add a source`, async () => {
      clear()
      await openSources()
      must((await pg.locator('[data-capture-line]').innerText()).startsWith('Capture'), 'Capture is not first')
      const labels = await pg.locator('[data-source-card] [data-source-label]').allInnerTexts()
      must(JSON.stringify(labels) === JSON.stringify(['Google Calendar', 'Gmail', 'Your assistant', 'Claude']), 'the sources are ' + labels.join(', '))
      const text = await pg.locator('[data-brain-sources]').innerText()
      must(!/Coming|Add a source|Add more|Channels|Kinds/.test(text) && (await pg.locator('[data-source-tile], [data-group]').count()) === 0, 'the page still shows a Coming tile, a tab or Add a source')
      for (const sys of ['google-calendar', 'gmail', 'hermes', 'claude']) must((await pg.locator(`[data-source-card][data-system="${sys}"] [data-source-connect]`).count()) === 1, `${sys} has no Connect button`)
      await noSideways()
    })
    await check('BRAIN.58', `${width} px: Connect Gmail shows the return address with Copy before leaving the site; I've added it goes on to Google; once a sign-in has come back the step is not shown`, async () => {
      const was = googleOn()
      clear()
      const hits = []
      await pg.route('https://accounts.google.com/**', (r) => { hits.push(r.request().url()); return r.fulfill({ status: 200, contentType: 'text/html', body: 'Google' }) })
      try {
        await openSources()
        await pg.locator('[data-source-card][data-system="gmail"] [data-source-connect]').click()
        await pg.locator('[data-redirect-step]').waitFor({ timeout: 10000 })
        must((await pg.locator('[data-gmail-redirect]').innerText()).endsWith('connected_app.callback/life-os-gmail-1'), 'the address is ' + await pg.locator('[data-gmail-redirect]').innerText())
        must(await pg.locator('[data-redirect-copy]').isVisible() && (await pg.locator('[data-redirect-link]').getAttribute('href')).startsWith('https://console.cloud.google.com/'), 'Copy or the Google Cloud link is missing')
        must(!hits.length, 'the browser had already left for Google')
        await pg.getByRole('button', { name: "I've added it" }).click()
        await pg.waitForURL(/accounts\.google\.com\/o\/oauth2\/v2\/auth/, { timeout: 15000 })
        must(hits.length >= 1 && /redirect_uri=/.test(hits[0]) && hits[0].includes('life-os-gmail-1'), 'Google was not sent the address: ' + hits[0])
        clear()
        const address = (await s.api('connections.gmail_setup')).redirect_uri
        bench(`frappe.db.set_default("lifeos_redirects_confirmed", ${JSON.stringify(address)})`)
        await openSources()
        await pg.locator('[data-source-card][data-system="gmail"] [data-source-connect]').click()
        await pg.locator('[data-gmail-connect]').waitFor({ timeout: 10000 })
        await pg.getByRole('button', { name: 'Continue to Google' }).waitFor({ timeout: 10000 })
        must((await pg.locator('[data-redirect-step]').count()) === 0, 'the step shows for an address that has been confirmed')
      } finally { await pg.unroute('https://accounts.google.com/**'); clear(); googleBack(was) }
    })
    await check('BRAIN.59', `${width} px: Gmail's Try it searches the (fake) inbox for a word and shows the matches; with no inbox it says so`, async () => {
      clear()
      bench(`from lifeos import mail
c = frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "gmail", "mailbox": "owner@example.com", "label": "owner@example.com", "active": 1, "connected_by": "owner@lifeos.test"}).insert(ignore_permissions=True)
mail.account_for_connection(c)`)
      try {
        await s.open('/life/brain/sources/gmail?tab=try')
        await pg.locator('[data-mail-try]').waitFor({ timeout: 15000 })
        await pg.locator('[data-mail-query]').fill('advance')
        await pg.locator('[data-mail-search]').click()
        await pg.locator('[data-mail-hit]').first().waitFor({ timeout: 15000 })
        must((await pg.locator('[data-mail-hit]').count()) === 1 && (await pg.locator('[data-mail-subject]').innerText()) === 'Advance tax reminder', 'the matches are ' + await pg.locator('[data-mail-hits]').innerText())
        await pg.locator('[data-mail-query]').fill('tax')
        await pg.locator('[data-mail-search]').click()
        await pg.waitForFunction(() => document.querySelectorAll('[data-mail-hit]').length === 2, null, { timeout: 15000 })
        await pg.locator('[data-mail-query]').fill('zzzqqq')
        await pg.locator('[data-mail-search]').click()
        await pg.locator('[data-mail-none]').waitFor({ timeout: 15000 })
        clear()
        await pg.locator('[data-mail-query]').fill('tax')
        await pg.locator('[data-mail-search]').click()
        await pg.locator('[data-mail-error]').waitFor({ timeout: 15000 })
        must((await pg.locator('[data-mail-error]').innerText()).includes('No inbox is connected. Connect Gmail in Brain › Sources.'), 'the error says: ' + await pg.locator('[data-mail-error]').innerText())
        must(!(await pg.locator('[data-mail-hit]').count()), 'hits stayed after the error')
      } finally { clear() }
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
    await check('BRAIN.44', `${width} px: Sources offers Connect Gmail, a connected mailbox says it is a daily digest searched live and "Processed by: the Brain", every card has a Processed by line`, async () => {
      await openSources()
      must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state on an empty space')
      const tile = pg.locator('[data-source-card][data-system="gmail"]')
      must((await tile.locator('[data-source-connect]').innerText()) === 'Connect' && (await tile.innerText()).includes('Gmail'), 'the Gmail row has no Connect button: ' + await tile.innerText())
      await tile.locator('[data-source-connect]').waitFor({ timeout: 15000 }) // the button is enabled once permissions have loaded
      await tile.locator('[data-source-connect]').click()
      await pg.locator('[data-gmail-connect]').waitFor({ timeout: 5000 })
      const t = await pg.locator('[data-gmail-connect]').innerText()
      must(/copies none of your mail and never deletes any/.test(t) && /send, draft, archive or label/.test(t), 'the dialog does not say what it may do: ' + t)
      await pg.keyboard.press('Escape')
      bench(`frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "gmail", "mailbox": "i58-${width}@example.com", "label": "i58-${width}@example.com", "active": 1}).insert(ignore_permissions=True)
for system in ("hermes", "claude", "google-calendar"):
    frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": system, "active": 1}).insert(ignore_permissions=True)`)
      await openSources()
      const mail = pg.locator('[data-source-card][data-system="gmail"]')
      must((await mail.locator('[data-source-line]').innerText()).includes('Daily digest, and searched live'), 'the mailbox line says: ' + await mail.locator('[data-source-line]').innerText())
      must((await mail.locator('[data-processed-by]').innerText()) === 'Processed by: the Brain', 'the mailbox does not say the Brain processes it')
      const lines = await pg.locator('[data-source-card] [data-processed-by]').allInnerTexts()
      must(lines.length === 4 && lines.every((x) => /^(Processed by|Not processed)/.test(x)), 'every card needs a Processed by line: ' + lines.join(' | '))
      must(lines.includes('Processed by: Your assistant') && lines.filter((x) => x === 'Not processed: kept as is').length === 2, 'the lines are wrong: ' + lines.join(' | '))
      await mail.locator('[data-source-open]').click()
      await pg.locator('[data-source-settings][data-system="gmail"]').waitFor({ timeout: 5000 })
      must(await pg.locator('[data-gmail-include]').isVisible() && await pg.locator('[data-gmail-skip]').isVisible(), 'the always include and always skip lists are missing')
      must(!(await pg.locator('[data-gmail-attach]').count()), 'the old attachments switch is still there')
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
      await pg.waitForURL((u) => u.searchParams.get('open') === `inbox:${item}`, { timeout: 10000 })
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
      must((await pg.locator('[data-group], [data-kinds]').count()) === 0, 'the Channels and Kinds tabs are still there')
      await s.open('/life/brain/sources/kind-document')
      await pg.locator('[data-source-page][data-source="kind-document"]').waitFor({ timeout: 10000 })
      must(/^Brain \/ Sources/.test(await pathOf()) && (await pg.locator('[data-page-title]').innerText()) === 'Documents (PDF)', 'the path says: ' + await pathOf())
      const strip = await pg.locator('[data-source-strip]').innerText()
      for (const word of ['Arrives from', 'This week', 'Filed without you', 'AI cost this week', 'Skill']) must(strip.includes(word), `the strip lacks ${word}: ${strip}`)
      must(strip.includes('ingest-document v'), 'the strip does not name the skill and its version')
      for (const t of ['Overview', 'Rules', 'Examples & lessons', 'Activity', 'Try it']) must(await pg.locator(`[data-tab-bar] >> text="${t}"`).first().isVisible(), `no ${t} tab`)
      await pg.locator('[data-page-back]').click()
      await pg.locator('[data-brain-sources][data-loaded="1"]').waitFor({ timeout: 10000 })
      await openSources()
      await pg.locator('[data-capture-rules]').click()
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
        await openSources()
        must(await pg.locator('[data-sources-empty]').isVisible(), 'no empty state')
        must(await pg.locator('[data-email-in]').isVisible(), 'the email-in address does not say how to set it up')
        for (const sys of ['gmail', 'google-calendar']) must((await pg.locator(`[data-source-card][data-system="${sys}"]`).innerText()).length > 10, `${sys} has no hint`)
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

// Brain > Sources > an agent (issue 85): what it waits for, knows, can do, may read, has scheduled and did, carried by the connector in agent/connector/.
// Each agent here is a fixture with the key i85-<width> and a folder of files the real connector script reads and changes.
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const system = `i85-${width}`
  const home = fs.mkdtempSync(path.join(process.env.TMPDIR || '/tmp', 'i85-agent-'))
  const put = (name, data) => fs.writeFileSync(path.join(home, name), JSON.stringify(data))
  const read = (name) => JSON.parse(fs.readFileSync(path.join(home, name), 'utf8'))
  const connector = () => JSON.parse(execFileSync('python3', [path.join(root, 'agent/connector/connector.py'), '--home', home, '--system', system, '--space', SPACE],
    { env: { ...process.env, LIFEOS_URL: base, LIFEOS_API_KEY: agentKey, LIFEOS_API_SECRET: agentSecret }, encoding: 'utf8' }).trim().split('\n').pop())
  const open = async () => { await s.open(`/life/brain/sources/${system}`); await pg.locator('[data-agent-panel] [data-agent-section="connector"]').waitFor({ timeout: 10000 }) }
  try {
    await check('BRAIN.49', `${width} px: an agent's page shows Waiting, Knows, Can, May read, Scheduled and Did from the connector's report; approving a waiting item moves it to Did`, async () => {
      put('memory.json', [{ id: 'f1', text: `I85 prefers mornings ${width}`, origin: 'WhatsApp chat', learned_on: '2026-11-01' }, { id: 'f2', text: `I85 daughter is in class 5 ${width}` }])
      put('jobs.json', [{ id: 'j1', name: `I85 morning digest ${width}`, schedule: 'Every day 7:00', paused: false }])
      put('settings.json', { abilities: { send_email: 'ask' } })
      put('actions.json', [{ id: 'a1', action: 'send_email', title: `I85 chase Mehi Motors ${width}`, draft: 'Hello, a gentle reminder about the invoice.', status: 'Waiting' },
        { id: 'a2', action: 'read_email', title: `I85 read the morning mail ${width}`, status: 'Done', cost: 0.0123 }])
      fs.mkdirSync(path.join(home, 'skills/chase'), { recursive: true })
      fs.writeFileSync(path.join(home, 'skills/chase/SKILL.md'), '# Chase\nChases overdue invoices.\n')
      must(connector().report.facts === 2, 'the first report did not carry the facts')
      must(connector().report.facts === 0, 'a repeated report changed something')
      await open()
      must((await pg.locator('[data-page-title]').innerText()) === 'Your assistant', 'the agent is not shown as Your assistant: ' + await pg.locator('[data-page-title]').innerText())
      for (const k of ['waiting', 'knows', 'can', 'read', 'scheduled', 'did', 'connector']) must(await pg.locator(`[data-agent-section="${k}"]`).isVisible(), `no ${k} section`)
      must((await pg.locator('[data-fact]').count()) === 2 && (await pg.locator('[data-fact-origin]').first().innerText()).includes('WhatsApp'), 'the facts or where they came from are missing')
      must((await pg.locator('[data-ability]').count()) === 9 && (await pg.locator('[data-ability-key="pay"] [data-ability-fixed]').innerText()) === 'Always off', 'the eight actions, with pay always off, are missing')
      must((await pg.locator('[data-area]').count()) >= 1 && await pg.locator('[data-area-vault]').isVisible(), 'the areas and the Vault are missing')
      must((await pg.locator('[data-job]').count()) === 1, 'the job is missing')
      must((await pg.locator('[data-agent-skills]').innerText()).includes('chase'), 'the skill it reported is missing')
      const waiting = pg.locator('[data-agent-section="waiting"] [data-agent-request]')
      must((await waiting.count()) === 1 && (await waiting.locator('[data-request-draft]').innerText()).includes('gentle reminder'), 'the waiting request and its draft are missing')
      must((await pg.locator('[data-did]').count()) === 1, 'Did should list the one thing it did')
      const needs = await owner.api('brain.needs_you', { space: SPACE })
      must(needs.agent_requests.some((r) => r.title.includes(`I85 chase Mehi Motors ${width}`)), 'Needs you does not list the request')
      await noSideways()
      await waiting.locator('[data-request-approve]').click()
      await pg.locator('[data-agent-section="waiting"] [data-agent-empty="waiting"]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-did]').count()) === 2, 'the approved request did not move to Did')
      const again = connector()
      must(again.decisions.length === 1 && again.decisions[0].decision === 'approved', 'the connector was not told the answer')
      must(connector().decisions.length === 0, 'the answer was handed over twice')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.50', `${width} px: editing a fact and pausing a job show waiting until the connector confirms; a switch is changed the same way`, async () => {
      await open()
      const fact = pg.locator(`[data-fact][data-fact-id="f1"]`)
      await fact.locator('[data-fact-edit]').click()
      await fact.locator('[data-fact-input] input, input[data-fact-input]').first().fill(`I85 prefers afternoons ${width}`)
      await fact.locator('[data-fact-save]').click()
      await fact.locator('[data-change="waiting"]').waitFor({ timeout: 10000 })
      must((await fact.locator('[data-fact-text]').innerText()).includes('afternoons'), 'the page does not show the new text while it waits')
      await pg.locator('[data-job] [data-job-toggle]').click()
      await pg.locator('[data-job] [data-change="waiting"]').waitFor({ timeout: 10000 })
      await pg.locator('[data-ability-key="send_email"] [data-ability-select]').click()
      await pg.getByRole('option', { name: 'Off' }).first().click()
      await pg.locator('[data-ability-key="send_email"] [data-change="waiting"]').waitFor({ timeout: 10000 })
      await pg.locator('[data-fact-delete]').last().click()
      await pg.locator('[data-fact][data-fact-id="f2"] [data-change="waiting"]').waitFor({ timeout: 10000 })
      must(read('memory.json').some((f) => f.text.includes('mornings')), 'the connector files changed before it ran')
      await noSideways()
      const ran = connector()
      must(ran.applied === 4 && ran.failed === 0, `the connector applied ${ran.applied} and failed ${ran.failed}`)
      must(read('memory.json').length === 1 && read('memory.json')[0].text.includes('afternoons'), 'the connector did not apply the fact changes')
      must(read('jobs.json')[0].paused === true && read('settings.json').abilities.send_email === 'off', 'the connector did not apply the job and the switch')
      await open()
      must((await pg.locator('[data-fact]').count()) === 1 && (await pg.locator('[data-fact-text]').innerText()).includes('afternoons'), 'the page does not show the applied fact')
      must((await pg.locator('[data-change="waiting"]').count()) === 0, 'something still waits after the connector confirmed')
      must((await pg.locator('[data-job]').getAttribute('data-paused')) === '1' && (await pg.locator('[data-ability-key="send_email"]').getAttribute('data-mode')) === 'off', 'the job or the switch is not as confirmed')
      // a change the agent cannot apply is failed, with its reason
      put('jobs.json', [])
      await pg.locator('[data-job] [data-job-toggle]').click()
      await pg.locator('[data-job] [data-change="waiting"]').waitFor({ timeout: 10000 })
      must(connector().failed === 1, 'the connector did not fail a change it could not apply')
      await open()
      must((await pg.locator('[data-job]').count()) === 0, 'the job is still listed after the agent dropped it')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.51', `${width} px: an agent that has reported nothing says what will appear in each section`, async () => {
      const empty = `i85-empty-${width}`
      bench(`frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "${empty}", "active": 1}).insert(ignore_permissions=True)`)
      await s.open(`/life/brain/sources/${empty}`)
      await pg.locator('[data-agent-panel] [data-agent-section="connector"]').waitFor({ timeout: 10000 })
      for (const k of ['waiting', 'knows', 'scheduled', 'did']) must(await pg.locator(`[data-agent-empty="${k}"]`).isVisible(), `no empty state for ${k}`)
      must((await pg.locator('[data-agent-empty="knows"]').innerText()).includes('Nothing yet') && await pg.locator('[data-connector-how]').isVisible(), 'the empty page does not say what fills it')
      must((await pg.locator('[data-page-title]').innerText()) === 'Your assistant', 'the empty agent is not shown as Your assistant')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`frappe.set_user("Administrator")
for dt in ("Life Agent Fact", "Life Agent Job", "Life Agent Change", "Life Agent Action", "Life Agent Config", "Life Connection"):
    filters = {"system": ["like", "i85-%"]} if dt == "Life Connection" else {"agent": ["like", "i85-%"]}
    for n in frappe.get_all(dt, filters=filters, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)`)
    fs.rmSync(home, { recursive: true, force: true })
    await s.ctx.close()
  }
}

// Google through Life OS (issue 86): an agent's own idea waits for the owner's OK, Ask searches Gmail live. The fake Google and fake Gmail are the site's own
// (site config lifeos_fake_gmail); the fake agent here is a Life Connection with the key i86-<width>.
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const phone = width < 768
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const system = `i86-${width}`
  bench(`frappe.set_user("Administrator")
from lifeos.mail import fake
fake.clear()
if not frappe.db.get_value("Life Space", "${SPACE}", "owner_user"): frappe.db.set_value("Life Space", "${SPACE}", "owner_user", "owner@lifeos.test")
for n in frappe.get_all("Life Mail Account", filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc("Life Mail Account", n, force=1, ignore_permissions=True)
frappe.get_doc({"doctype": "Life Mail Account", "space": "${SPACE}", "user": "owner@lifeos.test", "provider": "gmail", "address": "owner@example.com", "label": "Personal", "is_default": 1}).insert(ignore_permissions=True)
frappe.get_doc({"doctype": "Life Connection", "space": "${SPACE}", "system": "${system}", "active": 1}).insert(ignore_permissions=True)`)
  try {
    await check('BRAIN.52', `${width} px: an agent's suggested reply waits in Needs you and on its page; approving sends it (fake Google) and moves it to Did, with who asked`, async () => {
      bench(`from lifeos.agents import acts
frappe.set_user("Administrator")
acts.request("${SPACE}", "${system}", "email.send", {"to": "meera@example.com", "subject": "I86 quote ${width}", "body": "Hello Meera, the quote is attached."}, "agent")
acts.request("${SPACE}", "${system}", "calendar.create", {"title": "I86 lunch ${width}", "start": "2026-11-25T13:00:00", "end": "2026-11-25T14:00:00"}, "owner", "Put lunch with Meera on Wednesday")`)
      const needs = await owner.api('brain.needs_you', { space: SPACE })
      must(needs.agent_requests.some((r) => r.title.includes(`I86 quote ${width}`)), 'Needs you does not list the reply')
      await s.open(`/life/brain/sources/${system}`)
      await pg.locator('[data-agent-panel] [data-agent-section="connector"]').waitFor({ timeout: 10000 })
      const waiting = pg.locator('[data-agent-section="waiting"] [data-agent-request]')
      must((await waiting.count()) === 1 && (await waiting.locator('[data-request-draft]').innerText()).includes('the quote is attached'), 'the reply and its draft are not on the agent page')
      const did = pg.locator('[data-did]')
      must((await did.count()) === 1 && (await did.first().locator('[data-did-asked]').innerText()).includes('Put lunch with Meera on Wednesday'), 'the owner request is not in Did with the owner words')
      must(!bench('from lifeos.mail import fake\nprint([c["call"] for c in fake.calls()])').includes('send'), 'the reply was sent before the owner said so')
      await noSideways()
      await waiting.locator('[data-request-approve]').click()
      await pg.locator('[data-agent-section="waiting"] [data-agent-empty="waiting"]').waitFor({ timeout: 10000 })
      must((await did.count()) === 2, 'the approved reply did not move to Did')
      must((await pg.locator('[data-did-asked]').allInnerTexts()).some((t) => t.includes('Its own idea, with your OK')), 'Did does not say it was the agent own idea')
      must(bench('from lifeos.mail import fake\nprint([c["call"] for c in fake.calls()])').includes('send'), 'approving did not send it (fake Google): ' + bench(`print(frappe.get_all("Life Agent Action", filters={"agent": "${system}"}, fields=["status", "error", "title"]))`).split('\\n').pop())
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.54', `${width} px: the daily email digest is one Brain item of the real people's mail by inbox, each line with Open in Gmail and File it; File it makes the thread's own item`, async () => {
      const digest = bench(`from lifeos.mail import digest
frappe.set_user("Administrator")
print(digest.make("owner@lifeos.test", "${SPACE}", 1))`).split('\n').pop()
      must(digest && digest !== 'None', 'the digest was not made: ' + digest)
      await s.open(`/life/brain/captures?tab=email&open=source:${digest}`)
      await pg.locator('[data-digest]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-digest-section]').first().getAttribute('data-digest-section')) === 'Personal', 'the digest is not grouped by inbox')
      const lines = pg.locator('[data-digest-item]')
      must((await lines.count()) === 2 && (await lines.first().locator('[data-open-gmail]').count()) === 1, 'the lines or their Open in Gmail buttons are missing')
      await noSideways()
      await lines.filter({ hasText: '2014 tax return' }).locator('[data-file-mail]').click()
      let made = 'None'
      for (let i = 0; i < 20 && made === 'None'; i++) { await pg.waitForTimeout(300); made = bench(`print(frappe.db.get_value("Life Inbox Item", {"space": "${SPACE}", "source_system": "gmail", "external_id": "fake-tax-2014"}, "name"))`).split('\n').pop() }
      must(made !== 'None', 'File it did not make the thread\'s item')
      must((await lines.filter({ hasText: '2014 tax return' }).locator('[data-file-mail]').innerText()).includes('Filed'), 'the line does not say it is filed')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    const askUi = async (question) => {
      await s.open('/life/today')
      if (phone) { await pg.locator('[data-chat-bar-open]').first().click(); await pg.locator('[data-ask-panel] textarea').fill(question); await pg.locator('[data-ask-send]:visible').click() }
      else { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(500); await pg.keyboard.type(question); await pg.waitForTimeout(300); await pg.keyboard.press('Enter') }
      await pg.locator('[data-ask-answer]:visible').last().waitFor({ timeout: 15000 })
    }
  } finally {
    bench(`frappe.set_user("Administrator")
for dt in ("Life Agent Action", "Life Agent Config"):
    for n in frappe.get_all(dt, filters={"agent": "${system}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Connection", filters={"system": "${system}"}, pluck="name"): frappe.delete_doc("Life Connection", n, force=1, ignore_permissions=True)
for dt in ("Life Mail Account", "Life Mail Search"):
    for n in frappe.get_all(dt, filters={"space": "${SPACE}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "source_system": "gmail"}, pluck="name"): frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Issue 117: a Brain that learns. Rules (made by hand, by the Brain from corrections, by Ask), Needs you with one button, and how a source is processed.
// Senders and titles start "I117 " / "i117-" so the clean-up finds them; the rules made here are deleted at the end of each width.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const SENDER = `i117-${width}-${stamp}@rungamattee.com`
  const rulesNow = () => JSON.parse(bench(`import json
print(json.dumps([{"name": r.name, "sender": r.sender, "action": r.action, "enabled": r.enabled, "builtin": r.builtin, "used": r.used_count, "made_by": r.made_by, "no_area": r.no_area, "item_kind": r.item_kind}
  for r in frappe.get_all("Life Rule", filters={"space": "${SPACE}"}, fields=["*"])]))`).split('\n').pop())
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  const openRules = async () => { await s.open('/life/settings?tab=rules'); await pg.locator('[data-brain-rules]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(400) }
  const pick = async (name) => { await pg.getByRole('menuitem', { name }).first().click() }
  bench(`frappe.set_user("Administrator")
from lifeos.brain import rules
rules.ensure_builtins("${SPACE}")
frappe.db.set_single_value("Life Settings", "own_domains", "rungamattee.com")`)
  try {
    await check('BRAIN.63', `${width} px: Settings > Brain > Rules lists the built-in rules in plain words; + Add a rule makes one through the form, "used 0 times"; Change > Switch off, then on, then Delete`, async () => {
      await openRules()
      const t = await pg.locator('[data-brain-rules]').innerText()
      must(/your own company's address/.test(t) && /it is a chat or email digest or journal photo/.test(t), 'the built-in rules are not listed in plain words: ' + t)
      await pg.locator('[data-add-rule]').first().click()
      await pg.getByLabel('Is from this address').waitFor({ timeout: 5000 })
      await pg.getByLabel('Is from this address').fill(SENDER)
      await pg.getByLabel('No area').check()
      await pg.getByRole('button', { name: 'Add rule' }).click()
      const row = pg.locator('[data-rule-row]', { hasText: SENDER })
      await row.waitFor({ timeout: 10000 })
      const text = await row.innerText()
      must(text.includes(`When mail is from ${SENDER}: file with no area`) && text.includes('used 0 times'), 'the rule reads: ' + text)
      await row.locator('[data-rule-change]').click()
      await pick('Switch off')
      await pg.locator('[data-rule-row][data-enabled="0"]', { hasText: SENDER }).waitFor({ timeout: 10000 })
      must(rulesNow().find((r) => r.sender === SENDER)?.enabled === 0, 'the rule is not off on the server')
      await pg.locator('[data-rule-row]', { hasText: SENDER }).locator('[data-rule-change]').click()
      await pick('Switch on')
      await pg.locator('[data-rule-row][data-enabled="1"]', { hasText: SENDER }).waitFor({ timeout: 10000 })
      await noSideways()
      await pg.locator('[data-rule-row]', { hasText: SENDER }).locator('[data-rule-change]').click()
      await pick('Delete')
      await pg.locator('[data-rule-row]', { hasText: SENDER }).waitFor({ state: 'detached', timeout: 10000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.64', `${width} px: a Needs you row has exactly one button, Change; Change > Not needed twice for one sender makes a drop rule without asking, and Activity says "New rule … Change"`, async () => {
      const item = () => JSON.parse(bench(`import json
frappe.set_user("Administrator")
from frappe.utils import add_to_date, now_datetime
d = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "I117 noise ${width} ${stamp}", "source_type": "Email", "sender": "${SENDER}", "source_system": "gmail", "status": "To Review",
  "raw_text": "Weekly noise.", "received_on": add_to_date(now_datetime(), days=-900)}).insert(ignore_permissions=True)
career = frappe.db.get_value("Life Area", {"space": "${SPACE}", "area_name": "Career"})
p = frappe.get_doc({"doctype": "Life Proposal", "space": "${SPACE}", "inbox_item": d.name, "kind": "Task", "preview": "Read the noise", "payload": frappe.as_json({"title": "Read the noise", "area": career}),
  "confidence": 0.6, "status": "Pending", "reason": "Weekly mail from this sender"}).insert(ignore_permissions=True)
print(json.dumps({"item": d.name, "proposal": p.name}))`).split('\n').pop())
      for (let n = 0; n < 2; n++) {
        const made = item()
        await s.open('/life/brain')
        const row = pg.locator(`[data-needs-row][data-proposal="${made.proposal}"]`)
        await row.waitFor({ timeout: 10000 })
        const counts = [await row.locator('[data-row-actions] button').count(), await row.locator('[data-change]').count(), await row.locator('[data-keep], [data-drop]').count()]
        must(counts.join() === '1,1,0', 'the row has more than Change (buttons, change, keep or drop): ' + counts.join())
        await row.locator('[data-change]').click()
        await row.locator('[data-drop]').click()
        await row.waitFor({ state: 'detached', timeout: 10000 })
        if (n === 0) must(!rulesNow().some((r) => r.sender === SENDER), 'one correction already made a rule')
      }
      const made = rulesNow().find((r) => r.sender === SENDER)
      must(made && made.action === 'Drop' && made.made_by === 'Brain', 'no drop rule after the second Not needed: ' + JSON.stringify(made))
      await s.open('/life/brain/activity')
      const line = pg.locator('[data-new-rule]', { hasText: SENDER })
      await line.waitFor({ timeout: 10000 })
      must((await line.innerText()).includes('New rule:') && (await line.locator('[data-new-rule-change]').innerText()) === 'Change', 'the line is: ' + await line.innerText())
      await noSideways()
    })
    await check('BRAIN.66', `${width} px: Gmail's Rules tab lists the sender rule and the two built-in rules in the order they are tried with "used n times", marks an all-sources rule, leaves a Calendar rule off; Change > Switch off there shows off in Settings`, async () => {
      bench(`frappe.set_user("Administrator")
frappe.db.delete("Life Rule", {"space": "${SPACE}", "made_by": ["in", ["Brain", "Owner"]]})
for d in (dict(sender="${SENDER}", source="gmail", action="File", no_area=1), dict(source="google-calendar", action="Drop"), dict(title_words="I117 invoice", action="File", no_area=1)):
    frappe.get_doc({"doctype": "Life Rule", "space": "${SPACE}", "made_by": "Owner", "enabled": 1, "used_count": 3 if d.get("sender") else 0, **d}).insert(ignore_permissions=True)`)
      await s.open('/life/brain/sources/gmail?tab=rules')
      await pg.locator('[data-source-rules]').waitFor({ timeout: 10000 })
      await pg.locator('[data-rule-row]').first().waitFor({ timeout: 10000 })
      const rows = await pg.locator('[data-source-rules] [data-rule-row]').allInnerTexts()
      must(rows.length === 4, `${rows.length} rules, not 4: ${rows.join(' | ')}`)
      must(rows[0].includes(SENDER) && rows[0].includes('used 3 times'), 'the sender rule is not first with its use: ' + rows[0])
      must(rows.some((r) => /your own company's address/.test(r)) && rows.some((r) => /chat or email digest/.test(r)), 'the built-in rules are missing')
      must(rows.some((r) => r.includes('I117 invoice') && r.includes('all sources')), 'the all-sources rule is not marked')
      must(!rows.some((r) => r.includes('Google Calendar')), 'the Calendar rule is on Gmail\'s page')
      const brain = await pg.locator('[data-brain-line]').innerText()
      must(brain.startsWith('Everything else: the Brain reads it') && (await pg.locator('[data-brain-skill]').getAttribute('href')).endsWith('/brain/skills/process-capture'), 'the Brain line is: ' + brain)
      await pg.locator('[data-recently]').waitFor({ timeout: 5000 })
      await noSideways()
      const mine = pg.locator('[data-source-rules] [data-rule-row]', { hasText: SENDER })
      await mine.locator('[data-rule-change]').click()
      await pick('Switch off')
      await pg.locator('[data-source-rules] [data-rule-row][data-enabled="0"]', { hasText: SENDER }).waitFor({ timeout: 10000 })
      await openRules()
      await pg.locator('[data-rule-row][data-enabled="0"]', { hasText: SENDER }).waitFor({ timeout: 10000 })
    })
    await check('BRAIN.67', `${width} px: Recently on Gmail's page says "Rule: …" for an item a rule filed and "The Brain" for one it guessed`, async () => {
      bench(`frappe.set_user("Administrator")
for title, by in (("I117 by rule ${width}", "Rule: when mail is from ${SENDER}: file with no area"), ("I117 by brain ${width}", "process-capture v1")):
    frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": title, "source_type": "Email", "source_system": "gmail", "status": "Done", "processed_by": by,
      "raw_text": "x"}).insert(ignore_permissions=True)`)
      await s.open('/life/brain/sources/gmail?tab=rules')
      const rows = pg.locator('[data-recently] [data-recent-row]')
      await rows.first().waitFor({ timeout: 10000 })
      const text = Object.fromEntries((await rows.allInnerTexts()).map((t) => t.split('\n').filter(Boolean)).map(([a, b]) => [a, b]))
      must((text[`I117 by rule ${width}`] || '').startsWith('Rule: '), 'the rule-filed item says: ' + JSON.stringify(text))
      must(text[`I117 by brain ${width}`] === 'The Brain', 'the guessed item says: ' + JSON.stringify(text))
    })
    await check('BRAIN.68', `${width} px: a reason line on a Needs you row has no "Jai" and no "requested"`, async () => {
      bench(`frappe.set_user("Administrator")
from lifeos.skills import runner
frappe.db.set_value("Life Skill", "process-capture", "active", 1)
from frappe.utils import add_to_date, now_datetime
d = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "I117 Conversation recap — 18–25 November 2026 ${width}", "source_type": "Email", "status": "New",
  "raw_text": "A summary of my chats this week.", "received_on": add_to_date(now_datetime(), days=-899)}).insert(ignore_permissions=True)
frappe.db.commit()
runner.run("process-capture", {"doctype": "Life Inbox Item", "name": d.name, "space": "${SPACE}"}, "Button")
frappe.db.set_value("Life Skill", "process-capture", "active", 0)`)
      await s.open('/life/brain')
      await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
      const reasons = await pg.locator('[data-needs-row] [data-row-reason]').allInnerTexts()
      must(reasons.length > 0, 'no row has a reason line')
      must(!reasons.some((t) => /\bJai\b|requested/i.test(t)), 'a reason is written about the owner or the instructions: ' + reasons.join(' | '))
      const skill = bench('print("second person" in frappe.db.get_value("Life Skill", "process-capture", "instructions") or "in the second person" in frappe.db.get_value("Life Skill", "process-capture", "instructions"))').split('\n').pop()
      must(skill === 'True', 'process-capture does not tell the Brain to write for the owner')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    bench(`frappe.set_user("Administrator")
frappe.db.delete("Life Rule", {"space": "${SPACE}", "made_by": ["in", ["Brain", "Owner"]]})
frappe.db.set_single_value("Life Settings", "own_domains", "")
frappe.db.set_value("Life Skill", "process-capture", "active", 0)
for n in frappe.get_all("Life Inbox Item", filters={"space": "${SPACE}", "title": ["like", "I117 %"]}, pluck="name"): frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Issue 118: Activity opens a drawer; the item's pane is tabbed; the summary is scanned (To act on, Updates, Reports). Titles start "I118 ".
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const T = (what) => `I118 ${what} ${width} ${stamp}`
  const seed = (what, withSummary) => JSON.parse(bench(`import json
frappe.set_user("Administrator")
from lifeos.brain import asks
raw = "\\n".join(f"- Email {n}: a message from someone about thing {n}" for n in range(1, 10))
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": "${SPACE}", "title": "${T(what)}", "source_type": "Email Digest", "status": "Done", "raw_text": "## Mail\\n" + raw,
  "received_on": frappe.utils.now_datetime(), "sender": "digest-${what}-${stamp}@x.example"}).insert(ignore_permissions=True)
if ${withSummary ? 'True' : 'False'}:
  asks.apply(item, {"line": "9 emails, 26 Nov", "to_act_on": [
    {"who": "Arijit Chatterjee (HDFC Bank)", "what": "wants the signed KYC form by Friday", "source": "Email 1", "route": "plate"},
    {"who": "Anindita Goswami", "what": "proposes an audit call; your CA is copied", "source": "Email 4", "route": "waiting", "waiting_on": "Rohan CA"},
    {"who": "Ravi Singh", "what": "unclear what he needs on the notice", "source": "Email 5"}],
    "updates": [{"what": "Two trademark threads with Ravi Singh: renewal filed, objection open", "source": "Email 6"}],
    "reports": [{"title": "Tea price list", "source": "Email 7"}, {"title": "Ghatia lots", "source": "Email 8"}, {"title": "GST reconciliation", "source": "Email 9"}]})
frappe.db.commit()
print(json.dumps({"item": item.name}))`).split('\n').pop())
  const row = (i) => pg.locator(`[data-activity-row][data-item="${i}"]`)
  const feed = async () => { await s.open('/life/brain/activity?source=Email%20Digest'); await pg.locator('[data-activity]').waitFor({ timeout: 10000 }); await pg.waitForTimeout(500) }
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  let a, b
  try {
    a = await seed('plain', false)
    b = await seed('summarised', true)
    await check('BRAIN.69', `${width} px: an Activity row opens the item in the side pane with the list beside it; j steps to the next row; Open full page opens /item/<id>`, async () => {
      await feed()
      await row(b.item).locator('[data-row-item]').click()
      await pg.locator(`[data-pane][data-pane-ref="inbox:${b.item}"]`).waitFor({ timeout: 10000 })
      must(pathOf(pg) === '/life/brain/activity', 'the page left Activity')
      must(await row(b.item).isVisible(), 'the list is gone')
      if (!phone) {
        const order = await pg.locator('[data-activity-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-item')))
        const next = order[order.indexOf(b.item) + 1]
        must(next, 'there is no next row')
        await pg.locator('[data-pane]').focus()
        await pg.keyboard.press('j')
        await pg.locator(`[data-pane][data-pane-ref="inbox:${next}"]`).waitFor({ timeout: 10000 })
        await pg.keyboard.press('k')
        await pg.locator(`[data-pane][data-pane-ref="inbox:${b.item}"]`).waitFor({ timeout: 10000 })
      }
      await pg.locator('[data-pane-full]').click()
      await pg.waitForURL((u) => u.pathname === `/life/item/${b.item}`, { timeout: 10000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.70', `${width} px: the pane's tabs are Summary, Emails 9, Decisions 0 and What came of it 0; it opens on Summary; ptab=emails opens Emails; the page has the same tabs`, async () => {
      await s.open(`/life/brain/activity?source=Email%20Digest&open=inbox:${a.item}`)
      const tabs = pg.locator('[data-pane-tabs]')
      await tabs.waitFor({ timeout: 10000 })
      const names = (await tabs.locator('[role="tab"]').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim())
      must(JSON.stringify(names) === JSON.stringify(['Summary', 'Emails 9', 'Decisions 0', 'What came of it 0']), 'the tabs are ' + JSON.stringify(names))
      must((await tabs.getAttribute('data-tab-current')) === 'summary', 'it did not open on Summary')
      await s.open(`/life/brain/activity?source=Email%20Digest&open=inbox:${a.item}&ptab=emails`)
      await pg.locator('[data-pane-tabs]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-pane-tabs]').getAttribute('data-tab-current')) === 'emails', 'ptab=emails did not open Emails')
      must(await pg.locator('[data-pane] [data-digest]').isVisible(), 'the emails are not shown')
      await s.open(`/life/item/${a.item}`)
      await pg.locator('[data-item-tabs]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-item-tabs] [role="tab"]').count()) === 4, 'the page does not have four tabs')
      await noSideways()
    })
    await check('BRAIN.71', `${width} px: the Summary tab shows To act on, Updates and Reports with their counts; Change moves a line and its task`, async () => {
      await s.open(`/life/brain/activity?source=Email%20Digest&open=inbox:${b.item}`)
      const pane = pg.locator('[data-pane]')
      await pane.locator('[data-summary]').waitFor({ timeout: 10000 })
      const n = async (g) => Number(await pane.locator(`[data-summary-group="${g}"] [data-group-count]`).first().innerText())
      must((await n('act')) === 3 && (await n('updates')) === 1 && (await n('reports')) === 3, 'the counts are wrong')
      must((await pane.locator('[data-summary-line]').innerText()) === '9 emails, 26 Nov', 'the line on top is wrong')
      must((await pane.locator('[data-summary-reports]').innerText()).includes('Tea price list · Ghatia lots'), 'the reports are not one line')
      const unsure = pane.locator('[data-summary-line-row="act"]').nth(2)
      must((await unsure.locator('[data-line-where]').getAttribute('data-where')) === 'waiting', 'the unsure line is not in the waiting pile')
      await unsure.locator('[data-line-change]').click()
      await pg.getByRole('menuitem', { name: 'Your plate' }).click()
      await pg.waitForFunction(() => document.querySelectorAll('[data-pane] [data-summary-line-row="act"]')[2]?.querySelector('[data-line-where]')?.getAttribute('data-where') === 'plate', null, { timeout: 10000 })
      const came = (await pane.locator('[data-pane-tabs] [role="tab"]').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim())
      must(came[3] === 'What came of it 3', 'the tasks of the lines are not under What came of it: ' + came[3])
      const task = JSON.parse(bench(`import json
print(json.dumps(frappe.get_all("Life Task", filters={"inbox_item": "${b.item}", "title": ["like", "Ravi Singh%"]}, fields=["status", "waiting_on"])))`).split('\n').pop())
      must(task[0].status === 'Open', 'the task did not move to the plate: ' + JSON.stringify(task))
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.72', `${width} px: on a phone the pane fills the width, the tabs fit or scroll sideways, and nothing is cut off`, async () => {
      await s.open(`/life/brain/activity?source=Email%20Digest&open=inbox:${b.item}`)
      const pane = pg.locator('[data-pane]')
      await pane.locator('[data-summary]').waitFor({ timeout: 10000 })
      const box = await pane.boundingBox()
      if (phone) must(box.width >= width - 2, `the pane is ${box.width} px of ${width}`)
      must(await pane.evaluate((e) => e.scrollWidth <= e.clientWidth + 1), 'something in the pane is cut off sideways')
      must(await pane.locator('[data-pane-tabs]').isVisible(), 'no tabs')
      await noSideways()
    })
  } finally {
    bench(`frappe.set_user("Administrator")
items = frappe.get_all("Life Inbox Item", filters={"title": ["like", "I118 %"]}, pluck="name")
for n in frappe.get_all("Life Task", filters={"inbox_item": ["in", items or [""]]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
for n in items: frappe.delete_doc("Life Inbox Item", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}

// Issue 125: what an agent did shows in Activity with who asked, a drawer and Undo; Chat lists the owner's conversation on the agent's channel, read only.
const ASSISTANT = 'hermes125'
const assistantSeed = (width) => `import json
frappe.set_user("Administrator")
from lifeos.agents import limits
cfg = limits.config("${SPACE}", "${ASSISTANT}", create=True)
cfg.display_name = "Hermes"
cfg.agent_user = "hermes@lifeos.test"
cfg.save(ignore_permissions=True)
limits.set_ability(cfg, "write_pages", "ask")
frappe.set_user("hermes@lifeos.test")
from lifeos.api import tools
done = tools.people_add("Ekta Jalan I125 ${width} ${stamp}", space="${SPACE}", source_system="${ASSISTANT}", asked_by="owner", owner_message="Make Ekta Jalan a person")
frappe.db.commit()
print(json.dumps({"action": done["action"], "person": done["person"]}))`
const assistantClean = `frappe.set_user("Administrator")
for n in frappe.get_all("Life Person", filters={"space": "${SPACE}", "full_name": ["like", "% I125 %"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Agent Action", {"space": "${SPACE}", "agent": "${ASSISTANT}"})
frappe.db.delete("Life Agent Job", {"space": "${SPACE}", "agent": "${ASSISTANT}"})
frappe.db.delete("Life Agent Config", {"space": "${SPACE}", "agent": "${ASSISTANT}"})
for t in frappe.get_all("Life Ask Thread", filters={"space": "${SPACE}", "source_system": "${ASSISTANT}"}, pluck="name"):
  frappe.delete_doc("Life Ask Thread", t, force=1, ignore_permissions=True)`
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
  try {
    const seeded = JSON.parse(bench(assistantSeed(width)).split('\n').pop())
    await check('BRAIN.73', `${width} px: Activity lists "Hermes · you asked" for an agent's act with its request in the drawer; the Assistant chip shows only those; Undo removes the person`, async () => {
      await s.open('/life/brain/activity')
      const row = pg.locator(`[data-assistant-row][data-action="${seeded.action}"]`)
      await row.waitFor({ timeout: 10000 })
      const text = (await row.innerText()).replace(/\s+/g, ' ')
      must(/Hermes · you asked/.test(text) && /Added Ekta Jalan/i.test(text), 'the row reads: ' + text)
      await noSideways()
      await row.locator('[data-assistant-open]').click()
      must((await row.locator('[data-assistant-request]').innerText()).includes('Make Ekta Jalan a person'), 'the drawer does not show the request')
      await noSideways()
      await pg.locator('[data-outcome="assistant"]').click()
      await pg.waitForFunction(() => !document.querySelector('[data-activity-row]:not([data-assistant-row])') && document.querySelector('[data-assistant-row]'), null, { timeout: 10000 })
      await row.locator('[data-assistant-undo]').click()
      for (let i = 0; i < 40 && bench(`print(frappe.db.exists("Life Person", "${seeded.person}") or "gone")`).split('\n').pop() !== 'gone'; i++) await pg.waitForTimeout(250)
      must(bench(`print(frappe.db.exists("Life Person", "${seeded.person}") or "gone")`).split('\n').pop() === 'gone', 'Undo left the person')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('BRAIN.74', `${width} px: Chat's History lists the relayed conversation "on Telegram"; it opens read only with its turns in order and no question box`, async () => {
      const turns3 = [{ role: 'owner', text: 'Add a task to call Ekta', at: '2026-11-26 09:00:00' }, { role: 'assistant', text: 'Done, it is on Today.', at: '2026-11-26 09:00:05' },
        { role: 'owner', text: 'Thanks', at: '2026-11-26 09:01:00' }]
      const out = (await (await agentFetch('chats.relay', { turns: JSON.stringify(turns3), channel: 'Telegram', source_system: ASSISTANT, external_id: `tg-${width}-${stamp}`, space: SPACE })).json()).message
      must(out?.added === 3, 'the relay answered ' + JSON.stringify(out))
      await s.open('/life')
      // issue 120: History is inside the chat panel (laptop) or the chat sheet (phone)
      if (phone) await pg.locator('[data-chat-bar-open]').first().click(); else { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(500) }
      await pg.locator('[data-ask-history-open]:visible').first().click()
      const rowH = pg.locator('[data-history-row]', { hasText: 'on Telegram' }).first()
      await rowH.waitFor({ timeout: 10000 })
      must((await rowH.innerText()).includes('Hermes · Telegram'), 'the row reads: ' + (await rowH.innerText()))
      await noSideways()
      await rowH.locator('a').first().click()
      await pg.locator('[data-ask-readonly]:visible').first().waitFor({ timeout: 10000 })
      const turns = await pg.locator('[data-ask-thread]:visible [data-ask-question], [data-ask-thread]:visible [data-ask-answer]').allInnerTexts()
      must(turns.map((t) => t.trim()).join('|') === 'Add a task to call Ekta|Done, it is on Today.|Thanks', 'the turns are: ' + turns.join('|'))
      must((await pg.locator('[data-ask-input]:visible').count()) === 0, 'there is a question box on a relayed thread')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    // Chat on Flow (issue 119): the real run (Flow's agent, tools, usage) against the fake model of tools/fake_openai.py
    await check('BRAIN.75', `${width} px: Chat runs on Flow: the box reads "Search or chat", a question streams an answer in the Chat panel and writes one usage row, the Chat panel opens with the shortcut, /life/ask goes to Today, and no visible text says Ask`, async () => {
      chatOn()
      try {
        await s.open('/life')
        const nav = await pg.locator('body').innerText()
        must(!/\bAsk\b/.test(nav), 'the screen says Ask: ' + (nav.match(/.{20}\bAsk\b.{20}/s) || [''])[0])
        if (!phone) {
          must((await pg.locator('[data-ask-box]').innerText()).includes('Search or chat'), 'the box does not read "Search or chat"')
          await pg.keyboard.press('/'); await pg.waitForTimeout(300)
          must(await pg.locator('input[aria-label="Search or chat"]').count(), 'the palette does not say "Search or chat"')
          must(!/\bAsk\b/.test(await pg.locator('[role="dialog"]').first().innerText()), 'the palette says Ask')
          await pg.keyboard.press('Escape'); await pg.waitForTimeout(300)
          await pg.keyboard.press('Control+k'); await pg.waitForTimeout(500) // issue 120: the shortcut opens the chat panel itself, with the box ready
          await pg.keyboard.type('What tasks do I have?'); await pg.waitForTimeout(300)
          await pg.keyboard.press('Enter')
        } else await pg.locator('[data-chat-bar-open]').first().click()
        await pg.waitForTimeout(600)
        if (phone) { await pg.locator('[data-ask-panel] textarea').fill('What tasks do I have?'); await pg.locator('[data-ask-send]:visible').click() }
        const panel = pg.locator('[data-ask-panel]:visible')
        await pg.waitForTimeout(700) // the one ongoing conversation may hold earlier answers: wait for the new one
        await panel.locator('[data-ask-working]').waitFor({ state: 'detached', timeout: 90000 })
        await panel.locator('[data-ask-answer][data-status="Done"]').last().waitFor({ timeout: 5000 })
        must((await panel.locator('[data-ask-answer]').last().innerText()).includes('From the tool'), 'the answer is not the model\'s')
        must(!/\bAsk\b/.test(await panel.innerText()), 'the panel says Ask')
        must((await panel.locator('h2').first().innerText()).trim() === 'Chat', 'the panel is not titled Chat')
        const usage = bench('print(frappe.db.count("Life AI Usage", {"purpose": "Chat", "creation": [">", frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-3)]}))').split('\n').pop()
        must(Number(usage) >= 1, 'no Chat usage row was written: ' + usage)
        if (!phone) await pg.locator('[data-ask-close]').click(); else await pg.keyboard.press('Escape')
        await s.open('/life/ask?tab=history')
        must(new URL(pg.url()).pathname === '/life/today', '/life/ask did not go to Today: ' + pg.url())
        must(!/\bAsk\b/.test(await pg.locator('body').innerText()), 'the screen says Ask')
        await s.open('/life/settings?tab=advanced&part=ai')
        await pg.locator('[data-ai-chat-card]').waitFor({ timeout: 10000 })
        must(!/\bAsk\b/.test(await pg.locator('body').innerText()), 'Settings says Ask')
      } finally {
        chatOff()
      }
    })

    // with no provider set in Flow: the question shows what search finds and the key line (the result is the same at the cap, which names the spend)
    await check('BRAIN.76', `${width} px: with no model in Flow, a question says "Chat needs an AI key" with its link, and at the monthly cap Chat refuses and shows the spend`, async () => {
      await s.open('/life')
      if (phone) { await pg.locator('[data-chat-bar-open]').first().click(); await pg.locator('[data-ask-panel] textarea').fill('What is open this week?'); await pg.locator('[data-ask-send]:visible').click() }
      else { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(500); await pg.keyboard.type('What is open this week?'); await pg.waitForTimeout(300); await pg.keyboard.press('Enter') }
      await pg.locator('[data-refusal="not_set_up"]').waitFor({ timeout: 15000 })
      must((await pg.locator('[data-ask-refusal]').innerText()).includes('Chat needs an AI key'), 'no "Chat needs an AI key" message')
      must((await pg.locator('[data-ask-key-link]').getAttribute('href')).includes('part=ai'), 'the link does not go to Settings › AI')
      if (!phone) await pg.locator('[data-ask-close]').click(); else await pg.keyboard.press('Escape')
      chatOn()
      bench(`frappe.get_doc({"doctype": "Life AI Usage", "user": "owner@lifeos.test", "month": frappe.utils.now_datetime().strftime("%Y-%m"), "model": "m", "cost": 99, "purpose": "Test"}).insert(ignore_permissions=True)`)
      try {
        const res = await s.api('chat.send', { question: 'What is open?', space: SPACE })
        must(res.error === 'cap' && /\$\d+\.\d\d of \$30/.test(res.error_text), `the cap did not refuse: ${JSON.stringify(res).slice(0, 200)}`)
        await s.open('/life')
        if (phone) await pg.locator('[data-chat-bar-open]').first().click(); else await pg.locator('[data-nav-chat]').click()
        await pg.locator('[data-ask-panel] textarea').fill('What is open?')
        await pg.locator('[data-ask-send]:visible').click()
        await pg.locator('[data-refusal="cap"]').waitFor({ timeout: 15000 })
        must((await pg.locator('[data-refusal="cap"]').innerText()).includes('of $30'), 'the refusal does not show the spend')
      } finally {
        bench('frappe.db.delete("Life AI Usage", {"purpose": "Test"})')
        chatOff()
      }
    })
  } finally {
    bench(assistantClean)
    await s.ctx.close()
  }
}

// Issue 130: handing off in Chat, with the fake model of tools/fake_openai.py. "Vivek owes me …" only tracks and the answer says nothing was sent; "Ask Vivek for …" drafts, and the
// draft is on the task with Send (nothing is sent until then).
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const phone = width < 800
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
  try {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "the ITR draft%"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
if not frappe.db.exists("Life Person", {"space": "${SPACE}", "full_name": "Vivek I130"}):
    frappe.get_doc({"doctype": "Life Person", "space": "${SPACE}", "full_name": "Vivek I130", "kind": "Person", "email": "vivek130@example.com", "phone": "+91 98765 43210"}).insert(ignore_permissions=True)
if not frappe.db.exists("Life Mail Account", {"space": "${SPACE}", "user": "owner@lifeos.test"}):
    frappe.get_doc({"doctype": "Life Mail Account", "space": "${SPACE}", "user": "owner@lifeos.test", "provider": "gmail", "address": "owner@example.com", "label": "Personal", "is_default": 1}).insert(ignore_permissions=True)
from lifeos.mail import fake
fake.clear()`)
    await check('BRAIN.77', `${width} px: in Chat "Vivek owes me the ITR draft by Friday" makes a waiting task and says nothing was sent; "Ask Vivek for the ITR draft by Friday" drafts, with Send on the task`, async () => {
      chatOn()
      try {
        const panel = () => pg.locator('[data-ask-panel]:visible').first()
        const answered = async () => { await pg.waitForTimeout(700); await panel().locator('[data-ask-working]').waitFor({ state: 'detached', timeout: 90000 }); await panel().locator('[data-ask-answer][data-status="Done"]').last().waitFor({ timeout: 5000 }) }
        const say = async (text) => { await pg.locator('[data-ask-input]:visible').fill(text); await pg.locator('[data-ask-send]:visible').click(); await answered() }
        await s.open('/life/today')
        if (!phone) { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(600) } else { await pg.locator('[data-chat-bar-open]').first().click(); await pg.waitForTimeout(800) }
        await say('Vivek owes me the ITR draft by Friday')
        const answer = await panel().locator('[data-ask-answer]').last().innerText()
        must(/nothing was sent/i.test(answer), 'the answer does not say nothing was sent: ' + answer)
        const made = JSON.parse(bench(`import json
from lifeos.mail import fake
t = frappe.get_all("Life Task", filters={"space": "${SPACE}", "title": "the ITR draft"}, fields=["status", "waiting_on", "handed_off_how", "check_by"])
print(json.dumps({"tasks": [[x.status, x.waiting_on, x.handed_off_how, str(x.check_by)] for x in t], "sent": [c["call"] for c in fake.calls()]}))`).split('\n').pop())
        must(made.tasks.length === 1 && made.tasks[0][0] === 'Waiting' && made.tasks[0][1] === 'Vivek I130' && made.tasks[0][2] === 'track', 'the task is ' + JSON.stringify(made.tasks))
        must(!made.sent.length, 'something was sent: ' + made.sent)
        await say('Ask Vivek for the ITR draft by Friday')
        must(/drafted/i.test(await panel().locator('[data-ask-answer]').last().innerText()), 'the answer does not say it is drafted')
        await panel().locator('[data-ask-done-open]').last().click()
        await pg.locator('[data-handoff-send]').waitFor({ timeout: 15000 })
        must((await pg.locator('[data-handoff-message]').innerText()).includes('ITR draft'), 'the draft does not name the ITR draft')
        const calls = bench('from lifeos.mail import fake\nprint([c["call"] for c in fake.calls()])').split('\n').pop()
        must(calls.includes('draft') && !calls.includes("'send'"), 'the calls are ' + calls)
        must(!errors.length, 'script errors: ' + errors.join(' | '))
      } finally {
        chatOff()
      }
    })
  } finally {
    bench(`for n in frappe.get_all("Life Task", filters={"title": ["like", "the ITR draft%"]}, pluck="name"): frappe.delete_doc("Life Task", n, force=1, ignore_permissions=True)
frappe.db.delete("Life Agent Action", {"space": "${SPACE}", "agent": "lifeos-chat"})
for n in frappe.get_all("Life Person", filters={"full_name": ["like", "%I130"]}, pluck="name"): frappe.delete_doc("Life Person", n, force=1, ignore_permissions=True)
for n in frappe.get_all("Life Mail Account", filters={"space": "${SPACE}", "user": "owner@lifeos.test"}, pluck="name"): frappe.delete_doc("Life Mail Account", n, force=1, ignore_permissions=True)`)
    await s.ctx.close()
  }
}
