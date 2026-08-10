export const LANGUAGE_PACK_DOCUMENT_TYPE = "RLMResearchPlanner.language-pack";
export const LANGUAGE_PACK_SCHEMA_VERSION = 1;
export const LANGUAGE_PACK_SECTIONS = ["messages", "categories", "research", "buildings", "effects", "resources"];
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

function translatedText(value, section, key) {
  const sourceText = String(value && typeof value === "object" ? value.source || "" : "");
  const text = String(value && typeof value === "object" ? value.text || "" : value || "").trim();
  if (/[<>]/u.test(text)) throw new Error(`${section}.${key}: translated text must not contain HTML markup`);
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

export function languagePackFromPayload(raw) {
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
      const text = translatedText(value, section, key);
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

export function languagePackTemplate({ catalog, castleCatalog, messages }) {
  const categories = Object.fromEntries(catalog.categories.map((category) => [category.id, entry(catalog.sourceCategoryTitle(category, "en-US"))]));
  const research = Object.fromEntries([...catalog.nodes.values()].map((node) => [node.id, entry(catalog.sourceNodeName(node, "en-US"))]));
  const effects = Object.fromEntries([...catalog.nodes.values()].filter((node) => node.effectLabel).map((node) => [node.id, entry(node.effectLabel)]));
  const buildings = Object.fromEntries(castleCatalog.order.map((buildingId) => [buildingId, entry(castleCatalog.sourceBuildingName(buildingId, "en-US"))]));
  const resources = Object.fromEntries(Object.entries(messages).filter(([key]) => key.startsWith("resource.")).map(([key, value]) => [key.slice("resource.".length), entry(value)]));
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
    messages: Object.fromEntries(Object.entries(messages).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => [key, entry(value)])),
    categories,
    research,
    buildings,
    effects,
    resources,
  };
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
