// Every server call the Library screens make (Everything, Files, People and one person). A component calls these, never
// `api(` directly.
import { group } from '@/data/call'

export const libraryData = {
  everything: group('everything', ['list']),
  counts: group('counts', ['get']),
  files: group('files', ['list']),
  people: group('people', ['get', 'list']),
  pages: group('pages', ['get', 'index', 'pinned', 'pin', 'unpin', 'reorder', 'visit', 'rewrite', 'set_status', 'rename', 'merge', 'archive', 'remove_link', 'add_note', 'delete_note']),
  wiki: group('wiki', ['change', 'changes', 'create_page', 'health', 'move', 'overview', 'pages', 'undo']),
  links: group('links', ['suggest']),
  library: group('library', ['get', 'list', 'save', 'tree', 'versions']),
  search: group('search', ['query']),
  graph: group('graph', ['get']),
  someday: group('someday', ['create']),
  archive: group('archive', ['set']),
  trash: group('trash', ['delete']),
}
