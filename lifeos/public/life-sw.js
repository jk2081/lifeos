// Life OS service worker (issue 50), served at /life/sw.js (lifeos/web/pwa.py).
// 1. It caches only the app's own static files (/assets/lifeos/…). It never caches an API response, a page or a record.
// 2. It takes what other apps share to Life OS (a POST to /life/share) and keeps it in IndexedDB on this phone, then sends the
//    person to the share screen. Nothing is sent to the server from here.
const STATIC_CACHE = 'lifeos-static-v1'
const STATIC_PREFIX = '/assets/lifeos/'
const HASHED = '/assets/lifeos/frontend/assets/' // built files carry a hash in their name, so they never change
// Issue 90: a page that fails to load shows one of two pages, in the app's colours (light and dark follow the system, as the app does).
// No connection (the device is offline): the capture note. The server does not answer (the device is online): it retries every 5 seconds
// and loads the page by itself; after 2 minutes it adds Try again.
const PAGE_HEAD = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>Life OS</title>'
  + '<style>body{margin:0;font:16px/1.5 system-ui,sans-serif;padding:2rem;background:#fff;color:#171717}main{max-width:30rem;margin:12vh auto 0}'
  + 'h1{font-size:1.25rem;margin:0 0 .75rem}p{margin:.5rem 0;color:#525252}button{margin-top:1rem;font:inherit;padding:.5rem 1rem;border-radius:.5rem;border:1px solid #d4d4d4;background:#171717;color:#fff;cursor:pointer}'
  + '@media(prefers-color-scheme:dark){body{background:#161616;color:#ededed}p{color:#a3a3a3}button{background:#ededed;color:#171717;border-color:#404040}}</style>'
const OFFLINE_PAGE = PAGE_HEAD + '<body><main data-offline-page="no-connection"><h1>Life OS needs a connection</h1>'
  + '<p>Only capture works without one. Open Life OS again when you are back online. What you captured is kept on this device and sent then.</p></main></body>'
const NOT_RESPONDING_PAGE = PAGE_HEAD + '<body><main data-offline-page="not-responding"><h1>Life OS is not responding right now. Trying again…</h1>'
  + '<p data-keeps-happening hidden>If this keeps happening, the server may be down.</p><button data-try-again hidden onclick="location.reload()">Try again</button></main>'
  + '<script>(function(){var t0=Date.now();function ok(r){return r.status<502||r.status>504}'
  + 'function go(){fetch(location.href,{cache:"no-store",headers:{"X-Life-Retry":"1"}}).then(function(r){if(ok(r))location.reload()}).catch(function(){})}'
  + 'setInterval(function(){go();if(Date.now()-t0>=120000){document.querySelector("[data-try-again]").hidden=false;document.querySelector("[data-keeps-happening]").hidden=false}},5000)})()</script></body>'
const html = (body) => new Response(body, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } })
async function page(req) {
  try {
    const res = await fetch(req)
    if (res.status < 502 || res.status > 504) return res
  } catch (err) { /* handled below */ }
  return html(self.navigator.onLine ? NOT_RESPONDING_PAGE : OFFLINE_PAGE)
}

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
  if (req.mode === 'navigate' && url.pathname.startsWith('/life')) return e.respondWith(page(req))
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
