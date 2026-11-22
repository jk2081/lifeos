// Life OS service worker (issue 50), served at /life/sw.js (lifeos/pwa.py).
// 1. It caches only the app's own static files (/assets/lifeos/…). It never caches an API response, a page or a record.
// 2. It takes what other apps share to Life OS (a POST to /life/share) and keeps it in IndexedDB on this phone, then sends the
//    person to the share screen. Nothing is sent to the server from here.
const STATIC_CACHE = 'lifeos-static-v1'
const STATIC_PREFIX = '/assets/lifeos/'
const HASHED = '/assets/lifeos/frontend/assets/' // built files carry a hash in their name, so they never change
const OFFLINE_PAGE = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Life OS</title>'
  + '<body style="font:16px system-ui;padding:2rem;max-width:30rem;margin:auto"><h1 style="font-size:1.25rem">Life OS needs a connection</h1>'
  + '<p>Only capture works without one. Open Life OS again when you are back online. What you captured is kept on this phone and sent then.</p></body>'

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(STATIC_CACHE).then((c) => c.addAll(['/assets/lifeos/icons/icon-192.png', '/assets/lifeos/icons/icon-512.png'])).then(() => self.skipWaiting()))
})
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  if (req.method === 'POST' && url.pathname === '/life/share') return e.respondWith(takeShare(req))
  if (req.method !== 'GET') return
  if (url.pathname.startsWith(STATIC_PREFIX)) return e.respondWith(staticFile(req, url))
  if (req.mode === 'navigate' && url.pathname.startsWith('/life')) return e.respondWith(fetch(req).catch(() => new Response(OFFLINE_PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } })))
})

async function staticFile(req, url) {
  const cache = await caches.open(STATIC_CACHE)
  const hit = await cache.match(req)
  if (hit && url.pathname.startsWith(HASHED)) return hit
  try {
    const res = await fetch(req)
    if (res.ok && res.type === 'basic' && !res.headers.has('Set-Cookie')) await cache.put(req, res.clone())
    return res
  } catch (err) {
    if (hit) return hit
    throw err
  }
}

// ---- the share target -------------------------------------------------------------------------------------------------------
function openDb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open('lifeos-phone', 1)
    r.onupgradeneeded = () => {
      for (const s of ['queue', 'shares']) if (!r.result.objectStoreNames.contains(s)) r.result.createObjectStore(s, { keyPath: 'id' })
    }
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

async function takeShare(req) {
  const id = (self.crypto.randomUUID && self.crypto.randomUUID()) || String(Date.now()) + Math.random().toString(16).slice(2)
  try {
    const form = await req.formData()
    const files = form.getAll('files').filter((f) => f && typeof f !== 'string').map((f) => ({ name: f.name || 'shared', type: f.type, blob: f }))
    const share = { id, title: String(form.get('title') || ''), text: String(form.get('text') || ''), url: String(form.get('url') || ''), files, created: Date.now() }
    const db = await openDb()
    await new Promise((resolve, reject) => {
      const tx = db.transaction('shares', 'readwrite')
      tx.objectStore('shares').put(share)
      tx.oncomplete = resolve
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (err) {
    return Response.redirect('/life/share?failed=1', 303)
  }
  return Response.redirect('/life/share?id=' + encodeURIComponent(id), 303)
}
