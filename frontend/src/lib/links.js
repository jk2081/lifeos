// Backlinks of a record: records that link to it with [[Title]], plus records tied to it by a field.
import { api } from './api'

export async function loadBacklinks(doctype, name) {
  try {
    return await api('links.backlinks', { doctype, name })
  } catch (e) {
    return []
  }
}
