import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";


const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(SCRIPT_DIRECTORY, "..", "..");
const DEVELOPMENT_PWA_ROOT = join(PROJECT_ROOT, "..", "RLMResearchPlannerPWA");
const PUBLIC_PWA_ROOT = join(PROJECT_ROOT, "tools", "RLMResearchPlannerPWA");
const PWA_ROOT = existsSync(join(DEVELOPMENT_PWA_ROOT, "package.json"))
  ? DEVELOPMENT_PWA_ROOT
  : PUBLIC_PWA_ROOT;
const CATALOG_PATH = join(PWA_ROOT, "data", "research", "catalog.json");
const DATASET_ROOT = join(PWA_ROOT, "data", "research-dataset");
const BASELINE_ROOT = join(PROJECT_ROOT, "dataset", "baseline");
const DOCUMENT_TYPE = "RLMResearchPlanner.research-baseline";
const SCHEMA_VERSION = 1;

const { normalizeCatalog } = await import(pathToFileURL(join(PWA_ROOT, "src", "catalog.js")).href);
const { createPlan } = await import(pathToFileURL(join(PWA_ROOT, "src", "planning.js")).href);
const { defaultState } = await import(pathToFileURL(join(PWA_ROOT, "src", "state.js")).href);


function sortedObject(value) {
  if (Array.isArray(value)) return value.map(sortedObject);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right, "en-US"))
        .map(([key, item]) => [key, sortedObject(item)]),
    );
  }
  return value;
}


function canonicalJsonSha256(value) {
  const canonicalObject = (item) => {
    if (Array.isArray(item)) return item.map(canonicalObject);
    if (item && typeof item === "object") {
      return Object.fromEntries(
        Object.entries(item)
          .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
          .map(([key, nested]) => [key, canonicalObject(nested)]),
      );
    }
    return item;
  };
  return createHash("sha256")
    .update(JSON.stringify(canonicalObject(value)), "utf8")
    .digest("hex");
}


function levelPayload(level) {
  return {
    level: level.level,
    academy_level: level.academyLevel,
    base_time_seconds: level.baseTimeSeconds,
    technolabe_count: level.technolabeCount,
    costs: { ...level.costs },
    power: level.power,
    requirements: [...level.requirements]
      .map((requirement) => ({
        research_id: requirement.researchId,
        level: requirement.level,
      })),
    buildings: { ...level.buildings },
    costs_verified: level.costsVerified,
  };
}


function nodePayload(node) {
  return {
    id: node.id,
    names: { ...node.names },
    max_level: node.maxLevel,
    row: node.row,
    column: node.column,
    effect_label: node.effectLabel,
    effect_values: { ...node.effectValues },
    levels: [...node.levels.values()]
      .sort((left, right) => left.level - right.level)
      .map(levelPayload),
  };
}


function categoryPayload(category, sourceHash) {
  return {
    document_type: DOCUMENT_TYPE,
    schema_version: SCHEMA_VERSION,
    platform: "pwa",
    source_catalog_sha256: sourceHash,
    category_id: category.id,
    titles: { ...category.titles },
    verification_status: category.status,
    scope: category.scope || "",
    nodes: [...category.nodes]
      .sort((left, right) => left.row - right.row || left.column - right.column || left.id.localeCompare(right.id, "en-US"))
      .map(nodePayload),
    display_connections: [...category.edges]
      .map(([from, to]) => [from, to])
      .sort(([leftFrom, leftTo], [rightFrom, rightTo]) => leftFrom.localeCompare(rightFrom, "en-US") || leftTo.localeCompare(rightTo, "en-US")),
  };
}


function planStepPayload(step) {
  return {
    research_id: step.researchId,
    level: step.level,
    base_time_seconds: step.baseSeconds,
    adjusted_time_seconds: step.adjustedSeconds,
    after_help_seconds: step.afterHelpSeconds,
    costs: { ...step.costs },
    costs_verified: step.costsVerified,
    technolabe_count: step.technolabeCount,
    technolabe_efficiency_percent: step.technolabeEfficiencyPercent,
  };
}


