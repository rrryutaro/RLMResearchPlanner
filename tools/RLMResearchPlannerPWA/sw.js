const SCOPE_PATH = new URL(self.registration.scope).pathname;
const SCOPE_KEY = SCOPE_PATH.replace(/[^a-z0-9]+/giu, "-").replace(/^-+|-+$/gu, "") || "root";
const IS_PREVIEW_SCOPE = /\/preview\/$/u.test(SCOPE_PATH);
const CACHE_NAMESPACE = IS_PREVIEW_SCOPE ? "rlm-research-planner-preview" : "rlm-research-planner-pwa";
const CACHE_PREFIX = `${CACHE_NAMESPACE}-${SCOPE_KEY}-`;
const LEGACY_CACHE_PREFIX = "rlm-research-planner-pwa-v";
const CACHE_NAME = `${CACHE_PREFIX}v0.1.2-b1`;
const APP_SHELL = [
  "./", "./index.html", "./styles.css?v=0.1.2-b1", "./manifest.webmanifest", "./icons/app-icon.svg",
  "./src/app.js?v=0.1.2-b1", "./src/catalog.js?v=0.1.2-b1", "./src/planning.js?v=0.1.2-b1", "./src/castle-planning.js?v=0.1.2-b1", "./src/state.js?v=0.1.2-b1", "./src/language-pack.js?v=0.1.2-b1", "./src/paid-value.js?v=0.1.2-b1", "./src/speedup-inventory.js?v=0.1.2-b1", "./src/resource-format.js?v=0.1.2-b1", "./src/tree-layout.js?v=0.1.2-b1", "./src/tree-zoom.js?v=0.1.2-b1",
  "./data/research-dataset/manifest.json?v=0.1.2-b1", "./data/research-dataset/sources.json?v=0.1.2-b1", "./data/research-dataset/evidence.json?v=0.1.2-b1", "./data/research-dataset/id-aliases.json?v=0.1.2-b1",
  "./data/research-dataset/locales/ja-JP.json?v=0.1.2-b1", "./data/research-dataset/locales/en-US.json?v=0.1.2-b1",
  "./data/research-dataset/trees/economy.json?v=0.1.2-b1", "./data/research-dataset/trees/defense.json?v=0.1.2-b1", "./data/research-dataset/trees/military.json?v=0.1.2-b1", "./data/research-dataset/trees/monster_hunt.json?v=0.1.2-b1", "./data/research-dataset/trees/upgrade_defenses.json?v=0.1.2-b1", "./data/research-dataset/trees/upgrade_military.json?v=0.1.2-b1", "./data/research-dataset/trees/army_leadership.json?v=0.1.2-b1", "./data/research-dataset/trees/military_command.json?v=0.1.2-b1", "./data/research-dataset/trees/familiars.json?v=0.1.2-b1", "./data/research-dataset/trees/familiar_battles.json?v=0.1.2-b1", "./data/research-dataset/trees/sigils.json?v=0.1.2-b1", "./data/research-dataset/trees/wonder_battles.json?v=0.1.2-b1", "./data/research-dataset/trees/gear.json?v=0.1.2-b1", "./data/research-dataset/trees/advanced_wonder_battles.json?v=0.1.2-b1", "./data/research-dataset/trees/mana_awakening.json?v=0.1.2-b1", "./data/research-dataset/trees/guild_duel.json?v=0.1.2-b1",
  "./data/buildings/castle_catalog.json?v=0.1.2-b1", "./data/i18n/ja-JP.json?v=0.1.2-b1", "./data/i18n/en-US.json?v=0.1.2-b1",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL.map((url) => new Request(url, { cache: "reload" })))).then(() => self.skipWaiting()));
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
