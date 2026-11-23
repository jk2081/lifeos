// Every server call the Library screens make (Everything, Files, People and one person). A component calls these, never
// `api(` directly.
import { group } from '@/data/call'

export const libraryData = {
  everything: group('everything', ['list']),
  counts: group('counts', ['get']),
  files: group('files', ['list']),
  people: group('people', ['get', 'list']),
}
