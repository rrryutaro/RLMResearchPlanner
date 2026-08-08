import { freeSecondsForVip } from "./state.js?v=0.0.6-b1";

export const CASTLE_RESOURCE_KEYS = ["food", "stone", "timber", "ore", "gold_hammer"];

function localText(values, locale) {
  return values?.[locale] || values?.[locale?.split("-")[0]] || values?.["en-US"] || Object.values(values || {})[0] || "";
}

export async function loadCastleCatalog(url = "./data/buildings/castle_catalog.json") {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`城・施設データを読み込めませんでした (${response.status})`);
  return normalizeCastleCatalog(await response.json());
}

export function normalizeCastleCatalog(raw) {
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
  return {
    buildings,
    order: [...buildings.keys()],
    buildingName(buildingId, locale) { const building = buildings.get(buildingId); return building ? localText(building.names, locale) : buildingId; },
  };
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
  const speed = Math.max(0, Number(settings.constructionSpeedPercent) || 0);
  let remaining = Math.ceil(Math.max(0, Number(baseSeconds) || 0) / (1 + speed / 100));
  remaining = Math.max(0, remaining - freeSecondsForVip(settings.vipLevel));
  for (let count = 0; count < Math.max(0, Number(settings.maxGuildHelps) || 0) && remaining > 0; count += 1) {
    remaining = Math.max(0, Math.ceil(remaining - Math.max(60, remaining * 0.01)));
  }
  return remaining;
}

export function createCastlePlan(catalog, state, targetCastleLevel) {
  const castle = catalog.buildings.get("castle");
  const current = Math.min(castle.maxLevel, Math.max(1, Math.trunc(Number(state.settings.castleLevel) || 1)));
  const target = Math.min(castle.maxLevel, Math.max(current, Math.trunc(Number(targetCastleLevel) || current)));
  const effectiveLevels = effectiveBuildingLevels(catalog, current, state.buildingLevels);
  const steps = [];
  const completed = new Set();
  const visiting = new Set();
  const issues = [];
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
  addBuilding("castle", target);
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
  return {
    currentCastleLevel: current,
    targetCastleLevel: target,
    effectiveLevels,
    steps,
    buildings: [...grouped.values()],
    totals: { baseSeconds: steps.reduce((sum, step) => sum + step.baseSeconds, 0), adjustedSeconds: steps.reduce((sum, step) => sum + step.adjustedSeconds, 0), costs: totalCosts },
    issues: [...new Set(issues)],
  };
}

export function buildingLevelsAfterCastleStep(plan, selectedStep, currentCastleLevel, currentBuildingLevels = {}) {
  const selectedIndex = plan.steps.findIndex(
    (step) => step.buildingId === selectedStep.buildingId && step.level === selectedStep.level,
  );
  if (selectedIndex < 0) {
    return {
      castleLevel: Math.max(1, Number(currentCastleLevel) || 1),
      buildingLevels: { ...currentBuildingLevels },
    };
  }
  let castleLevel = Math.max(1, Number(currentCastleLevel) || 1);
  const buildingLevels = { ...currentBuildingLevels };
  for (const completed of plan.steps.slice(0, selectedIndex + 1)) {
    if (completed.buildingId === "castle") {
      castleLevel = Math.max(castleLevel, completed.level);
    } else {
      buildingLevels[completed.buildingId] = Math.max(
        Number(buildingLevels[completed.buildingId] || 0),
        completed.level,
      );
    }
  }
  return { castleLevel, buildingLevels };
}
