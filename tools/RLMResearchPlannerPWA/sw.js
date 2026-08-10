const CACHE_NAME = "rlm-research-planner-pwa-v0.0.13-b1";
const APP_SHELL = [
  "./", "./index.html", "./styles.css?v=0.0.13-b1", "./manifest.webmanifest", "./icons/app-icon.svg",
  "./src/app.js?v=0.0.13-b1", "./src/catalog.js?v=0.0.13-b1", "./src/planning.js?v=0.0.13-b1", "./src/castle-planning.js?v=0.0.13-b1", "./src/state.js?v=0.0.13-b1", "./src/resource-format.js?v=0.0.13-b1", "./src/tree-layout.js?v=0.0.13-b1", "./src/tree-zoom.js?v=0.0.13-b1", "./data/research/catalog.json", "./data/buildings/castle_catalog.json", "./data/i18n/ja-JP.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).then(async (response) => {
      if (response.ok) await caches.open(CACHE_NAME).then((cache) => cache.put("./index.html", response.clone()));
      return response;
    }).catch(() => caches.match("./index.html")));
    return;
  }
  event.respondWith(fetch(event.request).then(async (response) => {
    if (response.ok && new URL(event.request.url).origin === self.location.origin) await caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
    return response;
  }).catch(async () => (await caches.match(event.request)) || caches.match("./index.html")));
});
