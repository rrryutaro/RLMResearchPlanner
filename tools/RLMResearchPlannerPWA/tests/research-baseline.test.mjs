import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";

const developmentDesktopRoot = new URL("../../RLMResearchPlanner/", import.meta.url);
const publicDesktopRoot = new URL("../../../", import.meta.url);
const desktopRoot = existsSync(fileURLToPath(new URL("pyproject.toml", developmentDesktopRoot)))
  ? developmentDesktopRoot
  : publicDesktopRoot;
const { buildPwaBaseline } = await import(new URL("dataset/scripts/export_pwa_baseline.mjs", desktopRoot));
const baselineRoot = new URL("dataset/baseline/", desktopRoot);


async function readJson(relativePath) {
  return JSON.parse(await readFile(new URL(relativePath, baselineRoot), "utf8"));
}


test("checked-in PWA research baseline matches the current loader", async () => {
  const baseline = await buildPwaBaseline();
  const manifest = await readJson("manifest.json");

  assert.equal(baseline.sourceHash, manifest.source_catalog.sha256);
  assert.deepEqual(Object.keys(baseline.categories), manifest.category_ids);
  for (const [categoryId, payload] of Object.entries(baseline.categories)) {
    assert.deepEqual(payload, await readJson(`pwa/categories/${categoryId}.json`));
  }
  assert.deepEqual(baseline.plans, await readJson("pwa/plans.json"));
  const differences = await readJson("platform-differences.json");
  assert.deepEqual(differences.known_runtime_policy_differences, []);
  assert.deepEqual(differences.shared_data_differences, []);
  assert.deepEqual(differences.metadata_differences, []);
  assert.deepEqual(differences.display_connection_differences, []);
  assert.deepEqual(differences.representative_plan_differences, []);
});
