import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  allocateTalentPlan,
  expandTalentTargets,
  normalizeTalentCatalog,
  talentLayoutColumns,
  talentPlayerLevelRequirement,
  talentDirectiveFromPayload,
  talentDirectivePayload,
} from "../src/talent-planning.js";

const raw = JSON.parse(await readFile(new URL("../data/talents/catalog.json", import.meta.url), "utf8"));
const catalog = normalizeTalentCatalog(raw);

test("talent catalog contains the complete tree and usable presets", () => {
  assert.equal(catalog.talents.size, 47);
  assert.equal(catalog.presets.length, 6);
  assert.ok(catalog.presetById.has("army_general"));
  assert.equal(catalog.defaultAvailablePoints, 278);
  assert.equal(catalog.pointRewardsByLevel.reduce((sum, value) => sum + value, 0), 278);
});

test("talent layout keeps military and economy in stable lanes", () => {
  const layout = talentLayoutColumns(catalog);
  const military = [...catalog.talents.values()].filter((item) => item.branch === "military").map((item) => layout.columns.get(item.id));
  const economy = [...catalog.talents.values()].filter((item) => item.branch === "economy").map((item) => layout.columns.get(item.id));
  assert.ok(Math.max(...military) < Math.min(...economy));
  assert.ok(Math.min(...economy) - Math.max(...military) >= 1);
  assert.equal(layout.columns.get("squad_offense_i"), 1);
  assert.equal(layout.columns.get("food_production_i"), 2);
  assert.equal(layout.columns.get("cavalry_offense_i"), 1);
  assert.equal(layout.columns.get("stone_production_i"), 2);
  assert.ok(layout.columns.get("trap_building_i") < layout.columns.get("cavalry_offense_i"));
  assert.ok(layout.columns.get("stone_production_i") < layout.columns.get("construction_speed_i"));
  const expectedRows = [
    ["squad_offense_i", "food_production_i"],
    ["trap_building_i", "cavalry_offense_i", "stone_production_i", "construction_speed_i"],
    ["training_speed_i", "ranged_offense_i", "timber_production_i", "research_i"],
    ["siege_engine_offense_i", "infantry_offense_i", "ore_production_i", "gold_production_i"],
    ["trap_offense_i", "squad_defense_i", "food_production_ii", "max_load_i"],
    ["squad_health_i", "stone_production_ii", "gathering_i"],
    ["siege_engine_offense_ii", "ranged_offense_ii", "ore_production_ii", "timber_production_ii"],
    ["trap_building_ii", "infantry_offense_ii", "construction_speed_ii", "gold_production_ii"],
    ["trap_offense_ii", "cavalry_offense_ii", "research_ii"],
    ["training_speed_ii", "infantry_offense_iii", "gathering_ii", "max_load_ii"],
    ["siege_engine_offense_iii", "cavalry_offense_iii", "food_production_iii"],
    ["trap_offense_iii", "ranged_offense_iii", "timber_production_iii", "ore_production_iii"],
    ["squad_defense_ii", "squad_health_ii", "stone_production_iii", "gold_production_iii"],
  ];
  expectedRows.forEach((expectedIds, index) => {
    const rowNumber = index + 1;
    const actualIds = [...catalog.talents.values()]
      .filter((talent) => talent.row === rowNumber)
      .sort((left, right) => layout.columns.get(left.id) - layout.columns.get(right.id))
      .map((talent) => talent.id);
    assert.deepEqual(actualIds, expectedIds);
    const expectedColumns = new Map([
      [1, [1, 2]],
      [6, [1, 2, 3]],
      [9, [0, 1, 2]],
      [11, [0, 1, 2]],
    ]).get(rowNumber) || expectedIds.map((_id, column) => column);
    assert.deepEqual(expectedIds.map((id) => layout.columns.get(id)), expectedColumns);
  });
});

test("preset expansion puts prerequisites before selected talents", () => {
  const preset = catalog.presetById.get("growth_speed");
  const plan = expandTalentTargets(catalog, preset.targets);
  const index = (id, level) => plan.findIndex((step) => step.talentId === id && step.targetLevel === level);
  assert.ok(index("stone_production_i", 2) < index("construction_speed_i", 10));
  assert.ok(index("construction_speed_i", 10) < index("research_i", 10));
});

test("allocation stops at the available point count", () => {
  const preset = catalog.presetById.get("infantry_war");
  const allocation = allocateTalentPlan(catalog, preset.targets, 25);
  assert.equal(allocation.usedPoints, 25);
  assert.equal(allocation.remainingPoints, 0);
  assert.ok(allocation.requiredPoints > allocation.usedPoints);
});

test("required talent points convert to the minimum player level", () => {
  assert.equal(talentPlayerLevelRequirement(catalog, 0).playerLevel, 1);
  assert.equal(talentPlayerLevelRequirement(catalog, 1).playerLevel, 2);
  assert.equal(talentPlayerLevelRequirement(catalog, 278).playerLevel, 60);
  assert.equal(talentPlayerLevelRequirement(catalog, 288, 10).playerLevel, 60);
  assert.equal(talentPlayerLevelRequirement(catalog, 289, 10).shortageAtMaxLevel, 1);
});

test("priority keeps prerequisites ahead of the selected target", () => {
  const preset = catalog.presetById.get("growth_speed");
  const allocation = allocateTalentPlan(catalog, preset.targets, 8, "research_i");
  const ids = allocation.steps.map((step) => step.talentId);
  assert.ok(ids.indexOf("construction_speed_i") < ids.indexOf("research_i"));
  assert.ok(ids.indexOf("research_i") < ids.indexOf("construction_speed_ii"));
});

test("general army preset prioritizes shared army stats", () => {
  const preset = catalog.presetById.get("army_general");
  assert.deepEqual(preset.targets.map((step) => step.talentId), [
    "squad_health_i",
    "squad_health_ii",
    "squad_offense_i",
    "squad_defense_i",
    "squad_defense_ii",
  ]);
});

test("talent directive preserves ordered stable IDs", () => {
  const steps = [
    { talentId: "food_production_i", targetLevel: 2 },
    { talentId: "stone_production_i", targetLevel: 2 },
    { talentId: "construction_speed_i", targetLevel: 10 },
  ];
  const payload = talentDirectivePayload(steps, { name: "Build", catalogVersion: "1.0.0" });
  const directive = talentDirectiveFromPayload(payload);
  assert.equal(Object.hasOwn(payload, "available_points"), false);
  assert.equal(directive.name, "Build");
  assert.deepEqual(directive.steps, steps);
});
