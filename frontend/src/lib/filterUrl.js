// The URL form of a list's filters, and back.
//
// A list keeps its filters in the query string in the short form the count links have always used
// (status=Done, area=<id>, due=overdue). The library's Filter and QuickFilter controls work on a list of
// conditions, which travel as Frappe "wire" filters: [fieldname, operator, value]. This module is the one
// place that maps between the two. It has no imports, so it is tested with plain node (tests/filterUrl.test.js).
//
// A screen describes its short parameters with a spec, one entry per parameter:
//   { key, field, kind: 'value' }            status=Done        <->  [status, '=', 'Done']
//   { key, field, kind: 'link' }             area=<id>          <->  [area, '=', <id>]
//                                            area=none          <->  [area, 'is', 'not set']
//   { key, field, kind: 'from' | 'to' }      from=2026-11-01    <->  [date, '>=', '2026-11-01']   ('to' uses '<=')
//   { key, field, kind: 'preset', presets }  due=overdue        <->  whatever presets.overdue(today) returns
//   { key, kind: 'flag' }                    done=1             a switch that is not a condition on a field
// An entry may carry `skip`, a list of values that are not conditions: the values of the list's state tabs
// (status=Done selects the Done tab). They stay in the URL and in the saved view, and never reach the filter controls.
// Conditions with no short form go, as they are, into one parameter: f=<JSON list of wire filters>.

export const WIRE_KEY = 'f'
export const SORT_KEYS = ['sort', 'dir']

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const text = (v) => (Array.isArray(v) ? v[0] : v) == null ? '' : String(Array.isArray(v) ? v[0] : v)
const skipped = (entry, value) => Array.isArray(entry.skip) && entry.skip.includes(value)
const isOn = (v) => ['1', 'true', 'yes', 'on'].includes(text(v).toLowerCase())

function shortToWire(entry, value, today) {
  const { field, kind } = entry
  if (kind === 'value') return [field, '=', value]
  if (kind === 'link') return value === 'none' ? [field, 'is', 'not set'] : [field, '=', value]
  if (kind === 'from') return [field, '>=', value]
  if (kind === 'to') return [field, '<=', value]
  if (kind === 'preset') return entry.presets[value] ? entry.presets[value](today) : null
  return null
}

function wireToShort(entry, [field, op, value], today) {
  if (field !== entry.field) return null
  const { kind } = entry
  const plain = typeof value === 'string' && value !== ''
  if (kind === 'value' && op === '=' && plain) return value
  if (kind === 'link') {
    if (op === '=' && plain && value !== 'none') return value
    if (op === 'is' && value === 'not set') return 'none'
  }
  if (kind === 'from' && op === '>=' && plain) return value
  if (kind === 'to' && op === '<=' && plain) return value
  if (kind === 'preset') {
    for (const name of Object.keys(entry.presets)) if (same(entry.presets[name](today), [field, op, value])) return name
  }
  return null
}

/** The wire filters and switches a query string stands for. Unknown or empty parameters are ignored. */
export function queryToFilters(query = {}, spec = [], today = '') {
  const wire = []
  const flags = {}
  for (const entry of spec) {
    const value = text(query[entry.key])
    if (!value || skipped(entry, value)) continue
    if (entry.kind === 'flag') {
      if (isOn(value)) flags[entry.key] = true
      continue
    }
    const w = shortToWire(entry, value, today)
    if (w) wire.push(w)
  }
  wire.push(...parseWire(query[WIRE_KEY]))
  return { wire, flags }
}

/** The query parameters for a list of wire filters and switches. Every key of the spec is present,
 *  set to undefined when it is off, so the result can be merged over an existing query to replace its filters. */
export function filtersToQuery(wire = [], flags = {}, spec = [], today = '') {
  const query = { [WIRE_KEY]: undefined }
  for (const entry of spec) query[entry.key] = undefined
  const rest = []
  for (const w of wire) {
    if (!Array.isArray(w) || w.length !== 3) continue
    // the first parameter that can say this condition, and has not been used yet, takes it
    const entry = spec.find((e) => e.kind !== 'flag' && query[e.key] === undefined && wireToShort(e, w, today) !== null)
    if (entry) query[entry.key] = wireToShort(entry, w, today)
    else rest.push(w)
  }
  for (const entry of spec) if (entry.kind === 'flag' && flags[entry.key]) query[entry.key] = '1'
  if (rest.length) query[WIRE_KEY] = JSON.stringify(rest)
  return query
}

