import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { currentEffect, loadJsonResource, normalizeCatalog } from "../src/catalog.js";
import { TECHNOLABE_CAPACITY_SECONDS, adjustedTime, afterGuildHelps, createPlan, defaultTargetLevel, formatDuration, isResearchConnectionUnlocked, isTechnolabeRecommended, paginateItems, researchLevelsAfterPlan, shortestAvailable, technolabeUsage } from "../src/planning.js";
import { RESOURCE_KEYS, backupPayload, defaultState, guildHelpCount, hasSavedState, loadState, maxGuildHelpsForCastle, mergeResearchDirectiveTasks, playerStorageKey, researchDirectiveFromPayload, researchDirectivePayload, saveState, stateFromBackup } from "../src/state.js";
import { formatResourceAmount } from "../src/resource-format.js";
import { compactExplicitRowSlots, explicitTreeLayout, visibleTreeLayout } from "../src/tree-layout.js";
import { clampTreeZoom, fitTreeZoom } from "../src/tree-zoom.js";
import { CASTLE_RESOURCE_KEYS, buildingLevelsAfterCastleStep, createCastlePlan, minimumBuildingLevels, minimumGemsForAmount, normalizeCastleCatalog } from "../src/castle-planning.js";
import { languagePackFromPayload } from "../src/language-pack.js";

async function loadGeneratedResearchDocuments() {
  const root = new URL("../data/research-dataset/", import.meta.url);
  const readJson = async (path) => JSON.parse(await readFile(new URL(path, root), "utf8"));
  const manifest = await readJson("manifest.json");
  return {
    manifest,
    sources: await readJson(manifest.sources_path),
    evidence: await readJson(manifest.evidence_path),
    aliases: await readJson(manifest.aliases_path),
    trees: Object.fromEntries(await Promise.all((manifest.trees || []).map(async (entry) => [entry.id, await readJson(entry.path)]))),
    locales: Object.fromEntries(await Promise.all((manifest.locales || []).map(async (entry) => [entry.locale, await readJson(entry.path)]))),
  };
}

const researchDocuments = await loadGeneratedResearchDocuments();
const catalog = normalizeCatalog(researchDocuments);
const developmentDesktopRoot = new URL("../../RLMResearchPlanner/", import.meta.url);
const publicDesktopRoot = new URL("../../../", import.meta.url);
const desktopRoot = existsSync(fileURLToPath(new URL("pyproject.toml", developmentDesktopRoot)))
  ? developmentDesktopRoot
  : publicDesktopRoot;
const desktopUrl = (path) => new URL(path, desktopRoot);
const castleRaw = JSON.parse(await readFile(new URL("../data/buildings/castle_catalog.json", import.meta.url), "utf8"));
const castleCatalog = normalizeCastleCatalog(castleRaw);
const pwaLocale = JSON.parse(await readFile(new URL("../data/i18n/ja-JP.json", import.meta.url), "utf8"));
const desktopLocale = JSON.parse(await readFile(desktopUrl("resources/i18n/ja-JP.json"), "utf8"));
const desktopEnglishLocale = JSON.parse(await readFile(desktopUrl("resources/i18n/en-US.json"), "utf8"));
const desktopJapaneseLocale = desktopLocale;
const indexHtml = await readFile(new URL("../index.html", import.meta.url), "utf8");
const appSource = await readFile(new URL("../src/app.js", import.meta.url), "utf8");
const planningSource = await readFile(new URL("../src/planning.js", import.meta.url), "utf8");
const stylesSource = await readFile(new URL("../styles.css", import.meta.url), "utf8");
const serviceWorkerSource = await readFile(new URL("../sw.js", import.meta.url), "utf8");
const webManifest = JSON.parse(await readFile(new URL("../manifest.webmanifest", import.meta.url), "utf8"));
const versionSource = await readFile(new URL("../version.py", import.meta.url), "utf8");
const packageMetadata = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const japaneseDataGuide = await readFile(desktopUrl("docs/ja-JP/data-files.md"), "utf8");
const englishDataGuide = await readFile(desktopUrl("docs/en-US/data-files.md"), "utf8");
const japaneseTranslationGuide = await readFile(desktopUrl("docs/ja-JP/translation-files.md"), "utf8");
const englishTranslationGuide = await readFile(desktopUrl("docs/en-US/translation-files.md"), "utf8");
const communityTranslationGuide = await readFile(desktopUrl("translations/community/README.md"), "utf8");
const japaneseCommunityTranslationGuide = await readFile(desktopUrl("translations/community/README.ja.md"), "utf8");
const publicReadme = await readFile(desktopUrl("README.md"), "utf8");
const englishReadme = await readFile(desktopUrl("README.en.md"), "utf8");
const securityPolicy = await readFile(desktopUrl("SECURITY.md"), "utf8");
const languagePackSchema = JSON.parse(await readFile(desktopUrl("schemas/language-pack.schema.json"), "utf8"));

test("public version omits the internal asset build number", () => {
  const publicVersion = packageMetadata.version;
  const buildNumber = versionSource.match(/^__build__\s*=\s*(\d+)$/mu)?.[1];
  const assetVersion = `${publicVersion}-b${buildNumber}`;
  assert.equal(publicVersion, "0.1.4");
  assert.doesNotMatch(publicVersion, /\+b\d+$/u);
  assert.match(versionSource, new RegExp(`__build__\\s*=\\s*${buildNumber}\\b`));
  assert.match(appSource, new RegExp(`RELEASE_VERSION\\s*=\\s*"${publicVersion.replaceAll(".", "\\.")}"`));
  assert.match(appSource, new RegExp(`DEVELOPMENT_BUILD\\s*=\\s*${buildNumber}\\b`));
  assert.match(appSource, /const APP_VERSION = RELEASE_VERSION;/);
  assert.doesNotMatch(appSource, /\$\{RELEASE_VERSION\}\+b/u);
  assert.match(appSource, /IS_PREVIEW\s*=\s*\/\\\/preview/);
  assert.match(appSource, /classList\.toggle\("is-preview", IS_PREVIEW\)/);
  assert.match(appSource, /document\.title\s*=\s*`RLM Research Planner \$\{versionLabel\}`/);
  assert.match(appSource, /pwa\.preview_version/u);
  assert.match(indexHtml, /v0\.1\.4 Preview/u);
  assert.match(indexHtml, new RegExp(`id="header-version"[^>]*data-i18n-title="pwa\\.version"[^>]*>v${publicVersion.replaceAll(".", "\\.")}<\\/span>`));
  assert.match(stylesSource, /\.app-version-badge\.is-preview/);
  assert.match(serviceWorkerSource, /rlm-research-planner-preview/);
  assert.match(serviceWorkerSource, /key\.startsWith\(CACHE_PREFIX\)/);
  for (const source of [indexHtml, appSource, planningSource, serviceWorkerSource]) {
    assert.match(source, new RegExp(assetVersion.replaceAll(".", "\\.")));
    assert.doesNotMatch(source, /b\d+-\d+/);
  }
});

