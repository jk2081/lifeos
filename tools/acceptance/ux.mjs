import { SPACE, addDays, areaId, bench, browser, check, must, owner, path, runAgent, session, stamp, today } from './context.mjs'

// Run at 1440 px and at 390 px. `node tools/acceptance.mjs --ux` runs only these.
export const uxArea = areaId('Tea & Coffee')
export const ux = {}
{
  // records the checks need, made through the API as the owner. ux.goal is an open-ended goal of the area (what a project was
  // before set 6); ux.oldProject is the id an old project link carries (the table is gone since issue 48).
  const former = JSON.parse(bench(`import json
print(json.dumps(frappe.db.sql("select name from \`tabLife Goal\` where space='${SPACE}' and area='${uxArea}' and horizon='Long term' and outcome='In Progress' and is_archived=0 and is_someday=0 order by creation limit 1")))`).split('\n').pop())
  must(former.length, 'no open-ended goal of Tea & Coffee on the acceptance site')
  ux.goal = former[0][0]
  ux.oldProject = 'PRJ-0001'
  ux.goalTitle = (await owner.api('goals.get', { goal: ux.goal })).goal.title
  ux.task = (await owner.api('tasks.quick_add', { text: `UX door task ${stamp}`, space: SPACE, goal: ux.goal, area: uxArea, priority: 'I', due_date: addDays(-2) })).name
  await owner.api('tasks.quick_add', { text: `UX due today ${stamp}`, space: SPACE, area: uxArea, due_date: today })
  const doneTask = (await owner.api('tasks.quick_add', { text: `UX done ${stamp}`, space: SPACE, goal: ux.goal, area: uxArea })).name
  await owner.api('tasks.set_status', { task: doneTask, status: 'Done' })
  const carried = (await owner.api('tasks.quick_add', { text: `UX carried ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.carry_forward', { task: carried })
  const old = (await owner.api('tasks.quick_add', { text: `UX archived by the job ${stamp}`, space: SPACE, area: uxArea })).name
  await owner.api('tasks.set_status', { task: old, status: 'Done' })
  bench(`from lifeos.library import archive\nfrappe.set_user("owner@lifeos.test")\narchive.set_archived("Life Task", "${old}", True, "Auto")`)
  ux.note = (await owner.api('library.save', { space: SPACE, title: `UX note ${stamp}`, area: uxArea, content_md: 'A reference note for the UX checks.' })).name
  ux.vault = (await owner.api('vault.save', { space: SPACE, values: { title: `UX permit ${stamp}`, doc_type: 'Other', expiry_date: addDays(20), area: uxArea } })).name
  ux.chat = (await owner.api('chats.log', { space: SPACE, title: `UX chat ${stamp}`, area: uxArea, goal: ux.goal, summary_md: 'Talked about the UX checks.',
    open_items: ['Follow up on the UX checks'] })).name
  const item = await owner.api('inbox.create_item', { title: `UX inbox ${stamp}`, source_type: 'Message', space: SPACE, raw_text: 'Buy a new kettle. Call the estate manager.' })
  runAgent()
  ux.inbox = item.name
}

export const num = (text, which = 0) => { const m = String(text).match(/\d+/g); if (!m) throw new Error(`no number in "${text}"`); return Number(m[which]) }
// A bare list URL restores the remembered view, so the checks that want the whole list say so: all=1.
// Set 6: the lists are tabs of the four places; Projects are goals of type Open, the Vault's documents are captures.
export const ROW = '[data-row]'
export const LISTS = [
  ['Inbox', '/life/brain/queue?all=1'], ['Timeline', '/life/library/timeline?all=1'], ['Tasks', '/life/goals/tasks?view=list'],
  ['Goals', '/life/goals?all=1'], ['Documents', '/life/library/documents?tab=documents&all=1'], ['Captures', '/life/brain/captures?all=1'],
  ['Notes', '/life/library/notes?view=list&all=1'], ['All', '/life/library?view=list&all=1'], ['Archive', '/life/library/archive?all=1'],
].map(([name, p]) => [name, p, ROW])
// one filter for each ListView, set through the library's quick-filter strip: [screen, path, URL key, URL value, the control's label, the option to pick, text to type for a Link]
// The Area filters of set 4 are the lens since set 6 (U.40 and up check it); the Archive's only other quick filter is a text field.
export const FILTERS = [
  ['Inbox', '/life/brain/queue?all=1', 'source_type', 'Message', 'Source Type', 'Message'], ['Tasks', '/life/goals/tasks?view=list', 'priority', 'I', 'Priority', 'I'],
  ['Tasks table', '/life/goals/tasks?view=table&status=all', 'priority', 'I', 'Priority', 'I'], ['Goals', '/life/goals?status=all', 'type', 'Long term', 'Horizon', 'Long term'],
  ['Captures', '/life/brain/captures?all=1', 'status', 'Done', 'Status', 'Done'],
  ['Notes', '/life/library/notes?view=list&all=1', 'goal', ux.goal, 'Goal', ux.goalTitle, ux.goalTitle.slice(0, 6)],
]
// UX fixes, set 3: the state tabs of each list screen. [screen, path, the URL parameter of the tabs, the tab values in order (the first is the default), another filter]
// The other filter is mostly the lens's area (set 6), so each tab's count is checked with an area chosen too.
export const STATE_TABS = [
  ['Inbox', '/life/brain/queue', 'status', ['To Review', 'Waiting', 'Failed'], 'source_type=Message'],
  ['Tasks', '/life/goals/tasks', 'status', ['open', 'loops', 'Waiting', 'Done', 'Someday', 'all'], `area=${uxArea}`],
  ['Goals', '/life/goals', 'status', ['in_progress', 'achieved', 'closed', 'someday', 'all'], `area=${uxArea}`],
  ['Archive', '/life/library/archive', 'type', ['all', 'Life Task', 'Life Note', 'Life Chat Log', 'Life Vault Document', 'Life Inbox Item', 'trash'], `area=${uxArea}`],
  ['Someday', '/life/goals/someday', 'tab', ['all', 'due', 'tasks', 'goals', 'notes'], `area=${uxArea}`],
  ['Captures', '/life/brain/captures', 'tab', ['all', 'chats', 'voice', 'documents', 'photos', 'videos', 'articles', 'email', 'text'], `area=${uxArea}`],
  ['All', '/life/library', 'tab', ['all', 'notes', 'chats', 'voice', 'documents', 'photos', 'videos', 'articles', 'email', 'text'], `area=${uxArea}`],
]


// The part of the old UX walk's set-up that every check of it shares: one browser session at `width`, the helpers for panes, lists,
// filters and tabs, and the owner's pageerror log. A place that has such checks calls it once per width.
export async function uxKit(width) {
  const phone = width < 800
  const s = await session('owner@lifeos.test', width)
  const pg = s.page
  const errors = []
  pg.on('pageerror', (e) => errors.push(String(e)))
  const tag = `U${width}`
  const pane = pg.locator('[data-pane]')
  const settle = () => pg.waitForTimeout(450)
  const paneTitle = async () => { // the title once the record has loaded
    const el = pg.locator('[data-pane-title]')
    for (let i = 0; i < 20 && /^Loading/.test(await el.innerText()); i++) await pg.waitForTimeout(150)
    return el.innerText()
  }
  const overflow = () => pg.evaluate((w) => Math.max(document.documentElement.scrollWidth, window.innerWidth) - w, width) // a phone page that is too wide enlarges innerWidth too
  const count = async () => num(await pg.locator('[data-lv-count]').first().innerText())
  const clickRow = async (sel) => { await pg.locator(sel).first().click({ position: { x: 120, y: 14 } }); await settle() }
  // the list controls: the quick-filter strip on a wide screen, the same controls in a sheet behind the Filters button on a phone
  const controls = () => pg.locator(phone ? '[data-filter-sheet]' : '[data-lv-bar]')
  const openControls = async () => { if (phone) { await pg.locator('[data-filters-button]').click(); await pg.waitForTimeout(400) } }
  const closeControls = async () => { if (phone) { await pg.keyboard.press('Escape'); await pg.waitForTimeout(400) } }
  const pickQuick = async (label, option, type) => {
    await openControls()
    const box = (phone ? controls() : controls().locator('[data-quick-filters]')).locator(`[aria-label="${label}"]`).first()
    const more = controls().getByRole('button', { name: /\d+ more/ })
    if (!(await box.count()) && await more.count()) { await more.first().click(); await pg.waitForTimeout(200) }
    await box.click()
    if (type) await pg.keyboard.type(type, { delay: 20 })
    await pg.waitForTimeout(type ? 900 : 300)
    await pg.getByRole('option', { name: option, exact: !type }).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    await closeControls()
  }
  // a place through the sidebar on a wide screen, the tab bar on a phone; a list through the place's tabs (set 6, issue 14)
  // issue 14: Tasks is Goals > All tasks, Captures is Brain > Activity
  const PLACE_OF = { Tasks: ['Goals', 'tasks'], 'No goal': ['Goals', 'no-goal'], Goals: ['Goals', 'by-area'], Notes: ['Library', 'notes'], Captures: ['Brain', 'activity'] }
  const nav = async (label) => {
    const [place, tab] = PLACE_OF[label] || [label]
    if (phone) await pg.locator(`[data-tabbar] [data-tab-item="${place}"]`).first().click()
    else await pg.locator(`[data-sidebar] [data-nav-item="${place}"]`).first().click()
    await pg.waitForLoadState('networkidle')
    await settle()
    if (tab) {
      await pg.locator(`[data-place-tabs] [data-tab="${tab}"]`).first().click()
      await pg.waitForLoadState('networkidle')
      await settle()
    }
  }

  // issue 46: no lens. The phone's menu sheet (behind "Life OS" at the top) holds Settings and, on two or more spaces, the spaces
  const openMore = async () => { await pg.locator('[data-more-title]').click(); await pg.waitForTimeout(400) }
  const closeMore = async () => { if (await pg.locator('[data-more-sheet]:visible').count()) { await pg.keyboard.press('Escape'); await pg.waitForTimeout(300) } }
  const S5 = (what) => `S5 ${what} ${width} ${stamp}`
  // on a phone the tab bar is fixed over the bottom of the screen: bring the target to the middle first
  const tap = async (loc) => { await loc.evaluate((el) => el.scrollIntoView({ block: 'center' })); await pg.waitForTimeout(150); await loc.click() }
  const tasksLike = async (title) => (await s.api('tasks.list', { space: SPACE, status: 'any', filters: JSON.stringify([['title', 'like', `%${title}%`]]), page_length: 50 })).tasks
  // Ask from a screen: the scope chip, a cited answer whose citation opens its record, Make task only when clicked, the panel over the screen
  const askOn = async (path, wantScope, { pane: paneRef } = {}) => {
    await s.open(path)
    if (paneRef) {
      await pg.locator(`[data-ref="${paneRef}"]`).first().click()
      await settle()
      await pg.locator('[data-pane-ask]').click()
    } else if (phone) await pg.locator('[data-chat-bar-open]').first().click()
    else { await pg.keyboard.press('Control+k'); await pg.waitForTimeout(500); await pg.keyboard.type(`What is still open in ${stamp} here?`); await pg.waitForTimeout(300); await pg.keyboard.press('Enter') }
    await settle()
    const panel = pg.locator('[data-ask-panel]:visible')
    must(await panel.count(), `${path}: the Ask panel did not open`)
    if (phone) must(await pg.locator('[data-ask-sheet]:visible').count(), 'not a bottom sheet on a phone')
    else must(Math.abs((await panel.boundingBox()).width - 480) < 2, "the panel is not 480 px wide")
    const scope = (await pg.locator('[data-ask-scope]:visible').first().innerText()).trim()
    must(scope === wantScope, `${path}: the scope chip says "${scope}", not "${wantScope}"`)
    if (phone || paneRef) { await pg.locator('[data-ask-panel] textarea').fill('What is still open here?'); await pg.locator('[data-ask-send]:visible').click() }
    for (let i = 0; i < 40 && await pg.locator('[data-ask-answer][data-status="Working"]').count(); i++) await pg.waitForTimeout(250)
    await settle()
    return panel
  }
  // Area filters: no archived area and no area of another space, on every list with an Area filter; the Archive lists archived ones
  // Python on the acceptance site as the agent, answering JSON on its last line
  const asAgent = (code) => JSON.parse(bench(`frappe.set_user("hermes@lifeos.test")\nimport json\nfrom lifeos.api import wiki, library, sources, inbox, chats\nfrom lifeos import permissions\npermissions.clear_cache()\n${code}`).split('\n').pop())
  const editorEnd = async () => { await pg.locator('[data-live-editor] .cm-content').first().click(); await pg.keyboard.press('ControlOrMeta+End') }
  const docOf = (name) => s.api('library.get', { note: name })
  return { PLACE_OF, S5, asAgent, askOn, clickRow, closeControls, closeMore, controls, count, docOf, editorEnd, errors, nav, openControls, openMore, overflow, pane, paneTitle, pg, phone, pickQuick, s, settle, tag, tap, tasksLike }
}