/** What a list sends to its lifeos.api method: the short parameters by name, the switches, and the rest as `filters`. */
export function queryToRequest(query = {}, spec = []) {
  const params = {}
  for (const entry of spec) {
    const value = text(query[entry.key])
    if (!value || skipped(entry, value)) continue
    if (entry.kind === 'flag') {
      if (isOn(value)) params[entry.key] = 1
    } else if (entry.kind !== 'preset' || entry.presets[value]) params[entry.key] = value
  }
  const filters = parseWire(query[WIRE_KEY])
  return { params, filters }
}

// The operators the filter control reads back from a wire filter, in its spelling. A link may write them in any case
// ("like" as well as "LIKE"); one the control does not know would break the list (bug fix 1), so it is left out.
const WIRE_OPS = ['=', '!=', 'LIKE', 'NOT LIKE', '>', '<', '>=', '<=', 'in', 'not in', 'is', 'is not', 'between', 'timespan']
const WIRE_OP = Object.fromEntries([...WIRE_OPS.map((op) => [op.toLowerCase(), op]), ['equals', '='], ['not equals', '!=']])

export function parseWire(raw) {
  const value = text(raw)
  if (!value) return []
  try {
    const list = JSON.parse(value)
    if (!Array.isArray(list)) return []
    return list.filter((w) => Array.isArray(w) && w.length === 3 && typeof w[0] === 'string' && typeof w[1] === 'string' && WIRE_OP[w[1].trim().toLowerCase()])
      .map(([field, op, val]) => [field, WIRE_OP[op.trim().toLowerCase()], val])
  } catch {
    return []
  }
}

/** sort=due_date&dir=desc  <->  "due_date desc". Several sorts are comma separated in both parameters. */
export function queryToOrderBy(query = {}) {
  const fields = text(query.sort).split(',').map((s) => s.trim()).filter(Boolean)
  const dirs = text(query.dir).split(',').map((s) => s.trim())
  return fields.map((f, i) => `${f} ${dirs[i] === 'desc' ? 'desc' : 'asc'}`).join(', ')
}
export function orderByToQuery(orderBy = '') {
  const parts = String(orderBy).split(',').map((p) => p.trim().split(/\s+/)).filter((p) => p[0])
  if (!parts.length) return { sort: undefined, dir: undefined }
  const dirs = parts.map((p) => (String(p[1]).toLowerCase() === 'desc' ? 'desc' : 'asc'))
  return { sort: parts.map((p) => p[0]).join(','), dir: dirs.some((d) => d === 'desc') ? dirs.join(',') : undefined }
}

/** How many filters a query holds: conditions and switches, by the spec. */
export function activeCount(query = {}, spec = []) {
  let n = parseWire(query[WIRE_KEY]).length
  for (const entry of spec) {
    const value = text(query[entry.key])
    if (!value || skipped(entry, value)) continue
    if (entry.kind === 'flag' ? isOn(value) : entry.kind !== 'preset' || entry.presets[value]) n++
  }
  return n
}

/** The filter and sort part of a query, with empty values dropped and the keys in a fixed order: two queries
 *  that mean the same list give the same string. `keep` names other keys that belong to the list (the view). */
export function canonical(query = {}, spec = [], keep = []) {
  const keys = [...spec.map((e) => e.key), WIRE_KEY, ...SORT_KEYS, ...keep]
  const out = {}
  for (const key of keys) {
    const value = text(query[key])
    if (value) out[key] = value
  }
  return out
}

// ---- presets shared by the screens ----
export const DUE_PRESETS = {
  overdue: (today) => ['due_date', '<', today],
  today: (today) => ['due_date', '=', today],
  'today,overdue': (today) => ['due_date', '<=', today],
  week: () => ['due_date', 'timespan', 'this week'],
  none: () => ['due_date', 'is', 'not set'],
}