test("preview version and player data stay separate from production", () => {
  const productionKey = playerStorageKey("/RLMResearchPlanner/");
  const previewKey = playerStorageKey("/RLMResearchPlanner/preview/");
  assert.notEqual(productionKey, previewKey);
  const production = defaultState();
  production.settings.vipLevel = 11;
  const values = new Map([[productionKey, JSON.stringify(production)]]);
  const storage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
  assert.equal(hasSavedState(storage, "/RLMResearchPlanner/preview/"), true);
  const preview = loadState(storage, "/RLMResearchPlanner/preview/");
  assert.equal(preview.settings.vipLevel, 11);
  preview.settings.vipLevel = 12;
  saveState(preview, storage, "/RLMResearchPlanner/preview/");
  assert.equal(JSON.parse(values.get(productionKey)).settings.vipLevel, 11);
  assert.equal(JSON.parse(values.get(previewKey)).settings.vipLevel, 12);
});

test("first launch is distinguishable from saved player data", () => {
  const storage = { getItem: () => null };
  assert.equal(hasSavedState(storage, "/RLMResearchPlanner/"), false);
  assert.equal(hasSavedState(storage, "/RLMResearchPlanner/preview/"), false);
});

test("owned speedups use a list and one shared add-edit form", () => {
  assert.match(indexHtml, /id="speedup-inventory-list"/u);
  assert.match(indexHtml, /id="speedup-inventory-editor"[^>]*hidden/u);
  for (const id of ["kind", "duration", "unit", "quantity", "save", "cancel", "delete"]) {
    assert.equal([...indexHtml.matchAll(new RegExp(`id="speedup-inventory-${id}"`, "gu"))].length, 1);
  }
  assert.match(appSource, /function openSpeedupInventoryEditor\(index = -1\)/u);
  assert.match(appSource, /function saveSpeedupInventoryEntry\(\)/u);
  assert.match(appSource, /row = create\("button", "speedup-inventory-row"\)/u);
  assert.match(stylesSource, /\.speedup-inventory-row\.is-selected/u);
  assert.doesNotMatch(appSource, /speedup-quantity-field/u);
});

test("paid pack contents use a list and one shared add-edit form", () => {
  assert.match(indexHtml, /id="paid-item-list"/u);
  assert.match(indexHtml, /id="paid-item-editor"[^>]*hidden/u);
  for (const id of ["kind", "name", "quantity", "duration", "unit", "gem-value", "points", "save", "cancel", "delete"]) {
    assert.equal([...indexHtml.matchAll(new RegExp(`id="paid-item-${id}"`, "gu"))].length, 1);
  }
  assert.match(appSource, /function openPaidItemEditor\(index = -1\)/u);
  assert.match(appSource, /function savePaidItem\(\)/u);
  assert.match(appSource, /"speedup-inventory-row paid-item-summary-row"/u);
  assert.doesNotMatch(appSource, /create\("article", "paid-item-row"\)/u);
});

test("speed-up simulation separates owned use, gems, and remaining time", () => {
  assert.match(indexHtml, /<details id="plan-speedup-summary" class="speedup-simulation"><\/details>/u);
  assert.match(appSource, /create\("details", "speedup-simulation castle-speedup-simulation"\)/u);
  assert.match(appSource, /speedup-owned-section/u);
  assert.match(appSource, /speedup-missing-section/u);
  assert.match(appSource, /plan\.speedup_direct_gems/u);
  assert.match(appSource, /useGemsForSpeedups/u);
  assert.match(appSource, /speedup-recommendation-breakdown/u);
  assert.match(appSource, /plan\.speedup_offer_speedups/u);
  assert.match(appSource, /plan\.speedup_offer_gems/u);
  assert.match(appSource, /plan\.speedup_offer_remaining/u);
  assert.match(stylesSource, /\.speedup-breakdown-part/u);
});

test("Japanese and English data-file and translation guides stay publishable", () => {
  assert.match(indexHtml, /id="help-files-body"/u);
  for (const locale of [pwaLocale, desktopLocale]) {
    assert.match(locale.messages["help.files.body"], /docs\/ja-JP\/data-files\.md/u);
    assert.match(locale.messages["help.files.body"], /docs\/ja-JP\/translation-files\.md/u);
  }
  for (const guide of [japaneseDataGuide, englishDataGuide]) {
    assert.match(guide, /Backup|バックアップ/u);
    assert.match(guide, /Research directive|研究指示/u);
    assert.match(guide, /Translation|翻訳/u);
  }
  for (const guide of [japaneseTranslationGuide, englishTranslationGuide]) {
    assert.match(guide, /fallback_locale/u);
    assert.match(guide, /\{count\}/u);
    assert.match(guide, /direction/u);
  }
  assert.equal(languagePackSchema.properties.document_type.const, "RLMResearchPlanner.language-pack");
  assert.deepEqual(languagePackSchema.properties.direction.enum, ["ltr", "rtl"]);
  for (const guide of [communityTranslationGuide, japaneseCommunityTranslationGuide]) {
    assert.match(guide, /BCP 47/u);
    assert.match(guide, /license|ライセンス/u);
  }
});

test("startup shows progress and postpones service worker installation until content is ready", () => {
  assert.match(indexHtml, /id="startup-loading"[^>]*role="status"/u);
  assert.match(indexHtml, /id="startup-loading-message"[^>]*>Loading…/u);
  assert.match(stylesSource, /\.startup-loading-spinner/u);
  assert.match(indexHtml, /window\.rlmMarkStartupComplete\s*=\s*\(\)\s*=>[\s\S]*startupLoading\.hidden\s*=\s*true/u);
  assert.match(indexHtml, /setTimeout\(registerServiceWorker, 0\)/u);
  assert.match(indexHtml, /if \(!hadController \|\| refreshing\) return/u);
  assert.doesNotMatch(indexHtml, /else if \("serviceWorker" in navigator\)/u);
});

