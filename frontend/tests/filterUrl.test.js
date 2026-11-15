import test from 'node:test'
import assert from 'node:assert/strict'
import { DUE_PRESETS, EXPIRY_PRESETS, activeCount, canonical, filtersToQuery, orderByToQuery, parseWire, queryToFilters, queryToOrderBy, queryToRequest } from '../src/lib/filterUrl.js'

const TODAY = '2026-11-15'
const TASKS = [
  { key: 'area', field: 'area', kind: 'link' }, { key: 'project', field: 'project', kind: 'link' }, { key: 'tag', field: 'tag', kind: 'value' },
  { key: 'priority', field: 'priority', kind: 'link' }, { key: 'goal', field: 'goal', kind: 'value' },
  { key: 'due', field: 'due_date', kind: 'preset', presets: DUE_PRESETS }, { key: 'status', field: 'status', kind: 'value' },
  { key: 'completed_from', field: 'completed_on', kind: 'from' }, { key: 'completed_to', field: 'completed_on', kind: 'to' },
  { key: 'done', kind: 'flag' }, { key: 'archived', kind: 'flag' },
]
const VAULT = [{ key: 'holder', field: 'holder', kind: 'link' }, { key: 'type', field: 'doc_type', kind: 'value' },
  { key: 'expiry', field: 'expiry_date', kind: 'preset', presets: EXPIRY_PRESETS }, { key: 'archived', kind: 'flag' }]
const clean = (q) => Object.fromEntries(Object.entries(q).filter(([, v]) => v !== undefined))

test('short parameters become wire filters', () => {
  const { wire, flags } = queryToFilters({ status: 'Done', area: 'a1', priority: 'none', due: 'overdue', done: '1', open: 'task:x', view: 'table' }, TASKS, TODAY)
  assert.deepEqual(wire, [['area', '=', 'a1'], ['priority', 'is', 'not set'], ['due_date', '<', TODAY], ['status', '=', 'Done']])
  assert.deepEqual(flags, { done: true })
})

test('every existing count link round-trips', () => {
  const links = [
    { status: 'To Review' }, { due: 'today,overdue' }, { due: 'overdue' }, { due: 'today' }, { due: 'week' }, { due: 'none' },
    { project: 'p1', done: '1', archived: '1' }, { area: 'none' }, { area: 'a1', priority: 'I' }, { tag: 't1', goal: 'g1' },
    { status: 'Done', completed_from: '2026-11-09', completed_to: '2026-11-15' }, { status: 'Carried' }, { project: 'none' },
  ]
  for (const q of links) {
    const { wire, flags } = queryToFilters(q, TASKS, TODAY)
    assert.deepEqual(clean(filtersToQuery(wire, flags, TASKS, TODAY)), q)
  }
  for (const q of [{ expiry: 'expired' }, { expiry: 'soon' }, { expiry: 'later' }, { expiry: 'none' }, { holder: 'none', type: 'Medical', expiry: 'expired' }, { archived: '1' }]) {
    const { wire, flags } = queryToFilters(q, VAULT, TODAY)
    assert.deepEqual(clean(filtersToQuery(wire, flags, VAULT, TODAY)), q)
  }
})

test('a preset is worked out for today, not stored as a date', () => {
  assert.deepEqual(queryToFilters({ due: 'overdue' }, TASKS, '2026-12-01').wire, [['due_date', '<', '2026-12-01']])
  assert.deepEqual(queryToFilters({ expiry: 'soon' }, VAULT, '2026-12-15').wire, [['expiry_date', 'between', ['2026-12-15', '2027-02-13']]])
  // yesterday's "overdue" is a plain date condition today: it has no short form any more
  const q = filtersToQuery([['due_date', '<', '2026-11-14']], {}, TASKS, TODAY)
  assert.equal(q.due, undefined)
  assert.deepEqual(JSON.parse(q.f), [['due_date', '<', '2026-11-14']])
})

test('conditions with no short form go into f, and come back', () => {
  const wire = [['title', 'like', '%tea%'], ['status', 'in', ['Open', 'Doing']], ['area', '=', 'a1'], ['priority', '!=', 'I'], ['due_date', '>', '2026-12-01']]
  const q = filtersToQuery(wire, { archived: true }, TASKS, TODAY)
  assert.equal(q.area, 'a1')
  assert.equal(q.archived, '1')
  assert.equal(q.status, undefined)
  assert.deepEqual(JSON.parse(q.f), [['title', 'like', '%tea%'], ['status', 'in', ['Open', 'Doing']], ['priority', '!=', 'I'], ['due_date', '>', '2026-12-01']])
  const back = queryToFilters(clean(q), TASKS, TODAY)
  assert.deepEqual(new Set(back.wire.map((w) => JSON.stringify(w))), new Set(wire.map((w) => JSON.stringify(w))))
  assert.deepEqual(back.flags, { archived: true })
})

