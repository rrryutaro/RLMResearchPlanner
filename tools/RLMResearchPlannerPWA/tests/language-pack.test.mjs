import assert from "node:assert/strict";
import test from "node:test";

import {
  LANGUAGE_PACK_DOCUMENT_TYPE,
  defaultDirection,
  installLanguagePack,
  languagePackTemplate,
  languagePackFromPayload,
  localeManifestFromPayload,
  loadLanguagePacks,
  mergeLanguagePacks,
  normalizeLocale,
  packText,
  removeLanguagePack,
  resolveLanguagePack,
  selectPreferredLocale,
} from "../src/language-pack.js";

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
}

function payload(overrides = {}) {
  return {
    document_type: LANGUAGE_PACK_DOCUMENT_TYPE,
    schema_version: 1,
    locale: "ar",
    name: "العربية",
    direction: "rtl",
    fallback_locale: "en-US",
    messages: { "tab.tree": { source: "Research Tree", text: "شجرة الأبحاث" } },
    categories: {},
    research: { economy_construction_speed: { source: "Construction Speed", text: "سرعة البناء" } },
    buildings: {},
    effects: {},
    resources: {},
    talents: {},
    ...overrides,
  };
}

test("language pack uses the same normalized locale and RTL metadata as desktop", () => {
  const pack = languagePackFromPayload(payload({ locale: "AR_sa" }));
  assert.equal(pack.locale, "ar-SA");
  assert.equal(pack.direction, "rtl");
  assert.equal(packText(pack, "messages", "tab.tree"), "شجرة الأبحاث");
  assert.equal(packText(pack, "research", "economy_construction_speed"), "سرعة البناء");
  assert.equal(normalizeLocale("pt_br"), "pt-BR");
  assert.equal(defaultDirection("he-IL"), "rtl");
  assert.equal(defaultDirection("fr-FR"), "ltr");
});

test("initial locale follows browser preferences and installed language packs", () => {
  const available = ["ja-JP", "en-US", "ar", "fr-FR"];
  assert.equal(selectPreferredLocale(["ja-JP"], available), "ja-JP");
  assert.equal(selectPreferredLocale(["en-GB"], available), "en-US");
  assert.equal(selectPreferredLocale(["ar-SA"], available), "ar");
  assert.equal(selectPreferredLocale(["fr-CA"], available), "fr-FR");
  assert.equal(selectPreferredLocale(["de-DE"], available), "en-US");
});

test("language pack persists locally and can be removed without changing player state", () => {
  const storage = memoryStorage();
  const installed = installLanguagePack(payload(), storage);
  assert.equal(loadLanguagePacks(storage).ar.name, installed.name);
  assert.equal(removeLanguagePack("ar", storage), true);
  assert.deepEqual(loadLanguagePacks(storage), {});
});

test("language pack rejects HTML in user-provided translations", () => {
  assert.throws(
    () => languagePackFromPayload(payload({ messages: { "help.title": { source: "Help", text: "<b>Help</b>" } } })),
    /HTML/,
  );
});

test("language pack rejects changed message placeholders", () => {
  assert.throws(
    () => languagePackFromPayload(payload({
      messages: { "plan.count": { source: "{count} research tasks", text: "Research tasks: {total}" } },
    })),
    /placeholders/,
  );
});

test("language pack cannot override or export the official disclaimer", () => {
  const pack = languagePackFromPayload(payload({
    messages: {
      "tab.tree": { source: "Research Tree", text: "شجرة الأبحاث" },
      "app.disclaimer": { source: "Official disclaimer", text: "Replacement disclaimer" },
    },
  }));
  assert.equal(packText(pack, "messages", "app.disclaimer"), "");

  const template = languagePackTemplate({
    catalog: { categories: [], nodes: new Map(), datasetId: "test" },
    castleCatalog: { order: [] },
    talentCatalog: { talents: new Map(), talentName() { return ""; } },
    messages: { "tab.tree": "Research Tree", "app.disclaimer": "Official disclaimer" },
  });
  assert.equal(Object.hasOwn(template.messages, "app.disclaimer"), false);
});

test("locale manifest drives bundled locale registration without a coded language list", () => {
  const manifest = localeManifestFromPayload({
    document_type: "RLMResearchPlanner.locale-manifest",
    schema_version: 1,
    fallback_locale: "en-US",
    locales: [
      { locale: "en-US", name: "English", direction: "ltr", path: "en-US.json" },
      { locale: "ar", name: "العربية", direction: "rtl", path: "ar.json" },
    ],
  });
  assert.equal(manifest.fallbackLocale, "en-US");
  assert.deepEqual(manifest.locales.map((entry) => entry.locale), ["en-US", "ar"]);
  assert.equal(manifest.byLocale.ar.direction, "rtl");
});

test("custom translation overlays its bundled locale and preserves fallback text", () => {
  const english = languagePackFromPayload(payload({
    locale: "en-US", name: "English", direction: "ltr",
    messages: { "tab.tree": "Research Tree", "tab.help": "Help" },
  }), { trusted: true });
  const bundledArabic = languagePackFromPayload(payload({
    messages: { "tab.tree": "شجرة الأبحاث" },
    resources: { food: "الطعام" },
  }), { trusted: true });
  const customArabic = languagePackFromPayload(payload({
    messages: { "tab.tree": { source: "Research Tree", text: "الأبحاث" } },
    research: {},
  }));
  const resolved = resolveLanguagePack(
    "ar",
    { "en-US": english, ar: bundledArabic },
    { ar: customArabic },
    "en-US",
  );
  assert.equal(packText(resolved, "messages", "tab.tree"), "الأبحاث");
  assert.equal(packText(resolved, "messages", "tab.help"), "Help");
  assert.equal(packText(resolved, "resources", "food"), "الطعام");
  assert.equal(mergeLanguagePacks(english, bundledArabic).direction, "rtl");
});

test("arbitrary regional locale resolves to an installed base-language pack", () => {
  const english = languagePackFromPayload(payload({
    locale: "en-US", name: "English", direction: "ltr",
    messages: { "tab.tree": "Research Tree", "tab.help": "Help" },
  }), { trusted: true });
  const french = languagePackFromPayload(payload({
    locale: "fr-FR", name: "Français", direction: "ltr", fallback_locale: "en-US",
    messages: { "tab.tree": { source: "Research Tree", text: "Recherches" } },
    research: {},
  }));
  const selected = selectPreferredLocale(["fr-CA"], ["en-US", "fr-FR"], "en-US");
  const resolved = resolveLanguagePack(selected, { "en-US": english }, { "fr-FR": french }, "en-US");
  assert.equal(selected, "fr-FR");
  assert.equal(packText(resolved, "messages", "tab.tree"), "Recherches");
  assert.equal(packText(resolved, "messages", "tab.help"), "Help");
});
