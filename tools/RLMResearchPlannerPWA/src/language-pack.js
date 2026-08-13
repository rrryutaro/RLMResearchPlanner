export const LANGUAGE_PACK_DOCUMENT_TYPE = "RLMResearchPlanner.language-pack";
export const LANGUAGE_PACK_SCHEMA_VERSION = 1;
export const LANGUAGE_PACK_SECTIONS = [
  "messages", "categories", "research", "buildings", "effects", "effect_labels", "effect_values",
  "resources", "talents", "talent_effects", "talent_presets", "talent_preset_descriptions",
];
export const PROTECTED_MESSAGE_KEYS = new Set(["app.disclaimer"]);
const STORAGE_KEY = "rlm-research-planner-pwa.language-packs.v1";
const LOCALE_PATTERN = /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/;
const RTL_LANGUAGES = new Set(["ar", "arc", "ckb", "dv", "fa", "he", "ks", "nqo", "ps", "sd", "syr", "ug", "ur", "yi"]);

export function normalizeLocale(value) {
  const locale = String(value || "").trim().replaceAll("_", "-");
  if (!LOCALE_PATTERN.test(locale)) throw new Error("locale must be a BCP 47 language tag such as fr-FR or ar");
  return locale.split("-").map((part, index) => {
    if (index === 0) return part.toLocaleLowerCase("en-US");
    if (part.length === 2 && /^[A-Za-z]+$/.test(part)) return part.toLocaleUpperCase("en-US");
    if (part.length === 4 && /^[A-Za-z]+$/.test(part)) return `${part[0].toLocaleUpperCase("en-US")}${part.slice(1).toLocaleLowerCase("en-US")}`;
    return part;
  }).join("-");
}

export function defaultDirection(locale) {
  return RTL_LANGUAGES.has(String(locale).split("-", 1)[0].toLocaleLowerCase("en-US")) ? "rtl" : "ltr";
}

export function selectPreferredLocale(preferredLocales, availableLocales, fallbackLocale = "en-US") {
  const available = [];
  for (const value of availableLocales || []) {
    try {
      const locale = normalizeLocale(value);
      if (!available.includes(locale)) available.push(locale);
    } catch { /* Ignore invalid installed locale identifiers. */ }
  }
  const fallback = normalizeLocale(fallbackLocale);
  if (!available.length) return fallback;

  const preferred = [];
  for (const value of preferredLocales || []) {
    try {
      const locale = normalizeLocale(value);
      if (!preferred.includes(locale)) preferred.push(locale);
    } catch { /* Ignore invalid browser language identifiers. */ }
  }

  for (const locale of preferred) {
    const exact = available.find((candidate) => candidate.toLocaleLowerCase("en-US") === locale.toLocaleLowerCase("en-US"));
    if (exact) return exact;
    const language = locale.split("-", 1)[0].toLocaleLowerCase("en-US");
    const baseMatch = available.find((candidate) => candidate.split("-", 1)[0].toLocaleLowerCase("en-US") === language);
    if (baseMatch) return baseMatch;
  }

  return available.find((candidate) => candidate.toLocaleLowerCase("en-US") === fallback.toLocaleLowerCase("en-US")) || available[0];
}

function translatedText(value, section, key, trusted = false) {
  const sourceText = String(value && typeof value === "object" ? value.source || "" : "");
  const text = String(value && typeof value === "object" ? value.text || "" : value || "").trim();
  if (!trusted && /[<>]/u.test(text)) throw new Error(`${section}.${key}: translated text must not contain HTML markup`);
  if ([...text].some((character) => character.charCodeAt(0) < 32 && !"\t\n\r".includes(character))) throw new Error(`${section}.${key}: translated text contains a control character`);
  if (text.length > 20000) throw new Error(`${section}.${key}: translated text is too long`);
  if (section === "messages" && text && sourceText) {
    const placeholders = (input) => [...input.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map((match) => match[1]).sort();
    if (JSON.stringify(placeholders(text)) !== JSON.stringify(placeholders(sourceText))) {
      throw new Error(`${section}.${key}: translated text must keep the source placeholders`);
    }
  }
  return text;
}

export function languagePackFromPayload(raw, { trusted = false } = {}) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("language pack must be a JSON object");
  if (raw.document_type !== LANGUAGE_PACK_DOCUMENT_TYPE) throw new Error("unsupported language pack document_type");
  if (Number(raw.schema_version) !== LANGUAGE_PACK_SCHEMA_VERSION) throw new Error("unsupported language pack schema_version");
  const locale = normalizeLocale(raw.locale);
  const direction = String(raw.direction || defaultDirection(locale)).trim().toLocaleLowerCase("en-US");
  if (!new Set(["ltr", "rtl"]).has(direction)) throw new Error("direction must be ltr or rtl");
  const name = String(raw.name || locale).trim();
  if (!name || name.length > 100) throw new Error("name is required and must be at most 100 characters");
  const sections = {};
  for (const section of LANGUAGE_PACK_SECTIONS) {
    const source = raw[section] || {};
    if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error(`${section} must be an object`);
    sections[section] = Object.fromEntries(Object.entries(source).flatMap(([rawKey, value]) => {
      const key = String(rawKey).trim();
      if (!key || key.length > 300) throw new Error(`${section} contains an invalid key`);
      if (!trusted && section === "messages" && PROTECTED_MESSAGE_KEYS.has(key)) return [];
      const text = translatedText(value, section, key, trusted);
      return text ? [[key, text]] : [];
    }));
  }
  return {
    locale,
    name,
    direction,
    fallbackLocale: normalizeLocale(raw.fallback_locale || "en-US"),
    author: String(raw.author || "").trim().slice(0, 200),
    license: String(raw.license || "").trim().slice(0, 200),
    datasetId: String(raw.catalog_dataset_id || "").trim().slice(0, 200),
    effectSeparator: Object.hasOwn(raw, "effect_separator") ? String(raw.effect_separator ?? "").slice(0, 20) : null,
    sections,
    source: raw,
  };
}

