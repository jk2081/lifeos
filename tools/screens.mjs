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
    const project = await first('Life Project', { space: 'Private', title: 'Ghillidary turnaround' })
    const goal = await first('Life Goal'), jpage = await first('Life Journal Page'), note = await first('Life Note'), task = await first('Life Task', { space: 'Private', status: 'Open' })
    const vault = await first('Life Vault Document'), chat = await first('Life Chat Log')
    const review = await first('Life Inbox Item', { space: 'Private', status: 'To Review' })
    const wikiPage = await first('Life Note', { space: 'Private', collection: 'Wiki', is_rules: 0 }).catch(() => null)
    const wikiChange = await first('Life Wiki Change').catch(() => null)
    const SCREENS = [
      ['today', '/life'], ['inbox', '/life/inbox?all=1'], ['inbox-pane', `/life/inbox?all=1&open=inbox:${review}`], ['review', `/life/inbox/${review}/review`],
      ['timeline', '/life/timeline?all=1'], ['tasks', '/life/tasks?view=list'], ['tasks-board', '/life/tasks?view=board'], ['tasks-table', '/life/tasks?view=table'],
      ['tasks-loops', '/life/tasks?view=loops'], ['tasks-pane', `/life/tasks?view=list&open=task:${task}`],
      ['cal-month', '/life/calendar/month'], ['cal-week', '/life/calendar/week'], ['cal-agenda', '/life/calendar/agenda'], ['cal-year', '/life/calendar/year'],
      ['j-12wy', '/life/journal'], ['j-goals', '/life/journal/goals'], ['j-month', '/life/journal/month'], ['j-habits', '/life/journal/habits'],
      ['j-checkins', '/life/journal/checkins'], ['j-pages', '/life/journal/pages'], ['j-review', '/life/journal/review'], ['goal', `/life/journal/goals/${goal}`],
      ['jpage', `/life/journal/pages/${jpage}`], ['areas', '/life/areas'], ['area', `/life/areas/${area}`], ['projects', '/life/projects?view=list'],
      ['projects-cards', '/life/projects?view=cards'], ['project', `/life/projects/${project}`], ['library', `/life/library/${note}`], ['library-list', '/life/library?view=list&all=1'],
      ['note-pane', `/life/library?view=list&all=1&open=note:${note}`], ['vault', '/life/vault?all=1'], ['vault-pane', `/life/vault?all=1&open=vault:${vault}`],
      ['chats', '/life/sources?tab=chats&all=1'], ['chat-pane', `/life/sources?tab=chats&all=1&open=chat:${chat}`], ['graph', '/life/graph'], ['archive', '/life/archive?all=1'], ['settings', '/life/settings'],
      // set 3: the tabs of the area and project pages, the pane's tabs, the review and journal page on a phone, Settings, Goals
      ...['projects', 'tasks', 'notes', 'wiki', 'documents', 'chats', 'timeline'].map((t) => [`area-${t}`, `/life/areas/${area}?tab=${t}`]),
      ...['tasks', 'notes', 'documents', 'chats', 'links'].map((t) => [`project-${t}`, `/life/projects/${project}?tab=${t}`]),
      ['task-pane-notes', `/life/tasks?view=list&open=task:${task}&ptab=notes`], ['task-pane-links', `/life/tasks?view=list&open=task:${task}&ptab=links`],
      ['goal-pane-tasks', `/life/goals?status=all&open=goal:${goal}&ptab=tasks`], ['goal-pane-history', `/life/goals?status=all&open=goal:${goal}&ptab=history`],
      ['chat-pane-items', `/life/sources?tab=chats&all=1&open=chat:${chat}&ptab=items`], ['vault-pane-file', `/life/vault?all=1&open=vault:${vault}&ptab=file`],
      ['page-pane', `/life/journal/pages?open=page:${jpage}&ptab=transcript`], ['project-pane', `/life/projects?status=all&open=project:${project}&ptab=tasks`],
      ['review-original', `/life/inbox/${review}/review?tab=original`], ['jpage-transcript', `/life/journal/pages/${jpage}?tab=transcript`],
      ...['appearance', 'default', 'review', 'areas', 'tags', 'habits', 'dimensions', 'connections', 'archive', 'archived', 'members', 'agents'].map((t) => [`settings-${t}`, `/life/settings?tab=${t}`]),
      // UX fixes, set 4: Sources, the Wiki, the editor
      ...['all', 'chats', 'voice', 'documents', 'photos', 'articles', 'email', 'text'].map((t) => [`sources-${t}`, `/life/sources?tab=${t}&all=1`]),
      ['sources-grid', '/life/sources?view=grid&all=1'], ['sources-chats-day', '/life/sources?tab=chats&view=day&all=1'],
      ...['original', 'text', 'summary', 'made', 'details'].map((t) => [`source-pane-${t}`, `/life/sources?all=1&open=source:${review}&ptab=${t}`]),
      ...['pages', 'changes', 'health', 'rules'].map((t) => [`wiki-${t}`, `/life/wiki?tab=${t}`]),
      ...(wikiPage ? ['note', 'sources', 'links', 'history'].map((t) => [`wiki-pane-${t}`, `/life/wiki?open=note:${wikiPage}&ptab=${t}`]) : []),
      ...(wikiChange ? [['wiki-change', `/life/wiki?tab=changes&open=change:${wikiChange}`]] : []),
      ['wiki-graph', '/life/graph?collection=Wiki'], ['dev-editor', '/life/dev/editor'], ['library-tree', '/life/library?view=tree'],
      ['goals', '/life/goals?status=all'], ['goals-progress', '/life/goals?all=1'], ['more', '/life'],
    ].filter(([n]) => !only.length || only.includes(n))
    for (const [name, p] of SCREENS) {
      await page.goto(base + p, { waitUntil: 'networkidle' })
      await page.waitForTimeout(700)
      if (name === 'more' && width < 800) { await page.locator('[data-tabbar] [aria-label="More"]').click(); await page.waitForTimeout(600) }
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
