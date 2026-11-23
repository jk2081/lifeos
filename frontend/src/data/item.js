// Every server call the item screens make (the item page, the record pane and the pane of each kind of record).
// A component calls these, never `api(` directly.
import { group } from '@/data/call'

export const itemData = {
  inbox: group('inbox', ['get', 'item_page', 'retry']),
  sources: group('sources', ['made_from']),
  review: group('review', ['decide', 'update_payload']),
  meta: group('meta', ['proposal_schema']),
  archive: group('archive', ['restore', 'set']),
  trash: group('trash', ['delete']),
  library: group('library', ['get', 'set_sensitive']),
  wiki: group('wiki', ['changes', 'move']),
  tasks: group('tasks', ['carry_forward', 'get', 'quick_add', 'set_status', 'update']),
  goals: group('goals', ['add_to_cycle', 'close', 'detail', 'get', 'set_status', 'update']),
  chats: group('chats', ['close_item', 'get', 'make_task']),
  someday: group('someday', ['create']),
  calendar: group('calendar', ['delete_event', 'entry', 'get']),
  people: group('people', ['options']),
  vault: group('vault', ['add_person', 'get', 'save', 'set_file']),
}
