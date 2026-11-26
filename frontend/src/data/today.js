// Every server call the Today screens make (Today, Tasks, Timeline, Someday, Archive, Outbox, a Focus page, quick add and
// capture). A component calls these, never `api(` directly.
import { group } from '@/data/call'

export const todayData = {
  session: group('session', ['boot', 'counts']),
  someday: group('someday', ['create', 'list']),
  tasks: group('tasks', ['confirm_area', 'list', 'quick_add', 'reschedule_overdue', 'set_status', 'update']),
  calendar: group('calendar', ['add_important_date', 'week_plan', 'year_plan']),
  trash: group('trash', ['list', 'restore']),
  archive: group('archive', ['list', 'restore']),
  focus: group('focus', ['get']),
  settings: group('settings', ['save_item']),
  outbox: group('outbox', ['bring_back', 'chart', 'list']),
  timeline: group('timeline', ['get']),
  old_items: group('old_items', ['undo_auto']),
  today: group('today', ['get', 'skip_banner']),
  dashboard: group('dashboard', ['get', 'list']),
  goals: group('goals', ['toggle_habit']),
}
