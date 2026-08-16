import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { normalizeCastleCatalog } from "../src/castle-planning.js";
import { normalizeCatalog } from "../src/catalog.js";
import {
  defaultPaidValuation,
  paidOfferExchangePayload,
  paidOffersFromExchangePayload,
} from "../src/paid-value.js";
import { loadState, playerStorageKey, saveState } from "../src/state.js";

const pwaRoot = new URL("../", import.meta.url);
const text = (path) => readFile(new URL(path, pwaRoot), "utf8");

const [
  packageSource,
  versionSource,
  indexHtml,
  appSource,
  workerSource,
  planningSource,
  stateSource,
  speedupInventorySource,
  castlePlanningSource,
  castleSource,
  localeManifestSource,
] = await Promise.all([
  text("package.json"),
  text("version.py"),
  text("index.html"),
  text("src/app.js"),
  text("sw.js"),
  text("src/planning.js"),
  text("src/state.js"),
  text("src/speedup-inventory.js"),
  text("src/castle-planning.js"),
  text("data/buildings/castle_catalog.json"),
  text("data/i18n/manifest.json"),
]);

const packageVersion = JSON.parse(packageSource).version;
const packageMatch = packageVersion.match(/^(\d+\.\d+\.\d+)$/u);
assert.ok(packageMatch, "package.jsonの正式版番号はビルド番号を含まないx.y.z形式にしてください");
const [, releaseVersion] = packageMatch;
const buildMatch = versionSource.match(/^__build__\s*=\s*(\d+)$/mu);
assert.ok(buildMatch, "version.pyの内部ビルド番号を読み取れません");
const [, buildNumber] = buildMatch;
const assetVersion = `${releaseVersion}-b${buildNumber}`;

assert.match(versionSource, new RegExp(`__version__\\s*=\\s*"${releaseVersion.replaceAll(".", "\\.")}"`), "version.pyの公開版が一致しません");
assert.match(versionSource, new RegExp(`__build__\\s*=\\s*${buildNumber}\\b`), "version.pyのビルド番号が一致しません");
assert.match(appSource, new RegExp(`RELEASE_VERSION\\s*=\\s*"${releaseVersion.replaceAll(".", "\\.")}"`), "app.jsの公開版が一致しません");
assert.match(appSource, new RegExp(`DEVELOPMENT_BUILD\\s*=\\s*${buildNumber}\\b`), "app.jsのビルド番号が一致しません");
assert.match(appSource, new RegExp(`ASSET_VERSION\\s*=\\s*"${assetVersion.replaceAll(".", "\\.")}"`), "app.jsのデータ版番号が一致しません");
assert.match(appSource, /const APP_VERSION = RELEASE_VERSION;/u, "画面表示用の版番号が公開版と一致しません");
assert.doesNotMatch(appSource, /\$\{RELEASE_VERSION\}\+b/u, "画面表示に内部ビルド番号が含まれています");
assert.match(indexHtml, new RegExp(`styles\\.css\\?v=${assetVersion.replaceAll(".", "\\.")}`), "CSSの版番号が一致しません");
assert.match(indexHtml, new RegExp(`src/app\\.js\\?v=${assetVersion.replaceAll(".", "\\.")}`), "起動スクリプトの版番号が一致しません");
assert.match(workerSource, new RegExp(`v${assetVersion.replaceAll(".", "\\.")}`), "Service Workerのキャッシュ版が一致しません");
assert.match(workerSource, /src\/speedup-inventory\.js/u, "Service Worker に所持スピードアップ計算が含まれていません");
for (const source of [appSource, planningSource, stateSource, speedupInventorySource, castlePlanningSource, workerSource]) {
  const staleVersions = [...source.matchAll(/\?v=([0-9.]+-b\d+)/gu)]
    .map((match) => match[1])
    .filter((value) => value !== assetVersion);
  assert.deepEqual(staleVersions, [], `異なるアセット版が残っています: ${staleVersions.join(", ")}`);
}

