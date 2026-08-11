import { freeSecondsForVip, guildHelpCount } from "./state.js?v=0.1.1-b2";
import { loadJsonResource } from "./catalog.js?v=0.1.1-b2";

export const CASTLE_RESOURCE_KEYS = ["food", "stone", "timber", "ore", "gold_hammer", "war_tome", "steel_cuffs", "soul_crystal", "mana_ore", "mana_crystal", "mana_steel"];

function localText(values, locale) {
  return values?.[locale] || values?.[locale?.split("-")[0]] || values?.["en-US"] || Object.values(values || {})[0] || "";
}

export async function loadCastleCatalog(url = "./data/buildings/castle_catalog.json") {
  return normalizeCastleCatalog(await loadJsonResource(url, "城・施設データ"));
}

export function normalizeCastleCatalog(raw) {
  let languagePack = null;
  const buildings = new Map();
  for (const source of raw.buildings || []) {
    const levels = new Map();
    for (const [levelText, level] of Object.entries(source.levels || {})) {
      levels.set(Number(levelText), {
        level: Number(levelText),
        baseTimeSeconds: Math.max(0, Number(level.base_time_seconds) || 0),
        costs: Object.fromEntries(CASTLE_RESOURCE_KEYS.map((key) => [key, Math.max(0, Number(level.costs?.[key]) || 0)])),
        requirements: (level.requirements || []).map((item) => ({ buildingId: String(item.building_id), level: Math.max(1, Number(item.level) || 1) })),
      });
    }
    buildings.set(source.id, { id: source.id, names: { ...(source.names || {}) }, maxLevel: Number(source.max_level || 25), levels });
  }
  if (!buildings.has("castle")) throw new Error("城データがありません");
  const manaSource = raw.castle_mana_progression || {};
  const manaStages = new Map(Object.entries(manaSource.stages || {}).map(([stageText, source]) => {
    const stage = Number(stageText);
    return [stage, {
      stage,
      baseTimeSeconds: Math.max(0, Number(source.base_time_seconds) || 0),
      costs: Object.fromEntries(CASTLE_RESOURCE_KEYS.map((key) => [key, Math.max(0, Number(source.costs?.[key]) || 0)])),
    }];
  }));
  const gemShopPacks = Object.fromEntries(Object.entries(raw.gem_shop_packs || {}).map(([key, packs]) => [key, (packs || []).map((pack) => ({
    quantity: Math.max(1, Math.trunc(Number(pack.quantity) || 1)),
    gems: Math.max(0, Math.trunc(Number(pack.gems) || 0)),
  }))]));
  return {
    buildings,
    manaStages,
    maxManaStage: Math.max(0, ...manaStages.keys()),
    manaNames: { ...(manaSource.names || {}) },
    gemShopPacks,
    order: [...buildings.keys()],
    setLanguagePack(pack) { languagePack = pack || null; },
    sourceBuildingName(buildingId, locale) { const building = buildings.get(buildingId); return building ? localText(building.names, locale) : buildingId; },
    buildingName(buildingId, locale) { const building = buildings.get(buildingId); return languagePack?.sections?.buildings?.[buildingId] || (building ? localText(building.names, languagePack?.fallbackLocale || locale) : buildingId); },
    manaName(locale) { return localText(this.manaNames, locale) || this.buildingName("castle", locale); },
  };
}

export function minimumGemsForAmount(amount, packs) {
  const required = Math.max(0, Math.trunc(Number(amount) || 0));
  const normalized = (packs || []).map((pack) => ({
    quantity: Math.max(1, Math.trunc(Number(pack.quantity) || 1)),
    gems: Math.max(0, Math.trunc(Number(pack.gems) || 0)),
  })).filter((pack) => pack.quantity > 0);
  if (!required) return 0;
  if (!normalized.length) throw new Error("ジェムショップの購入単位がありません");
  const limit = required + Math.max(...normalized.map((pack) => pack.quantity)) - 1;
  const costs = Array(limit + 1).fill(Number.POSITIVE_INFINITY);
  costs[0] = 0;
  for (let owned = 0; owned <= limit; owned += 1) {
    if (!Number.isFinite(costs[owned])) continue;
    for (const pack of normalized) {
      const next = Math.min(limit, owned + pack.quantity);
      costs[next] = Math.min(costs[next], costs[owned] + pack.gems);
    }
  }
  return Math.min(...costs.slice(required));
}

export function gemCostsFor(catalog, costs, ownedResources = {}) {
  return Object.fromEntries(Object.entries(catalog.gemShopPacks || {}).flatMap(([key, packs]) => {
    const missing = Math.max(0, Number(costs?.[key] || 0) - Number(ownedResources?.[key] || 0));
    return missing > 0 ? [[key, minimumGemsForAmount(missing, packs)]] : [];
  }));
}

