const CACHE_VERSION = "v3";
const STATIC_CACHE = `inversure-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `inversure-runtime-${CACHE_VERSION}`;

const OFFLINE_URL = "/static/core/pwa/offline.html";

const PRECACHE_URLS = [
  OFFLINE_URL,
  "/static/core/pwa/manifest.json",
  "/static/core/pwa/icon-192.png",
  "/static/core/pwa/icon-512.png",
  "/static/core/pwa/push.js",
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
  const isAppApi = isSameOrigin && requestUrl.pathname.startsWith("/app/");

  if (isAppApi) {
    event.respondWith(fetch(event.request));
    return;
  }

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

self.addEventListener("push", event => {
  let data = {};
  try {
    if (event.data) data = event.data.json();
  } catch (e) {
    data = { title: "Inversure", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Inversure";
  const options = {
    body: data.body || "Tienes una nueva actualización.",
    icon: "/static/core/pwa/icon-192.png",
    badge: "/static/core/pwa/icon-192.png",
    data: { url: data.url || "/app/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/app/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url === targetUrl && "focus" in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
