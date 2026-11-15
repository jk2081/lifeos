// The New menu of the sidebar and the phone's More list, and the two counts the navigation shows.
import router from '@/router'
import { store } from './store'

export function newMenuItems() {
  return [
    { label: 'Task', icon: 'lucide-square-check', onClick: () => (store.quickAdd = true) },
    { label: 'Note', icon: 'lucide-file-text', onClick: () => (store.newKind = 'note') },
    { label: 'Project', icon: 'lucide-chart-no-axes-column', onClick: () => (store.newKind = 'project') },
    { label: 'Add to Inbox', icon: 'lucide-inbox', onClick: () => router.push('/inbox') },
  ]
}

// Inbox: items to review. Tasks: open tasks due today or overdue, the same number as Today's "Due today".
export function navCount(label) {
  if (label === 'Inbox' && store.counts.to_review) {
    return { n: store.counts.to_review, to: { path: '/inbox', query: { status: 'To Review' } }, label: `${store.counts.to_review} to review`, door: 'nav-review' }
  }
  if (label === 'Tasks' && store.counts.due) {
    return { n: store.counts.due, to: { path: '/tasks', query: { due: 'today,overdue', view: 'list' } }, label: `${store.counts.due} due today or overdue`, door: 'nav-due' }
  }
  return null
}
