// Bug fix 1: walk every place, every tab of Plan and Library, and every view of Plan's rhythms by clicking through the app
// as a person would (not by loading each URL), and report any screen that fails: a script error, the error boundary's
// message, a body left empty, or the journal screens' header buttons missing. It ends by checking that navigation still
// works. Used by tools/acceptance.mjs (BF1 checks) and, read-only, against the owner's site (--owner-read-only).

// the views of Plan's rhythms and, for the journal screens, a button each puts into the header's #jr-actions
const RHYTHMS = {
  week: [['Review'], ['Calendar'], ['Agenda']], // set 8: the review is its own screen; Pause leaves it for the Calendar
  month: [['Plan', 'Previous month'], ['Habits', 'Previous month'], ['Check-ins'], ['Calendar']],
  '12-weeks': [[null, 'Weekly review']], // one view: no switch
  year: [['Calendar'], ['Goals across cycles', 'All goals']],
}
const PLAN = ['week', 'month', '12-weeks', 'year', 'goals', 'tasks', 'someday']
const LIBRARY = ['all', 'notes', 'captures', 'outbox', 'timeline', 'archive']

export async function walkScreens(page, { width, settle = () => page.waitForTimeout(500) }) {
  const phone = width < 800
  const errors = []
  const onError = (e) => errors.push(String(e).split('\n')[0])
  page.on('pageerror', onError)
  const failures = []
  let seen = 0
  const place = async (label) => {
    await page.locator(phone ? `[data-tab-item="${label}"]` : `[data-nav-item="${label}"]`).first().click()
    await page.waitForLoadState('networkidle')
    await settle()
  }
  // set 8: the weekly review has no place tabs or view switch of its own; Pause returns to the Week's calendar
  const leaveReview = async () => {
    if (await page.locator('[data-review-pause]:visible').count()) {
      await page.locator('[data-review-pause]:visible').first().click()
      await page.waitForLoadState('networkidle')
      await settle()
    }
  }
  const tab = async (value) => {
    await leaveReview()
    await page.locator(`[data-place-tabs] [data-tab="${value}"]`).first().click()
    await page.waitForLoadState('networkidle')
    await settle()
  }
  const view = async (label) => {
    if (!label) return
    if (label === 'Review' && await page.locator('[data-review]').count()) return
    await leaveReview()
    await page.locator('[data-plan-views]:visible').first().getByText(label, { exact: true }).click()
    await page.waitForLoadState('networkidle')
    await settle()
  }
  const inspect = async (name, button) => {
    seen += 1
    const s = await page.evaluate((b) => {
      const main = document.querySelector('[data-main]')
      const head = main?.querySelector('[data-page-head]')
      const text = (main?.innerText || '').length - (head?.innerText || '').length
      return { failed: document.querySelector('[data-screen-error]')?.innerText.split('\n')[0] || '', text,
        button: !b || [...document.querySelectorAll('#jr-actions button, #jr-actions a')]
          .some((el) => el.getAttribute('aria-label') === b || el.innerText.trim() === b) }
    }, button || '')
    const problems = []
    if (errors.length) problems.push('script error: ' + errors.splice(0).join(' | '))
    if (s.failed) problems.push(s.failed)
    if (s.text < 40) problems.push('empty body')
    if (!s.button) problems.push(`no "${button}" button in the header`)
    if (problems.length) failures.push(`${name}: ${problems.join('; ')}`)
  }

  for (const label of ['Today', 'Inbox']) { await place(label); await inspect(label) }
  await place('Plan')
  for (const t of PLAN) {
    await tab(t)
    if (!RHYTHMS[t]) { await inspect(`Plan > ${t}`); continue }
    // each view, then back to the first: switching views inside a mounted rhythm is how the review broke
    for (const [label, button] of [...RHYTHMS[t], RHYTHMS[t][0]]) { await view(label); await inspect(`Plan > ${t} > ${label || 'Cycle'}`, button) }
  }
  await place('Library')
  for (const t of LIBRARY) { await tab(t); await inspect(`Library > ${t}`) }
  // navigation still moves the page after all of that
  await place('Plan'); await tab('week'); await view('Review')
  await place('Today')
  const path = await page.evaluate(() => location.pathname)
  if (path.replace(/\/$/, '') !== '/life') failures.push(`navigation: Today left the page at ${path}`)
  await inspect('Today after the walk')
  page.off('pageerror', onError)
  return { seen, failures }
}
