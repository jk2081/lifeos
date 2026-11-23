// Settings: Profile, Areas, Rhythms, Members, Sources, Rules, Skills, Cost, the ladder and the calendar connection.
// Checks are numbered SETTINGS.<n> in the order they appear here; `node tools/acceptance.mjs --only=SETTINGS` runs this file's checks.
import { SPACE, WIDTHS, areaId, areas, base, bench, check, must, owner, pathOf, results, session, stamp, today } from './context.mjs'
import { uxKit } from './ux.mjs'

for (const width of WIDTHS) {
  const { asAgent, count, errors, nav, overflow, pg, phone, s, settle, tag } = await uxKit(width)
  await check('SETTINGS.1', `${width} px: Settings: every section from the menu and the URL, old links to their new homes, rename a tag and a part, archive a part (its open task moved) and restore it, members, a Rhythms setting survives a reload, no role names`, async () => {
    let step = 'sections'
    const problems = []
    try {
    // issue 44: eight pages and Advanced (Sources is the Brain's screen)
    const SECTIONS = ['profile', 'calendar', 'areas', 'rhythms', 'habits', 'data', 'sources', 'rules', 'members', 'advanced']
    const PAGES = SECTIONS.filter((x) => x !== 'sources')
    const cur = () => pg.locator('[data-settings-section]').getAttribute('data-current')
    const menuItems = async () => { await s.open('/life/settings'); return pg.locator('[data-settings-menu] [data-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-section'))) }
    const listed = await menuItems()
    must(JSON.stringify(listed) === JSON.stringify(SECTIONS), `the menu lists ${listed}`)
    for (const [old, now] of [['default', 'profile'], ['review', 'rhythms']]) {
      await s.open(`/life/settings?tab=${old}`)
      must((await cur()) === now, `?tab=${old} opened ${await cur()}, not ${now}`)
    }
    for (const sec of PAGES) {
      await s.open(`/life/settings?tab=${sec}`)
      must((await cur()) === sec, `?tab=${sec} opened ${await cur()}`)
      await s.open('/life/settings')
      if (phone) must(await pg.locator('[data-settings-menu]').isVisible() && !(await pg.locator('[data-settings-section]').count()), 'on a phone the menu is not the first screen')
      await pg.locator(`[data-settings-menu] [data-section="${sec}"]`).click()
      await settle()
      must((await cur()) === sec && (phone ? !(await pg.locator('[data-settings-menu]').count()) : true), `the menu did not open ${sec}`)
      must((await overflow()) <= 0, `${sec}: the page scrolls sideways`)
      const text = await pg.locator('[data-main]').innerText()
      // a recorded AI call names the user who made it (the Brain's own runs are Administrator's), so that name is data, not a role label
      const shown = text.replace(/ · Administrator$/gm, '')
      must(!/Life (Agent|User|Admin)|Administrator/.test(shown), `${sec}: a role name or Administrator shows`)
    }
    // areas (issue 12): Settings > Areas lists the seven with their parts; a part is renamed in its Edit dialog and archived
    // there, its open tasks moving to the place chosen. Rename in place stays for habits.
    const got = async () => (await s.api('settings.get', { space: SPACE }))
    step = 'areas: rename a part in its Edit dialog'
    const A = `UX3 area A ${width} ${stamp}`
    const B = `UX3 area B ${width} ${stamp}`
    const a = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: A, sort_order: 900 })).name
    const b = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: B, sort_order: 901 })).name
    const career = (await got()).areas.find((x) => x.is_life_area && x.area_name === 'Career').name
    await s.open('/life/settings?tab=areas')
    await pg.locator(`[data-edit-part="${a}"]`).click()
    await pg.locator('[data-part-title] input, input[data-part-title]').first().fill(A + ' renamed')
    await pg.getByRole('button', { name: 'Save', exact: true }).click()
    await pg.waitForTimeout(900)
    must((await got()).areas.find((x) => x.name === a).area_name === A + ' renamed', 'renaming a part did not save')
    must(await pg.locator(`[data-parts-of="Career"] [data-part="${a}"]`).innerText().then((t) => t.includes(A + ' renamed')), 'the renamed part does not show under Career')
    // no Delete or Remove for areas or habits
    step = 'no Delete or Remove for areas or habits'
    const itemsOf = async (n) => { await pg.locator(`[data-row-name="${n}"] [data-row-menu]`).click(); await pg.waitForTimeout(250); const t = await pg.getByRole('menuitem').allInnerTexts(); await pg.keyboard.press('Escape'); await pg.waitForTimeout(200); return t.map((x) => x.trim()) }
    must(!(await pg.locator('[data-areas-section]').getByRole('button', { name: /^(Delete|Remove)$/ }).count()), 'areas: a Delete or Remove button')
    for (const sec of ['habits', 'rhythms']) {
      await s.open(`/life/settings?tab=${sec}`)
      const first = pg.locator('[data-settings-list] [data-row-name]').first()
      if (await first.count()) { const t = await itemsOf(await first.getAttribute('data-row-name')).catch(() => []); must(!t.some((x) => /Delete|Remove/.test(x)), `${sec}: ${t}`) }
      must(!(await pg.getByRole('button', { name: /^(Delete|Remove)$/ }).count()), `${sec}: a Delete or Remove button`)
    }
    // archive B, a part with an open task: the task moves to Career itself, B leaves the Areas screen and the pickers, is under
    // Archived and comes back in place
    step = 'archive B: its task moves to Career, and it leaves the Areas screen and the pickers'
    const task = await s.api('tasks.quick_add', { text: `UX3 filed under B ${width} ${stamp}`, space: SPACE, area: b })
    await s.open('/life/settings?tab=areas')
    await pg.locator(`[data-edit-part="${b}"]`).click()
    await pg.locator('[data-archive-part]').click()
    await pg.waitForTimeout(500)
    must(await pg.locator('[data-archive-part-dialog] [data-move-to]').count(), 'no question where the open task goes')
    await pg.getByRole('button', { name: 'Archive', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    const tree = (await s.api('area.tree', { space: SPACE })).areas.map((x) => x.name)
    const ctx = (await s.api('meta.space_context', { space: SPACE })).areas.map((x) => x.name)
    must(!tree.includes(b) && !ctx.includes(b), 'an archived area is still on the Areas screen or in the pickers')
    must(!(await pg.locator(`[data-part="${b}"]`).count()), 'the archived part is still listed')
    must((await s.api('tasks.get', { task: task.name })).area === career, 'the open task did not move to Career')
    if (!phone) must(!(await pg.locator(`[data-nav-pin="${b}"]`).count()), 'the archived area is still in the sidebar')
    await s.open('/life/settings?tab=advanced&part=archive')
    if (await pg.locator(`[data-archived-row="${b}"]`).count()) {
      await pg.locator(`[data-restore="${b}"]`).click()
      await pg.waitForTimeout(1200)
    } else { // an app bug: noted, and the area is restored through the API so the rest of the check runs
      problems.push('the archived area is not under Settings > Advanced > Archive, so it cannot be restored there')
      await s.api('settings.save_item', { kind: 'area', name: b, is_archived: 0, with_children: 1 })
    }
    const back = (await got()).areas
    must(!back.find((x) => x.name === b).is_archived && back.find((x) => x.name === b).parent_area === career, 'Restore did not bring B back in place')
    // tidy: the task and both test areas go (the site is rebuilt before each run, but nothing is left behind anyway)
    await s.api('frappe.client.delete', { doctype: 'Life Task', name: task.name })
    await s.api('settings.save_item', { kind: 'area', name: a, delete: 1 })
    await s.api('settings.save_item', { kind: 'area', name: b, delete: 1 })
    // a changed Rhythms setting says Saved and survives a reload; it is put back after
    step = 'a changed Rhythms setting says Saved and survives a reload'
    const was = (await s.api('settings.get', { space: SPACE })).settings
    const next = was.score_target === 86 ? 85 : 86
    try {
      await s.open('/life/settings?tab=rhythms')
      const box = pg.locator('[data-setting="score_target"] input, input[data-setting="score_target"]').first()
      await box.fill(String(next))
      await box.press('Tab')
      await pg.getByText('Saved', { exact: true }).first().waitFor({ timeout: 5000 })
      await pg.waitForTimeout(1200)
      await pg.reload({ waitUntil: 'networkidle' })
      await settle()
      must(Number(await pg.locator('[data-setting="score_target"] input, input[data-setting="score_target"]').first().inputValue()) === next, 'the score target did not survive a reload')
      const saved = (await s.api('settings.get', { space: SPACE })).settings
      must(saved.score_target === next, 'the Rhythms settings were not saved')
    } finally {
      await s.api('settings.save', { values: { score_target: was.score_target } })
    }
    // add and remove a member through the dialogs
    step = 'add and remove a member through the dialogs'
    await s.open('/life/settings?tab=members')
    if (phone) { await pg.locator('[data-settings-section] button[role="combobox"], [data-settings-section] [aria-label="Space"]').first().click(); await pg.getByRole('option', { name: 'Shared', exact: true }).click() }
    else await pg.locator('[data-member-spaces] [data-space="Shared"]').click()
    await settle()
    const who = 'stranger@lifeos.test'
    if (await pg.locator(`[data-member="${who}"]`).count()) await s.api('settings.set_member', { space: 'Shared', user: who, remove: 1 }), await s.open('/life/settings?tab=members')
    await pg.locator('[data-add-member]').click()
    await pg.waitForTimeout(300)
    await pg.locator('[data-add-dialog] button, [data-add-dialog] input').first().click()
    await pg.keyboard.type('stranger', { delay: 30 })
    await pg.waitForTimeout(1200)
    await pg.getByRole('option', { name: /stranger/i }).first().click()
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    must(await pg.locator(`[data-member="${who}"]`).count(), 'Add member did not add the person')
    await pg.locator(`[data-member-menu="${who}"]`).click()
    await pg.getByRole('menuitem', { name: 'Remove' }).click()
    await pg.getByRole('button', { name: 'Remove', exact: true }).last().click()
    await pg.waitForTimeout(1200)
    must(!(await pg.locator(`[data-member="${who}"]`).count()), 'Remove did not remove the person')
    must(await pg.locator('[data-owner-badge]').count(), 'the owner has no Owner badge')
    // the family member has no People and agents group, and no Assistants, Ask and AI or Backups
    step = 'the family member has no admin sections'
    const fam = await session('family@lifeos.test', width)
    await fam.open('/life/settings')
    must(!(await fam.page.locator('[data-settings-group="people"]').count()), 'the family user sees People and agents')
    must(!(await fam.page.locator('[data-settings-menu] [data-section="members"], [data-settings-menu] [data-section="advanced"]').count()), 'the family user sees an admin section')
    await fam.ctx.close()
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    must(!problems.length, problems.join('; '))
    return `${SECTIONS.length} sections`
    } catch (e) { throw new Error(`[${step}] ${String(e.message || e).split('\n')[0]}`) }
  })

  if (!phone) await check('SETTINGS.2', 'access: the family user sees no Private sources, pages or changes; the agent cannot see a source behind a Vault document while the switch is off', async () => {
    const item = await s.api('inbox.create_item', { title: `S4 passport scan ${stamp}`, source_type: 'Upload', space: SPACE })
    const vault = await s.api('vault.save', { space: SPACE, values: { title: `S4 passport ${stamp}`, doc_type: 'ID', area: areaId('Money & Legal') } })
    bench(`from lifeos import index\nfrappe.db.set_value("Life Inbox Item", "${item.name}", "vault_document", "${vault.name}")\nindex.update(frappe.get_doc("Life Inbox Item", "${item.name}"))\nfrappe.db.set_value("Life Space", "${SPACE}", "agents_can_read_vault", 0)`)
    const seen = await asAgent(`rows = sources.list(space="${SPACE}", page_length=500)["sources"]
try:
	inbox.get("${item.name}"); got = "allowed"
except Exception:
	got = "refused"
print(json.dumps({"listed": any(r["name"] == "${item.name}" for r in rows), "get": got}))`)
    must(!seen.listed && seen.get === 'refused', `the agent sees the Vault source: ${JSON.stringify(seen)}`)
    const fam = await session('family@lifeos.test')
    try {
      for (const m of [['sources.list', { space: SPACE }], ['wiki.changes', { space: SPACE }], ['wiki.pages', { space: SPACE }]]) {
        const r = await fam.api(m[0], m[1], { raw: true })
        must(r.status() >= 400, `the family member could call ${m[0]} on Private`)
      }
      const shared = await fam.api('sources.list', { space: 'Shared', page_length: 500 })
      must(!shared.sources.some((r) => r.title.includes(stamp) && r.title.startsWith('S4')), 'the family member sees a Private source')
      await fam.open('/life/brain/captures')
      must(!(await fam.page.locator('[data-main]').innerText()).includes(`S4 keep`), 'a Private source shows to the family member')
      const ch = await fam.api('frappe.client.get_count', { doctype: 'Life Wiki Change', filters: { space: SPACE } }, { raw: true })
      must(!ch.ok() || (await ch.json()).message === 0, 'the family member counts Private wiki changes')
    } finally { await fam.ctx.close() }
  })
  await s.ctx.close()
}


