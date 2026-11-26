// The tabs of an inbox item, in its pane and on its page (issue 118): Summary, then the original (Emails n for a digest, File, Transcript or
// Original), Decisions n and What came of it n. The tab is in the URL (ptab= in the pane, tab= on the page).

// the emails of a digest: its list items, not those under "Left out"
export function emailCount(text) {
  let n = 0
  let skip = false
  for (const line of String(text || '').split('\n')) {
    const h = /^#{1,4}\s+(.*)$/.exec(line)
    if (h) { skip = /left out/i.test(h[1]); continue }
    if (!skip && /^\s{0,1}(?:[-*+]|\d+[.)])\s+\S/.test(line)) n++
  }
  return n
}

export function originalKey(item) {
  if (item.source_type === 'Email Digest') return 'emails'
  if (item.source_type === 'Voice Note') return 'transcript'
  if (item.files?.length && !item.raw_text) return 'file'
  return 'original'
}
const LABEL = { emails: 'Emails', file: 'File', transcript: 'Transcript', original: 'Original' }

export function itemTabs(item) {
  if (!item) return []
  const key = originalKey(item)
  const pending = item.proposals.filter((p) => p.status === 'Pending').length
  return [{ value: 'summary', label: 'Summary' },
    { value: key, label: LABEL[key], ...(key === 'emails' ? { count: emailCount(item.raw_text), noun: 'emails' } : {}) },
    { value: 'decisions', label: 'Decisions', count: pending, noun: 'decisions' },
    { value: 'came', label: 'What came of it', count: item.came_of_it?.length ?? 0, noun: 'records' }]
}
