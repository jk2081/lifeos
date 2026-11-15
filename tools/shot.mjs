// Take screenshots of Life OS screens with headless Chrome.
//   node tools/shot.mjs <name>=<path> ... [--user owner|family] [--widths 1440,390] [--full]
// Reads the test password from .env (LIFEOS_DEV_PASSWORD). Writes PNGs to screenshots/.
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env'), 'utf8').split('\n').filter(Boolean).map((l) => l.split('=')))
const args = process.argv.slice(2)
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def }
const flag = (name) => args.includes('--' + name)
const user = opt('user', 'owner') + '@lifeos.test'
const widths = opt('widths', '1440,390').split(',').map(Number)
const base = opt('base', 'http://localhost:18000')
const scheme = opt('scheme', 'light')
const pages = args.filter((a, i) => a.includes('=') && !a.startsWith('--') && !(args[i - 1] || '').startsWith('--')).map((a) => { const i = a.indexOf('='); return [a.slice(0, i), a.slice(i + 1)] })
const script = opt('eval', '')

const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
fs.mkdirSync(path.join(root, 'screenshots'), { recursive: true })
for (const width of widths) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, deviceScaleFactor: 1, colorScheme: scheme,
    timezoneId: 'Asia/Kolkata', isMobile: width < 800, hasTouch: width < 800 })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  const res = await page.request.post(base + '/api/method/login', { form: { usr: user, pwd: env.LIFEOS_DEV_PASSWORD } })
  if (!res.ok()) throw new Error('login failed ' + res.status())
  for (let [name, p] of pages) {
    // {review} = the oldest item waiting for review; {method:lifeos.api.x|field} = a value from an API call
    if (p.includes('{review}')) {
      const r = await (await page.request.get(base + '/api/method/lifeos.api.inbox.list?space=Private&status=To%20Review')).json()
      const items = r.message.items
      p = p.replace('{review}', items[items.length - 1].name)
    }
    const m = p.match(/\{get:([^|]+)\|([^|]+)\|([^}]+)\}/)
    if (m) {
      const r = await (await page.request.get(base + `/api/method/frappe.client.get_value?doctype=${encodeURIComponent(m[1])}&filters=${encodeURIComponent(m[2])}&fieldname=name`)).json()
      p = p.replace(m[0], r.message.name)
    }
    await page.goto(base + p, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
    if (script) { await page.evaluate(script); await page.waitForTimeout(600) }
    const file = path.join(root, 'screenshots', `${name}-${width}${scheme === 'dark' ? '-dark' : ''}.png`)
    await page.screenshot({ path: file, fullPage: flag('full') })
    const overflow = await page.evaluate((w) => Math.max(document.documentElement.scrollWidth, window.innerWidth) - w, width)
    console.log(`${file}  overflowX=${overflow}${errors.length ? '  ERRORS: ' + [...new Set(errors)].slice(0, 4).join(' | ') : ''}`)
    errors.length = 0
  }
  await ctx.close()
}
await browser.close()