export function minimumBuildingLevels(catalog, castleLevel) {
  const levels = Object.fromEntries(catalog.order.map((id) => [id, 0]));
  const visiting = new Set();
  const requireBuilding = (buildingId, targetLevel) => {
    const building = catalog.buildings.get(buildingId);
    if (!building) return;
    const target = Math.min(building.maxLevel, Math.max(0, Math.trunc(Number(targetLevel) || 0)));
    if (target <= Number(levels[buildingId] || 0)) return;
    const previous = Number(levels[buildingId] || 0);
    levels[buildingId] = target;
    for (let level = previous + 1; level <= target; level += 1) {
      const key = `${buildingId}\0${level}`;
      if (visiting.has(key)) throw new Error(`施設の前提条件が循環しています: ${buildingId}:${level}`);
      visiting.add(key);
      for (const requirement of building.levels.get(level)?.requirements || []) requireBuilding(requirement.buildingId, requirement.level);
      visiting.delete(key);
    }
  };
  requireBuilding("castle", castleLevel);
  return levels;
}

function effectiveBuildingLevels(catalog, castleLevel, savedLevels = {}) {
  const levels = minimumBuildingLevels(catalog, castleLevel);
  for (const [buildingId, rawValue] of Object.entries(savedLevels || {})) {
    const building = catalog.buildings.get(buildingId);
    if (!building) continue;
    levels[buildingId] = Math.max(Number(levels[buildingId] || 0), Math.min(building.maxLevel, Math.max(0, Math.trunc(Number(rawValue) || 0))));
  }
  levels.castle = Math.max(Number(levels.castle || 0), Number(castleLevel) || 1);
  return levels;
}

function adjustedConstructionTime(baseSeconds, settings) {
  const speed = Math.max(0, Number(settings.constructionSpeedPercent) || 0)
    + Math.max(0, Number(settings.constructionSpeedBoostPercent) || 0);
  let remaining = Math.ceil(Math.max(0, Number(baseSeconds) || 0) / (1 + speed / 100));
  remaining = Math.max(0, remaining - freeSecondsForVip(settings.vipLevel));
  for (let count = 0; count < guildHelpCount(settings) && remaining > 0; count += 1) {
    remaining = Math.max(0, Math.ceil(remaining - Math.max(60, remaining * 0.01)));
  }
  return remaining;
}

