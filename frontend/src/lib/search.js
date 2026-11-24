// Search, shared by the palette and Ask's "needs an AI key" notice (issue 98): the screens and settings that can be
// found by name, and what a click on a result does.
import router from '@/router'
import { store } from '@/lib/store'
import { openRef, refOf } from '@/lib/pane'

// A small fixed list: what it is called, other words for it, where it opens. `admin` ones are only offered to a Life Admin.
export const SCREENS = [
  { label: 'Settings › AI', words: 'ai key api key anthropic model cost cap provider', to: '/settings?tab=advanced&part=ai', admin: true },
  { label: 'Settings › Connections', words: 'connections sources gmail calendar email google', to: '/brain/sources' },
  { label: 'Settings › Areas', words: 'areas parts focuses', to: '/settings?tab=areas' },
  { label: 'Settings › Rhythms', words: 'rhythms review day week start cycle score', to: '/settings?tab=rhythms' },
  { label: 'Settings › Habits', words: 'habits', to: '/settings?tab=habits' },
  { label: 'Settings › Rules', words: 'rules sensitive notes', to: '/settings?tab=rules' },
  { label: 'Settings › People and agents', words: 'members spaces agents people', to: '/settings?tab=members', admin: true },
  { label: 'Settings › Data', words: 'data reset export', to: '/settings?tab=data' },
  { label: 'Settings › Backups and updates', words: 'backups updates import advanced', to: '/settings?tab=advanced&part=backups', admin: true },
  { label: 'Settings › Profile', words: 'profile appearance dark theme name notifications shortcuts', to: '/settings?tab=profile' },
  { label: 'Today', words: 'day plate', to: '/today' },
  { label: 'Brain', words: 'needs you inbox captures activity queue', to: '/brain' },
  { label: 'Goals', words: 'tasks cycles someday 12 week year', to: '/goals' },
  { label: 'Library', words: 'notes wiki documents vault people chats files', to: '/library' },
  { label: 'Weekly review', words: 'review', to: '/review' },
  { label: 'Skills', words: 'skills brain', to: '/brain/skills' },
  { label: 'Archive and trash', words: 'archive trash deleted', to: '/library/archive' },
  { label: 'Ask history and insights', words: 'ask history insights threads', to: '/ask?tab=history' },
]

const WORDS = /[\p{L}\p{N}]+/gu
/** The screens whose name or words start with every word typed. */
export function screenHits(text) {
  const typed = String(text || '').toLowerCase().match(WORDS) || []
  if (!typed.length) return []
  return SCREENS.filter((s) => !s.admin || store.isAdmin).filter((s) => {
    const have = `${s.label} ${s.words}`.toLowerCase().match(WORDS) || []
    return typed.every((w) => have.some((h) => h.startsWith(w)))
  })
}

/** Open a search result: in the pane over the screen you are on when it has one, else its page. */
export function openHit(r) {
  if (r.screen) return router.push(r.screen)
  if (r.space && r.space !== store.space) Object.assign(store, { space: r.space, lensArea: '' }) // a result in another space: its whole space
  if (r.ref_doctype === 'Life Inbox Item') return router.push(r.route) // a capture opens its item page (issue 10)
  const ref = refOf(r.ref_doctype, r.ref_name)
  return ref ? openRef(ref) : router.push(String(r.route || '/').replace(/^\/life/, '') || '/')
}
