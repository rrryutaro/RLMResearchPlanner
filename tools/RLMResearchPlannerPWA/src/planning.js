import { RESOURCE_KEYS, freeSecondsForVip } from "./state.js?v=0.0.9-b1";

export const TECHNOLABE_CAPACITY_SECONDS = 33 * 86400 + 3 * 3600 + 59 * 60;

export function technolabeUsage(baseSeconds, sourcedCount = null) {
  if (baseSeconds == null) return { count: null, efficiencyPercent: null };
  const base = Math.max(0, Number(baseSeconds) || 0);
  if (!base) return { count: 0, efficiencyPercent: null };
  const count = sourcedCount != null && Number(sourcedCount) > 0
    ? Math.max(1, Math.trunc(Number(sourcedCount)))
    : Math.max(1, Math.ceil(base / TECHNOLABE_CAPACITY_SECONDS));
  return {
    count,
    efficiencyPercent: Math.min(100, base / (count * TECHNOLABE_CAPACITY_SECONDS) * 100),
  };
}

export function defaultTargetLevel(currentLevel, maxLevel) {
  const maximum = Math.max(0, Math.trunc(Number(maxLevel) || 0));
  const current = Math.max(0, Math.min(maximum, Math.trunc(Number(currentLevel) || 0)));
  return Math.min(maximum, current + 1);
}

export function adjustedTime(baseSeconds, settings) {
  const speed = Math.max(0, Number(settings.researchSpeedPercent) || 0) + Math.max(0, Number(settings.researchSpeedBoostPercent) || 0);
  let remaining = Math.ceil(Math.max(0, Number(baseSeconds) || 0) / (1 + speed / 100));
  remaining = Math.max(0, remaining - freeSecondsForVip(settings.vipLevel));
  for (let count = 0; count < Math.max(0, Number(settings.maxGuildHelps) || 0) && remaining > 0; count += 1) {
    remaining = Math.max(0, Math.ceil(remaining - Math.max(60, remaining * 0.01)));
  }
  return remaining;
}