test('two conditions on one field: the first takes the short form, the second goes to f', () => {
  const q = filtersToQuery([['status', '=', 'Open'], ['status', '=', 'Done']], {}, TASKS, TODAY)
  assert.equal(q.status, 'Open')
  assert.deepEqual(JSON.parse(q.f), [['status', '=', 'Done']])
  const range = filtersToQuery([['completed_on', '>=', '2026-11-01'], ['completed_on', '<=', '2026-11-30']], {}, TASKS, TODAY)
  assert.equal(range.completed_from, '2026-11-01')
  assert.equal(range.completed_to, '2026-11-30')
  assert.equal(range.f, undefined)
})

test('clearing sets every filter key to undefined', () => {
  const q = filtersToQuery([], {}, TASKS, TODAY)
  assert.deepEqual(clean(q), {})
  for (const e of TASKS) assert.ok(e.key in q)
  assert.ok('f' in q)
})

test('what is sent to the server', () => {
  const r = queryToRequest({ status: 'Done', due: 'overdue', done: '1', archived: '0', f: JSON.stringify([['title', 'like', '%x%']]), sort: 'title', open: 'task:1' }, TASKS)
  assert.deepEqual(r.params, { status: 'Done', due: 'overdue', done: 1 })
  assert.deepEqual(r.filters, [['title', 'like', '%x%']])
  assert.deepEqual(queryToRequest({ due: 'sometime' }, TASKS).params, {})
})

test('bad input is ignored, never thrown', () => {
  assert.deepEqual(parseWire('not json'), [])
  assert.deepEqual(parseWire('{"a":1}'), [])
  assert.deepEqual(parseWire(JSON.stringify([['a', '=', 1], 'x', [1, 2, 3], ['only', 'two']])), [['a', '=', 1]])
  assert.deepEqual(queryToFilters({ f: '[[', status: ['Done', 'Open'], due: 'never' }, TASKS, TODAY).wire, [['status', '=', 'Done']])
  assert.deepEqual(queryToFilters(undefined, TASKS, TODAY), { wire: [], flags: {} })
})

test('sort and direction', () => {
  assert.equal(queryToOrderBy({ sort: 'due_date', dir: 'desc' }), 'due_date desc')
  assert.equal(queryToOrderBy({ sort: 'title' }), 'title asc')
  assert.equal(queryToOrderBy({ sort: 'status,title', dir: 'asc,desc' }), 'status asc, title desc')
  assert.equal(queryToOrderBy({}), '')
  assert.deepEqual(orderByToQuery('due_date desc'), { sort: 'due_date', dir: 'desc' })
  assert.deepEqual(orderByToQuery('title asc'), { sort: 'title', dir: undefined })
  assert.deepEqual(orderByToQuery('status asc, title desc'), { sort: 'status,title', dir: 'asc,desc' })
  assert.deepEqual(orderByToQuery(''), { sort: undefined, dir: undefined })
  for (const o of ['due_date desc', 'title asc', 'status asc, title desc']) assert.equal(queryToOrderBy(orderByToQuery(o)), o)
})

test('counting active filters and the canonical form', () => {
  assert.equal(activeCount({}, TASKS), 0)
  assert.equal(activeCount({ view: 'table', open: 'task:1', sort: 'title' }, TASKS), 0)
  assert.equal(activeCount({ status: 'Done', done: '1', f: JSON.stringify([['title', 'like', '%x%'], ['owner', '=', 'a@b.c']]) }, TASKS), 4)
  assert.deepEqual(canonical({ view: 'table', status: 'Done', open: 'task:1', area: '', sort: 'title', all: '1' }, TASKS, ['view']), { status: 'Done', sort: 'title', view: 'table' })
  assert.equal(JSON.stringify(canonical({ status: 'Done', area: 'a' }, TASKS)), JSON.stringify(canonical({ area: 'a', status: 'Done' }, TASKS)))
})

test('values that are state tabs are not conditions', () => {
  const spec = [{ key: 'status', field: 'status', kind: 'value', skip: ['open', 'loops', 'Waiting', 'Done', 'all'] }, { key: 'area', field: 'area', kind: 'link' }]
  // status=Done is the Done tab: no condition for the controls, not counted as a filter, not sent as a parameter, kept in the saved query
  assert.deepEqual(queryToFilters({ status: 'Done', area: 'a1' }, spec, '2026-11-15').wire, [['area', '=', 'a1']])
  assert.equal(activeCount({ status: 'Done' }, spec), 0)
  assert.equal(activeCount({ status: 'Done', area: 'a1' }, spec), 1)
  assert.deepEqual(queryToRequest({ status: 'Done', area: 'a1' }, spec).params, { area: 'a1' })
  assert.deepEqual(canonical({ status: 'Done', open: 'task:x' }, spec), { status: 'Done' })
  // a status that is not a tab is an ordinary condition
  assert.deepEqual(queryToFilters({ status: 'Dropped' }, spec, '2026-11-15').wire, [['status', '=', 'Dropped']])
  assert.equal(activeCount({ status: 'Dropped' }, spec), 1)
  assert.deepEqual(queryToRequest({ status: 'Dropped' }, spec).params, { status: 'Dropped' })
})