export function loadLanguagePacks(storage = localStorage) {
  try {
    const values = JSON.parse(storage.getItem(STORAGE_KEY) || "[]");
    return Object.fromEntries((Array.isArray(values) ? values : []).flatMap((raw) => {
      try { const pack = languagePackFromPayload(raw); return [[pack.locale, pack]]; }
      catch { return []; }
    }));
  } catch { return {}; }
}

function saveLanguagePacks(packs, storage) {
  storage.setItem(STORAGE_KEY, JSON.stringify(Object.values(packs).map((pack) => pack.source)));
}

export function installLanguagePack(raw, storage = localStorage) {
  const pack = languagePackFromPayload(raw);
  const packs = loadLanguagePacks(storage);
  packs[pack.locale] = pack;
  saveLanguagePacks(packs, storage);
  return pack;
}

export function removeLanguagePack(locale, storage = localStorage) {
  const normalized = normalizeLocale(locale);
  const packs = loadLanguagePacks(storage);
  if (!packs[normalized]) return false;
  delete packs[normalized];
  saveLanguagePacks(packs, storage);
  return true;
}

export function packText(pack, section, key, fallback = "") {
  return String(pack?.sections?.[section]?.[key] || fallback);
}

const entry = (source) => ({ source: String(source || ""), text: "" });

export function languagePackTemplate({ catalog, castleCatalog, talentCatalog, messages, fallbackPack = null }) {
  const categories = Object.fromEntries(catalog.categories.map((category) => [category.id, entry(catalog.sourceCategoryTitle(category, "en-US"))]));
  const research = Object.fromEntries([...catalog.nodes.values()].map((node) => [node.id, entry(catalog.sourceNodeName(node, "en-US"))]));
  const effects = Object.fromEntries([...catalog.nodes.values()].filter((node) => node.effectLabel).map((node) => [node.id, entry(node.effectLabel)]));
  const buildings = Object.fromEntries(castleCatalog.order.map((buildingId) => [buildingId, entry(castleCatalog.sourceBuildingName(buildingId, "en-US"))]));
  for (const [key, value] of Object.entries(fallbackPack?.sections?.buildings || {})) {
    if (!Object.hasOwn(buildings, key)) buildings[key] = entry(value);
  }
  const resources = Object.fromEntries(Object.entries(messages).filter(([key]) => key.startsWith("resource.")).map(([key, value]) => [key.slice("resource.".length), entry(value)]));
  const talents = Object.fromEntries([...(talentCatalog?.talents?.values?.() || [])].map((talent) => [talent.id, entry(talentCatalog.talentName(talent, "en-US"))]));
  const talentEffects = Object.fromEntries([...(talentCatalog?.talents?.values?.() || [])].map((talent) => [talent.id, entry(talentCatalog.effectName(talent, "en-US"))]));
  const talentPresets = Object.fromEntries((talentCatalog?.presets || []).map((preset) => [preset.id, entry(talentCatalog.presetName(preset, "en-US"))]));
  const talentPresetDescriptions = Object.fromEntries((talentCatalog?.presets || []).map((preset) => [preset.id, entry(talentCatalog.presetDescription(preset, "en-US"))]));
  return {
    document_type: LANGUAGE_PACK_DOCUMENT_TYPE,
    schema_version: LANGUAGE_PACK_SCHEMA_VERSION,
    locale: "xx",
    name: "New language",
    direction: "ltr",
    fallback_locale: "en-US",
    author: "",
    license: "",
    catalog_dataset_id: catalog.datasetId || "",
    effect_separator: " ",
    messages: Object.fromEntries(Object.entries(messages).filter(([key]) => !PROTECTED_MESSAGE_KEYS.has(key)).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => [key, entry(value)])),
    categories,
    research,
    buildings,
    effects,
    effect_labels: Object.fromEntries(Object.entries(fallbackPack?.sections?.effect_labels || {}).map(([key, value]) => [key, entry(value)])),
    effect_values: Object.fromEntries(Object.entries(fallbackPack?.sections?.effect_values || {}).map(([key, value]) => [key, entry(value)])),
    resources,
    talents,
    talent_effects: talentEffects,
    talent_presets: talentPresets,
    talent_preset_descriptions: talentPresetDescriptions,
  };
}

