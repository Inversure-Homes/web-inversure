const CACHE_VERSION = "v1";
const STATIC_CACHE = `inversure-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `inversure-runtime-${CACHE_VERSION}`;

const OFFLINE_URL = "/static/core/pwa/offline.html";

const PRECACHE_URLS = [
  OFFLINE_URL,
  "/static/core/pwa/manifest.json",
  "/static/core/pwa/icon-192.png",
  "/static/core/pwa/icon-512.png",
  "/static/core/style.css",
  "/static/landing/landing.css",
  "/static/landing/landing-card.css",
  "/static/landing/landing.js",
  "/static/core/proyecto.js"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => ![STATIC_CACHE, RUNTIME_CACHE].includes(key)).map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;

  const requestUrl = new URL(event.request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(RUNTIME_CACHE).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request).then(r => r || caches.match(OFFLINE_URL)))
    );
    return;
  }

  if (isSameOrigin) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
        const clone = response.clone();
        caches.open(RUNTIME_CACHE).then(cache => cache.put(event.request, clone));
        return response;
      }))
    );
  }
});