test("the public README is Japanese-first and links the security policy", () => {
  assert.match(publicReadme, /^# RLMResearchPlanner\s+日本語 \| \[English\]\(README\.en\.md\)/u);
  assert.match(publicReadme, /セキュリティポリシー/u);
  assert.match(publicReadme, /raw\.githubusercontent\.com\/rrryutaro\/RLMResearchPlanner\/main\/tools\/RLMResearchPlannerPWA\/docs\/qr\.png/u);
  assert.match(publicReadme, /## 重要な注意・免責/u);
  assert.match(publicReadme, /無償の非公式ツール/u);
  assert.match(publicReadme, /ゲーム画面で確認/u);
  assert.match(englishReadme, /^# RLMResearchPlanner\s+\[日本語\]\(README\.md\) \| English/u);
  assert.match(englishReadme, /## Important notice and disclaimer/u);
  assert.match(englishReadme, /\[security policy\]\(SECURITY\.md\)/u);
  assert.match(securityPolicy, /非公開脆弱性報告/u);
  assert.match(securityPolicy, /security\/advisories\/new/u);
});

test("JSON resources retry without accepting a cached HTML document", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), cache: options?.cache });
    return {
      ok: true,
      text: async () => calls.length === 1 ? "<!doctype html>" : '{"value":1}',
    };
  };
  try {
    assert.deepEqual(await loadJsonResource("./data/example.json?v=0.1.0-b1", "テストデータ"), { value: 1 });
    assert.equal(calls.length, 2);
    assert.equal(calls[0].cache, "default");
    assert.equal(calls[1].cache, "reload");
    assert.match(calls[1].url, /[?&]reload=\d+$/u);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("resource caption updates cannot replace the decrement button label", () => {
  assert.doesNotMatch(appSource, /previousElementSibling\.textContent\s*=\s*RESOURCE_NAMES/);
  assert.match(appSource, /caption\.id\s*=\s*`resource-label-\$\{key\}`/);
  assert.match(appSource, /byId\(`resource-label-\$\{key\}`\)/);
});

test("shortest research pagination clamps pages and preserves every item", () => {
  const values = Array.from({ length: 23 }, (_unused, index) => index + 1);
  assert.deepEqual(paginateItems(values, 0, 10), {
    items: values.slice(0, 10), page: 0, pageSize: 10, totalItems: 23, totalPages: 3,
  });
  assert.deepEqual(paginateItems(values, 1, 10).items, values.slice(10, 20));
  assert.deepEqual(paginateItems(values, 99, 10), {
    items: values.slice(20), page: 2, pageSize: 10, totalItems: 23, totalPages: 3,
  });
  assert.deepEqual(paginateItems([], 4, 20), {
    items: [], page: 0, pageSize: 20, totalItems: 0, totalPages: 0,
  });
  assert.match(indexHtml, /id="shortest-previous"/);
  assert.match(indexHtml, /id="shortest-page-status"/);
  assert.match(indexHtml, /id="shortest-next"/);
});

test("help exposes application, data, and third-party licenses", () => {
  assert.match(indexHtml, /data-i18n="help\.disclaimer\.title">重要な注意・免責</u);
  assert.match(indexHtml, /data-i18n="app\.disclaimer"[^>]*>[^<]*無償の非公式ツール/u);
  assert.match(indexHtml, />ライセンス・出典</);
  for (const pack of [desktopEnglishLocale, desktopJapaneseLocale]) {
    assert.match(pack.messages["help.license.body"], /href="https:\/\/github\.com\/rrryutaro\/RLMResearchPlanner\/blob\/main\/LICENSE"/);
    assert.match(pack.messages["help.license.body"], /href="https:\/\/github\.com\/rrryutaro\/RLMResearchPlanner\/blob\/main\/DATA_LICENSE\.md"/);
    assert.match(pack.messages["help.license.body"], /href="https:\/\/github\.com\/rrryutaro\/RLMResearchPlanner\/blob\/main\/licenses\/THIRD_PARTY_NOTICES\.md"/);
  }
});

test("help reports the verified game version without making it a requirement", () => {
  assert.match(indexHtml, /動作確認済みゲームバージョンはv2\.200\.309/);
  assert.match(indexHtml, /必須バージョンではなく/);
});

test("five-column source rows use the same compact four-slot layout as desktop", () => {
  assert.deepEqual(compactExplicitRowSlots([0, 1, 3, 4], 5, 4), [0, 1, 2, 3]);
  assert.deepEqual(compactExplicitRowSlots([1, 3], 5, 4), [1, 2]);
  assert.deepEqual(compactExplicitRowSlots([0, 2, 4], 5, 4), [0, 1.5, 3]);
  const military = catalog.categories.find((category) => category.id === "military");
  const layout = explicitTreeLayout(military.nodes);
  assert.equal(layout.columnCount, 4);
  assert.equal(layout.slots.get("military_intelligence_report"), 1);
  assert.equal(layout.slots.get("military_quick_maneuvers_i"), 2);
  assert.equal(layout.slots.get("military_infantry_offense_i"), 0);
  assert.equal(layout.slots.get("military_siege_attack_i"), 1);
  assert.equal(layout.slots.get("military_ranged_offense_i"), 2);
  assert.equal(layout.slots.get("military_cavalry_offense_i"), 3);

  const advancedWonder = catalog.categories.find((category) => category.id === "advanced_wonder_battles");
  const advancedLayout = explicitTreeLayout(advancedWonder.nodes);
  assert.equal(advancedLayout.slots.get("advanced_wonder_battles_infantry_durability_wonder_iii"), 0);
  assert.equal(advancedLayout.slots.get("advanced_wonder_battles_ranged_durability_wonder_iii"), 1.5);
  assert.equal(advancedLayout.slots.get("advanced_wonder_battles_cavalry_durability_wonder_iii"), 3);
});

test("a research card defaults its target to the next level", () => {
  assert.equal(defaultTargetLevel(0, 10), 1);
  assert.equal(defaultTargetLevel(7, 10), 8);
  assert.equal(defaultTargetLevel(10, 10), 10);
  assert.match(appSource, /const defaultLevel = defaultTargetLevel\(level, node\.maxLevel\)/);
  assert.match(appSource, /option\.selected = targetLevel === defaultLevel/);
});

test("tree zoom can shrink exactly to the whole-tree fit", () => {
  const category = catalog.categories[0];
  const contentWidth = 72 + category.columnCount * 250 + Math.max(0, category.columnCount - 1) * 42;
  const contentHeight = 72 + category.rowCount * 174 + Math.max(0, category.rowCount - 1) * 62;
  const fitted = fitTreeZoom(412, 360, contentWidth, contentHeight);
  assert.ok(fitted < 0.5);
  assert.ok(contentWidth * fitted <= 410);
  assert.ok(contentHeight * fitted <= 358);
  assert.equal(clampTreeZoom(0, fitted), fitted);
  assert.equal(clampTreeZoom(2, fitted), 1.5);
  assert.match(indexHtml, /id="zoom-fit"[^>]*>全体<\/button>/);
  assert.match(appSource, /event\.pointerType === "touch"/);
  assert.match(appSource, /pinch\.zoom \* distance \/ pinch\.distance/);
});

test("desktop mouse click is not captured until the tree is actually dragged", () => {
  const pointerDown = appSource.slice(appSource.indexOf('viewport.addEventListener("pointerdown"'), appSource.indexOf('viewport.addEventListener("pointermove"'));
  const mousePointerDown = pointerDown.slice(pointerDown.indexOf('if (event.pointerType === "mouse"'));
  assert.doesNotMatch(mousePointerDown, /setPointerCapture/);
  assert.match(appSource, /Math\.hypot\(dx, dy\) > 6[\s\S]*viewport\.setPointerCapture\(event\.pointerId\)/);
});

test("desktop catalog is fully available to the PWA", () => {
  assert.equal(catalog.categories.length, 16);
  assert.equal(catalog.nodes.size, 399);
  assert.equal([...catalog.nodes.values()].reduce((count, node) => count + node.levels.size, 0), 3143);
  assert.equal([...catalog.nodes.values()].reduce((count, node) => count + node.maxLevel, 0), 3385);
  assert.equal(catalog.categories.reduce((count, category) => count + category.dataStats.times, 0), 2923);
  assert.equal(catalog.categories.reduce((count, category) => count + category.dataStats.costs, 0), 3022);
  assert.equal(catalog.categoryTitle(catalog.categories[0], "ja-JP"), "経済");
  assert.equal(catalog.datasetVersion, "0.1.0");
  assert.match(indexHtml, /id="dataset-version"/u);
  assert.equal(catalog.checkedOn, "2026-08-07");
  assert.equal(catalog.categories[0].dataStats.times, 90);
  assert.deepEqual(catalog.nodes.get("sigils_helmet_sigil").levels.get(1).costs, {
    food: 8137320,
    stone: 4068660,
    timber: 4068660,
    ore: 1356220,
    gold: 3904320,
    ancient_tomes: 96,
  });
});

test("a third RTL locale changes names without changing research facts", () => {
  const arabic = structuredClone(researchDocuments.locales["en-US"]);
  arabic.locale = "ar";
  arabic.direction = "rtl";
  arabic.fallback_locale = "en-US";
  arabic.trees = { economy: "الاقتصاد" };
  arabic.research = { economy_construction_speed: "سرعة البناء" };
  arabic.metrics = {};
  const localized = normalizeCatalog({
    ...researchDocuments,
    locales: { ...researchDocuments.locales, ar: arabic },
  });
  const node = localized.nodes.get("economy_construction_speed");
  assert.equal(localized.categoryTitle(localized.categories[0], "ar"), "الاقتصاد");
  assert.equal(localized.nodeName(node, "ar"), "سرعة البناء");
  assert.equal(node.maxLevel, catalog.nodes.get(node.id).maxLevel);
  assert.deepEqual([...node.levels.entries()], [...catalog.nodes.get(node.id).levels.entries()]);
});

test("compact resource amounts use whole thousands", () => {
  assert.equal(formatResourceAmount(142_710, "short"), "142K");
  assert.equal(formatResourceAmount(999_999, "short"), "999K");
  assert.equal(formatResourceAmount(1_234_567, "short"), "1.23M");
});

test("Lunar Foundry is the one-level unlock research, not mana building stages", () => {
  const foundry = catalog.nodes.get("gear_lunar_foundry");
  assert.equal(foundry.maxLevel, 1);
  assert.equal(foundry.levels.size, 1);
  const level = foundry.levels.get(1);
  assert.equal(level.baseTimeSeconds, 13 * 86400 + 5 * 3600);
  assert.equal(level.academyLevel, 25);
  assert.equal(level.technolabeCount, 1);
  assert.deepEqual(level.requirements, [
    { researchId: "gear_bigger_infirmary_iii", level: 4 },
    { researchId: "gear_barracks_expansion_ii", level: 4 },
  ]);
});

test("category selector has a static fallback before JavaScript starts", () => {
  const markup = indexHtml.match(/<select id="category-select"[^>]*>([\s\S]*?)<\/select>/)?.[1] || "";
  assert.equal([...markup.matchAll(/<option value=/g)].length, 16);
  assert.match(indexHtml, /id="category-drawer"/);
  assert.equal([...indexHtml.matchAll(/<details class="settings-card/g)].length, 11);
  assert.match(indexHtml, /data-tab="castle"[^>]*data-i18n="tab\.castle"[^>]*>建設<\/button>/);
  assert.match(indexHtml, /id="construction-target"/);
  assert.match(indexHtml, /id="construction-selection"/);
  assert.match(indexHtml, /id="shortest-selected"/);
  assert.match(indexHtml, /id="setting-construction-speed"/);
  assert.match(indexHtml, /id="setting-construction-boost"/);
  assert.match(indexHtml, /<summary data-i18n="player\.construction_time_settings">建設時間<\/summary>/);
  assert.match(indexHtml, /<summary data-i18n="player\.research_time_settings">研究時間<\/summary>/);
  assert.ok(indexHtml.indexOf("serviceWorker.register") < indexHtml.indexOf("src=\"./src/app.js"));
  assert.match(indexHtml, /The data cannot be loaded when this HTML file is opened directly/);
  assert.match(indexHtml, /id="node-level-down"[^>]*>−<\/button>/);
  assert.match(indexHtml, /id="node-level-up"[^>]*>＋<\/button>/);
  assert.match(indexHtml, /id="complete-plan"/);
  assert.match(indexHtml, /id="register-plan"/);
  assert.match(appSource, /card\.classList\.add\("is-selected"\)/);
  assert.match(appSource, /selectedNodeId = node\.id/);
  assert.match(appSource, /function numberStepper\(input\)/);
  assert.match(stylesSource, /\.number-stepper/);
  assert.match(stylesSource, /\.research-card\.is-selected/);
  assert.match(stylesSource, /--selection: #c58bff/);
  assert.doesNotMatch(appSource, /research-selected-badge/);
  assert.match(indexHtml, /id="plan-tasks-mode"/);
  assert.match(indexHtml, /class="resource-mode-compact"/);
  assert.match(appSource, /"step-complete", t\("plan\.complete_step", "研究完了"\)/);
  assert.match(appSource, /"plan-row-effect", `\$\{t\("plan\.effect", "効果"\)\} \$\{effect\}`/);
  assert.match(indexHtml, /id="plan-steps-title"/);
  assert.match(appSource, /planRow\(step, \{ showCategory: false \}\)/);
  assert.match(appSource, /if \(showCategory\) main\.append\(create\("span", "plan-row-category"/);
  assert.match(stylesSource, /\.plan-row-effect \{[^}]*overflow-wrap: anywhere;[^}]*white-space: normal;/);
  assert.match(appSource, /"detail-item detail-effect"/);
});

test("all catalog resource types are included in planning and backup state", () => {
  assert.deepEqual(RESOURCE_KEYS, ["food", "stone", "timber", "ore", "gold", "gold_hammer", "war_tome", "steel_cuffs", "soul_crystal", "ancient_tomes", "lunite", "mana_ore", "special"]);
  const state = defaultState();
  state.settings.academyLevel = 25;
  const target = [...catalog.nodes.values()].find((node) => [...node.levels.values()].some((level) => Number(level.costs.ancient_tomes || 0) > 0));
  const level = [...target.levels.values()].find((item) => Number(item.costs.ancient_tomes || 0) > 0).level;
  const plan = createPlan(catalog, state, target.id, level);
  assert.ok(plan.totals.costs.ancient_tomes > 0);
});

test("Japanese effect text is normalized without game labels", () => {
  const food = catalog.nodes.get("economy_food_harvest_1");
  const languagePack = languagePackFromPayload(pwaLocale, { trusted: true });
  assert.equal(currentEffect(food, 9, {
    locale: "ja-JP",
    name: "食糧収穫I",
    translatedLabel: languagePack.sections.effects[food.id],
    languagePack,
  }), "食糧生産量+58%");
});

test("research speed, VIP free time, and duration use game format", () => {
  const settings = defaultState().settings;
  settings.vipLevel = 1;
  settings.researchSpeedPercent = 224.84;
  assert.equal(adjustedTime(420, settings), 0);
  assert.equal(formatDuration(139623), "1d 14:47:03");
});

test("research start time and maximum guild-help estimate stay separate", () => {
  const settings = defaultState().settings;
  settings.vipLevel = 11;
  settings.researchSpeedPercent = 224.84;
  settings.maxGuildHelps = 30;
  assert.equal(adjustedTime(473040, settings), 139623);
  assert.equal(afterGuildHelps(10000, 0), 10000);
  assert.ok(afterGuildHelps(10000, 30) > 7300);
  assert.ok(afterGuildHelps(10000, 30) < 7500);
  assert.notEqual(afterGuildHelps(10000, 30), 7000);
});

test("guild help input follows the Castle-level limit", () => {
  assert.equal(maxGuildHelpsForCastle(1), 6);
  assert.equal(maxGuildHelpsForCastle(20), 25);
  assert.equal(maxGuildHelpsForCastle(25), 30);
  assert.equal(guildHelpCount({ castleLevel: 20, maxGuildHelps: 99 }), 25);

  const state = defaultState();
  state.settings.castleLevel = 20;
  state.settings.maxGuildHelps = 99;
  const restored = stateFromBackup(backupPayload(state));
  assert.equal(restored.settings.maxGuildHelps, 25);
  assert.match(indexHtml, /id="setting-helps"[^>]*max="6"/);
  assert.match(appSource, /maxGuildHelpsForCastle/);
});

test("tree connection state follows level-one research prerequisites", () => {
  const target = [...catalog.nodes.values()].find((node) => node.levels.get(1)?.requirements.length);
  const state = defaultState();
  assert.equal(isResearchConnectionUnlocked(target, state), false);
  for (const requirement of target.levels.get(1).requirements) {
    state.researchLevels[requirement.researchId] = requirement.level;
  }
  assert.equal(isResearchConnectionUnlocked(target, state), true);
  assert.match(stylesSource, /\.tree-lines path\.is-inactive \{ stroke: #35505a; \}/);
  assert.match(stylesSource, /\.tree-lines path\.is-active \{ stroke: #dca51e; \}/);
});

test("player settings use level, talent, resources, and acceleration subviews", () => {
  assert.doesNotMatch(indexHtml, /data-tab="talent"/);
  assert.doesNotMatch(indexHtml, /id="tab-talent"/);
  assert.match(indexHtml, /id="player-view-level-button"/);
  assert.match(indexHtml, /id="player-view-acceleration-button"/);
  assert.match(indexHtml, /id="player-view-resources-button"/);
  assert.match(indexHtml, /id="player-view-talent-button"/);
  const playerTabs = [...indexHtml.matchAll(/id="player-view-(level|talent|resources|acceleration)-button"/gu)].map((match) => match[1]);
  assert.deepEqual(playerTabs, ["level", "talent", "resources", "acceleration"]);
  assert.match(indexHtml, /data-player-section="acceleration"/);
  assert.match(indexHtml, /data-player-section="resources"/);
  assert.match(indexHtml, /id="player-view-talent" class="player-subview" hidden/);
});

test("talent planning keeps priority navigation available while settings are collapsed", () => {
  assert.match(indexHtml, /<select id="talent-preset"><\/select>/u);
  assert.match(indexHtml, /id="talent-priority"/u);
  assert.match(indexHtml, /id="talent-priority-previous"/u);
  assert.match(indexHtml, /id="talent-priority-next"/u);
  assert.match(indexHtml, /id="talent-auto-follow"/u);
  assert.match(indexHtml, /id="talent-plan-controls" class="talent-plan-controls"/u);
  assert.match(indexHtml, /id="talent-settings-toggle"[^>]*aria-expanded="false"/u);
  assert.match(indexHtml, /id="talent-settings-panel" class="talent-settings-panel" hidden/u);
  assert.match(indexHtml, /class="talent-control-row"/u);
  assert.match(indexHtml, /class="talent-summary-inline"/u);
  assert.match(indexHtml, /id="setting-player-level"/u);
  assert.match(indexHtml, /id="tab-scroll-previous"/u);
  assert.match(indexHtml, /id="tab-scroll-next"/u);
  assert.match(indexHtml, /data-i18n="talent\.auto_follow_short"/u);
  assert.doesNotMatch(indexHtml, /id="talent-available-points"[^>]*type="number"/u);
  assert.match(appSource, /function syncTalentPointCapacity\(\)/u);
  assert.match(indexHtml, /<details class="settings-card talent-directive-card">\s*<summary data-i18n="talent\.details"/u);
  assert.ok(indexHtml.indexOf('id="talent-tree-viewport"') < indexHtml.indexOf('id="talent-description"'));
  assert.doesNotMatch(indexHtml, /player-talent-heading/u);
  assert.doesNotMatch(indexHtml, /id="talent-preset-previous"/u);
  assert.doesNotMatch(indexHtml, /id="talent-preset-next"/u);
  assert.match(indexHtml, /id="talent-tree-viewport"/u);
  assert.match(indexHtml, /id="talent-tree-lines"/u);
  assert.match(indexHtml, /id="talent-tree-cards"/u);
  assert.doesNotMatch(indexHtml, /id="talent-plan-list"/u);
  assert.match(appSource, /function renderTalentTree\(allocation\)/u);
  assert.match(appSource, /talentAutoFollowPending/u);
  assert.match(appSource, /button\?\.setAttribute\("aria-expanded", String\(expanded\)\)/u);
  assert.match(appSource, /viewport\.scrollTo/u);
  assert.match(appSource, /military_command_hidden_talent/u);
  assert.match(stylesSource, /\.talent-tree-card\.is-priority/u);
  assert.match(stylesSource, /\.talent-choice-stepper[^}]*gap:\s*0/u);
});

test("filtered tree layouts compact visible row gaps", () => {
  const nodes = [
    { id: "first", row: 7, column: 1 },
    { id: "second", row: 18, column: 3 },
  ];
  const layout = visibleTreeLayout(nodes);
  assert.equal(layout.rowCount, 2);
  assert.equal(layout.rowSlots.get(7), 0);
  assert.equal(layout.rowSlots.get(18), 1);
});

test("level edits update only affected tree elements and defer hidden plans", () => {
  const dialogBinding = appSource.slice(
    appSource.indexOf("function bindDialog()"),
    appSource.indexOf("function openNodeDialog("),
  );
  const bulkRendering = appSource.slice(
    appSource.indexOf("function renderBulkLevels()"),
    appSource.indexOf("function updateBulkProgress("),
  );
  assert.match(appSource, /function updateVisibleResearchState\(changedNode\)/u);
  assert.match(appSource, /function updateLineStates\(\)/u);
  assert.match(appSource, /path\.dataset\.toId = toId/u);
  assert.match(appSource, /function markResearchPlansDirty\(\)/u);
  assert.match(appSource, /if \(activeTab !== "plan"\) return/u);
  assert.match(dialogBinding, /updateVisibleResearchState\(node\)/u);
  assert.match(dialogBinding, /updateBulkLevelValue\(node\.id, level\)/u);
  assert.match(dialogBinding, /markResearchPlansDirty\(\)/u);
  assert.doesNotMatch(dialogBinding, /renderTree\(\)|renderBulkLevels\(\)|refreshCurrentPlan\(\)/u);
  assert.match(bulkRendering, /updateVisibleResearchState\(node\)/u);
  assert.match(bulkRendering, /markResearchPlansDirty\(\)/u);
  assert.doesNotMatch(bulkRendering, /renderTree\(\)|refreshCurrentPlan\(\)|renderShortest\(\)/u);
});

test("research selection is synchronized across every visible card", () => {
  const selectionSync = appSource.slice(
    appSource.indexOf("function updateResearchCardSelection()"),
    appSource.indexOf("function updateBulkLevelValue("),
  );
  const dialogOpening = appSource.slice(
    appSource.indexOf("function openNodeDialog("),
    appSource.indexOf("function populateTargetLevels("),
  );
  assert.match(selectionSync, /querySelectorAll\("\.research-card"\)/u);
  assert.match(selectionSync, /classList\.toggle\("is-selected", card\.dataset\.nodeId === selectedNodeId\)/u);
  assert.match(dialogOpening, /selectedNodeId = nodeId;\s+updateResearchCardSelection\(\);/u);
});

test("target planning returns the recorded prerequisites", () => {
  const state = defaultState();
  state.settings.academyLevel = 25;
  const target = [...catalog.nodes.values()].find((node) => node.maxLevel > 1 && node.levels.has(2));
  const plan = createPlan(catalog, state, target.id, 2);
  assert.ok(plan.steps.length >= 2);
  assert.ok(plan.totals.adjustedSeconds >= 0);
  assert.equal(plan.totals.afterHelpSeconds, plan.steps.reduce((sum, step) => sum + Number(step.afterHelpSeconds || 0), 0));
});

test("Guild Duel plans expose unavailable time and dedicated material data", () => {
  const target = catalog.nodes.get("guild_duel_gathering_incentive");
  const plan = createPlan(catalog, defaultState(), target.id, 1);

  assert.equal(plan.steps.length, 1);
  assert.equal(plan.steps[0].baseSeconds, null);
  assert.equal(plan.steps[0].costsVerified, false);
  assert.equal(plan.totals.unknownTime, 1);
  assert.equal(plan.totals.unknownCosts, 1);
  assert.match(appSource, /unknown_special_material/u);
  assert.match(appSource, /speedup_unknown_time/u);
});

test("target planning lists all lower dependency layers first", () => {
  const level = (requirements = []) => ({ baseTimeSeconds: 100, technolabeCount: 1, costs: {}, costsVerified: true, requirements, buildings: {} });
  const node = (id, requirements = []) => ({ id, categoryId: "test", maxLevel: 1, levels: new Map([[1, level(requirements)]]) });
  const d = node("d");
  const c = node("c", [{ researchId: "d", level: 1 }]);
  const b = node("b");
  const z = node("z", [{ researchId: "c", level: 1 }, { researchId: "b", level: 1 }]);
  const miniCatalog = { nodes: new Map([z, b, c, d].map((item) => [item.id, item])) };

  const plan = createPlan(miniCatalog, defaultState(), "z", 1);

  assert.deepEqual(plan.steps.map((step) => step.researchId), ["b", "d", "c", "z"]);
});

test("every catalog plan lists each level after all prerequisites", () => {
  for (const target of catalog.nodes.values()) {
    const plan = createPlan(catalog, defaultState(), target.id, target.maxLevel);
    const completed = {};
    for (const step of plan.steps) {
      assert.equal(step.level, Number(completed[step.researchId] || 0) + 1, `${target.id}: ${step.researchId} Lv.${step.level}`);
      const level = catalog.nodes.get(step.researchId).levels.get(step.level);
      for (const requirement of level?.requirements || []) {
        assert.ok(
          Number(completed[requirement.researchId] || 0) >= requirement.level,
          `${target.id}: ${step.researchId} Lv.${step.level} before ${requirement.researchId} Lv.${requirement.level}`,
        );
      }
      completed[step.researchId] = step.level;
    }
  }
});

test("Technolabe efficiency uses original time and sourced item counts", () => {
  assert.equal(TECHNOLABE_CAPACITY_SECONDS, 33 * 86400 + 3 * 3600 + 59 * 60);
  const usage = technolabeUsage(12 * 86400, 2);
  assert.equal(usage.count, 2);
  assert.ok(Math.abs(usage.efficiencyPercent - (12 * 86400 / (2 * TECHNOLABE_CAPACITY_SECONDS) * 100)) < 0.0001);
  assert.equal(technolabeUsage(30 * 86400).count, null);
  const screenshotUsage = technolabeUsage(5_427_900, 6);
  assert.equal(screenshotUsage.count, 6);
  assert.equal(screenshotUsage.efficiencyPercent.toFixed(1), "31.6");
  const sourcedLevels = [...catalog.nodes.values()].flatMap((node) => [...node.levels.values()]).filter((item) => item.technolabeCount != null);
  assert.ok(sourcedLevels.length > 2900);
});

test("Technolabe recommendation uses the configured efficiency boundary", () => {
  assert.equal(isTechnolabeRecommended(95), true);
  assert.equal(isTechnolabeRecommended(94.9), false);
  assert.equal(isTechnolabeRecommended(92.5, 92.5), true);
  assert.equal(isTechnolabeRecommended(null, 0), false);
  const state = defaultState();
  assert.equal(state.settings.technolabeRecommendationThresholdPercent, 95);
  assert.equal(state.settings.technolabeCount, 0);
  state.settings.technolabeCount = 19;
  state.settings.technolabeRecommendationThresholdPercent = 97.5;
  const restored = stateFromBackup(backupPayload(state));
  assert.equal(restored.settings.technolabeRecommendationThresholdPercent, 97.5);
  assert.equal(restored.settings.technolabeCount, 19);
  assert.match(indexHtml, /id="setting-technolabe-threshold"/u);
  assert.match(indexHtml, /id="setting-technolabe-count"/u);
  assert.match(indexHtml, /id="technolabe-only"/u);
  assert.match(appSource, /plan\.technolabe_recommended/u);
  assert.match(stylesSource, /\.plan-row-wisdom\.is-recommended/u);
});

test("marking a target plan complete applies every prerequisite step", () => {
  const state = defaultState();
  state.settings.academyLevel = 25;
  const target = [...catalog.nodes.values()].find((node) => {
    const level = node.levels.get(1);
    return level?.requirements.some((requirement) => requirement.researchId !== node.id);
  });
  const plan = createPlan(catalog, state, target.id, 1);
  assert.ok(plan.steps.length > 1);
  const completed = researchLevelsAfterPlan(plan, state.researchLevels);
  for (const step of plan.steps) {
    assert.ok(completed[step.researchId] >= step.level);
  }
});

test("shortest list contains only startable next levels", () => {
  const state = defaultState();
  state.settings.academyLevel = 25;
  const steps = shortestAvailable(catalog, state);
  assert.ok(steps.length > 0);
  assert.ok(steps.every((step) => step.level === 1));
  assert.deepEqual([...steps].sort((a, b) => a.adjustedSeconds - b.adjustedSeconds), steps);
});

test("backup payload round-trips with desktop schema", () => {
  const state = defaultState();
  state.settings.playerLevel = 42;
  state.settings.vipLevel = 11;
  state.settings.researchSpeedPercent = 228;
  state.settings.constructionSpeedPercent = 176.25;
  state.settings.constructionSpeedBoostPercent = 20;
  state.settings.castleLevel = 25;
  state.settings.castleTargetLevel = 25;
  state.settings.castleManaStage = 2;
  state.settings.castleTargetManaStage = 4;
  state.researchLevels.economy_construction_speed = 7;
  state.buildingLevels.castle_wall = 12;
  state.settings.resourceDisplayMode = "short";
  state.settings.speedupInventory = [
    { kind: "general", durationSeconds: 3600, quantity: 2 },
    { kind: "research", durationSeconds: 1800, quantity: 4 },
  ];
  state.settings.useGemsForSpeedups = true;
  state.talentAutoFollow = false;
  state.planTasks.push({ researchId: "economy_construction_speed", targetLevel: 8, createdAt: "test-date" });
  const restored = stateFromBackup(backupPayload(state));
  assert.equal(restored.settings.playerLevel, 42);
  assert.equal(restored.settings.vipLevel, 11);
  assert.equal(restored.settings.researchSpeedPercent, 228);
  assert.equal(restored.settings.constructionSpeedPercent, 176.25);
  assert.equal(restored.settings.constructionSpeedBoostPercent, 20);
  assert.equal(restored.settings.castleTargetLevel, 25);
  assert.equal(restored.settings.castleManaStage, 2);
  assert.equal(restored.settings.castleTargetManaStage, 4);
  assert.equal(restored.researchLevels.economy_construction_speed, 7);
  assert.equal(restored.buildingLevels.castle_wall, 12);
  assert.equal(restored.settings.resourceDisplayMode, "short");
  assert.deepEqual(restored.settings.speedupInventory, state.settings.speedupInventory);
  assert.equal(restored.settings.useGemsForSpeedups, true);
  assert.equal(restored.talentAutoFollow, false);
  assert.deepEqual(restored.planTasks, [{ researchId: "economy_construction_speed", targetLevel: 8, createdAt: "test-date", sourceName: "" }]);
});

test("paid workspace separates entry, saved offers, comparison, and sharing", () => {
  assert.match(indexHtml, /id="paid-view-input" class="paid-subview paid-editor/);
  assert.match(indexHtml, /id="paid-view-saved" class="paid-subview" hidden/);
  assert.match(indexHtml, /id="paid-view-comparison" class="paid-subview" hidden/);
  assert.match(indexHtml, /id="paid-view-share" class="paid-subview" hidden/);
  assert.match(indexHtml, /id="paid-export-all"/);
  assert.match(indexHtml, /id="paid-export-valuation"/);
  assert.match(appSource, /function exportAllPaidOffers\(\)/);
  assert.match(appSource, /function exportPaidValuation\(\)/);
});

test("research directive contains tasks only and round-trips its metadata", () => {
  const payload = researchDirectivePayload([
    { researchId: "military_heroic_fighter", targetLevel: 1 },
    { researchId: "upgrade_military_heroic_fighter_subsidy", targetLevel: 7 },
    { researchId: "upgrade_military_heroic_fighter_subsidy", targetLevel: 10 },
  ], {
    name: "レジェンドファイター研究計画",
    datasetId: "test-dataset",
    gameVersion: "v2.200.309",
  });

  assert.equal(payload.document_type, "RLMResearchPlanner.research-directive");
  assert.equal(payload.name, "レジェンドファイター研究計画");
  assert.deepEqual(payload.tasks, [
    { research_id: "military_heroic_fighter", target_level: 1 },
    { research_id: "upgrade_military_heroic_fighter_subsidy", target_level: 10 },
  ]);
  for (const privateKey of ["player", "settings", "research_levels", "building_levels", "resources"]) {
    assert.equal(Object.hasOwn(payload, privateKey), false);
  }
  assert.deepEqual(researchDirectiveFromPayload(payload), {
    name: "レジェンドファイター研究計画",
    datasetId: "test-dataset",
    gameVersion: "v2.200.309",
    tasks: [
      { researchId: "military_heroic_fighter", targetLevel: 1 },
      { researchId: "upgrade_military_heroic_fighter_subsidy", targetLevel: 10 },
    ],
  });
});

test("importing a research directive merges tasks without replacing player data", () => {
  const state = defaultState();
  state.settings.vipLevel = 11;
  state.settings.researchSpeedPercent = 228;
  state.settings.resources.food = 1_234_567;
  state.researchLevels.economy_construction_speed = 7;
  state.buildingLevels.academy = 24;
  state.planTasks = [{ researchId: "economy_construction_speed", targetLevel: 8, createdAt: "existing", sourceName: "" }];
  const preserved = {
    settings: structuredClone(state.settings),
    researchLevels: structuredClone(state.researchLevels),
    buildingLevels: structuredClone(state.buildingLevels),
  };

  const directive = researchDirectiveFromPayload(researchDirectivePayload([
    { researchId: "economy_construction_speed", targetLevel: 10 },
    { researchId: "military_heroic_fighter", targetLevel: 1 },
  ], { name: "共有研究計画" }));
  const merged = mergeResearchDirectiveTasks(state.planTasks, directive.tasks, directive.name, "imported");
  state.planTasks = merged.tasks;

  assert.deepEqual(merged, {
    tasks: [
      { researchId: "economy_construction_speed", targetLevel: 10, createdAt: "existing", sourceName: "共有研究計画" },
      { researchId: "military_heroic_fighter", targetLevel: 1, createdAt: "imported", sourceName: "共有研究計画" },
    ],
    added: 1,
    updated: 1,
    unchanged: 0,
  });
  assert.deepEqual(state.settings, preserved.settings);
  assert.deepEqual(state.researchLevels, preserved.researchLevels);
  assert.deepEqual(state.buildingLevels, preserved.buildingLevels);
});

test("an imported research task is complete or recalculated from the recipient's current levels", () => {
  const targetId = "military_heroic_fighter";
  const freshState = defaultState();
  freshState.settings.academyLevel = 25;
  const fullPlan = createPlan(catalog, freshState, targetId, 1);
  assert.ok(fullPlan.steps.length > 1);

  const partialState = defaultState();
  partialState.settings.academyLevel = 25;
  const firstStep = fullPlan.steps[0];
  partialState.researchLevels[firstStep.researchId] = firstStep.level;
  const remainingPlan = createPlan(catalog, partialState, targetId, 1);
  assert.ok(remainingPlan.steps.length < fullPlan.steps.length);
  assert.equal(remainingPlan.steps.some((step) => step.researchId === firstStep.researchId && step.level <= firstStep.level), false);

  const completedState = defaultState();
  completedState.settings.academyLevel = 25;
  completedState.researchLevels = researchLevelsAfterPlan(fullPlan, completedState.researchLevels);
  const completedPlan = createPlan(catalog, completedState, targetId, 1);
  assert.equal(completedPlan.steps.length, 0);
  assert.equal(completedPlan.totals.adjustedSeconds, 0);
});

test("installed PWA stays portrait-first and pages crowded tabs", () => {
  assert.equal(webManifest.orientation, "portrait-primary");
  assert.match(stylesSource, /\.tab-bar\.is-overflowing[^}]*grid-auto-columns: calc\(\(100% - 8px\) \/ 3\)/u);
  assert.match(appSource, /currentIndex \+ direction \* 3/u);
});

test("target plans expose the unmet dependency graph for the mobile plan tree", () => {
  const state = defaultState();
  state.settings.academyLevel = 25;
  const plan = createPlan(catalog, state, "military_heroic_fighter", 1);

  assert.ok(Object.keys(plan.requiredLevels).length > 1);
  assert.equal(plan.requiredLevels.military_heroic_fighter, 1);
  assert.ok(plan.edges.length > 0);
  assert.ok(plan.edges.every(([fromId, toId]) => (
    Object.hasOwn(plan.requiredLevels, fromId)
    && Object.hasOwn(plan.requiredLevels, toId)
  )));
  assert.match(indexHtml, /id="plan-tree-viewport"/u);
  assert.match(appSource, /function renderPlanTree\(\)/u);
  assert.match(stylesSource, /\.plan-tree-viewport/u);
});

test("castle planning traces prerequisite facilities and totals costs", () => {
  assert.equal(castleCatalog.buildings.size, 18);
  assert.ok([...castleCatalog.buildings.values()].every((building) => building.levels.size === 25));
  assert.ok([...castleCatalog.buildings.values()].every((building) => building.levels.get(25).costs.gold_hammer === 1));
  assert.equal(castleCatalog.maxManaStage, 5);
  const state = defaultState();
  state.settings.castleLevel = 5;
  const plan = createCastlePlan(castleCatalog, state, 6);
  assert.deepEqual(plan.steps.map((step) => [step.buildingId, step.level]), [
    ["castle_wall", 5],
    ["vault", 1],
    ["vault", 2],
    ["vault", 3],
    ["vault", 4],
    ["vault", 5],
    ["castle", 6],
  ]);
  assert.deepEqual(plan.totals.costs, Object.fromEntries(CASTLE_RESOURCE_KEYS.map((key) => [key, plan.steps.reduce((sum, step) => sum + Number(step.costs[key] || 0), 0)])));
  assert.equal(minimumBuildingLevels(castleCatalog, 5).castle_wall, 4);
});

test("shared PC and PWA help uses the desktop locale as its source", () => {
  for (const key of ["help.plan.body", "help.castle.body"]) {
    assert.equal(pwaLocale.messages[key], desktopLocale.messages[key]);
  }
  assert.match(indexHtml, /id="help-plan-body"/);
  assert.match(indexHtml, /id="help-construction-body"/);
  assert.match(appSource, /messages\["help\.plan\.body"\]/);
  assert.match(appSource, /messages\["help\.castle\.body"\]/);
  assert.match(pwaLocale.messages["help.plan.body"], /開始時/);
  assert.match(pwaLocale.messages["help.plan.body"], /ヘルプ後/);
  assert.match(pwaLocale.messages["help.plan.body"], /城Lv\.25の30回/);
});

test("individual Academy planning includes advanced facilities and gem estimates", () => {
  const state = defaultState();
  state.settings.castleLevel = 25;
  state.buildingLevels = { academy: 24, battle_hall: 24, prison: 24, altar: 24 };
  state.settings.resources.war_tome = 1000;
  const plan = createCastlePlan(castleCatalog, state, 25, 0, {
    targetBuildingId: "academy",
    targetBuildingLevel: 25,
  });
  const steps = new Set(plan.steps.map((step) => `${step.buildingId}:${step.level}`));
  assert.ok(steps.has("battle_hall:25"));
  assert.ok(steps.has("prison:25"));
  assert.ok(steps.has("altar:25"));
  assert.equal(plan.totals.costs.war_tome, 4500);
  assert.equal(plan.totals.gemCosts.war_tome, 35500);
  assert.equal(minimumGemsForAmount(1001, castleCatalog.gemShopPacks.war_tome), 10015);
});

test("castle planning adds the temporary construction boost to construction speed", () => {
  const permanent = defaultState();
  permanent.settings.castleLevel = 24;
  permanent.settings.constructionSpeedPercent = 200;
  const temporary = defaultState();
  temporary.settings.castleLevel = 24;
  temporary.settings.constructionSpeedPercent = 175;
  temporary.settings.constructionSpeedBoostPercent = 25;
  assert.equal(
    createCastlePlan(castleCatalog, temporary, 25).totals.adjustedSeconds,
    createCastlePlan(castleCatalog, permanent, 25).totals.adjustedSeconds,
  );
});

test("completing a castle step applies every earlier prerequisite step", () => {
  const state = defaultState();
  state.settings.castleLevel = 5;
  const plan = createCastlePlan(castleCatalog, state, 6);
  const result = buildingLevelsAfterCastleStep(
    plan,
    plan.steps.at(-1),
    state.settings.castleLevel,
    state.settings.castleManaStage,
    state.buildingLevels,
  );
  assert.equal(result.castleLevel, 6);
  assert.equal(result.castleManaStage, 0);
  assert.equal(result.buildingLevels.castle_wall, 5);
  assert.equal(result.buildingLevels.vault, 5);
});

test("castle planning supports Lv.25-1 through Lv.25-5", () => {
  const state = defaultState();
  state.settings.castleLevel = 25;
  state.settings.castleManaStage = 1;
  const plan = createCastlePlan(castleCatalog, state, 25, 5);
  assert.deepEqual(plan.steps.map((step) => [step.level, step.manaStage]), [
    [25, 2], [25, 3], [25, 4], [25, 5],
  ]);
  assert.equal(plan.currentManaStage, 1);
  assert.equal(plan.targetManaStage, 5);
  assert.equal(plan.totals.costs.mana_ore, 23029 * 4);
  assert.equal(plan.totals.costs.mana_crystal, 242 * 4);
  const completed = buildingLevelsAfterCastleStep(
    plan,
    plan.steps.at(-1),
    state.settings.castleLevel,
    state.settings.castleManaStage,
    state.buildingLevels,
  );
  assert.equal(completed.castleLevel, 25);
  assert.equal(completed.castleManaStage, 5);
});

test("construction speed reduces castle plan time without changing resources", () => {
  const state = defaultState();
  state.settings.castleLevel = 24;
  const normal = createCastlePlan(castleCatalog, state, 25);
  state.settings.constructionSpeedPercent = 200;
  const faster = createCastlePlan(castleCatalog, state, 25);
  assert.ok(faster.totals.adjustedSeconds < normal.totals.adjustedSeconds);
  assert.deepEqual(faster.totals.costs, normal.totals.costs);
  assert.ok(faster.totals.costs.gold_hammer >= 1);
});

test("resource values support exact and abbreviated display", () => {
  assert.equal(formatResourceAmount(1_234_567, "exact", "en-US"), "1,234,567");
  assert.equal(formatResourceAmount(999, "short", "en-US"), "999");
  assert.equal(formatResourceAmount(1_000, "short", "en-US"), "1K");
  assert.equal(formatResourceAmount(1_234_567, "short", "en-US"), "1.23M");
  assert.equal(formatResourceAmount(4_975_911, "short", "en-US"), "4.97M");
});
