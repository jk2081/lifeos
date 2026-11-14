// Upload one file to a record with Frappe's standard endpoint. Files are always private.
export async function uploadFile(file, doctype, docname, fieldname) {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('is_private', '1')
  body.append('doctype', doctype)
  body.append('docname', docname)
  if (fieldname) body.append('fieldname', fieldname)
  const res = await fetch('/api/method/upload_file', {
    method: 'POST', body, headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '', Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`Upload of ${file.name} failed (${res.status}).`)
  return (await res.json()).message
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
