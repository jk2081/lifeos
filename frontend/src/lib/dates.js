// Dates arrive from the server as site-time strings (Asia/Kolkata) and are shown as they are.
export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
export const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function parse(s) {
  if (!s) return null
  if (s instanceof Date) return s
  const [y, m, d] = String(s).slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}
export function iso(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
export function addDays(s, n) {
  const d = parse(s)
  d.setDate(d.getDate() + n)
  return iso(d)
}
export function diffDays(a, b) {
  return Math.round((parse(a) - parse(b)) / 86400000)
}
export function short(s, withYear = false) {
  const d = parse(s)
  if (!d) return ''
  return `${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)}${withYear ? ' ' + d.getFullYear() : ''}`
}
export function long(s, withYear = false) {
  const d = parse(s)
  if (!d) return ''
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${withYear ? ' ' + d.getFullYear() : ''}`
}
export function weekday(s, len = 0) {
  const d = parse(s)
  return d ? (len ? DAYS[d.getDay()].slice(0, len) : DAYS[d.getDay()]) : ''
}
export function time(s) {
  return s && String(s).length >= 16 ? String(s).slice(11, 16) : ''
}
export function dateTime(s) {
  return s ? `${short(s)}, ${time(s)}` : ''
}
export function startOfWeek(s) {
  const d = parse(s)
  const back = (d.getDay() + 6) % 7
  d.setDate(d.getDate() - back)
  return iso(d)
}

/** A run of days, no repeats: "23 – 29 November", "30 November – 6 December". */
export function dayRange(a, b) {
  const x = parse(a), y = parse(b)
  if (x.getTime() === y.getTime()) return long(a)
  return x.getMonth() === y.getMonth() && x.getFullYear() === y.getFullYear() ? `${x.getDate()} – ${long(b)}` : `${long(a)} – ${long(b)}`
}
/** When an event is, as it reads in the drawer: "Tuesday, 24 November · all day", "24–25 November · all day",
 *  "Tuesday, 24 November · 10:00 to 11:00". The year shows only when it is not this one. */
export function eventWhen(starts, ends, allDay) {
  const yr = (s) => (parse(s).getFullYear() === new Date().getFullYear() ? '' : ` ${parse(s).getFullYear()}`)
  const first = String(starts).slice(0, 10), last = String(ends || starts).slice(0, 10)
  if (allDay) {
    if (last > first) {
      const x = parse(first), y = parse(last)
      const days = x.getMonth() === y.getMonth() && x.getFullYear() === y.getFullYear() ? `${x.getDate()}–${long(last)}` : `${long(first)} – ${long(last)}`
      return `${days}${yr(last)} · all day`
    }
    return `${weekday(first)}, ${long(first)}${yr(first)} · all day`
  }
  const span = ends && time(ends) ? `${time(starts)} to ${time(ends)}` : time(starts)
  return `${weekday(first)}, ${long(first)}${yr(first)} · ${last > first ? `${span} (until ${long(last)})` : span}`
}
