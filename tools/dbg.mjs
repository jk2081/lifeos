import { chromium } from 'playwright-core'
import fs from 'node:fs'
const env = Object.fromEntries(fs.readFileSync('.env', 'utf8').split('\n').filter(Boolean).map((l) => l.split('=')))
const base = 'http://localhost:18000'
const width = Number(process.argv[2] || 1440)
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
const ctx = await browser.newContext({ viewport: { width, height: width < 800 ? 844 : 1000 }, isMobile: width < 800, hasTouch: width < 800 })
const page = await ctx.newPage()
page.on('pageerror', (e) => console.log('PAGEERROR', String(e)))
page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text()))
await page.request.post(base + '/api/method/login', { form: { usr: 'owner@lifeos.test', pwd: env.LIFEOS_DEV_PASSWORD } })
const open = async (p) => { await page.goto(base + p, { waitUntil: 'networkidle' }); await page.waitForTimeout(400) }
globalThis.page = page; globalThis.open = open
await (await import(process.argv[3])).default(page, open)
await browser.close()