export function formatDuration(seconds) {
  let value = Math.max(0, Math.trunc(Number(seconds) || 0));
  const days = Math.floor(value / 86400); value %= 86400;
  const hours = Math.floor(value / 3600); value %= 3600;
  const minutes = Math.floor(value / 60); const secs = value % 60;
  const clock = [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
  return days ? `${days}d ${clock}` : clock;
}

function isRequirementMet(requirement, levels) {
  return Number(levels[requirement.researchId] || 0) >= requirement.level;
}

export function isNextLevelAvailable(node, state) {
  const nextLevel = Number(state.researchLevels[node.id] || 0) + 1;
  if (nextLevel > node.maxLevel) return false;
  const data = node.levels.get(nextLevel);
  if (!data || data.baseTimeSeconds == null) return false;
  const academy = Math.max(Number(data.academyLevel || 0), Number(data.buildings.academy || 0));
  return academy <= state.settings.academyLevel && data.requirements.every((requirement) => isRequirementMet(requirement, state.researchLevels));
}

export function isInstantNextLevel(node, state) {
  if (!isNextLevelAvailable(node, state)) return false;
  const next = Number(state.researchLevels[node.id] || 0) + 1;
  return adjustedTime(node.levels.get(next).baseTimeSeconds, state.settings) === 0;
}

export function shortestAvailable(catalog, state) {
  const steps = [];
  for (const node of catalog.nodes.values()) {
    if (!isNextLevelAvailable(node, state)) continue;
    const level = Number(state.researchLevels[node.id] || 0) + 1;
    const data = node.levels.get(level);
    steps.push(stepFrom(node, level, data, state.settings));
  }
  return steps.sort((a, b) => a.adjustedSeconds - b.adjustedSeconds || a.baseSeconds - b.baseSeconds || a.researchId.localeCompare(b.researchId));
}

export function createPlan(catalog, state, targetId, targetLevel) {
  const target = catalog.nodes.get(targetId);
  if (!target) throw new Error("研究項目が見つかりません");
  const normalizedTarget = Math.min(target.maxLevel, Math.max(1, Number(targetLevel) || 1));
  const required = new Map([[targetId, normalizedTarget]]);
  const pending = [targetId];
  const issues = [];
  while (pending.length) {
    const researchId = pending.shift();
    const node = catalog.nodes.get(researchId);
    if (!node) continue;
    const current = Number(state.researchLevels[researchId] || 0);
    const needed = required.get(researchId);
    for (let level = current + 1; level <= needed; level += 1) {
      const data = node.levels.get(level);
      if (!data) { issues.push(`${node.id}:${level} の詳細データがありません`); continue; }
      for (const requirement of data.requirements) {
        if (!catalog.nodes.has(requirement.researchId) || requirement.researchId === researchId) continue;
        if (Number(state.researchLevels[requirement.researchId] || 0) >= requirement.level) continue;
        const prerequisite = catalog.nodes.get(requirement.researchId);
        const nextRequired = Math.min(prerequisite.maxLevel, requirement.level);
        if (nextRequired > Number(required.get(requirement.researchId) || 0)) {
          required.set(requirement.researchId, nextRequired);
          pending.push(requirement.researchId);
        }
      }
    }
  }

  const stepMap = new Map();
  for (const [researchId, needed] of required) {
    const node = catalog.nodes.get(researchId);
    for (let level = Number(state.researchLevels[researchId] || 0) + 1; level <= needed; level += 1) {
      stepMap.set(`${researchId}\0${level}`, { node, level, data: node.levels.get(level) });
    }
  }
  const dependencies = new Map([...stepMap.keys()].map((key) => [key, new Set()]));
  for (const [key, item] of stepMap) {
    const previous = `${item.node.id}\0${item.level - 1}`;
    if (stepMap.has(previous)) dependencies.get(key).add(previous);
    for (const requirement of item.data?.requirements || []) {
      const dependency = `${requirement.researchId}\0${requirement.level}`;
      if (stepMap.has(dependency) && dependency !== key) dependencies.get(key).add(dependency);
    }
  }
  const categoryOrder = new Map((catalog.categories || []).map((category, index) => [category.id, index]));
  const nodeOrder = new Map([...catalog.nodes.keys()].map((researchId, index) => [researchId, index]));
  const compareStepKeys = (leftKey, rightKey) => {
    const left = stepMap.get(leftKey);
    const right = stepMap.get(rightKey);
    const leftOrder = [
      Number(categoryOrder.get(left.node.categoryId) ?? 999),
      Number(left.node.row ?? 999),
      Number(left.node.column ?? 999),
      Number(nodeOrder.get(left.node.id) ?? 999999),
      Number(left.level),
    ];
    const rightOrder = [
      Number(categoryOrder.get(right.node.categoryId) ?? 999),
      Number(right.node.row ?? 999),
      Number(right.node.column ?? 999),
      Number(nodeOrder.get(right.node.id) ?? 999999),
      Number(right.level),
    ];
    for (let index = 0; index < leftOrder.length; index += 1) {
      if (leftOrder[index] !== rightOrder[index]) return leftOrder[index] - rightOrder[index];
    }
    return left.node.id.localeCompare(right.node.id);
  };
  const dependents = new Map([...stepMap.keys()].map((key) => [key, new Set()]));
  const remainingPrerequisites = new Map();
  for (const [key, requiredKeys] of dependencies) {
    remainingPrerequisites.set(key, requiredKeys.size);
    for (const requiredKey of requiredKeys) dependents.get(requiredKey)?.add(key);
  }
  const ordered = [];
  let ready = [...stepMap.keys()].filter((key) => remainingPrerequisites.get(key) === 0).sort(compareStepKeys);
  while (ready.length) {
    const currentLayer = ready;
    const nextLayer = [];
    for (const key of currentLayer) {
      ordered.push(stepMap.get(key));
      for (const dependent of dependents.get(key) || []) {
        const remaining = Number(remainingPrerequisites.get(dependent) || 0) - 1;
        remainingPrerequisites.set(dependent, remaining);
        if (remaining === 0) nextLayer.push(dependent);
      }
    }
    ready = nextLayer.sort(compareStepKeys);
  }
  if (ordered.length !== stepMap.size) {
    issues.push("研究データに循環する前提条件があるため、循環部分は依存順を確定できません");
    const orderedKeys = new Set(ordered.map((item) => `${item.node.id}\0${item.level}`));
    const unresolved = [...stepMap.keys()].filter((key) => !orderedKeys.has(key)).sort(compareStepKeys);
    ordered.push(...unresolved.map((key) => stepMap.get(key)));
  }

  const totals = { baseSeconds: 0, adjustedSeconds: 0, costs: Object.fromEntries(RESOURCE_KEYS.map((key) => [key, 0])), unknownTime: 0, unknownCosts: 0, technolabeCount: 0, technolabeEfficiencyPercent: null };
  const steps = ordered.map(({ node, level, data }) => {
    if (!data || data.baseTimeSeconds == null) totals.unknownTime += 1;
    else totals.baseSeconds += data.baseTimeSeconds;
    if (!data?.costsVerified) totals.unknownCosts += 1;
    const step = stepFrom(node, level, data, state.settings);
    totals.adjustedSeconds += step.adjustedSeconds || 0;
    totals.technolabeCount += Number(step.technolabeCount || 0);
    for (const key of RESOURCE_KEYS) totals.costs[key] += Number(step.costs[key] || 0);
    return step;
  });
  if (totals.baseSeconds > 0 && totals.technolabeCount > 0) {
    totals.technolabeEfficiencyPercent = Math.min(100, totals.baseSeconds / (totals.technolabeCount * TECHNOLABE_CAPACITY_SECONDS) * 100);
  }
  return { targetId, targetLevel: normalizedTarget, steps, totals, issues };
}

export function researchLevelsAfterPlan(plan, currentLevels) {
  const levels = { ...currentLevels };
  for (const step of plan?.steps || []) {
    levels[step.researchId] = Math.max(
      Number(levels[step.researchId] || 0),
      Number(step.level || 0),
    );
  }
  return levels;
}

function stepFrom(node, level, data, settings) {
  const baseSeconds = data?.baseTimeSeconds == null ? null : Number(data.baseTimeSeconds);
  const technolabe = technolabeUsage(baseSeconds, data?.technolabeCount);
  return {
    researchId: node.id,
    categoryId: node.categoryId,
    level,
    baseSeconds,
    adjustedSeconds: baseSeconds == null ? null : adjustedTime(baseSeconds, settings),
    technolabeCount: technolabe.count,
    technolabeEfficiencyPercent: technolabe.efficiencyPercent,
    costs: { ...(data?.costs || {}) },
  };
}