export function localeManifestFromPayload(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("locale manifest must be a JSON object");
  if (raw.document_type !== "RLMResearchPlanner.locale-manifest" || Number(raw.schema_version) !== 1) throw new Error("unsupported locale manifest");
  const seen = new Set();
  const locales = (Array.isArray(raw.locales) ? raw.locales : []).map((entry) => {
    const locale = normalizeLocale(entry?.locale);
    if (seen.has(locale)) throw new Error(`duplicate bundled locale: ${locale}`);
    seen.add(locale);
    const name = String(entry?.name || "").trim();
    const direction = String(entry?.direction || defaultDirection(locale)).trim().toLocaleLowerCase("en-US");
    const path = String(entry?.path || "").trim();
    if (!name || name.length > 100) throw new Error(`${locale}: locale name is invalid`);
    if (!new Set(["ltr", "rtl"]).has(direction)) throw new Error(`${locale}: direction must be ltr or rtl`);
    if (!path || /[\\/]/u.test(path) || path === "." || path === "..") throw new Error(`${locale}: locale path is invalid`);
    return { locale, name, direction, path };
  });
  if (!locales.length) throw new Error("locale manifest must register at least one locale");
  const fallbackLocale = normalizeLocale(raw.fallback_locale || "en-US");
  if (!seen.has(fallbackLocale)) throw new Error("locale manifest fallback is not registered");
  return { fallbackLocale, locales, byLocale: Object.fromEntries(locales.map((entry) => [entry.locale, entry])) };
}

export async function loadBundledLanguagePacks(manifestUrl, version = "") {
  const response = await fetch(manifestUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`language manifest could not be loaded (${response.status})`);
  const manifest = localeManifestFromPayload(await response.json());
  const baseUrl = new URL(manifestUrl, globalThis.location?.href || "http://localhost/");
  const entries = await Promise.all(manifest.locales.map(async (entry) => {
    const url = new URL(entry.path, baseUrl);
    if (version) url.searchParams.set("v", version);
    const localeResponse = await fetch(url, { cache: "no-store" });
    if (!localeResponse.ok) throw new Error(`${entry.locale}: language pack could not be loaded (${localeResponse.status})`);
    const pack = languagePackFromPayload(await localeResponse.json(), { trusted: true });
    if (pack.locale !== entry.locale || pack.name !== entry.name || pack.direction !== entry.direction) throw new Error(`${entry.locale}: language pack metadata does not match its manifest entry`);
    return [entry.locale, pack];
  }));
  return { manifest, packs: Object.fromEntries(entries) };
}

export function mergeLanguagePacks(...values) {
  const packs = values.filter(Boolean);
  if (!packs.length) return null;
  const selected = packs[packs.length - 1];
  const effectSeparator = [...packs].reverse().find((pack) => pack.effectSeparator !== null && pack.effectSeparator !== undefined)?.effectSeparator ?? " ";
  return {
    ...selected,
    effectSeparator,
    sections: Object.fromEntries(LANGUAGE_PACK_SECTIONS.map((section) => [
      section,
      Object.assign({}, ...packs.map((pack) => pack.sections?.[section] || {})),
    ])),
  };
}

export function resolveLanguagePack(locale, bundledPacks, customPacks, fallbackLocale = "en-US") {
  const bundled = bundledPacks || {};
  const custom = customPacks || {};
  const layers = [];
  const visiting = new Set();
  const addLocale = (candidate) => {
    if (!candidate || visiting.has(candidate)) return;
    visiting.add(candidate);
    const selected = custom[candidate] || bundled[candidate];
    if (selected?.fallbackLocale && selected.fallbackLocale !== candidate) addLocale(selected.fallbackLocale);
    if (bundled[candidate]) layers.push(bundled[candidate]);
    if (custom[candidate]) layers.push(custom[candidate]);
  };
  addLocale(fallbackLocale);
  addLocale(locale);
  return mergeLanguagePacks(...layers);
}

export function applyDocumentLanguage(locale, direction = defaultDirection(locale)) {
  document.documentElement.lang = locale;
  document.documentElement.dir = direction;
  document.body?.setAttribute("dir", direction);
}

export function translateStatic(root, messages) {
  root.querySelectorAll("[data-i18n]").forEach((element) => {
    const value = messages[element.dataset.i18n];
    if (value) element.textContent = value;
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    const value = messages[element.dataset.i18nPlaceholder];
    if (value) element.setAttribute("placeholder", value);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((element) => {
    const value = messages[element.dataset.i18nTitle];
    if (value) element.setAttribute("title", value);
  });
  root.querySelectorAll("[data-i18n-aria]").forEach((element) => {
    const value = messages[element.dataset.i18nAria];
    if (value) element.setAttribute("aria-label", value);
  });
}
