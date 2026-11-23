// Bug fix 1: walk every place, every tab of each place, and every view of Today's rhythms by clicking through the app
// as a person would (not by loading each URL), and report any screen that fails: a script error, the error boundary's
// message, a body left empty, or the journal screens' header buttons missing. It ends by checking that navigation still
// works. Used by tools/acceptance.mjs (BF1 checks) and, read-only, against the owner's site (--owner-read-only).

// the views of Today's rhythms (Plan's before issue 14; the month plan and 12 Weeks moved to Goals > Cycles in issue 45) and, for the journal screens, a button each puts into the header's #jr-actions
const RHYTHMS = {
  week: [['Review'], ['Calendar'], ['Agenda']], // set 8: the review is its own screen; Pause leaves it for the Calendar
  month: [['Habits', 'Previous month'], ['Calendar']],
  year: [['Calendar'], ['Goals across cycles', 'All goals']],
}
// issue 14: the four places, each tab, and the pages linked at the foot of a place
const PLACES = {
  Today: { tabs: ['day', 'week', 'month', 'year'] },
  Brain: { tabs: ['needs-you', 'activity', 'sources'], pages: ['outbox'] },
  Goals: { tabs: ['by-area', 'tasks', 'no-goal'], pages: ['someday'] },
  Library: { tabs: ['all', 'notes', 'documents', 'people', 'chats'], pages: ['timeline', 'archive'] },
}

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
  let current = 'day'
  const tab = async (value) => {
    current = value
    await leaveReview()
    await page.locator(`[data-place-tabs] [data-tab="${value}"]`).first().click()
    await page.waitForLoadState('networkidle')
    await settle()
  }
  const view = async (label) => {
    if (!label) return
    if (label === 'Review' && await page.locator('[data-review]').count()) {
      // already on the review: let it finish loading before the next click (CI once timed out on the tab bar here)
      await page.waitForLoadState('networkidle')
      await page.locator(phone ? '[data-tab-item]' : '[data-nav-item]').first().waitFor({ state: 'visible' })
      await settle()
      return
    }
    await leaveReview()
    // issue 16: Week, Month and Year open on screens of their own; the older views are reached by `view=` until the switch shows
    if (!(await page.locator('[data-plan-views]:visible').count())) {
      const KEYS = { 'Goals across cycles': 'goals' }
      await page.goto(new URL(`/life/today/${current}?view=${KEYS[label] || label.toLowerCase()}`, page.url()).href)
    } else await page.locator('[data-plan-views]:visible').first().getByText(label, { exact: true }).click()
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

  const pageLink = async (key) => {
    await page.locator(`[data-place-link="${key}"]`).first().click()
    await page.waitForLoadState('networkidle')
    await settle()
  }
  for (const [label, p] of Object.entries(PLACES)) {
    await place(label)
    for (const t of p.tabs) {
      await tab(t)
      if (!RHYTHMS[t]) { await inspect(`${label} > ${t}`); continue }
      // each view, then back to the first: switching views inside a mounted rhythm is how the review broke
      for (const [v, button] of [...RHYTHMS[t], RHYTHMS[t][0]]) { await view(v); await inspect(`${label} > ${t} > ${v}`, button) }
    }
    for (const k of p.pages || []) { await pageLink(k); await inspect(`${label} > ${k}`) }
  }
  // navigation still moves the page after all of that
  await place('Today'); await tab('week'); await view('Review')
  // issue 14: Today's own tab is the place already open on the Week's review, so move away and back
  await place('Brain')
  await place('Today')
  const path = await page.evaluate(() => location.pathname)
  if (path.replace(/\/$/, '') !== '/life/today') failures.push(`navigation: Today left the page at ${path}`)
  await inspect('Today after the walk')
  page.off('pageerror', onError)
  return { seen, failures }
}
