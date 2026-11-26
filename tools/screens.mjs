// The screenshot pass: every screen at 1440 px and 390 px, in light and dark.
//   node tools/screens.mjs [--only name,name] [--schemes light,dark] [--widths 1440,390]
// Writes screenshots/s-<name>-<width>[-dark].png and prints, for each, horizontal overflow, script errors and
// text whose contrast against its background is below 4.5 to 1. Exits 1 if it found any of those.
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env'), 'utf8').split('\n').filter(Boolean).map((l) => l.split('=')))
const base = process.env.LIFEOS_URL || 'http://localhost:18000'
const args = process.argv.slice(2)
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def }
const only = opt('only', '').split(',').filter(Boolean)
const schemes = opt('schemes', 'light,dark').split(',')
const widths = opt('widths', '1440,390').split(',').map(Number)

const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
let problems = 0

// Text below 4.5 to 1, measured in the page: the colour of each piece of text against the first opaque background behind it.
function lowContrast() {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1
  const cx = cv.getContext('2d', { willReadFrequently: true })
  const cache = new Map()
  const rgba = (c) => {
    if (cache.has(c)) return cache.get(c)
    cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1)
    const d = cx.getImageData(0, 0, 1, 1).data
    const out = [d[0], d[1], d[2], d[3] / 255]
    cache.set(c, out)
    return out
  }
  const over = (top, under) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1) }
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]) }
  const page = rgba(getComputedStyle(document.body).backgroundColor)[3] ? rgba(getComputedStyle(document.body).backgroundColor) : [255, 255, 255, 1]
  const background = (el) => {
    const layers = []
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const s = getComputedStyle(e)
      if (s.backgroundImage !== 'none') return null // a picture or gradient: not measured
      const c = rgba(s.backgroundColor)
      if (c[3] > 0) { layers.push(c); if (c[3] === 1) break }
    }
    let bg = page
    for (const l of layers.reverse()) bg = over(l, bg)
    return bg
  }
  const slots = (el) => { // the library parts it sits in, innermost first
    const names = []
    for (let e = el; e && names.length < 3; e = e.parentElement?.closest('[data-slot]')) if (e.dataset?.slot) names.push(e.dataset.slot)
    return names.join(' < ') || 'no library part'
  }
  const out = new Map()
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.textContent.trim()
    if (!text) continue
    const el = n.parentElement
    if (!el || el.closest('[disabled], [aria-disabled="true"], [data-disabled], [aria-hidden="true"], svg, canvas, .cm-editor')) continue
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue
    const s = getComputedStyle(el)
    if (s.visibility === 'hidden' || s.display === 'none') continue
    let opacity = 1
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) opacity *= Number(getComputedStyle(e).opacity)
    if (opacity < 0.05) continue
    const hit = document.elementFromPoint(Math.min(r.left + 3, innerWidth - 1), r.top + r.height / 2)
    if (hit && !el.contains(hit) && !hit.contains(el)) continue // covered by something else
    const bg = background(el)
    if (!bg) continue
    const fg0 = rgba(s.color)
    const fg = over([fg0[0], fg0[1], fg0[2], fg0[3] * opacity], bg)
    const a = lum(fg), b = lum(bg)
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    if (ratio < 4.5) {
      const key = `${el.className}`.slice(0, 90) + '|' + ratio.toFixed(1)
      if (!out.has(key)) out.set(key, `${ratio.toFixed(2)} "${text.slice(0, 30)}" <${el.tagName.toLowerCase()} class="${`${el.className}`.slice(0, 90)}"> in ${slots(el)}`)
    }
  }
  return [...out.values()]
}