export function createCastlePlan(catalog, state, targetCastleLevel, targetManaStage = state.settings.castleTargetManaStage, options = {}) {
  const castle = catalog.buildings.get("castle");
  const current = Math.min(castle.maxLevel, Math.max(1, Math.trunc(Number(state.settings.castleLevel) || 1)));
  const targetBuildingId = options.targetBuildingId || "castle";
  const selectedBuilding = catalog.buildings.get(targetBuildingId);
  if (!selectedBuilding) throw new Error(`不明な施設: ${targetBuildingId}`);
  const target = targetBuildingId === "castle"
    ? Math.min(castle.maxLevel, Math.max(current, Math.trunc(Number(targetCastleLevel) || current)))
    : current;
  const currentManaStage = current >= castle.maxLevel
    ? Math.min(catalog.maxManaStage, Math.max(0, Math.trunc(Number(state.settings.castleManaStage) || 0)))
    : 0;
  const normalizedTargetManaStage = targetBuildingId === "castle" && target >= castle.maxLevel
    ? Math.min(catalog.maxManaStage, Math.max(currentManaStage, Math.trunc(Number(targetManaStage) || 0)))
    : 0;
  const effectiveLevels = effectiveBuildingLevels(catalog, current, state.buildingLevels);
  const steps = [];
  const completed = new Set();
  const visiting = new Set();
  const issues = [];
  const selectedTarget = targetBuildingId === "castle"
    ? target
    : Math.min(selectedBuilding.maxLevel, Math.max(Number(effectiveLevels[targetBuildingId] || 0), Math.trunc(Number(options.targetBuildingLevel) || 0)));
  const addBuilding = (buildingId, targetLevel) => {
    const building = catalog.buildings.get(buildingId);
    if (!building) { issues.push(`不明な施設: ${buildingId}`); return; }
    const normalized = Math.min(building.maxLevel, Math.max(0, Math.trunc(Number(targetLevel) || 0)));
    for (let level = Number(effectiveLevels[buildingId] || 0) + 1; level <= normalized; level += 1) {
      const key = `${buildingId}\0${level}`;
      if (completed.has(key)) continue;
      if (visiting.has(key)) throw new Error(`施設の前提条件が循環しています: ${buildingId}:${level}`);
      visiting.add(key);
      const data = building.levels.get(level);
      if (!data) { issues.push(`施設データ未収録: ${buildingId}:${level}`); visiting.delete(key); continue; }
      for (const requirement of data.requirements) addBuilding(requirement.buildingId, requirement.level);
      steps.push({ buildingId, level, baseSeconds: data.baseTimeSeconds, adjustedSeconds: adjustedConstructionTime(data.baseTimeSeconds, state.settings), costs: { ...data.costs } });
      completed.add(key);
      visiting.delete(key);
    }
  };
  addBuilding(targetBuildingId, selectedTarget);
  for (let stage = currentManaStage + 1; stage <= normalizedTargetManaStage; stage += 1) {
    const data = catalog.manaStages.get(stage);
    if (!data) { issues.push(`城マナ強化データ未収録: ${stage}`); continue; }
    steps.push({
      buildingId: "castle",
      level: castle.maxLevel,
      manaStage: stage,
      baseSeconds: data.baseTimeSeconds,
      adjustedSeconds: adjustedConstructionTime(data.baseTimeSeconds, state.settings),
      costs: { ...data.costs },
    });
  }
  const grouped = new Map();
  const totalCosts = Object.fromEntries(CASTLE_RESOURCE_KEYS.map((key) => [key, 0]));
  for (const step of steps) {
    if (!grouped.has(step.buildingId)) grouped.set(step.buildingId, { buildingId: step.buildingId, currentLevel: Number(effectiveLevels[step.buildingId] || 0), targetLevel: Number(effectiveLevels[step.buildingId] || 0), baseSeconds: 0, adjustedSeconds: 0, costs: Object.fromEntries(CASTLE_RESOURCE_KEYS.map((key) => [key, 0])) });
    const row = grouped.get(step.buildingId);
    row.targetLevel = Math.max(row.targetLevel, step.level);
    row.baseSeconds += step.baseSeconds;
    row.adjustedSeconds += step.adjustedSeconds;
    for (const key of CASTLE_RESOURCE_KEYS) { row.costs[key] += Number(step.costs[key] || 0); totalCosts[key] += Number(step.costs[key] || 0); }
  }
  const gemCosts = gemCostsFor(catalog, totalCosts, state.settings.resources || {});
  return {
    currentCastleLevel: current,
    targetCastleLevel: target,
    currentManaStage,
    targetManaStage: normalizedTargetManaStage,
    targetBuildingId,
    targetBuildingLevel: selectedTarget,
    effectiveLevels,
    steps,
    buildings: [...grouped.values()],
    totals: { baseSeconds: steps.reduce((sum, step) => sum + step.baseSeconds, 0), adjustedSeconds: steps.reduce((sum, step) => sum + step.adjustedSeconds, 0), costs: totalCosts, gemCosts, totalGems: Object.values(gemCosts).reduce((sum, value) => sum + Number(value || 0), 0) },
    issues: [...new Set(issues)],
  };
}

export function buildingLevelsAfterCastleStep(plan, selectedStep, currentCastleLevel, currentManaStage = 0, currentBuildingLevels = {}) {
  const selectedIndex = plan.steps.findIndex(
    (step) => step.buildingId === selectedStep.buildingId
      && step.level === selectedStep.level
      && Number(step.manaStage || 0) === Number(selectedStep.manaStage || 0),
  );
  if (selectedIndex < 0) {
    return {
      castleLevel: Math.max(1, Number(currentCastleLevel) || 1),
      castleManaStage: Math.max(0, Number(currentManaStage) || 0),
      buildingLevels: { ...currentBuildingLevels },
    };
  }
  let castleLevel = Math.max(1, Number(currentCastleLevel) || 1);
  let castleManaStage = castleLevel >= 25 ? Math.max(0, Number(currentManaStage) || 0) : 0;
  const buildingLevels = { ...currentBuildingLevels };
  for (const completed of plan.steps.slice(0, selectedIndex + 1)) {
    if (completed.buildingId === "castle") {
      castleLevel = Math.max(castleLevel, completed.level);
      castleManaStage = Math.max(castleManaStage, Number(completed.manaStage || 0));
    } else {
      buildingLevels[completed.buildingId] = Math.max(
        Number(buildingLevels[completed.buildingId] || 0),
        completed.level,
      );
    }
  }
  return { castleLevel, castleManaStage, buildingLevels };
}

export function castleProgressLabel(level, manaStage = 0) {
  const suffix = Number(level) >= 25 && Number(manaStage) > 0 ? `-${Number(manaStage)}` : "";
  return `Lv.${Number(level)}${suffix}`;
}