// Issue 1: people and agents in one place (Settings > People and agents: Spaces, Members, Agents)
const I1_AGENT = 'issue1-agent@lifeos.test'
const I1_NEW = 'issue1-newcomer@lifeos.test'
for (const width of WIDTHS) {
  const phone = width < 800
  const tag = `I1.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const settle = () => pg.waitForTimeout(500)
  const cur = () => pg.locator('[data-settings-section]').getAttribute('data-current')
  // an agent in no space, and a user with no Life OS role in no space
  const reset = () => bench(`from lifeos import devtools
frappe.set_user("Administrator")
devtools.make_user("${I1_AGENT}", "Issue One Agent", ["Life Agent"])
devtools.make_user("${I1_NEW}", "Issue One Newcomer", [])
u = frappe.get_doc("User", "${I1_NEW}"); u.flags.ignore_permissions = True; u.remove_roles("Life User", "Life Admin", "Life Agent")
for sp in frappe.get_all("Life Space", pluck="name"):
    doc = frappe.get_doc("Life Space", sp)
    for m in [m for m in doc.members if m.user in ("${I1_AGENT}", "${I1_NEW}")]: doc.remove(m)
    doc.save(ignore_permissions=True)
frappe.db.commit()`)
  const pickSpace = async (name) => {
    if (phone) { await pg.locator('[data-settings-section] [aria-label="Space"]').first().click(); await pg.getByRole('option', { name, exact: true }).click() }
    else await pg.locator(`[data-member-spaces] [data-space="${name}"]`).click()
    await settle()
  }
  const choose = async (sel, option) => {
    await pg.locator(sel).first().click()
    await pg.waitForTimeout(250)
    await pg.getByRole('option', { name: option, exact: true }).first().click()
    await pg.waitForTimeout(1200)
  }
  const shownAccess = async (sel) => (await pg.locator(sel).first().innerText()).trim()
  const addFromDialog = async (search, who) => {
    await pg.locator('[data-add-member]').click()
    await pg.waitForTimeout(400)
    await pg.locator('[data-add-dialog] input').first().click()
    await pg.keyboard.type(search, { delay: 30 })
    await pg.waitForTimeout(1200)
    await pg.getByRole('option', { name: new RegExp(who.split('@')[0].replace(/-/g, '.'), 'i') }).first().click()
    await settle()
  }
  const space = async (name) => (await s.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === name)

  await check('SETTINGS.3', `${width} px: an agent added with Add member shows in Members with its badge and in Agents; access changed in one view shows in the other; a user with no role is offered one`, async () => {
    reset()
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    // the agent: found by Add member with its kind, Can view by default with the note, and at once in the list with its badge
    await addFromDialog('Issue One Agent', I1_AGENT)
    must((await pg.locator('[data-add-picked]').getAttribute('data-kind')) === 'Agent', 'Add member does not show the agent as an agent')
    must(/Can view/.test(await pg.locator('[data-add-dialog] [data-add-access]').first().innerText()), 'an agent does not default to Can view')
    must(await pg.locator('[data-add-agent-note]').isVisible(), 'the note "Agents need Can edit…" is missing')
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1500)
    const row = pg.locator(`[data-members] [data-member="${I1_AGENT}"]`)
    must(await row.count(), 'the agent did not appear in Members after Add')
    must((await row.locator('[data-kind-badge]').innerText()).trim() === 'Agent', 'the agent has no Agent badge')
    must(/Can view/.test(await shownAccess(`[data-access="${I1_AGENT}"]`)), 'the agent was not added with Can view')
    // the filters: All, People, Agents with counts
    const tabs = await pg.locator('[data-member-filter]').innerText()
    const sp = await space(SPACE)
    for (const want of [`All ${sp.members.length}`, `People ${sp.people_count}`, `Agents ${sp.agent_count}`]) must(tabs.replace(/\s+/g, ' ').includes(want), `the filters read "${tabs}", not ${want}`)
    await pg.locator('[data-member-filter]').getByText(/^Agents/).click()
    await settle()
    must(await row.count() && !(await pg.locator('[data-members] [data-kind="Owner"], [data-members] [data-kind="Person"]').count()), 'Agents shows people')
    await pg.locator('[data-member-filter]').getByText(/^People/).click()
    await settle()
    must(!(await row.count()), 'People shows the agent')
    await pg.locator('[data-member-filter]').getByText(/^All/).click()
    await settle()
    // Agents: the same agent, the same access; change it there and Members matches, change it in Members and Agents matches
    await s.open('/life/settings?tab=agents')
    const ref = `${I1_AGENT}|${SPACE}`
    must(await pg.locator(`[data-agent="${I1_AGENT}"]`).count(), 'the agent is not under Agents')
    must(/Can view/.test(await shownAccess(`[data-agent-access="${ref}"]`)), 'Agents does not show Can view')
    must(await pg.locator(`[data-agent-user-link="${I1_AGENT}"]`).count(), 'the agent card has no link to its Frappe user')
    await choose(`[data-agent-access="${ref}"]`, 'Can edit')
    must((await space(SPACE)).members.find((m) => m.user === I1_AGENT)?.access === 'Write', 'Can edit in Agents was not saved')
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    must(/Can edit/.test(await shownAccess(`[data-access="${I1_AGENT}"]`)), 'Members does not match the change made in Agents')
    await choose(`[data-access="${I1_AGENT}"]`, 'Can view')
    await s.open('/life/settings?tab=agents')
    must(/Can view/.test(await shownAccess(`[data-agent-access="${ref}"]`)), 'Agents does not match the change made in Members')
    // a user with no Life OS role: said so, and Add waits until the owner says person or agent; a person gets Can edit
    await s.open('/life/settings?tab=members')
    await pickSpace(SPACE)
    await addFromDialog('Issue One Newcomer', I1_NEW)
    must(await pg.locator('[data-add-no-role]').isVisible(), 'a user with no role is not told so')
    must(await pg.getByRole('button', { name: 'Add', exact: true }).last().isDisabled(), 'Add is possible before choosing person or agent')
    await pg.locator('[data-add-role]').getByText('A person', { exact: true }).click()
    await settle()
    must(/Can edit/.test(await pg.locator('[data-add-dialog] [data-add-access]').first().innerText()), 'a person does not default to Can edit')
    await pg.getByRole('button', { name: 'Add', exact: true }).last().click()
    await pg.waitForTimeout(1500)
    must((await pg.locator(`[data-member="${I1_NEW}"] [data-kind-badge]`).innerText()).trim() === 'Person', 'the newcomer was not added as a person')
    must(!(await pg.locator(`[data-member="${I1_NEW}"] [data-access]`).count()) || /Can edit/.test(await shownAccess(`[data-access="${I1_NEW}"]`)), 'the newcomer was not added with Can edit')
    must(await pg.locator('[data-owner-badge]').count(), 'the owner has no Owner badge')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return 'agent and person added; access matched both ways'
  })

  await check('SETTINGS.4', `${width} px: Ask and agents' sensitive-item access switch from Spaces`, async () => {
    await s.open('/life/settings?tab=spaces')
    const before = await space(SPACE)
    must(/person|people/.test(await pg.locator(`[data-space-counts="${SPACE}"]`).innerText()) && /agent/.test(await pg.locator(`[data-space-counts="${SPACE}"]`).innerText()), 'Spaces has no people and agent counts')
    try {
      await pg.locator(`[data-ask-switch="${SPACE}"]`).click()
      await pg.waitForTimeout(1200)
      must((await space(SPACE)).ask_enabled === (before.ask_enabled ? 0 : 1), 'Ask in this space did not switch')
      await pg.locator(`[data-vault-switch="${SPACE}"]`).click()
      await pg.waitForTimeout(1500)
      must((await space(SPACE)).agents_can_read_vault === (before.agents_can_read_vault ? 0 : 1), 'Agents may open sensitive items did not switch')
      await s.open('/life/settings?tab=agents')
      const said = await pg.locator(`[data-agent-sensitive="${I1_AGENT}|${SPACE}"]`).innerText()
      must(before.agents_can_read_vault ? /No sensitive/.test(said) : /Opens sensitive/.test(said), `the agent card says "${said}" after the switch`)
    } finally {
      await s.api('settings.set_space_ask', { space: SPACE, ask_enabled: before.ask_enabled })
      await s.api('settings.set_agent_vault', { space: SPACE, allowed: before.agents_can_read_vault })
    }
  })

  await check('SETTINGS.5', `${width} px: ?tab=agents and the old names land on Members; Rules and Advanced list no members or agents`, async () => {
    for (const [asked, view] of [['agents', 'agents'], ['assistants', 'agents'], ['people', 'people'], ['spaces', 'spaces']]) {
      await s.open(`/life/settings?tab=${asked}`)
      must((await cur()) === 'members' && new URL(pg.url()).searchParams.get('view') === view, `?tab=${asked} opened ${await cur()} (${pg.url()})`)
    }
    for (const sec of ['rules', 'advanced']) {
      await s.open(`/life/settings?tab=${sec}`)
      must(!(await pg.locator('[data-settings-section] [data-member], [data-settings-section] [data-agent], [data-settings-section] [data-agent-access]').count()), `${sec} lists members or agents`)
      const text = await pg.locator('[data-settings-section]').innerText()
      must(!text.includes(I1_AGENT) && !text.includes('hermes@lifeos.test'), `${sec} names an agent`)
    }
    for (const sec of ['rules', 'advanced']) {
      await s.open(`/life/settings?tab=${sec}`)
      must(!(await pg.locator('[data-vault-switch], [data-ask-switch]').count()), `${sec} still has a per-space switch that moved to Spaces`)
    }
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  await s.api('settings.set_member', { space: SPACE, user: I1_AGENT, remove: 1 }).catch(() => {})
  await s.api('settings.set_member', { space: SPACE, user: I1_NEW, remove: 1 }).catch(() => {})
  await s.ctx.close()
}


// Issue 11: every area picker offers the seven areas of life that are on, each followed by its parts, indented; an area that
// is off, and its parts, are not offered. Checked on the area picker of a task.
for (const width of WIDTHS) {
  const tag = `I11.${width}`
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const SEVEN = ['Career', 'Health', 'Relationships', 'Money', 'Emotions', 'Mind', 'Environment']
  await check('SETTINGS.6', `${width} px: the area picker on a task shows the seven areas that are on with their parts indented, and no area that is off`, async () => {
    const all = (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas
    const life = all.filter((a) => a.is_life_area)
    must(life.map((a) => a.area_name).join() === SEVEN.join(), 'the space does not have the seven: ' + life.map((a) => a.area_name).join(', '))
    const off = life.find((a) => !a.is_on)
    must(off, 'every area of life is on, so nothing can be checked as off')
    const career = life.find((a) => a.area_name === 'Career')
    const hidden = `I11 part of an area that is off ${width} ${stamp}`
    await s.api('settings.save_item', { kind: 'area', space: SPACE, title: hidden, parent_area: off.name })
    const part = `I11 part of Career ${width} ${stamp}`
    const partId = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: part, parent_area: career.name })).name
    const task = await s.api('tasks.quick_add', { text: `I11 task ${width} ${stamp}`, space: SPACE, area: partId })
    const rows = (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas
    await s.open(`/life/goals/tasks?open=task:${task.name}`)
    const button = pg.locator('[data-task-area] button')
    must((await button.innerText()).includes(`Career / ${part}`), 'the picker does not name the task\'s part with its area: ' + await button.innerText())
    await button.click()
    await pg.waitForTimeout(300)
    // textContent keeps the indent, which innerText may trim
    const items = (await pg.getByRole('menuitem').evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+$/, '')))).filter((t) => t.trim() !== 'Remove')
    // where each item's first letter starts on screen
    const starts = await pg.getByRole('menuitem').evaluateAll((els) => els.map((e) => {
      const walk = document.createTreeWalker(e, NodeFilter.SHOW_TEXT)
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const i = n.data.search(/\S/)
        if (i < 0) continue
        const r = document.createRange()
        r.setStart(n, i)
        r.setEnd(n, i + 1)
        return [n.data.trim(), r.getBoundingClientRect().left]
      }
      return [e.textContent.trim(), null]
    }))
    await pg.keyboard.press('Escape')
    const parts = items.filter((t) => t.startsWith(' ')).map((t) => t.trim())
    const tops = items.filter((t) => !t.startsWith(' '))
    const on = life.filter((a) => a.is_on).map((a) => a.area_name)
    must(tops.join() === on.join(), `the areas offered are ${tops.join(', ')}; the areas that are on are ${on.join(', ')}`)
    must(!tops.includes(off.area_name) && !items.some((t) => t.includes(hidden)), `${off.area_name} is off but offered`)
    must(parts.includes(part), 'the new part of Career is not offered, indented')
    // each part sits right under its own area of life
    let current = null
    for (const t of items) {
      if (!t.startsWith(' ')) { current = life.find((a) => a.area_name === t); continue }
      const row = rows.find((a) => a.area_name === t.trim() && a.parent_area)
      must(row && current && row.parent_area === current.name, `${t.trim()} is not listed under its area`)
    }
    // the indent shows: a part's name starts to the right of every area's
    const at = Object.fromEntries(starts)
    const topLeft = Math.max(...tops.map((t) => at[t]))
    must(parts.every((t) => at[t] >= topLeft + 8), 'the parts are not indented: ' + starts.map(([t, x]) => `${t} at ${Math.round(x)}`).join(', '))
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    return `${tops.length} areas on, ${parts.length} parts`
  })
  await s.ctx.close()
}


