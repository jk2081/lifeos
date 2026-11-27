// Every server call the item screens make (the item page, the record pane and the pane of each kind of record).
// A component calls these, never `api(` directly.
import { group } from '@/data/call'

export const itemData = {
  inbox: group('inbox', ['change_line', 'get', 'item_page', 'retry']),
  sources: group('sources', ['made_from']),
  review: group('review', ['decide', 'update_payload']),
  meta: group('meta', ['proposal_schema']),
  archive: group('archive', ['restore', 'set']),
  trash: group('trash', ['delete']),
  library: group('library', ['get', 'set_sensitive']),
  wiki: group('wiki', ['changes', 'move']),
  tasks: group('tasks', ['carry_forward', 'get', 'hand_off', 'handoff_discard', 'handoff_edit', 'handoff_get', 'handoff_send', 'looks_done_confirm', 'looks_done_not_yet', 'nudge', 'nudge_decide', 'person_owed', 'person_phone', 'quick_add', 'set_status', 'update']),
  goals: group('goals', ['add_to_cycle', 'close', 'detail', 'get', 'set_status', 'toggle_habit', 'update']),
  chats: group('chats', ['close_item', 'get', 'make_task']),
  someday: group('someday', ['create']),
  calendar: group('calendar', ['add_note', 'delete_event', 'delete_note', 'entry', 'get', 'hide_event', 'note_to_task', 'set_key_date', 'update_note']),
  people: group('people', ['options']),
  tools: group('tools', ['people_add']),
  pages: group('pages', ['get']),
  dashboard: group('dashboard', ['list']),
  rules: group('rules', ['change']),
  vault: group('vault', ['add_person', 'get', 'save', 'set_file']),
}
