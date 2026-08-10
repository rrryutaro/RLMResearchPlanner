import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { normalizeCatalog } from "../tools/RLMResearchPlannerPWA/src/catalog.js";
import { normalizeCastleCatalog } from "../tools/RLMResearchPlannerPWA/src/castle-planning.js";
import { loadState } from "../tools/RLMResearchPlannerPWA/src/state.js";

const pwaRoot = new URL("../tools/RLMResearchPlannerPWA/", import.meta.url);
const text = (path) => readFile(new URL(path, pwaRoot), "utf8");

const [indexHtml, appSource, workerSource, researchSource, castleSource, japaneseSource, englishSource] = await Promise.all([
  text("index.html"),
  text("src/app.js"),
  text("sw.js"),
  text("data/research/catalog.json"),
  text("data/buildings/castle_catalog.json"),
  text("data/i18n/ja-JP.json"),
  text("data/i18n/en-US.json"),
]);

const assetVersion = indexHtml.match(/styles\.css\?v=([0-9.]+-b\d+)/)?.[1];
const appVersion = appSource.match(/RELEASE_VERSION\s*=\s*"([0-9.]+)"/)?.[1];
assert.ok(assetVersion, "index.htmlのアセット版番号を取得できません");
assert.ok(appVersion, "app.jsの公開版番号を取得できません");
assert.equal(assetVersion.replace(/-b\d+$/, ""), appVersion, "公開版とアセット版が一致していません");
assert.match(workerSource, new RegExp(`v${assetVersion.replaceAll(".", "\\.")}`), "Service Workerのキャッシュ版が一致していません");

const shellSource = workerSource.match(/const APP_SHELL\s*=\s*\[([\s\S]*?)\];/)?.[1] || "";
const shellPaths = [...shellSource.matchAll(/"(\.\/[^"\n]*)"/g)].map((match) => match[1]);
assert.ok(shellPaths.length >= 19, "配信対象ファイルが不足しています");
for (const shellPath of shellPaths) {
  const relative = shellPath.split("?", 1)[0].replace(/^\.\//, "");
  if (!relative) continue;
  await access(fileURLToPath(new URL(relative, pwaRoot)));
}

assert.match(indexHtml, /id="startup-recover"/, "最新版を再取得する操作がありません");
assert.match(indexHtml, /updateViaCache:\s*"none"/, "Service Worker更新時に旧HTTPキャッシュを回避していません");
assert.match(indexHtml, /registration\.scope === appRoot/, "復旧時のService Worker削除範囲が限定されていません");
assert.match(workerSource, /key\.startsWith\(CACHE_PREFIX\)/, "キャッシュ削除範囲がこのPWAに限定されていません");
assert.doesNotMatch(workerSource, /\(await caches\.match\(event\.request\)\) \|\| caches\.match\("\.\/index\.html"\)/, "データ取得失敗時にHTMLを返す処理が残っています");

const research = normalizeCatalog(JSON.parse(researchSource));
const castle = normalizeCastleCatalog(JSON.parse(castleSource));
const japanese = JSON.parse(japaneseSource);
const english = JSON.parse(englishSource);
assert.equal(research.categories.length, 16, "研究分野数が一致しません");
assert.equal(research.nodes.size, 399, "研究項目数が一致しません");
assert.equal(castle.buildings.size, 18, "施設数が一致しません");
assert.equal(Object.keys(japanese.messages || {}).length, Object.keys(english.messages || {}).length, "日本語と英語のUI項目数が一致しません");

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

console.log(`PWA release checks passed: ${appVersion}, ${shellPaths.length} files, ${research.nodes.size} research nodes.`);