// Issue 12: Settings > Areas. The seven areas of life with an On/Off switch, their parts with Edit and "+ Add a part of",
// archiving a part that holds open work asks where it goes, and a Life User who is not Life Admin sees it read-only.
for (const width of WIDTHS) {
  const tag = `I12.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e).split('\n')[0]))
  const lifeAreas = async () => (await s.api('area.tree', { space: SPACE, include_off: 1 })).areas.filter((a) => a.is_life_area)
  const lifeArea = async (n) => (await lifeAreas()).find((a) => a.area_name === n)
  const areasPage = async () => { await s.open(`/life/settings?tab=areas&space=${encodeURIComponent(SPACE)}`); await pg.locator('[data-areas-card]').waitFor() }
  const flip = async (n) => {
    await pg.locator(`[data-area-switch="${n}"]`).click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(700)
  }
  // what the area picker of a task offers
  let pickTask = null
  const pickerLabels = async () => {
    if (!pickTask) pickTask = (await s.api('tasks.quick_add', { text: `I12 picker task ${width} ${stamp}`, space: SPACE })).name
    await s.open(`/life/goals/tasks?open=task:${pickTask}`)
    await pg.locator('[data-task-area] button').click()
    await pg.waitForTimeout(300)
    const out = (await pg.getByRole('menuitem').allInnerTexts()).map((t) => t.trim())
    await pg.keyboard.press('Escape')
    return out
  }

  await check('SETTINGS.7', `${width} px: switching Money on shows it in the task area picker; off hides it; its goals come back when it is on again`, async () => {
    const was = (await lifeArea('Money')).is_on
    let goal = null
    try {
      await areasPage()
      if (was) { await flip('Money'); must(!(await lifeArea('Money')).is_on, 'Money did not switch off') }
      await areasPage()
      must((await pg.locator('[data-life-area="Money"]').getAttribute('data-on')) === '0', 'Money does not show as off')
      await flip('Money')
      must((await lifeArea('Money')).is_on, 'the switch did not turn Money on')
      must((await pickerLabels()).includes('Money'), 'Money is on but not in the task area picker')
      goal = (await s.api('goals.create', { title: `I12 goal in Money ${width} ${stamp}`, horizon: 'Long term', space: SPACE, area: (await lifeArea('Money')).name })).name
      const listed = async () => (await s.api('goals.list', { space: SPACE, page_length: 100, area: (await lifeArea('Money')).name }).catch(() => ({ goals: [] }))).goals.some((g) => g.name === goal)
      must(await listed(), 'the new goal in Money is not listed')
      await areasPage()
      must(/\d+ goals?/.test(await pg.locator('[data-life-area="Money"] [data-area-goals]').innerText()), 'Money shows no goal count')
      await flip('Money')
      must(!(await lifeArea('Money')).is_on, 'the switch did not turn Money off')
      must(!(await pickerLabels()).includes('Money'), 'Money is off but still in the task area picker')
      must(!(await s.api('goals.list', { space: SPACE, page_length: 100 })).goals.some((g) => g.name === goal), 'the goal of Money is listed while Money is off')
      await areasPage()
      await flip('Money')
      must((await s.api('goals.list', { space: SPACE, page_length: 100 })).goals.some((g) => g.name === goal), 'the goal did not come back when Money was switched on again')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    } finally {
      if (goal) await s.api('frappe.client.delete', { doctype: 'Life Goal', name: goal }).catch(() => {})
      const m = await lifeArea('Money')
      if (!!m.is_on !== !!was) await s.api('settings.save_item', { kind: 'area', name: m.name, is_on: was ? 1 : 0 })
    }
  })

  await check('SETTINGS.8', `${width} px: adding a part "CIS Board" under Career shows it in the list and in the pickers`, async () => {
    const name = `I12 CIS Board ${width} ${stamp}`
    await areasPage()
    await pg.locator('[data-add-part="Career"]').click()
    await pg.locator('[data-part-title] input, input[data-part-title]').first().fill(name)
    await pg.locator('[data-part-description] input, input[data-part-description]').first().fill('Vice Chair')
    await pg.getByRole('button', { name: 'Add', exact: true }).click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(700)
    const row = pg.locator(`[data-parts-of="Career"] [data-part-name="${name}"]`)
    must(await row.count(), 'the new part is not listed under Career')
    must((await row.innerText()).includes('Vice Chair · no goals'), 'the new part does not show its description and goal count: ' + await row.innerText())
    must((await pickerLabels()).includes(name), 'the new part is not in the task area picker')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check('SETTINGS.9', `${width} px: archiving a part with open tasks asks where to move them, and they end up there`, async () => {
    const career = (await lifeArea('Career')).name
    const part = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: `I12 part to archive ${width} ${stamp}`, parent_area: career })).name
    const dest = `I12 destination ${width} ${stamp}`
    const destId = (await s.api('settings.save_item', { kind: 'area', space: SPACE, title: dest, parent_area: career })).name
    const t1 = (await s.api('tasks.quick_add', { text: `I12 open task one ${width} ${stamp}`, space: SPACE, area: part })).name
    const t2 = (await s.api('tasks.quick_add', { text: `I12 open task two ${width} ${stamp}`, space: SPACE, area: part })).name
    await areasPage()
    await pg.locator(`[data-edit-part="${part}"]`).click()
    await pg.locator('[data-archive-part]').click()
    const dlg = pg.locator('[data-archive-part-dialog]')
    await dlg.waitFor()
    must((await dlg.innerText()).includes('2 open tasks'), 'the dialog does not say what is open: ' + await dlg.innerText())
    await dlg.locator('[data-move-to]').click()
    const options = (await pg.getByRole('option').allInnerTexts()).map((t) => t.trim())
    must(options[0] === 'Career itself' && options.includes(dest), 'the places offered are ' + options.join(', '))
    await pg.getByRole('option', { name: dest, exact: true }).click()
    await pg.getByRole('button', { name: 'Archive', exact: true }).last().click()
    await pg.waitForLoadState('networkidle')
    await pg.waitForTimeout(900)
    for (const t of [t1, t2]) must((await s.api('tasks.get', { task: t })).area === destId, 'a task did not move to the place chosen')
    must((await s.api('settings.get', { space: SPACE })).areas.find((a) => a.name === part).is_archived, 'the part was not archived')
    must(!(await pg.locator(`[data-part="${part}"]`).count()), 'the archived part is still listed')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })

  await check('SETTINGS.10', `${width} px: a Life User who is not Life Admin sees Settings > Areas read-only`, async () => {
    const fam = await session('family@lifeos.test', width)
    try {
      await fam.open('/life/settings?tab=areas&space=Shared')
      const fp = fam.page
      await fp.locator('[data-areas-card]').waitFor()
      const switches = fp.locator('[data-area-switch]')
      must((await switches.count()) === 7, `${await switches.count()} switches, not seven`)
      for (const sw of await switches.all()) must(await sw.isDisabled(), 'a switch can be used')
      must(!(await fp.locator('[data-edit-part], [data-add-part], [data-new]').count()), 'Edit, Add a part or New shows')
      must(await fp.locator('[data-areas-read-only]').isVisible(), 'no line saying only the owner can change areas')
      const career = (await fam.api('area.tree', { space: 'Shared' })).areas.find((a) => a.is_life_area && a.area_name === 'Career')
      const r = await fam.api('settings.save_item', { kind: 'area', name: career.name, is_on: 0 }, { raw: true })
      must(r.status() === 403, `the server let the family user switch an area (HTTP ${r.status()})`)
      must((await s.api('area.tree', { space: 'Shared' })).areas.some((a) => a.name === career.name), 'Career of Shared was switched off')
    } finally { await fam.ctx.close() }
  })

  await check('SETTINGS.11', `${width} px: the screen matches the mockup: intro, one card of the seven, switches, On by default on Career and Health, parts with Edit, the footer`, async () => {
    await areasPage()
    const main = await pg.locator('[data-settings-section]').innerText()
    must(main.includes('Seven areas cover a whole life.'), 'no intro line')
    must(await pg.locator('[data-areas-footer]').innerText() === 'Switching an area off hides it and its goals; nothing is deleted. The Brain stops filing into it and sends those items to Needs you.', 'the footer line differs')
    const names = await pg.locator('[data-life-area]').evaluateAll((els) => els.map((e) => e.getAttribute('data-life-area')))
    must(names.length === 7 && new Set(names).size === 7, 'not the seven: ' + names.join(', '))
    const ons = await pg.locator('[data-life-area]').evaluateAll((els) => els.map((e) => e.getAttribute('data-on')))
    must(ons.join('').replace(/0+$/, '').indexOf('0') < 0, 'the areas that are on are not listed first')
    const byDefault = await pg.locator('[data-life-area]').evaluateAll((els) => els.filter((e) => [...e.querySelectorAll('*')].some((x) => x.textContent.trim() === 'On by default' && x.offsetParent)).map((e) => e.getAttribute('data-life-area')))
    must(byDefault.sort().join() === 'Career,Health', '"On by default" is on ' + byDefault.join(', '))
    // the switch: left of the name on a wide screen, on the right on a phone
    for (const n of ['Career', 'Health']) {
      const sw = await pg.locator(`[data-area-switch="${n}"]`).boundingBox()
      const nm = await pg.locator(`[data-life-area="${n}"] [data-area-name]`).boundingBox()
      const card = await pg.locator('[data-areas-card]').boundingBox()
      if (phone) must(sw.x > nm.x + nm.width && sw.x + sw.width > card.x + card.width - 40, `${n}: the switch is not on the right`)
      else must(sw.x + sw.width < nm.x, `${n}: the switch is not left of the name`)
    }
    const parts = pg.locator('[data-parts-of="Career"] [data-part]')
    must(await parts.count(), 'Career lists no parts')
    must(await pg.locator('[data-parts-of="Career"] [data-edit-part]').count() === await parts.count(), 'a part has no Edit')
    must(/(no goals|\d+ goals?)\s*Edit$/.test((await parts.first().innerText()).trim()), 'a part shows no goal count before its Edit: ' + await parts.first().innerText())
    must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
  })
  if (pickTask) await s.api('frappe.client.delete', { doctype: 'Life Task', name: pickTask }).catch(() => {})
  await s.ctx.close()
}


// Issue 26: the ladder. A user made for the run (their own space, one task) is at level 1; their records are deleted after.
// I26.1 and I26.2 are unit tests (test_issue26_ladder).
for (const width of WIDTHS) {
  const tag = `I26.${width}`
  const phone = width < 800
  const user = `i26-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I26 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Task",):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let s
  try {
    bench(`from lifeos import devtools
devtools.make_user("${user}", "Ladder", ["Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)
frappe.get_doc({"doctype": "Life Task", "space": "${space}", "title": "I26 task ${width} ${stamp}"}).insert(ignore_permissions=True)`)
    s = await session(user, width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    // the card is in the sidebar on a desktop and in the menu sheet (the title) on a phone
    const openCard = async () => {
      await s.open('/life/today')
      if (phone) await pg.locator('[data-more-title]').click()
      return pg.locator('[data-setup-card]:visible')
    }
    await check('SETTINGS.12', `${width} px: the setup card shows the level and the next step, and links to How it works`, async () => {
      const card = await openCard()
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('Your setup · level 1 of 6'), 'the card says: ' + t)
      must(t.includes('Next: Connect a source'), 'the next step is not Connect a source: ' + t)
      await card.locator('[data-setup-how]').click()
      await pg.waitForFunction(() => location.pathname.endsWith('/how-it-works'), null, { timeout: 8000 })
      await pg.locator('[data-how]').waitFor({ timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('SETTINGS.13', `${width} px: How it works marks the current level as next, and shows the flow`, async () => {
      await s.open('/life/how-it-works')
      await pg.locator('[data-ladder]').waitFor({ timeout: 10000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-ladder-level]').length === 6, null, { timeout: 8000 })
      const marks = await pg.locator('[data-ladder-level]').evaluateAll((els) => els.map((e) => e.dataset.ladderMark).join())
      must(marks === 'done,next,later,later,later,later', 'the levels are marked ' + marks)
      const next = await pg.locator('[data-ladder-mark="next"]').innerText()
      must(next.includes('Level 2 · next') && next.includes('Connect a source'), 'next says: ' + next)
      must((await pg.locator('[data-how-flow] [data-how-step]').count()) === 4, 'the flow is not four boxes')
      await noSideways()
    })
    await check('SETTINGS.14', `${width} px: dismissing the card hides it for that user, and Settings still reaches How it works`, async () => {
      const card = await openCard()
      await card.locator('[data-setup-dismiss]').click()
      await pg.waitForFunction(() => !document.querySelector('[data-setup-card]'), null, { timeout: 8000 })
      await s.open('/life/today')
      await pg.waitForTimeout(800)
      if (phone) await pg.locator('[data-more-title]').click()
      must((await pg.locator('[data-setup-card]').count()) === 0, 'the card came back after a reload')
      await s.open('/life/settings?tab=places')
      await pg.locator('[data-settings-how]').click()
      await pg.waitForFunction(() => location.pathname.endsWith('/how-it-works'), null, { timeout: 8000 })
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}


// Issue 27: Settings, Assistant, Cost lists this month's spend by feature, matching the recorded calls. I27.1 to I27.4 are unit tests
// (test_issue27_gateway). The run's own calls are written under a feature made for it and deleted after.
for (const width of WIDTHS) {
  const tag = `I27.${width}`
  const feature = `I27 feature ${width} ${stamp}`
  const restore = () => bench(`frappe.db.delete("Life AI Usage", {"purpose": "${feature}"})`)
  let s
  try {
    // two haiku calls of 1,000,000 tokens in and 100,000 out: $0.15 each, $0.30 and 2,200,000 tokens in all
    bench(`from lifeos.ai import client
for _i in range(2):
    client.record("claude-haiku-5-5", {"input_tokens": 1000000, "output_tokens": 100000}, "${feature}", user="owner@lifeos.test")`)
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    await check('SETTINGS.15', `${width} px: Cost shows this month's spend by feature, matching the recorded calls`, async () => {
      await s.open('/life/settings?tab=cost')
      await pg.locator('[data-ai-spend]').waitFor({ timeout: 10000 })
      const row = pg.locator(`[data-cost-feature="${feature}"]`)
      await row.waitFor({ timeout: 8000 })
      const t = await row.innerText()
      must(t.includes('2,200,000 tokens') && t.includes('$0.30'), 'the feature row says: ' + t)
      must(/This month: \$/.test(await pg.locator('[data-cost-total]').innerText()), 'no this-month total')
      must((await pg.locator('[data-cost-call]').count()) >= 2, 'the last calls are not listed')
      must((await pg.locator('[data-cost-days]').innerText()).includes('call'), 'no by-day list')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}


// Issue 28: Brain > Skills lists process-capture; Test runs its examples (recorded answers) and shows pass or fail before saving; editing and
// saving makes version 2. A skill with no examples and no runs shows its empty states. I28.1 to I28.9 and I28.11 and .12 are unit tests
// (test_issue28_skills). The built-in skill is put back as the app ships it after, and the skill made here is deleted.
for (const width of WIDTHS) {
  const tag = `I28.${width}`
  const reset = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Skill Run", "Life Skill Version", "Life Skill Example"):
    frappe.db.delete(dt, {"skill": ("in", ["process-capture", "i28-empty-${width}"])})
frappe.db.delete("Life Skill", {"name": ("in", ["process-capture", "i28-empty-${width}"])})
from lifeos.skills import store
store.install()`)
  let s
  try {
    reset()
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    await check('SETTINGS.16', `${width} px: Skills lists process-capture, Test shows pass for each example, saving an edit makes version 2`, async () => {
      await s.open('/life/brain/skills')
      const card = pg.locator('[data-skill-card][data-skill="process-capture"]')
      await card.waitFor({ timeout: 10000 })
      const t = await card.innerText()
      must(t.includes('Process a capture') && t.includes('v1') && t.includes('Built-in') && /run/.test(t), 'the card says: ' + t)
      await noSideways()
      await card.locator('[data-skill-open]').click()
      await pg.locator('[data-skill-page][data-skill="process-capture"]').waitFor({ timeout: 10000 })
      must(await pg.locator('[data-skill-example]').count() === 4, 'the examples are not listed')
      await pg.locator('[data-skill-test]').click()
      await pg.locator('[data-example-result]').first().waitFor({ timeout: 15000 })
      await pg.waitForFunction(() => document.querySelectorAll('[data-example-result]').length === 4, null, { timeout: 15000 })
      const results = await pg.locator('[data-example-result]').evaluateAll((els) => els.map((e) => e.getAttribute('data-example-result')))
      must(results.every((r) => r === 'pass'), 'the examples say: ' + results.join(','))
      await pg.locator('[data-skill-text]').fill((await pg.locator('[data-skill-text]').inputValue()) + '\nAlways write the summary in plain words.\n')
      await pg.locator('[data-skill-save]').click()
      await pg.waitForFunction(() => document.querySelector('[data-skill-page]')?.getAttribute('data-version') === '2', null, { timeout: 10000 })
      must(await pg.locator('[data-skill-version-row]').count() === 2, 'two versions are not listed')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('SETTINGS.17', `${width} px: a skill with no examples and no runs says what will appear`, async () => {
      await s.api('skills.create', { slug: `i28-empty-${width}`, values: JSON.stringify({ title: `I28 empty ${width}`, trigger_kind: 'Button', tools: [], output_kind: 'Answer', instructions: 'Say hello.' }) })
      await s.open(`/life/brain/skills/i28-empty-${width}`)
      await pg.locator('[data-skill-page]').waitFor({ timeout: 10000 })
      const empties = await pg.locator('[data-empty]').allInnerTexts()
      must(empties.some((e) => e.includes('No examples yet.')) && empties.some((e) => e.includes('No runs yet.')), 'the empty states say: ' + empties.join(' | '))
      await noSideways()
    })
  } finally {
    if (s) await s.ctx.close()
    reset()
  }
}


// Issue 30: a proposed lesson shows in Needs you and on the skill page; Edit then Accept saves the edited words as a new version of the skill;
// removing an accepted lesson makes a version without it. I30.1, .2 and .5 are unit tests (test_issue30_lessons). The acceptance site's stand-in
// model answers every capture the same way, so process-capture's examples are replaced here by one it passes, and put back (store.install) after.
for (const width of WIDTHS) {
  const tag = `I30.${width}`
  const reset = (examples) => bench(`frappe.set_user("Administrator")
for dt in ("Life Skill Correction", "Life Skill Lesson"):
    frappe.db.delete(dt)
for dt in ("Life Skill Run", "Life Skill Version", "Life Skill Example"):
    frappe.db.delete(dt, {"skill": "process-capture"})
frappe.db.delete("Life Skill", {"name": "process-capture"})
from lifeos.skills import store
store.install()
${examples ? `frappe.db.delete("Life Skill Example", {"skill": "process-capture"})
import json
frappe.get_doc({"doctype": "Life Skill Example", "skill": "process-capture", "title": "Anything is filed", "source": "Owner",
  "input": json.dumps({"title": "Robusta prices", "text": "Robusta is up."}), "expected": json.dumps([{"has_proposal": {"kind": "Task"}}])}).insert()` : ''}`)
  // a proposed lesson with the three corrections it came from, as the Brain's improve-skill would have made it
  const propose = () => JSON.parse(bench(`import json
lesson = frappe.get_doc({"doctype": "Life Skill Lesson", "skill": "process-capture", "space": "${SPACE}", "status": "Proposed", "base_version": 1,
  "summary": "Commodity newsletters", "text": "Newsletters about commodity prices are for reading later, never a task."}).insert()
for i in range(3):
    frappe.get_doc({"doctype": "Life Skill Correction", "skill": "process-capture", "skill_version": 1, "space": "${SPACE}", "correction_type": "Area",
      "key": "area:Task:a>b", "detail": "The Brain filed a Task under Money; the owner filed it under Career.", "capture_title": f"Robusta prices {i}", "lesson": lesson.name}).insert()
print(json.dumps(lesson.name))`).split('\n').pop())
  let s
  try {
    reset(true)
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const noSideways = async () => must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    await check('SETTINGS.18', `${width} px: with no lessons Needs you has no lessons section and the skill page says what will appear`, async () => {
      await s.open('/life/brain')
      await pg.locator('[data-needs-you]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-needs-lessons]').count()) === 0, 'a lessons section shows with no lessons')
      await s.open('/life/brain/skills/process-capture')
      await pg.locator('[data-skill-lessons]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-skill-lessons]').innerText()).includes('No lessons yet.'), 'the skill page does not say what will appear')
      await noSideways()
    })
    await check('SETTINGS.19', `${width} px: a lesson shows in Needs you and on the skill page; Edit then Accept saves the edited words`, async () => {
      const name = propose()
      await s.open('/life/brain')
      const card = pg.locator(`[data-needs-lessons] [data-lesson="${name}"]`)
      await card.waitFor({ timeout: 10000 })
      must((await card.innerText()).includes('Newsletters about commodity prices') && (await card.innerText()).includes('3 corrections'), 'the lesson says: ' + (await card.innerText()))
      await noSideways()
      await s.open('/life/brain/skills/process-capture')
      await pg.locator(`[data-skill-lessons] [data-lesson="${name}"]`).waitFor({ timeout: 10000 })
      await s.open('/life/brain')
      await card.waitFor({ timeout: 10000 })
      await card.locator('[data-lesson-edit]').click()
      await card.locator('[data-lesson-text]').fill('Price newsletters are read later, not tasks.')
      await card.locator('[data-lesson-accept]').click()
      await pg.waitForFunction((n) => !document.querySelector(`[data-needs-lessons] [data-lesson="${n}"]`), name, { timeout: 15000 })
      const d = await s.api('skills.detail', { name: 'process-capture' })
      must(d.version === 2 && d.instructions.includes('Price newsletters are read later, not tasks.') && !d.instructions.includes('commodity prices'), 'the skill is: version ' + d.version)
      await s.open('/life/brain/skills/process-capture')
      const done = pg.locator(`[data-skill-lessons] [data-lesson="${name}"][data-status="Accepted"]`)
      await done.waitFor({ timeout: 10000 })
      must((await done.locator('[data-lesson-version]').innerText()).includes('version 2'), 'the lesson does not link its version')
      await noSideways()
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('SETTINGS.20', `${width} px: removing an accepted lesson makes a new version without it`, async () => {
      await s.open('/life/brain/skills/process-capture')
      const done = pg.locator('[data-skill-lessons] [data-lesson][data-status="Accepted"]')
      await done.waitFor({ timeout: 10000 })
      await done.locator('[data-lesson-remove]').click()
      await pg.waitForFunction(() => document.querySelector('[data-skill-page]')?.getAttribute('data-version') === '3', null, { timeout: 15000 })
      const d = await s.api('skills.detail', { name: 'process-capture' })
      must(!d.instructions.includes('Price newsletters') && !d.instructions.includes('Lessons from'), 'the text still has the lesson')
      must((await pg.locator('[data-skill-lessons] [data-lesson][data-status="Removed"]').count()) === 1, 'the lesson is not shown as removed')
      await noSideways()
    })
  } finally {
    if (s) await s.ctx.close()
    reset(false)
  }
}


// Issue 31: Settings > Calendar shows the calendars of the connected account and saves the one Life OS writes to (off by default).
// I31.1 to I31.4 are unit tests (test_issue31_gcal_write). The fixture calendar stands in for Google; the choice is cleared after.
for (const width of WIDTHS) {
  const tag = `I31.${width}.5`
  const restore = () => bench('frappe.defaults.clear_default("life_write_calendar", parent="owner@lifeos.test")')
  let s
  try {
    restore()
    s = await session('owner@lifeos.test', width)
    const pg = s.page
    await check('SETTINGS.21', `${width} px: Settings > Calendar lists the account's calendars and saves the one to write to`, async () => {
      await s.open('/life/settings?tab=calendar')
      const pick = pg.locator('[data-calendar-write]')
      await pick.waitFor({ timeout: 10000 })
      must((await pick.inputValue()) === '', 'writing is not off by default')
      must((await pick.locator('option').count()) >= 2, 'the calendars of the account are not listed')
      await pick.selectOption('primary')
      await pg.waitForTimeout(800)
      await s.open('/life/settings?tab=calendar')
      await pg.locator('[data-calendar-write]').waitFor({ timeout: 10000 })
      must((await pg.locator('[data-calendar-write]').inputValue()) === 'primary', 'the choice was not saved')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally {
    if (s) await s.ctx.close()
    restore()
  }
}


// Issue 44: Settings, simplified. Eight items and Advanced; old links land on their new places; the ladder decides what a person who is not
// a Life Admin sees. I44.6 (rename and merge tags in Library) was dropped by issue 60: Settings > Tags simply goes.
for (const width of WIDTHS) {
  const tag = `I44.${width}`
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
  const settle = () => pg.waitForTimeout(600)
  const cur = () => pg.locator('[data-settings-section]').getAttribute('data-current')
  const items = () => pg.locator('[data-settings-menu] [data-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-section')))
  const was = (await s.api('settings.get', { space: SPACE })).settings
  const save = (values) => s.api('settings.save', { values })
  try {
    await check('SETTINGS.22', `${width} px: the owner's menu is Profile, Calendar, Areas, Rhythms, Habits, Data, Sources, Rules, Members in four groups, and Advanced at the bottom`, async () => {
      await s.open('/life/settings')
      await pg.locator('[data-settings-menu] [data-section]').first().waitFor()
      must(JSON.stringify(await items()) === JSON.stringify(['profile', 'calendar', 'areas', 'rhythms', 'habits', 'data', 'sources', 'rules', 'members', 'advanced']), `the menu lists ${await items()}`)
      const groups = await pg.locator('[data-settings-menu] [data-settings-group]').evaluateAll((els) => els.map((e) => e.getAttribute('data-settings-group')))
      must(JSON.stringify(groups) === JSON.stringify(['me', 'space', 'brain', 'people']), `the groups are ${groups}`)
      must(!(await pg.locator('[data-settings-later]').count()), 'a Life Admin is told more settings come later')
      const adv = await pg.locator('[data-settings-menu] [data-section]').last().getAttribute('data-section')
      must(adv === 'advanced', 'Advanced is not last')
      if (phone) must(!(await pg.locator('[data-settings-section]').count()), 'on a phone a section is open before the menu')
      else must((await cur()) === 'profile', 'the first page is not Profile')
      // Sources opens the Brain's screen
      await pg.locator('[data-settings-menu] [data-section="sources"]').click()
      await settle()
      must(new URL(pg.url()).pathname === '/life/brain/sources', `Sources opened ${pg.url()}`)
    })

    await check('SETTINGS.23', `${width} px: Rhythms holds the weekly review, old items, working hours and the 12 Week Year, and each saves the same setting`, async () => {
      await s.open('/life/settings?tab=rhythms')
      await pg.locator('[data-settings-rhythms]').waitFor()
      const text = await pg.locator('[data-settings-section]').innerText()
      for (const want of ['Weekly review', 'Week starts on', 'Inbox items not dealt with', 'Working days', 'Current cycle', 'Score target', 'Break week'])
        must(text.includes(want), `Rhythms does not show "${want}"`)
      must(!text.includes('Check-in dimensions') && !text.includes('Month plan'), 'Rhythms still shows the check-in dimensions or the month plan')
      const pick = async (sel, label) => { await pg.locator(sel).first().click(); await pg.getByRole('option', { name: label, exact: true }).first().click(); await settle() }
      const day = was.weekly_review_day === 'Tuesday' ? 'Wednesday' : 'Tuesday'
      await pick('[data-setting="weekly_review_day"]', day)
      must((await s.api('settings.get', { space: SPACE })).settings.weekly_review_day === day, 'the review day was not saved')
      const start = was.week_starts_on === 'Sunday' ? 'Monday' : 'Sunday'
      await pick('[data-setting="week_starts_on"]', start)
      must((await s.api('settings.get', { space: SPACE })).settings.week_starts_on === start, 'week start was not saved')
      const box = pg.locator('input[data-setting="old_inbox_days"], [data-setting="old_inbox_days"] input').first()
      const days = Number(was.old_inbox_days || 7) === 9 ? 10 : 9
      await box.fill(String(days)); await box.press('Tab'); await settle()
      must(Number((await s.api('settings.get', { space: SPACE })).settings.old_inbox_days) === days, 'the old-items days were not saved')
      const wd = pg.locator('[data-work-day="Sunday"]')
      const had = String(was.work_days || 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday').includes('Sunday')
      await wd.click(); await settle()
      must(String((await s.api('settings.get', { space: SPACE })).settings.work_days).includes('Sunday') === !had, 'the working days were not saved')
      const target = was.score_target === 77 ? 78 : 77
      const tb = pg.locator('input[data-setting="score_target"], [data-setting="score_target"] input').first()
      await tb.fill(String(target)); await tb.press('Tab'); await settle()
      must(Number((await s.api('settings.get', { space: SPACE })).settings.score_target) === target, 'the score target was not saved')
      const brk = pg.locator('[data-setting="cycle_break_week"]')
      const bwant = was.cycle_break_week ? 'No' : 'Yes'
      await brk.getByText(bwant, { exact: true }).click(); await settle()
      must(Number((await s.api('settings.get', { space: SPACE })).settings.cycle_break_week) === (bwant === 'Yes' ? 1 : 0), 'the break week was not saved')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('SETTINGS.24', `${width} px: Profile shows Look and Reminders, and the theme takes effect`, async () => {
      await s.open('/life/settings?tab=profile')
      await pg.locator('[data-settings-profile]').waitFor()
      must(await pg.locator('[data-settings-look]').count() && await pg.locator('[data-settings-notifications]').count(), 'Profile has no Look or Reminders')
      must(/Keyboard shortcuts: press \? anywhere/.test(await pg.locator('[data-settings-shortcuts]').innerText()), 'no keyboard shortcuts line')
      const isDark = () => pg.evaluate(() => document.documentElement.classList.contains('dark') || document.documentElement.getAttribute('data-theme') === 'dark')
      try {
        await pg.locator('[data-theme-switch]').getByText('Dark', { exact: true }).click(); await settle()
        must(await isDark(), 'Dark did not take effect')
        await pg.locator('[data-theme-switch]').getByText('Light', { exact: true }).click(); await settle()
        must(!(await isDark()), 'Light did not take effect')
      } finally {
        await pg.locator('[data-theme-switch]').getByText('Light', { exact: true }).click()
      }
    })

    await check('SETTINGS.25', `${width} px: every old ?tab= value lands on its new place`, async () => {
      const MAP = [['default', 'profile'], ['appearance', 'profile'], ['notifications', 'profile'], ['shortcuts', 'profile'], ['calendar', 'calendar'], ['areas', 'areas'],
        ['rhythms', 'rhythms'], ['review', 'rhythms'], ['reset', 'data'], ['data', 'data'], ['habits', 'habits'], ['sensitive', 'rules'], ['note-rules', 'rules'],
        ['spaces', 'members', 'spaces'], ['members', 'members'], ['agents', 'members', 'agents'], ['ai', 'advanced', null, 'ai'], ['cost', 'advanced', null, 'ai'],
        ['import', 'advanced', null, 'import'], ['backups', 'advanced', null, 'backups'], ['places', 'profile']]
      for (const [old, now, view, part] of MAP) {
        await s.open(`/life/settings?tab=${old}`)
        await pg.locator('[data-settings-section]').waitFor()
        const u = new URL(pg.url())
        must((await cur()) === now && (view ? u.searchParams.get('view') === view : true) && (part && part !== 'ai' ? u.searchParams.get('part') === part : true), `?tab=${old} opened ${await cur()} at ${pg.url()}`)
      }
      for (const [old, path] of [['tags', '/life/library/archive'], ['archive', '/life/library/archive'], ['archived', '/life/library/archive'], ['connections', '/life/brain/sources'], ['sources', '/life/brain/sources']]) {
        await s.open(`/life/settings?tab=${old}`)
        must(new URL(pg.url()).pathname === path, `?tab=${old} opened ${pg.url()}, not ${path}`)
      }
    })

    await check('SETTINGS.26', `${width} px: Members lists people and agents with filters and a Spaces view that still switches Ask and sensitive-item access`, async () => {
      await s.open('/life/settings?tab=members')
      await pg.locator('[data-member-filter]').waitFor()
      const tabs = (await pg.locator('[data-member-filter]').innerText()).replace(/\s+/g, ' ')
      for (const w of ['All', 'People', 'Agents', 'Spaces']) must(tabs.includes(w), `the filters read "${tabs}"`)
      must(await pg.locator('[data-members] [data-member]').count(), 'Members lists nobody')
      await pg.locator('[data-member-filter]').getByText(/^Spaces/).click(); await settle()
      must(new URL(pg.url()).searchParams.get('view') === 'spaces' && await pg.locator(`[data-space-card="${SPACE}"]`).count(), 'the Spaces view does not show the space')
      const before = (await s.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE)
      try {
        await pg.locator(`[data-ask-switch="${SPACE}"]`).click(); await settle()
        must((await s.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE).ask_enabled === (before.ask_enabled ? 0 : 1), 'Ask did not switch')
        await pg.locator(`[data-vault-switch="${SPACE}"]`).click(); await settle()
        must((await s.api('settings.get', { space: SPACE })).spaces.find((x) => x.name === SPACE).agents_can_read_vault === (before.agents_can_read_vault ? 0 : 1), 'sensitive-item access did not switch')
        await s.open('/life/settings?tab=rules')
        await pg.locator(`[data-ask-vault-switch="${SPACE}"]`).waitFor()
      } finally {
        await s.api('settings.set_space_ask', { space: SPACE, ask_enabled: before.ask_enabled })
        await s.api('settings.set_agent_vault', { space: SPACE, allowed: before.agents_can_read_vault })
      }
    })

    await check('SETTINGS.27', `${width} px: Settings has no Tags page; Library's Trash and archive is where ?tab=tags goes`, async () => {
      await s.open('/life/settings')
      await pg.locator('[data-settings-menu] [data-section]').first().waitFor()
      must(!(await pg.locator('[data-settings-menu] [data-section="tags"]').count()), 'Settings still has Tags')
      await s.open('/life/settings?tab=tags')
      must(new URL(pg.url()).pathname === '/life/library/archive', `?tab=tags opened ${pg.url()}`)
    })

    // non-admins and the ladder: the level is the one the server reports, set here for each case
    const fam = await session('family@lifeos.test', width)
    try {
      const levelAt = async (n) => {
        await fam.page.route('**/lifeos.api.meta.setup_level*', (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: { level: n, of: 6, complete: false, dismissed: true, next: null, levels: [], done: [], how: [] } }) }))
        await fam.open('/life/settings')
        await fam.page.waitForFunction((lv) => document.querySelector('[data-settings-menu]') && (lv === 6 || document.querySelector('[data-settings-later]')), n, { timeout: 8000 }).catch(() => {})
        await fam.page.waitForTimeout(600)
        await fam.page.unroute('**/lifeos.api.meta.setup_level*')
        return fam.page.locator('[data-settings-menu] [data-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-section')))
      }
      await check('SETTINGS.28', `${width} px: a person who is not a Life Admin at level 1 sees Profile, Areas and Sources and the footer line; Rhythms appears at level 4`, async () => {
        const one = await levelAt(1)
        must(JSON.stringify(one) === JSON.stringify(['profile', 'areas', 'sources']), `level 1 shows ${one}`)
        const line = await fam.page.locator('[data-settings-later]').innerText()
        must(/More settings appear as you go up the ladder/.test(line) && /Rhythms and Data at level 4/.test(line), `the footer says "${line}"`)
        const four = await levelAt(4)
        must(JSON.stringify(four) === JSON.stringify(['profile', 'calendar', 'areas', 'rhythms', 'habits', 'data', 'sources', 'rules']), `level 4 shows ${four}`)
        // a page that is not in the menu yet is still reached by its link
        await fam.open('/life/settings?tab=habits')
        await fam.page.locator('[data-settings-section]').waitFor()
        must((await fam.page.locator('[data-settings-section]').getAttribute('data-current')) === 'habits', 'a link to a page not in the menu yet did not open it')
      })
      await check('SETTINGS.29', `${width} px: a person who is not a Life Admin does not see Advanced; the owner's Advanced opens AI key and cost, Import and export and Backups`, async () => {
        const all = await levelAt(6)
        must(!all.includes('advanced') && !all.includes('members'), `a non-admin at level 6 sees ${all}`)
        await fam.open('/life/settings?tab=advanced')
        await fam.page.waitForTimeout(800)
        must((await fam.page.locator('[data-settings-section]').getAttribute('data-current').catch(() => null)) !== 'advanced', 'a non-admin opened Advanced')
        await s.open('/life/settings?tab=advanced')
        await pg.locator('[data-advanced-parts]').waitFor()
        must(await pg.locator('[data-ai-settings]').count(), 'Advanced does not open AI key and cost')
        await pg.locator('[data-advanced-parts]').getByText('Import and export', { exact: true }).click(); await settle()
        must(await pg.locator('[data-chat-import]').count(), 'no Import and export')
        await pg.locator('[data-advanced-parts]').getByText('Backups', { exact: true }).click(); await settle()
        must(await pg.locator('[data-settings-backups]').count(), 'no Backups')
      })
    } finally { await fam.ctx.close() }

    await check('SETTINGS.30', `${width} px: the menu is the first screen on a phone and every page opens with Back`, async () => {
      for (const sec of ['profile', 'calendar', 'areas', 'rhythms', 'habits', 'rules', 'members', 'advanced']) {
        await s.open('/life/settings')
        await pg.locator(`[data-settings-menu] [data-section="${sec}"]`).waitFor()
        if (phone) must(!(await pg.locator('[data-settings-section]').count()), 'a section is open before the menu')
        await pg.locator(`[data-settings-menu] [data-section="${sec}"]`).click(); await settle()
        must((await cur()) === sec, `the menu did not open ${sec}`)
        const w = await pg.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        must(w <= 1, `${sec} scrolls sideways`)
        if (phone) {
          must(!(await pg.locator('[data-settings-menu]').count()), `${sec}: the menu is still shown`)
          await pg.locator('[data-settings-back]').click(); await settle()
          must(await pg.locator('[data-settings-menu]').isVisible() && !(await pg.locator('[data-settings-section]').count()), `${sec}: Back did not return to the menu`)
        }
      }
    })
  } finally {
    await save({ weekly_review_day: was.weekly_review_day, week_starts_on: was.week_starts_on || 'Monday', old_inbox_days: was.old_inbox_days || 7, work_days: was.work_days || 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday',
      score_target: was.score_target, cycle_break_week: was.cycle_break_week ? 1 : 0 })
    await s.ctx.close()
  }
}


// Issue 46: one space on new sites, and no lens. I46.1 and I46.2 are unit tests (test_i46_one_space). A user made for the run, with
// their own single space, stands for a new site (the acceptance site keeps two spaces, for I46.4 and I46.6). Titles start "I46 ".
for (const width of WIDTHS) {
  const tag = `I46.${width}`
  const phone = width < 800
  const user = `i46-${width}-${stamp}@lifeos.test`.toLowerCase()
  const space = `I46 ${width} ${stamp}`
  const restore = () => bench(`frappe.set_user("Administrator")
for dt in ("Life Task",):
    for n in frappe.get_all(dt, filters={"space": "${space}"}, pluck="name"): frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
from lifeos import devtools
devtools.purge_space("${space}", drop=True)
frappe.db.delete("DefaultValue", {"parent": "${user}"})
if frappe.db.exists("User", "${user}"): frappe.delete_doc("User", "${user}", force=1, ignore_permissions=True)`)
  let one = null
  const owner = await session('owner@lifeos.test', width)
  try {
    bench(`from lifeos import devtools
devtools.make_user("${user}", "One", ["Life Admin", "Life User"])
frappe.db.sql("delete from __Auth where doctype='User' and name=%s and fieldname='password'", "${user}")
frappe.db.sql("insert into __Auth (doctype, name, fieldname, password, encrypted) select doctype, %s, fieldname, password, encrypted from __Auth where doctype='User' and name='owner@lifeos.test' and fieldname='password'", "${user}")
frappe.get_doc({"doctype": "Life Space", "space_name": "${space}", "owner_user": "${user}", "members": [{"user": "${user}", "access": "Write"}]}).insert(ignore_permissions=True)
frappe.get_doc({"doctype": "Life Task", "space": "${space}", "title": "I46 task ${width} ${stamp}"}).insert(ignore_permissions=True)`)
    one = await session(user, width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    const settle = () => pg.waitForTimeout(700)
    const spaceUi = '[data-space-picker] button, [data-space-item], [data-space-sheet], [data-settings-space], [data-space-card], [data-member-spaces], [data-new-space], [data-space-chip]'

    await check('SETTINGS.31', `${width} px: on a one-space site no space picker, chip or Spaces view appears on any screen`, async () => {
      const screens = ['/life', '/life/brain', '/life/brain/captures', '/life/goals', '/life/goals/tasks', '/life/goals/someday', '/life/goals/cycles', '/life/library',
        '/life/library/notes', '/life/library/people', '/life/library/timeline', '/life/library/archive', '/life/today/week?view=calendar', '/life/ask',
        ...['profile', 'appearance', 'calendar', 'areas', 'rhythms', 'habits', 'rules', 'members', 'sources', 'advanced'].map((t) => `/life/settings?tab=${t}`),
        '/life/settings?tab=members&view=spaces', '/life/settings?tab=spaces']
      for (const p of screens) {
        await one.open(p)
        await settle()
        must(await pg.locator(spaceUi).count() === 0, `${p}: a space control is shown`)
        const text = await pg.locator('[data-main]').innerText()
        must(!/\bSpaces\b/.test(text) && !/Default space/.test(text) && !/Space for these settings/.test(text), `${p}: the page mentions spaces`)
        must(!/[Nn]o space/.test(text) && !text.includes(space), `${p}: the page shows a space name`)
      }
      if (phone) {
        await one.open('/life')
        await pg.locator('[data-more-title]').click()
        await pg.locator('[data-more-sheet]').waitFor()
        must(await pg.locator('[data-space-sheet]').count() === 0, 'the menu sheet lists spaces')
        must((await pg.locator('[data-more-title]').innerText()).trim() === 'Life OS', 'the title shows a space')
        await pg.keyboard.press('Escape')
      } else {
        must(!(await pg.locator('[data-sidebar] [data-slot="sidebar-header"]').innerText()).includes(space), 'the sidebar shows the space')
      }
      await one.open('/life/settings?tab=members')
      await settle()
      const tabs = await pg.locator('[data-member-filter]').innerText()
      must(!/Spaces/.test(tabs), `Members offers ${tabs.replace(/\s+/g, ' ')}`)
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })

    await check('SETTINGS.32', `${width} px: on a one-space site Ask is switched in Advanced and "Agents may open sensitive items" in Rules, and each takes effect`, async () => {
      const get = async () => (await one.api('settings.get', { space })).spaces.find((x) => x.name === space)
      const was = await get()
      try {
        await one.open('/life/settings?tab=advanced')
        const ask = pg.locator('[data-ai-ask] [data-ask-switch]')
        await ask.waitFor({ timeout: 10000 })
        await ask.click()
        await pg.waitForLoadState('networkidle')
        await settle()
        must(!!(await get()).ask_enabled !== !!was.ask_enabled, 'the Ask switch did not change the setting')
        await one.open('/life/settings?tab=rules')
        const vault = pg.locator('[data-sensitive-agents] [data-vault-switch]')
        await vault.waitFor({ timeout: 10000 })
        await vault.click()
        await pg.waitForLoadState('networkidle')
        await settle()
        must(!!(await get()).agents_can_read_vault !== !!was.agents_can_read_vault, 'the sensitive-items switch did not change the setting')
        must(await pg.locator('[data-sensitive] [data-ask-vault-switch]').count() === 1, 'Ask may read sensitive items is not in Rules')
      } finally {
        await one.api('settings.set_space_ask', { space, ask_enabled: was.ask_enabled ? 1 : 0 }).catch(() => {})
        await one.api('settings.set_agent_vault', { space, allowed: was.agents_can_read_vault ? 1 : 0 }).catch(() => {})
      }
    })

    await check('SETTINGS.33', `${width} px: a capture sent without a space on a one-space site lands in that space`, async () => {
      const made = await one.api('inbox.create_item', { title: `I46 capture ${width} ${stamp}`, raw_text: 'one space' })
      must(made.space === space, `the capture went to ${made.space}`)
    })
  } finally {
    if (one) await one.ctx.close()
    restore()
  }

  const pg = owner.page
  const settle = () => pg.waitForTimeout(700)
  try {
    await check('SETTINGS.34', `${width} px: the sidebar has no lens and no pinned areas; ?area= on Goals and Library is that page's area filter`, async () => {
      const area = (await owner.api('area.tree', { space: SPACE })).areas.find((a) => a.is_life_area && a.area_name === 'Career')
      must(area, 'no Career area')
      const calls = []
      const onReq = (r) => { const u = r.url(); if (u.includes('/api/method/lifeos.api.')) calls.push({ url: u, body: r.postData() || '' }) }
      pg.on('request', onReq)
      try {
        await owner.open('/life')
        must(await pg.locator('[data-lens-picker], [data-lens-bar], [data-lens-sheet]').count() === 0, 'a lens control is shown')
        if (!phone) {
          const side = await pg.locator('[data-sidebar]').innerText()
          must(!/Focus on an area|All of life/.test(side), 'the sidebar still has the lens')
          must(await pg.locator('[data-sidebar] [data-pinned-area]').count() === 0, 'pinned areas are in the sidebar')
        }
        for (const p of ['/life/goals', '/life/goals/tasks', '/life/library']) {
          calls.length = 0
          await pg.goto(`${base}${p}${p.includes('?') ? '&' : '?'}area=${area.name}`, { waitUntil: 'networkidle' })
          await settle()
          must(new URL(pg.url()).searchParams.get('area') === area.name, `${p}: the area left the URL`)
          must(calls.some((c) => new URL(c.url).searchParams.get('area') === area.name || c.body.includes(area.name)), `${p}: no request asked for the area`)
          await pg.locator('[data-main] a[href^="/life/"]').first().waitFor({ timeout: 5000 }).catch(() => {})
        }
        // a link to another page does not carry the area along: it is that page's filter
        await pg.goto(`${base}/life/goals/tasks?area=${area.name}`, { waitUntil: 'networkidle' })
        await (phone ? pg.locator('[data-tabbar] [data-tab-item="Library"]') : pg.locator('[data-sidebar] [data-nav-item="Library"]')).first().click()
        await pg.waitForURL((u) => u.pathname.startsWith('/life/library'), { timeout: 10000 })
        await pg.waitForLoadState('networkidle')
        must(!new URL(pg.url()).searchParams.get('area'), `the area was carried to the next page (${pg.url()})`)
      } finally {
        pg.off('request', onReq)
      }
    })

    await check('SETTINGS.35', `${width} px: on the acceptance site, which keeps two spaces, the space is picked in the ${phone ? 'menu sheet' : "sidebar's picker"} and Settings still shows Spaces`, async () => {
      must((await owner.api('session.boot')).spaces.length >= 2, 'the owner has fewer than two spaces')
      await owner.open('/life')
      if (phone) {
        await pg.locator('[data-more-title]').click()
        await pg.locator('[data-space-sheet]').waitFor({ timeout: 8000 })
        await pg.locator('[data-space-sheet] [data-space-item="Shared"]').click()
      } else {
        await pg.locator('[data-space-picker] button, [data-space-picker]').first().click()
        await pg.getByRole('menuitem', { name: 'Shared', exact: true }).click()
      }
      await pg.waitForLoadState('networkidle')
      await settle()
      must(new URL(pg.url()).searchParams.get('space') === 'Shared', 'the URL does not name Shared')
      await owner.open('/life/settings?tab=members&view=spaces&space=Private')
      must(await pg.locator('[data-space-card]').count() >= 2, 'Settings > Members > Spaces does not list the spaces')
      must(await pg.locator('[data-settings-space]').count() >= 1 || phone, 'the space picker of Settings is gone')
    })
  } finally {
    await owner.api('views.save', { screen: 'lens', space: '', state: { space: SPACE } }).catch(() => {})
    await owner.ctx.close()
  }
}


// Issue 54: context for agents. I54.1 to I54.6 are unit tests (test_issue54_context). Settings > Rules shows the card; a contradiction in Needs you,
// once decided, leaves the page with the chosen fact and its source. Titles start "I54 " (the debris finder knows them).
for (const width of WIDTHS) {
  const tag = `I54.${width}`
  let one = null
  try {
    one = await session('owner@lifeos.test', width)
    const pg = one.page
    const errors = []
    pg.on('pageerror', (x) => errors.push(String(x).split('\n')[0]))
    await check('SETTINGS.36', `${width} px: Settings, Rules shows "What agents know about you" with the current card`, async () => {
      const card = (await one.api('context.card', { space: SPACE })).card
      await one.open('/life/settings?tab=rules')
      const el = pg.locator('[data-agent-card]')
      await el.waitFor({ timeout: 10000 })
      must(/What agents know about you/.test(await pg.locator('[data-main]').innerText()), 'the heading is missing')
      const text = await el.innerText()
      must(text.includes('Areas that are on') && text.includes('Active goals'), 'the card lacks its sections: ' + text.slice(0, 200))
      must(text.includes(card.split('\n')[0].replace(/^#\s*/, '')), 'the card is not the current one')
      must(!(await el.locator('input, textarea').count()), 'the card can be edited')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      must(!errors.length, 'script errors: ' + errors.slice(0, 3).join(' | '))
    })
    await check('SETTINGS.37', `${width} px: a contradiction in Needs you, once decided, leaves the page with the chosen fact and its source`, async () => {
      const made = JSON.parse(bench(`import json
from frappe.utils import today
space = ${JSON.stringify(SPACE)}
item = frappe.get_doc({"doctype": "Life Inbox Item", "space": space, "title": "I54 invoice ${width} ${stamp}", "source_type": "Upload", "status": "Done", "raw_text": "Six dealerships", "received_on": today()}).insert(ignore_permissions=True)
a = frappe.get_doc({"doctype": "Life Note", "space": space, "collection": "Wiki", "title": "I54 Mehi ${width} ${stamp}", "summary": "Dealer", "content_md": "Mehi has 4 dealerships."}).insert(ignore_permissions=True)
b = frappe.get_doc({"doctype": "Life Note", "space": space, "collection": "Wiki", "title": "I54 Ranchi ${width} ${stamp}", "summary": "Accounts", "content_md": "Mehi has 6 dealerships.", "sources": [{"source_doctype": "Life Inbox Item", "source_name": item.name}]}).insert(ignore_permissions=True)
f = frappe.get_doc({"doctype": "Life Wiki Finding", "space": space, "topic": "I54 count ${width} ${stamp}", "question": "Two pages disagree on Mehi's dealership count: keep which?", "status": "Open",
  "options": json.dumps([{"page": a.name, "title": a.title, "fact": "Mehi has 4 dealerships.", "source_doctype": None, "source_name": None},
    {"page": b.name, "title": b.title, "fact": "Mehi has 6 dealerships.", "source_doctype": "Life Inbox Item", "source_name": item.name}])}).insert(ignore_permissions=True)
print(json.dumps({"a": a.name, "b": b.name, "f": f.name, "item": item.name}))`).split('\n').pop())
      await one.open('/life/brain')
      const row = pg.locator(`[data-contradiction="${made.f}"]`)
      await row.waitFor({ timeout: 10000 })
      must((await row.innerText()).includes('keep which?'), 'the question is not shown')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      await row.locator('[data-contradiction-keep="1"]').click()
      await row.waitFor({ state: 'detached', timeout: 10000 })
      const got = JSON.parse(bench(`import json
a = frappe.get_doc("Life Note", "${made.a}")
print(json.dumps({"text": a.content_md, "sources": [s.source_name for s in a.sources], "status": frappe.db.get_value("Life Wiki Finding", "${made.f}", "status")}))`).split('\n').pop())
      must(got.text.includes('6 dealerships') && !got.text.includes('4 dealerships'), 'the page says: ' + got.text)
      must(got.sources.includes(made.item), 'the page does not cite the chosen fact\'s source')
      must(got.status === 'Decided', 'the finding is ' + got.status)
    })
    // the empty state of Needs you with nothing to decide is I17's; this screen adds a section only when there is a contradiction
  } finally {
    if (one) await one.ctx.close()
  }
}


// Every skill the app ships has a card on Brain > Skills, and the skills that have examples pass them under Test.
{
  const s = await session('owner@lifeos.test')
  try {
    await check('SETTINGS.38', 'Skills: every built-in skill has its card, and Test passes the examples of each', async () => {
      const shipped = (await s.api('skills.list')).filter((k) => k.source === 'Built-in')
      must(shipped.length >= 12, `only ${shipped.length} built-in skills are listed`)
      await s.open('/life/brain/skills')
      let tested = 0
      for (const k of shipped) {
        must(await s.page.locator(`[data-skill-card][data-skill="${k.name}"]`).count(), `no card for ${k.name}`)
        const r = await s.api('skills.test', { name: k.name })
        must(r.passed === r.total, `${k.name}: ${r.passed} of ${r.total} examples pass`)
        tested += r.total
      }
      return `${shipped.length} skills, ${tested} examples`
    })
  } finally { await s.ctx.close() }
}



// Issue 72: Reset is a section of Settings > Data, and its old route lands on Today, which says the page moved.
for (const width of WIDTHS) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  try {
    await check('SETTINGS.39', `${width} px: Settings > Data holds the Reset section; /today/reset lands on Today and says that page moved`, async () => {
      await s.open('/life/settings?tab=data')
      await pg.locator('[data-reset]').first().waitFor({ timeout: 15000 })
      must(await pg.locator('[data-reset-goal]').count() === 1, "Settings > Data has no Reset goal bar")
      must((await pg.locator('[data-settings-section]').innerText()).includes('Suggested batches') || phone, 'the Reset section shows no batches')
      must((await pg.locator('[data-section-title]').innerText()).includes('Data'), 'the page is not titled Data')
      // the menu lists Data, and the old Reset section link lands on it
      await s.open('/life/settings?tab=reset')
      await pg.locator('[data-reset]').first().waitFor({ timeout: 15000 })
      must(new URL(pg.url()).searchParams.get('tab') === 'data', `?tab=reset opened ${pg.url()}`)
      // the Rhythms page no longer carries Reset
      await s.open('/life/settings?tab=rhythms')
      await pg.locator('[data-settings-rhythms]').waitFor()
      must(!(await pg.locator('[data-reset]').count()), 'Rhythms still holds Reset')
      // the old route
      await s.open('/life/today/reset')
      must(pathOf(pg) === '/life/today', `/today/reset opened ${pathOf(pg)}`)
      must(await pg.locator('[data-moved-note]').isVisible(), 'no "That page moved" note')
      must((await pg.locator('[data-moved-note]').innerText()).includes('That page moved'), 'the note does not say that page moved')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
    })
  } finally { await s.ctx.close() }
}

// Issue 32: the email-in address is shown in Settings > Sources, with the allowed senders, and never in the onboarding guide.
const EMAIL_IN = 'Acceptance Email-in'
for (const width of WIDTHS) {
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  try {
    await check('SETTINGS.40', `${width} px: Settings > Sources shows the email-in address and the allowed senders, and the onboarding guide says nothing about forwarding`, async () => {
      bench(`from frappe.utils import now
if not frappe.db.exists("Email Account", "${EMAIL_IN}"):
    d = frappe.get_doc({"doctype": "Email Account", "email_account_name": "${EMAIL_IN}", "email_id": "life-in-acceptance@example.com", "enable_incoming": 1,
        "enable_outgoing": 0, "password": "not-a-real-password", "imap_folder": [{"folder_name": "INBOX", "append_to": "Communication"}]})
    d.flags.ignore_validate = True
    d.insert(ignore_permissions=True)
frappe.db.set_single_value("Life Settings", "email_in_account", "${EMAIL_IN}")
frappe.db.set_single_value("Life Settings", "email_in_senders", "me-acceptance@example.com")
frappe.clear_cache(doctype="Life Settings")`)
      await s.open('/life/brain/sources')
      await pg.locator('[data-email-in]').waitFor({ timeout: 15000 })
      await pg.locator('[data-email-in-address]:has-text("life-in-acceptance@example.com")').waitFor({ timeout: 15000 })
      must(await pg.locator('[data-email-in-senders]').inputValue() === 'me-acceptance@example.com', 'the allowed sender is not shown')
      must(!(await pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'the page scrolls sideways')
      // the guide: no word about an address or forwarding
      const guide = (await import('node:fs')).readFileSync(new URL('../../frontend/src/components/OnboardingGuide.vue', import.meta.url), 'utf8')
      must(!/forward|email-in|email in/i.test(guide), 'the onboarding guide mentions email forwarding')
    })
  } finally {
    bench(`frappe.db.set_single_value("Life Settings", "email_in_account", None)
frappe.db.set_single_value("Life Settings", "email_in_senders", None)
frappe.clear_cache(doctype="Life Settings")`)
    await s.ctx.close()
  }
}
