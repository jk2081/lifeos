import test from 'node:test'
import assert from 'node:assert/strict'
import { parentOf, tabTitle, trailOf } from '../src/lib/trail.js'

const goal = [{ label: 'Goals', to: '/goals' }, { label: 'Career', to: '/goals?area=a' }]
test('the path ends with the title, the ancestors are links', () => {
  const t = trailOf(goal, 'Ghillidary yield')
  assert.deepEqual(t.map((p) => p.label), ['Goals', 'Career', 'Ghillidary yield'])
  assert.equal(t[2].to, undefined)
  assert.equal(t[0].to, '/goals')
})
test('back goes to the parent in the path', () => {
  assert.equal(parentOf(goal), '/goals?area=a')
  assert.equal(parentOf([]), '')
  assert.equal(parentOf(undefined), '')
})
test('the tab title is the path in reverse', () => {
  assert.equal(tabTitle('Ghillidary yield', goal), 'Ghillidary yield · Career · Goals — Life OS')
  assert.equal(tabTitle('Goals', []), 'Goals — Life OS')
})
// no page draws a header of its own: the shared one (PageHead.vue) is the only <h1>/<PageHeader> of a screen
test('no page component renders its own header outside the shared one', async () => {
  const { readdirSync, readFileSync, statSync } = await import('node:fs')
  const { join } = await import('node:path')
  const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
  const src = join(import.meta.dirname, '..', 'src')
  const own = walk(src).filter((f) => f.endsWith('.vue') && !/(PageHead|OnboardingGuide|ScreenErrorMessage)\.vue$/.test(f))
    .filter((f) => /<PageHeader\b|<h1[\s>]/.test(readFileSync(f, 'utf8')))
  assert.deepEqual(own.map((f) => f.slice(src.length)), [])
})
