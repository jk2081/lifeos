import test from 'node:test'
import assert from 'node:assert/strict'
import { plural } from '../src/lib/plural.js'

test('count labels use the right plural', () => {
  assert.equal(plural(0, 'tick'), '0 ticks')
  assert.equal(plural(1, 'tick'), '1 tick')
  assert.equal(plural(2, 'tick'), '2 ticks')
})