for (const scheme of schemes) {
  for (const width of widths) {
    const ctx = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, deviceScaleFactor: 1, colorScheme: scheme,
      timezoneId: 'Asia/Kolkata', isMobile: width < 800, hasTouch: width < 800 })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(String(e)))
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
    const res = await page.request.post(base + '/api/method/login', { form: { usr: 'owner@lifeos.test', pwd: env.LIFEOS_DEV_PASSWORD } })
    if (!res.ok()) throw new Error('login failed ' + res.status())
    const first = async (doctype, filters = { space: 'Private' }) => {
      const r = await (await page.request.get(`${base}/api/method/frappe.client.get_list?doctype=${encodeURIComponent(doctype)}&filters=${encodeURIComponent(JSON.stringify(filters))}&limit_page_length=1&order_by=creation%20asc`)).json()
      return r.message[0]?.name
    }
    const area = await first('Life Area', { space: 'Private', area_name: 'Tea & Coffee' })
    const openGoal = await first('Life Goal', { space: 'Private', title: 'Ghillidary turnaround' })
    const goal = await first('Life Goal', { horizon: '12 weeks' }), note = await first('Life Note'), task = await first('Life Task', { space: 'Private', status: 'Long term' })
    const vault = await first('Life Vault Document'), chat = await first('Life Chat Log')
    const review = await first('Life Inbox Item', { space: 'Private', status: 'To Review' })
    const wikiPage = await first('Life Note', { space: 'Private', collection: 'Wiki', is_rules: 0 }).catch(() => null)
    const wikiChange = await first('Life Wiki Change').catch(() => null)
    const numberGoal = await first('Life Goal', { space: 'Private', measure_kind: 'Number' }).catch(() => null)
    const lens = `area=${area}`
    // UX fixes, set 6: the four places, every Plan and Library tab and their views, the goal page, Settings' sections,
    // the lens (picker, chip, phone sheet), Today's banner; then the panes and screens kept from earlier sets
    const SCREENS = [
      ['today', '/life/?area='], ['today-lens', `/life/?${lens}`], ['today-banner', '/life/?area=&at=2026-11-22%2019:00:00'],
      ['needs-you', '/life/brain?area='], ['brain-activity', '/life/brain/activity?area='], ['brain-sources', '/life/brain/sources?area='], ['brain-skills', '/life/brain/skills?area='], ['skill', '/life/brain/skills/process-capture'], ['needs-you-lens', `/life/brain?${lens}`], ['inbox', '/life/brain/queue?all=1&area='], ['inbox-lens', `/life/brain/queue?all=1&${lens}`], ['inbox-pane', `/life/brain/queue?all=1&area=&open=inbox:${review}`], // issue 17: Needs you, and the old list as the Queue
       ['review', `/life/inbox/${review}/review`], ['item', `/life/item/${review}`],
      ...['week', 'month', 'year'].map((v) => [`today-${v}`, `/life/today/${v}?area=`]), ['today-other-day', '/life/today?area=&date=2026-12-02'], // issue 16
      ...['review', 'calendar', 'agenda'].map((v) => [`plan-week-${v}`, `/life/plan/week?view=${v}&area=`]),
      ...['plan', 'habits', 'calendar'].map((v) => [`plan-month-${v}`, `/life/plan/month?view=${v}&area=`]),
      ['plan-12-weeks', '/life/plan/12-weeks?area='], ['plan-12-weeks-lens', `/life/plan/12-weeks?${lens}`],
      ...['calendar', 'goals'].map((v) => [`plan-year-${v}`, `/life/plan/year?view=${v}&area=`]),
      ['plan-goals', '/life/plan/goals?status=all&area='], ['plan-goals-lens', `/life/plan/goals?${lens}`], ['plan-tasks', '/life/plan/tasks?view=list&area='],
      ['plan-tasks-board', '/life/plan/tasks?view=board&area='], ['plan-tasks-pane', `/life/plan/tasks?view=list&area=&open=task:${task}`],
      ['plan-someday', '/life/plan/someday?area='], ['settings-data', '/life/settings?tab=data'], ...['inventory', 'one'].map((t) => [`settings-data-${t}`, `/life/settings?tab=data&rtab=${t}`]),
      ['goal-open', `/life/plan/goals/${openGoal}`], ...['tasks', 'notes', 'captures', 'links'].map((t) => [`goal-open-${t}`, `/life/plan/goals/${openGoal}?tab=${t}`]),
      ['goal-12wy', `/life/plan/goals/${goal}`], ['goal-pane', `/life/plan/goals?status=all&area=&open=goal:${openGoal}`],
      ['library-all', '/life/library?all=1&area='], ['library-all-lens', `/life/library?all=1&${lens}`], ['library-all-grid', '/life/library?view=grid&all=1&area='],
      ...['list', 'tree', 'graph', 'changes', 'health'].map((v) => [`library-notes-${v}`, `/life/library/notes?view=${v}&area=`]),
      ['library-notes-assistant', '/life/library/notes?by=assistant&area='],
      ...['all', 'chats', 'documents', 'photos', 'pages'].map((t) => [`library-captures-${t}`, `/life/library/captures?tab=${t}&all=1&area=`]),
      ['library-captures-sensitive', '/life/library/captures?tab=documents&sensitive=1&area='], ['library-captures-chats-day', '/life/library/captures?tab=chats&view=day&all=1&area='],
      ['library-timeline', '/life/library/timeline?all=1&area='], ['library-archive', '/life/library/archive?all=1&area='], ['library-archive-trash', '/life/library/archive?type=trash&all=1&area='],
      ['note', `/life/library/${note}`], ['note-pane', `/life/library/notes?view=list&all=1&area=&open=note:${note}`],
      ['vault-pane', `/life/library/captures?tab=documents&all=1&area=&open=vault:${vault}`], ['chat-pane', `/life/library/captures?tab=chats&all=1&area=&open=chat:${chat}`],
      ...['original', 'text', 'summary', 'made', 'details'].map((t) => [`source-pane-${t}`, `/life/library/captures?all=1&area=&open=source:${review}&ptab=${t}`]),
      ...(wikiPage ? ['note', 'sources', 'links', 'history'].map((t) => [`assistant-pane-${t}`, `/life/library/notes?by=assistant&area=&open=note:${wikiPage}&ptab=${t}`]) : []),
      ...(wikiChange ? [['assistant-change', `/life/library/notes?view=changes&area=&open=change:${wikiChange}`]] : []),
      ['task-pane-notes', `/life/plan/tasks?view=list&area=&open=task:${task}&ptab=notes`], ['goal-pane-history', `/life/plan/goals?status=all&area=&open=goal:${goal}&ptab=history`],
      ['insights', '/life/insights'],
      ['ask-panel', '/life/?area='], ['ask-pane', `/life/plan/tasks?view=list&area=&open=task:${task}`],
      ['more-sheet', '/life/?area='], ['dev-editor', '/life/dev/editor'],
      // set 7: the Outbox, a number goal, New goal with "Done when…", the old Inbox items' batch
      ['library-outbox', '/life/library/outbox?area='], ['library-outbox-in', '/life/library/outbox?pile=in&period=12weeks&area='],
      ...(numberGoal ? [['goal-number', `/life/plan/goals/${numberGoal}`], ['goal-number-pane', `/life/plan/goals?status=all&area=&open=goal:${numberGoal}`]] : []),
      ['new-goal', '/life/plan/goals?area='], ['inbox-old', '/life/brain?all=1&area=&decisions=1'],
      ...['profile', 'appearance', 'notifications', 'shortcuts', 'areas', 'rhythms', 'habits', 'data', 'agents', 'connections', 'ai', 'sensitive',
        'note-rules', 'spaces', 'members', 'archive', 'import', 'backups'].map((t) => [`settings-${t}`, `/life/settings?tab=${t}&area=`]),
    ].filter(([n]) => !only.length || only.includes(n))
    for (const [name, p] of SCREENS) {
      await page.goto(base + p, { waitUntil: 'networkidle' })
      await page.waitForTimeout(700)
      if (name === 'more-sheet' && width < 800) { // the phone's menu sheet from the title bar (issue 46: no lens)
        await page.locator('[data-more-title]').first().click()
        await page.waitForTimeout(600)
      }
      if (name === 'new-goal') { // the New goal dialog on a number
        await page.locator('[data-new-goal]').first().click()
        await page.waitForTimeout(500)
        await page.locator('[data-goal-title] input, input[data-goal-title]').first().fill('Ghillidary yield 1800 kg/ha')
        await page.locator('[data-measure-kind]').getByText('A number').click()
        await page.waitForTimeout(400)
      }
      if (name === 'ask-panel' || name === 'ask-pane') { // a question asked from the screen, in the panel (a sheet on a phone)
        if (name === 'ask-pane') await page.locator('[data-pane-ask]').first().click()
        else if (width < 800) await page.locator('[data-chat-bar-open]').first().click()
        else { await page.keyboard.press('Meta+k'); await page.waitForTimeout(300); await page.keyboard.type('What is stuck in Ghillidary?'); await page.keyboard.press('Enter') }
        await page.waitForTimeout(500)
        const box = page.locator('[data-ask-panel] textarea')
        if (await box.count() && !(await page.locator('[data-ask-answer]').count())) { await box.first().fill('What is stuck in Ghillidary?'); await page.locator('[data-ask-send]:visible').first().click() }
        for (let i = 0; i < 40 && await page.locator('[data-ask-answer][data-status="Working"]').count(); i++) await page.waitForTimeout(250)
        await page.waitForTimeout(500)
      }
      const file = path.join(root, 'screenshots', `s-${name}-${width}${scheme === 'dark' ? '-dark' : ''}.png`)
      await page.screenshot({ path: file })
      const overflow = await page.evaluate((w) => Math.max(document.documentElement.scrollWidth, window.innerWidth) - w, width) // a phone page that is too wide enlarges innerWidth too
      const low = await page.evaluate(lowContrast)
      const bad = overflow > 0 || errors.length || low.length
      if (bad) problems++
      console.log(`${bad ? 'CHECK' : 'ok   '} ${scheme} ${width} ${name}${overflow > 0 ? `  overflowX=${overflow}` : ''}${errors.length ? '  ERRORS: ' + [...new Set(errors)].slice(0, 3).join(' | ').slice(0, 300) : ''}`)
      for (const l of low.slice(0, 8)) console.log('        contrast ' + l)
      errors.length = 0
    }
    await ctx.close()
  }
}
await browser.close()
console.log(problems ? `\n${problems} screens to check.` : '\nNo overflow, script errors or low-contrast text.')
process.exit(problems ? 1 : 0)