const shellSource = workerSource.match(/const APP_SHELL\s*=\s*\[([\s\S]*?)\];/u)?.[1] || "";
const shellPaths = [...shellSource.matchAll(/"(\.\/[^"\n]*)"/gu)].map((match) => match[1]);
assert.ok(shellPaths.length >= 20, "オフライン配信対象ファイルが不足しています");
for (const shellPath of shellPaths) {
  const relative = shellPath.split("?", 1)[0].replace(/^\.\//u, "");
  if (relative) await access(fileURLToPath(new URL(relative, pwaRoot)));
}

assert.match(indexHtml, /id="startup-retry"/u, "起動失敗時の再読み込み操作がありません");
assert.match(indexHtml, /id="startup-recover"/u, "古いキャッシュを破棄して最新版を再取得する操作がありません");
assert.match(indexHtml, /updateViaCache:\s*"none"/u, "Service Worker更新時に旧HTTPキャッシュを回避していません");
assert.match(indexHtml, /registration\.scope === appRoot/u, "復旧時のService Worker削除範囲が限定されていません");
assert.match(workerSource, /key\.startsWith\(CACHE_PREFIX\)/u, "キャッシュ削除範囲がこのPWAに限定されていません");
assert.match(workerSource, /SCOPE_KEY/u, "Service Workerキャッシュが配信先ごとに分離されていません");
assert.match(workerSource, /rlm-research-planner-preview/u, "確認版のキャッシュ名前空間が分離されていません");
assert.match(workerSource, /new Request\(url, \{ cache: "reload" \}\)/u, "PWA更新時にHTTPキャッシュを再利用しています");
assert.match(workerSource, /async function manifestAssets\(\)/u, "研究・翻訳マニフェストからオフライン対象を展開していません");
assert.match(workerSource, /locales\.locales/u, "全内蔵言語をオフライン対象にしていません");
assert.match((await text("src/catalog.js")), /JSONの代わりにHTMLが返されました/u, "古いキャッシュがHTMLを返した場合の検出がありません");
assert.doesNotMatch(workerSource, /\(await caches\.match\(event\.request\)\) \|\| caches\.match\("\.\/index\.html"\)/u, "データ取得失敗時にHTMLを返す処理が残っています");
assert.match(indexHtml, /id="shortest-previous"/u, "短時間順の前ページ操作がありません");
assert.match(indexHtml, /id="shortest-page-status"/u, "短時間順のページ表示がありません");
assert.match(indexHtml, /id="shortest-next"/u, "短時間順の次ページ操作がありません");
assert.match(indexHtml, /id="paid-view-share-button"/u, "課金データの共有画面がありません");
assert.match(indexHtml, /id="paid-export-valuation"/u, "課金比較設定だけを書き出す操作がありません");
assert.match(indexHtml, /id="speedup-inventory-groups"/u, "分野別の所持スピードアップ欄がありません");
assert.match(appSource, /SPEEDUP_DURATION_SECONDS/u, "固定時間別の所持数入力がありません");
assert.match(appSource, /create\("details", "speedup-inventory-kind"\)/u, "所持スピードアップが分野別の折り畳みになっていません");
assert.match(appSource, /SPEEDUP_DURATION_GROUPS\.map/u, "Speed-up durations are not grouped into minutes, hours, and days");
assert.match(appSource, /numberStepper\(input\)/u, "Speed-up quantities do not have minus and plus controls");
assert.doesNotMatch(indexHtml, /id="speedup-inventory-summary"/u, "An unusable all-category speed-up total is still displayed");
assert.doesNotMatch(indexHtml, /speedup-inventory-card/u, "The PWA acceleration page still has a redundant outer card");
assert.doesNotMatch(indexHtml, /data-i18n="player\.speedup_inventory_hint"/u, "The acceleration page still shows explanatory text outside Help");
assert.match(indexHtml, /id="help-player-body"/u, "The moved player-setting guidance is missing from Help");
assert.match(appSource, /SPEEDUP_DURATION_SECONDS\.includes\(durationSeconds\)/u, "Fixed speed-up labels do not preserve 60 minutes and 24 hours");
assert.match(indexHtml, /<details id="plan-speedup-summary" class="speedup-simulation"><\/details>/u, "The research speed-up simulation starts collapsed");
assert.match(appSource, /create\("details", "speedup-simulation castle-speedup-simulation"\)/u, "The construction speed-up simulation starts collapsed");
const elementIds = [...indexHtml.matchAll(/\sid="([^"]+)"/gu)].map((match) => match[1]);
assert.equal(new Set(elementIds).size, elementIds.length, "画面内に重複したidがあります");

const datasetManifest = JSON.parse(await text("data/research-dataset/manifest.json"));
const localeManifest = JSON.parse(localeManifestSource);
assert.equal(localeManifest.document_type, "RLMResearchPlanner.locale-manifest", "表示言語一覧の形式が正しくありません");
assert.equal(Number(localeManifest.schema_version), 1, "表示言語一覧の版に対応していません");
assert.ok((localeManifest.locales || []).some((entry) => entry.locale === localeManifest.fallback_locale), "表示言語のフォールバックが登録されていません");
const bundledLocales = Object.fromEntries(await Promise.all((localeManifest.locales || []).map(async (entry) => [
  entry.locale,
  JSON.parse(await text(`data/i18n/${entry.path}`)),
])));
for (const entry of localeManifest.locales || []) {
  const pack = bundledLocales[entry.locale];
  assert.equal(pack.document_type, "RLMResearchPlanner.language-pack", `${entry.locale}の言語パック形式が正しくありません`);
  assert.equal(pack.locale, entry.locale, `${entry.locale}の言語IDが一致しません`);
  assert.equal(pack.name, entry.name, `${entry.locale}の表示名が一致しません`);
  assert.equal(pack.direction, entry.direction, `${entry.locale}の文字方向が一致しません`);
}
const datasetDocuments = {
  manifest: datasetManifest,
  sources: JSON.parse(await text(`data/research-dataset/${datasetManifest.sources_path}`)),
  evidence: JSON.parse(await text(`data/research-dataset/${datasetManifest.evidence_path}`)),
  aliases: JSON.parse(await text(`data/research-dataset/${datasetManifest.aliases_path}`)),
  trees: Object.fromEntries(await Promise.all((datasetManifest.trees || []).map(async (entry) => [
    entry.id,
    JSON.parse(await text(`data/research-dataset/${entry.path}`)),
  ]))),
  locales: Object.fromEntries(await Promise.all((datasetManifest.locales || []).map(async (entry) => [
    entry.locale,
    JSON.parse(await text(`data/research-dataset/${entry.path}`)),
  ]))),
};
const research = normalizeCatalog(datasetDocuments);
const castle = normalizeCastleCatalog(JSON.parse(castleSource));
const fallbackLanguage = bundledLocales[localeManifest.fallback_locale];
assert.equal(research.categories.length, 16, "研究分野数が一致しません");
assert.equal(research.nodes.size, 399, "研究項目数が一致しません");
assert.equal([...research.nodes.values()].reduce((sum, node) => sum + node.maxLevel, 0), 3385, "研究の全レベル数が一致しません");
assert.equal([...research.nodes.values()].reduce((sum, node) => sum + node.levels.size, 0), 3179, "研究の詳細レベル数が一致しません");
assert.doesNotMatch(await text("src/catalog.js"), /function\s+(?:slugify|nearestVisibleEdges)\b/u, "旧ID生成または旧接続推定処理が残っています");
assert.match(appSource, /loadCatalog\("\.\/data\/research-dataset"/u, "PWAが共通研究データを読み込んでいません");
assert.equal(castle.buildings.size, 18, "施設数が一致しません");
for (const [locale, pack] of Object.entries(bundledLocales)) {
  const missingMessages = Object.keys(fallbackLanguage.messages || {}).filter((key) => !Object.hasOwn(pack.messages || {}, key));
  assert.deepEqual(missingMessages, [], `${locale}に未収録のUI項目があります`);
}
assert.doesNotMatch(appSource, /\[\s*"ja-JP"\s*,\s*"en-US"/u, "内蔵言語一覧がコードへ固定されています");

const oldState = {
  locale: "ja-JP",
  settings: { vipLevel: 11, researchSpeedPercent: 228, resources: { food: 1234 } },
  researchLevels: { economy_construction_speed: 7 },
  buildingLevels: { academy: 24 },
  planTasks: [{ researchId: "economy_construction_speed", targetLevel: 8, createdAt: "old" }],
};
const restored = loadState({ getItem: () => JSON.stringify(oldState) });
assert.equal(restored.settings.vipLevel, 11, "旧VIP設定を引き継げません");
assert.equal(restored.settings.researchSpeedPercent, 228, "旧研究速度を引き継げません");
assert.equal(restored.settings.constructionSpeedPercent, 0, "新しい設定の既定値を補完できません");
assert.equal(restored.researchLevels.economy_construction_speed, 7, "旧研究レベルを引き継げません");
assert.equal(restored.buildingLevels.academy, 24, "旧施設レベルを引き継げません");
assert.equal(restored.planTasks[0].targetLevel, 8, "旧研究タスクを引き継げません");

const productionStorageKey = playerStorageKey("/RLMResearchPlanner/");
const previewStorageKey = playerStorageKey("/RLMResearchPlanner/preview/");
assert.notEqual(productionStorageKey, previewStorageKey, "本番と確認版のプレイヤーデータが分離されていません");
const previewStorageValues = new Map([[productionStorageKey, JSON.stringify(oldState)]]);
const previewStorage = {
  getItem: (key) => previewStorageValues.get(key) || null,
  setItem: (key, value) => previewStorageValues.set(key, value),
};
const previewState = loadState(previewStorage, "/RLMResearchPlanner/preview/");
assert.equal(previewState.settings.vipLevel, 11, "確認版へ本番データを複製できません");
previewState.settings.vipLevel = 12;
saveState(previewState, previewStorage, "/RLMResearchPlanner/preview/");
assert.equal(JSON.parse(previewStorageValues.get(productionStorageKey)).settings.vipLevel, 11, "確認版が本番データを書き換えています");
assert.equal(JSON.parse(previewStorageValues.get(previewStorageKey)).settings.vipLevel, 12, "確認版データを独立保存できません");

const valuation = defaultPaidValuation();
valuation.pointsPerGem = 2.5;
const valuationOnly = paidOffersFromExchangePayload(paidOfferExchangePayload([], valuation, "settings"));
assert.equal(valuationOnly.offers.length, 0, "課金比較設定だけのファイルを読み込めません");
assert.equal(valuationOnly.valuation.pointsPerGem, 2.5, "課金比較設定を維持できません");

console.log(`PWA release checks passed: ${packageVersion}, ${shellPaths.length} shell files, ${Object.keys(bundledLocales).length} locales, ${research.nodes.size} research nodes.`);
