// Every server call the Brain screens make (Needs you, Activity, Sources, Skills and the lessons). A component calls these,
// never `api(` directly.
import { group } from '@/data/call'

export const brainData = {
  agentPage: group('agent_page', ['decide', 'delete_fact', 'edit_fact', 'get', 'pause_job', 'rename', 'set_ability', 'set_area', 'undo']),
  brain: group('brain', ['activity', 'needs_you']),
  inbox: group('inbox', ['file_myself', 'list', 'retry']),
  review: group('review', ['decide', 'decide_all']),
  context: group('context', ['decide']),
  lessons: group('lessons', ['accept', 'reject', 'remove']),
  connections: group('connections', ['gmail_connect', 'gmail_finish', 'gmail_remove', 'gmail_setup', 'microsoft_connect', 'microsoft_finish', 'microsoft_setup', 'save', 'sources']),
  settings: group('settings', ['get', 'save']),
  skills: group('skills', ['create', 'overview', 'save_auto_file', 'set_active']),
  old_items: group('old_items', ['apply', 'suggested', 'undo']),
  insights: group('insights', ['act', 'list', 'refresh']),
  reset: group('reset', ['undo']),
  mail: group('mail', ['file']),
  ask: group('ask', ['delete_thread', 'status', 'threads']),
  sources: group('sources', ['list', 'refile']),
  sourcePage: group('source_page', ['file_it', 'get', 'go_back', 'groups', 'save_rules', 'save_settings', 'teach', 'try_it']),
}
