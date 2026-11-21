// The ladder (issue 26): the person's level, from lifeos.api.meta.setup_level (cached on the server for a few minutes).
import { reactive } from 'vue'
import { api } from './api'

export const ladder = reactive({ loaded: false, level: 1, of: 6, complete: false, dismissed: false, next: null, levels: [], done: [] })

export async function loadLadder() {
  try {
    Object.assign(ladder, await api('meta.setup_level'), { loaded: true })
  } catch (e) { /* the card is not worth an error */ }
}

export async function dismissLadder(undo = false) {
  Object.assign(ladder, await api('meta.dismiss_setup', { undo: undo ? 1 : 0 }), { loaded: true })
}
