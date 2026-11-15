// Upload one file to a record. Files are always private. The request is frappe-ui's own upload helper
// (Frappe's standard /api/method/upload_file), so size limits and server messages are handled as in other Frappe apps.
import { useFileUpload } from 'frappe-ui'

export function uploadFile(file, doctype, docname, fieldname, onProgress) {
  return useFileUpload().upload(file, { private: true, doctype, docname, fieldname: fieldname || undefined, onProgress })
}

export function fileKind(name = '') {
  const n = name.toLowerCase()
  if (/\.(jpe?g|png|webp|gif|bmp|heic)$/.test(n)) return 'image'
  if (/\.(mp3|m4a|wav|ogg|opus|aac|webm)$/.test(n)) return 'audio'
  if (/\.pdf$/.test(n)) return 'pdf'
  if (/\.(txt|md|csv|json)$/.test(n)) return 'text'
  return 'file'
}

export function fileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}