function planPayload(category, catalog) {
  const target = [...category.nodes]
    .filter((node) => node.maxLevel > 0)
    .sort((left, right) => left.row - right.row || left.column - right.column || left.id.localeCompare(right.id, "en-US"))
    .at(-1);
  const result = createPlan(catalog, defaultState(), target.id, target.maxLevel);
  const requiredLevels = {};
  for (const step of result.steps) {
    requiredLevels[step.researchId] = Math.max(Number(requiredLevels[step.researchId] || 0), Number(step.level || 0));
  }
  return {
    category_id: category.id,
    target_research_id: target.id,
    target_level: target.maxLevel,
    required_levels: requiredLevels,
    steps: result.steps.map(planStepPayload),
    totals: {
      base_time_seconds: result.totals.baseSeconds,
      adjusted_time_seconds: result.totals.adjustedSeconds,
      after_help_seconds: result.totals.afterHelpSeconds,
      costs: { ...result.totals.costs },
      unknown_time_steps: result.totals.unknownTime,
      unknown_cost_steps: result.totals.unknownCosts,
      unknown_technolabe_steps: result.totals.unknownTechnolabe,
      technolabe_count: result.totals.technolabeCount,
      technolabe_base_seconds: result.totals.technolabeBaseSeconds,
      technolabe_efficiency_percent: result.totals.technolabeEfficiencyPercent,
    },
    issues: [...result.issues],
  };
}


export async function buildPwaBaseline() {
  const sourceCatalog = JSON.parse(await readFile(CATALOG_PATH, "utf8"));
  const sourceHash = canonicalJsonSha256(sourceCatalog);
  const manifest = JSON.parse(await readFile(join(DATASET_ROOT, "manifest.json"), "utf8"));
  const documents = {
    manifest,
    sources: JSON.parse(await readFile(join(DATASET_ROOT, manifest.sources_path), "utf8")),
    evidence: JSON.parse(await readFile(join(DATASET_ROOT, manifest.evidence_path), "utf8")),
    aliases: JSON.parse(await readFile(join(DATASET_ROOT, manifest.aliases_path), "utf8")),
    trees: Object.fromEntries(await Promise.all(manifest.trees.map(async (entry) => [
      entry.id,
      JSON.parse(await readFile(join(DATASET_ROOT, entry.path), "utf8")),
    ]))),
    locales: Object.fromEntries(await Promise.all(manifest.locales.map(async (entry) => [
      entry.locale,
      JSON.parse(await readFile(join(DATASET_ROOT, entry.path), "utf8")),
    ]))),
  };
  const catalog = normalizeCatalog(documents);
  const categories = Object.fromEntries(
    catalog.categories.map((category) => [category.id, categoryPayload(category, sourceHash)]),
  );
  return {
    sourceHash,
    categories,
    plans: {
      document_type: DOCUMENT_TYPE,
      schema_version: SCHEMA_VERSION,
      platform: "pwa",
      source_catalog_sha256: sourceHash,
      plans: catalog.categories.map((category) => planPayload(category, catalog)),
    },
  };
}


async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(sortedObject(value), null, 2)}\n`, "utf8");
}


export async function writePwaBaseline(baseline) {
  for (const [categoryId, payload] of Object.entries(baseline.categories)) {
    await writeJson(join(BASELINE_ROOT, "pwa", "categories", `${categoryId}.json`), payload);
  }
  await writeJson(join(BASELINE_ROOT, "pwa", "plans.json"), baseline.plans);
}


async function main() {
  const baseline = await buildPwaBaseline();
  await writePwaBaseline(baseline);
  process.stdout.write(`PWA research baseline generated: ${Object.keys(baseline.categories).length} categories\n`);
}


const entryPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (import.meta.url === entryPath) await main();
