// Every server call the Settings screens make (areas, members, the calendar, connections, Reset, the guide and the skill
// page). A component calls these, never `api(` directly.
import { group } from '@/data/call'

export const settingsData = {
  area: group('area', ['tree']),
  settings: group('settings', ['area_open_work', 'create_space', 'find_users', 'focus_offers', 'get', 'reorder', 'save', 'save_item', 'set_agent_vault', 'set_ai_key', 'set_ai_price', 'set_feature_cap', 'set_member', 'set_space_ask']),
  onboarding: group('onboarding', ['add_first_things', 'reset', 'save_you']),
  gcal: group('gcal', ['calendars', 'connect', 'disconnect', 'set_read', 'set_write', 'state', 'sync']),
  connections: group('connections', ['import_status', 'start_import']),
  reset: group('reset', ['apply_batch', 'decide', 'get', 'next_item', 'undo']),
  ask: group('ask', ['status']),
  context: group('context', ['card']),
  library: group('library', ['get']),
  skills: group('skills', ['accept_update', 'detail', 'rollback', 'run_log', 'save', 'set_active', 'test']),
}
