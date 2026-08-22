const SCOPE_PATH = new URL(self.registration.scope).pathname;
const SCOPE_KEY = SCOPE_PATH.replace(/[^a-z0-9]+/giu, "-").replace(/^-+|-+$/gu, "") || "root";
const IS_PREVIEW_SCOPE = /\/preview\/$/u.test(SCOPE_PATH);
const CACHE_NAMESPACE = IS_PREVIEW_SCOPE ? "rlm-research-planner-preview" : "rlm-research-planner-pwa";
const CACHE_PREFIX = `${CACHE_NAMESPACE}-${SCOPE_KEY}-`;
const LEGACY_CACHE_PREFIX = "rlm-research-planner-pwa-v";
const CACHE_NAME = `${CACHE_PREFIX}v0.1.9-b1`;
const APP_SHELL = [
  "./", "./index.html", "./styles.css?v=0.1.9-b1", "./manifest.webmanifest", "./icons/app-icon.svg",
  "./src/app.js?v=0.1.9-b1", "./src/catalog.js?v=0.1.9-b1", "./src/planning.js?v=0.1.9-b1", "./src/castle-planning.js?v=0.1.9-b1", "./src/talent-planning.js?v=0.1.9-b1", "./src/state.js?v=0.1.9-b1", "./src/language-pack.js?v=0.1.9-b1", "./src/paid-value.js?v=0.1.9-b1", "./src/speedup-inventory.js?v=0.1.9-b1", "./src/resource-format.js?v=0.1.9-b1", "./src/tree-layout.js?v=0.1.9-b1", "./src/tree-zoom.js?v=0.1.9-b1",
  "./data/research-dataset/manifest.json?v=0.1.9-b1", "./data/i18n/manifest.json?v=0.1.9-b1",
  "./data/buildings/castle_catalog.json?v=0.1.9-b1", "./data/talents/catalog.json?v=0.1.9-b1",
];

async function manifestAssets() {
  const [researchResponse, localeResponse] = await Promise.all([
    fetch("./data/research-dataset/manifest.json?v=0.1.9-b1", { cache: "reload" }),
    fetch("./data/i18n/manifest.json?v=0.1.9-b1", { cache: "reload" }),
  ]);
  if (!researchResponse.ok || !localeResponse.ok) throw new Error("Data manifest could not be loaded");
  const research = await researchResponse.json();
  const locales = await localeResponse.json();
  const versioned = (root, path) => `${root}${path}?v=0.1.9-b1`;
  return [
    versioned("./data/research-dataset/", research.sources_path),
    versioned("./data/research-dataset/", research.evidence_path),
    versioned("./data/research-dataset/", research.aliases_path),
    ...(research.trees || []).map((entry) => versioned("./data/research-dataset/", entry.path)),
    ...(research.locales || []).map((entry) => versioned("./data/research-dataset/", entry.path)),
    ...(locales.locales || []).map((entry) => versioned("./data/i18n/", entry.path)),
  ];
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll([...APP_SHELL, ...await manifestAssets()].map((url) => new Request(url, { cache: "reload" })));
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => (key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME) || (!IS_PREVIEW_SCOPE && key.startsWith(LEGACY_CACHE_PREFIX))).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
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
  }).catch(async (error) => {
    const cached = await caches.match(event.request);
    if (cached) return cached;
    throw error;
  }));
});
